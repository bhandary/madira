"""Sourcing briefs and the actions a tasting decision takes.

Gaps, quantities, prices, and purchase-order numbers come from services. The
model may phrase a rationale or a thank-you sentence. Demo mode uses the
deterministic model. Live mode calls the real model and fails when that call
fails. Nothing here approves a purchase order, publishes a list, or sends email.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.domain.compliance.service import record_audit_event
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.lists.coverage import cells_for_dish, confirmed_dishes, drink_style, matrix, style_match
from madira.domain.lists.pricing import ensure_default_rules, load_rules, normalize_category, price_for, section_name
from madira.domain.lists.service import _ensure_section, _guard_limits
from madira.domain.lists.versions import _insert_snapshot
from madira.domain.procurement.offers import current_offer, money_label
from madira.domain.procurement.orders import OrderError, place_draft_line
from madira.domain.session import session_scope
from madira.domain.tastings.service import (
    TastingError,
    _decision,
    _owned_sample,
    _owned_session,
    _sample_public,
    _venue,
)
from madira.models import (
    BeverageList,
    Invoice,
    ListEntry,
    ListItem,
    ListVersion,
    POLine,
    Product,
    PurchaseOrder,
    RepFollowup,
    Sample,
    Sku,
    SourcingBrief,
    Supplier,
    SupplierContact,
    SupplierOffer,
    Venue,
    WantItem,
)
from madira.money import DEFAULT_CURRENCY
from madira.tenancy import current_request, demo_posture
from madira.timestamps import format_wall

_phrase_override = None
_thanks_override = None
_HOUSE_CASE = 12
_UNMATCHED = "Match this sample to a catalog product before buying or listing it."
_NO_SKU = "This sample has no stocked bottle to order."
_NO_PRICE = "This sample has no quoted price or current offer."
_NO_SUPPLIER = "This sample has no supplier, so it cannot be added to a purchase order."
_PASS_REASON = "A pass needs a reason."


def set_phrase_completer(fn) -> None:
    """Tests inject the rationale writer. Production leaves this unset."""

    global _phrase_override
    _phrase_override = fn


def set_thanks_completer(fn) -> None:
    """Tests inject the thank-you writer. Production leaves this unset."""

    global _thanks_override
    _thanks_override = fn


def build_brief(venue_id: uuid.UUID) -> dict:
    """Turn uncovered list cells into a want list. Numbers are fixed before the model speaks."""

    with session_scope() as session:
        venue = _venue(session, venue_id)
        gaps, list_id = _gap_rows(session, venue)
        catalog = _catalog(session, venue)
    phrases = _rationales(gaps) if gaps else {}
    with session_scope() as session:
        venue = _venue(session, venue_id)
        actor = _actor()
        brief = SourcingBrief(
            venue_id=venue_id,
            list_id=list_id,
            title="Sourcing brief",
            status="draft",
            created_by_user_id=None if actor is None else actor[0],
        )
        session.add(brief)
        session.flush()
        for index, gap in enumerate(gaps):
            sample_id, offer_id = _links(session, venue_id, gap, catalog)
            text = phrases.get(index) or _fallback_rationale(gap)
            session.add(
                WantItem(
                    venue_id=venue_id,
                    brief_id=brief.id,
                    category=gap["category"],
                    style=gap["style"],
                    price_band=gap["price_band"],
                    quantity_hint=int(gap["quantity_hint"]),
                    dishes=gap["dishes"],
                    sample_id=sample_id,
                    offer_id=offer_id,
                    rationale=text,
                    position=index,
                )
            )
        session.flush()
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action="sourcing_brief.created",
            entity_type="sourcing_brief",
            entity_id=brief.id,
            after={"title": brief.title, "list_id": None if list_id is None else str(list_id), "items": len(gaps)},
        )
        payload = _brief_public(session, brief)
        session.commit()
        return {"brief": payload}


def list_briefs(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        _venue(session, venue_id)
        rows = session.scalars(
            select(SourcingBrief)
            .where(SourcingBrief.venue_id == venue_id)
            .order_by(SourcingBrief.created_at.desc(), SourcingBrief.id.desc())
        ).all()
        return {"briefs": [_brief_public(session, row) for row in rows]}


def get_brief(venue_id: uuid.UUID, brief_id: uuid.UUID) -> dict:
    with session_scope() as session:
        return {"brief": _brief_public(session, _owned_brief(session, venue_id, brief_id))}


def link_want_item(
    venue_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    sample_id: uuid.UUID | str | None = None,
    offer_id: uuid.UUID | str | None = None,
    clear_sample: bool = False,
    clear_offer: bool = False,
) -> dict:
    with session_scope() as session:
        venue = _venue(session, venue_id)
        item = _owned_item(session, venue_id, item_id)
        before = {"sample_id": item.sample_id, "offer_id": item.offer_id}
        if clear_sample:
            item.sample_id = None
        elif sample_id not in (None, ""):
            sample = _sample_in_venue(session, venue_id, sample_id)
            item.sample_id = sample.id
        if clear_offer:
            item.offer_id = None
        elif offer_id not in (None, ""):
            offer = session.get(SupplierOffer, _uuid(offer_id, "offer"))
            if offer is None or offer.venue_id != venue_id:
                raise NotFound("offer not found")
            item.offer_id = offer.id
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action="want_item.updated",
            entity_type="want_item",
            entity_id=item.id,
            before=before,
            after={"sample_id": item.sample_id, "offer_id": item.offer_id},
        )
        brief = _owned_brief(session, venue_id, item.brief_id)
        payload = _brief_public(session, brief)
        session.commit()
        return {"brief": payload, "item_id": str(item.id)}


def apply_decision(
    venue_id: uuid.UUID,
    session_id: uuid.UUID,
    sample_id: uuid.UUID,
    decision: str,
    reason: str | None = None,
) -> dict:
    """Store the decision and act on it. Buy and list stay drafts. Pass stores a reason."""

    label = _decision(decision)
    with session_scope() as session:
        venue = _venue(session, venue_id)
        sample = _owned_sample(session, venue_id, session_id, sample_id)
        if _already(sample, label, reason):
            return {"sample": _sample_public(session, venue, sample)}
        if label in {"buy", "list"} and sample.product_id is None:
            raise TastingError(_UNMATCHED)
        before = {
            "decision": sample.decision,
            "pass_reason": sample.pass_reason or "",
            "purchase_order_id": sample.purchase_order_id,
            "list_version_id": sample.list_version_id,
        }
        if label == "buy":
            _buy(session, venue, sample)
        elif label == "list":
            _list(session, venue, sample)
        elif label == "pass":
            text = " ".join(str(reason or "").split())
            if not text:
                raise TastingError(_PASS_REASON)
            if len(text) > 400:
                raise TastingError("The pass reason is too long.")
            sample.pass_reason = text
        else:
            sample.pass_reason = ""
        _stamp_decision(sample, label)
        action = {"buy": "sample.bought", "list": "sample.listed", "pass": "sample.passed"}.get(label, "sample.decision")
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action="sample.decision",
            entity_type="sample",
            entity_id=sample.id,
            before=before,
            after=_outcome(sample),
        )
        if action != "sample.decision":
            record_audit_event(
                session,
                org_id=venue.organization_id,
                venue_id=venue_id,
                action=action,
                entity_type="sample",
                entity_id=sample.id,
                before=before,
                after=_outcome(sample),
            )
        payload = _sample_public(session, venue, sample)
        session.commit()
        return {"sample": payload}


def draft_followup(venue_id: uuid.UUID, session_id: uuid.UUID) -> dict:
    """Write a follow-up draft. The purchase-order number is filled in here, not by the model."""

    with session_scope() as session:
        venue = _venue(session, venue_id)
        tasting = _owned_session(session, venue_id, session_id)
        facts = _followup_facts(session, venue, tasting)
    thanks = _thanks_line(facts)
    body = _followup_body(facts, thanks)
    with session_scope() as session:
        venue = _venue(session, venue_id)
        tasting = _owned_session(session, venue_id, session_id)
        actor = _actor()
        row = session.scalar(
            select(RepFollowup).where(RepFollowup.venue_id == venue_id, RepFollowup.session_id == tasting.id)
        )
        created = row is None
        before = None if row is None else {"subject": row.subject, "body": row.body}
        if row is None:
            row = RepFollowup(
                venue_id=venue_id,
                session_id=tasting.id,
                created_by_user_id=None if actor is None else actor[0],
            )
            session.add(row)
        row.supplier_id = facts["supplier_id"]
        row.to_email = facts["to_email"]
        row.subject = facts["subject"]
        row.body = body
        row.purchase_order_id = facts["purchase_order_id"]
        row.updated_at = datetime.now(timezone.utc)
        session.flush()
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue_id,
            action="rep_followup.drafted" if created else "rep_followup.updated",
            entity_type="rep_followup",
            entity_id=row.id,
            before=before,
            after={"subject": row.subject, "to_email": row.to_email, "sent": False, "purchase_order_id": row.purchase_order_id},
        )
        payload = _followup_public(session, venue, row)
        session.commit()
        return {"followup": payload}


def get_followup(venue_id: uuid.UUID, session_id: uuid.UUID) -> dict:
    with session_scope() as session:
        venue = _venue(session, venue_id)
        tasting = _owned_session(session, venue_id, session_id)
        row = session.scalar(
            select(RepFollowup).where(RepFollowup.venue_id == venue_id, RepFollowup.session_id == tasting.id)
        )
        if row is None:
            return {"followup": None}
        return {"followup": _followup_public(session, venue, row)}


def tasting_history(
    venue_id: uuid.UUID,
    *,
    supplier_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
) -> dict:
    """Tasted samples against bought purchase-order lines and invoice lines."""

    with session_scope() as session:
        _venue(session, venue_id)
        samples = session.scalars(select(Sample).where(Sample.venue_id == venue_id)).all()
        lines = session.scalars(
            select(POLine)
            .join(PurchaseOrder, PurchaseOrder.id == POLine.po_id)
            .where(POLine.venue_id == venue_id, PurchaseOrder.status != "canceled")
        ).all()
        orders = {
            order.id: order
            for order in session.scalars(select(PurchaseOrder).where(PurchaseOrder.venue_id == venue_id)).all()
        }
        invoices = session.scalars(select(Invoice).where(Invoice.venue_id == venue_id)).all()
        skus = session.scalars(select(Sku).where(Sku.venue_id == venue_id)).all()
        suppliers = {
            row.id: row.name
            for row in session.scalars(select(Supplier).where(Supplier.venue_id == venue_id)).all()
        }
        products = {}
        for sku in skus:
            product = None if sku.variant is None else sku.variant.product
            if product is not None:
                products[product.id] = product.name
        sku_by_id = {sku.id: sku for sku in skus}
        sku_by_code = {sku.barcode.casefold(): sku for sku in skus if sku.barcode}
        buckets: dict[tuple, dict] = {}

        def bucket(supplier_key, product_key):
            if supplier_id is not None and supplier_key != supplier_id:
                return None
            if product_id is not None and product_key != product_id:
                return None
            key = (supplier_key, product_key)
            row = buckets.get(key)
            if row is None:
                row = {
                    "supplier_id": "" if supplier_key is None else str(supplier_key),
                    "supplier": "" if supplier_key is None else suppliers.get(supplier_key, ""),
                    "product_id": "" if product_key is None else str(product_key),
                    "product": "" if product_key is None else products.get(product_key, ""),
                    "tasted": 0,
                    "buy": 0,
                    "list": 0,
                    "pass": 0,
                    "undecided": 0,
                    "bought_bottles": 0,
                    "invoiced_bottles": 0,
                    "last_cost_cents": None,
                    "last_cost_label": "",
                    "_when": "",
                }
                buckets[key] = row
            return row

        for sample in samples:
            row = bucket(sample.supplier_id, sample.product_id)
            if row is None:
                continue
            row["tasted"] += 1
            decision = sample.decision if sample.decision in {"buy", "list", "pass", "undecided"} else "undecided"
            row[decision] += 1
        seen_lines: set[uuid.UUID] = set()
        for line in lines:
            if line.id in seen_lines:
                continue
            seen_lines.add(line.id)
            order = orders.get(line.po_id)
            if order is None:
                continue
            sku = None if line.sku_id is None else sku_by_id.get(line.sku_id)
            product_key = None if sku is None or sku.variant is None else sku.variant.product_id
            row = bucket(order.supplier_id, product_key)
            if row is None:
                continue
            qty = int(Decimal(str(line.quantity_ordered or 0)).to_integral_value())
            row["bought_bottles"] += qty
            stamp = order.created_at.isoformat() if order.created_at is not None else ""
            cost = int(line.unit_cost_cents or line.unit_cost or 0)
            if stamp >= row["_when"]:
                row["_when"] = stamp
                row["last_cost_cents"] = cost
                row["last_cost_label"] = money_label(cost, line.currency or DEFAULT_CURRENCY)
        for invoice in invoices:
            for raw in invoice.extracted_lines or []:
                if not isinstance(raw, dict):
                    continue
                code = str(raw.get("sku") or "").casefold()
                sku = sku_by_code.get(code)
                product_key = None if sku is None or sku.variant is None else sku.variant.product_id
                row = bucket(invoice.supplier_id, product_key)
                if row is None:
                    continue
                try:
                    qty = int(Decimal(str(raw.get("quantity") or 0)).to_integral_value())
                except Exception:
                    qty = 0
                row["invoiced_bottles"] += qty
        rows = []
        for row in buckets.values():
            row.pop("_when", None)
            rows.append(row)
        rows.sort(key=lambda row: (row["supplier"], row["product"], row["product_id"]))
        return {"rows": rows}


def demo_phrase(prompt: str) -> str:
    from langchain_core.messages import HumanMessage

    from madira.agents.demo.model import DemoChatModel

    message = DemoChatModel(role="buyer-phrasing").invoke([HumanMessage(content=prompt)])
    content = message.content
    return content if isinstance(content, str) else str(content)


def demo_thanks(prompt: str) -> str:
    from langchain_core.messages import HumanMessage

    from madira.agents.demo.model import DemoChatModel

    message = DemoChatModel(role="rep-drafter").invoke([HumanMessage(content=prompt)])
    content = message.content
    return content if isinstance(content, str) else str(content)


def live_complete(prompt: str, *, kind: str) -> str:
    from madira.llm_runtime import resolve_runtime

    runtime = resolve_runtime()
    if runtime.demo_mode:
        raise DraftFailed(f"The {kind} could not be written because the model is not live.", 502)
    try:
        from langchain.chat_models import init_chat_model
        from langchain_core.messages import HumanMessage, SystemMessage

        kwargs = {}
        if runtime.api_key:
            kwargs["api_key"] = runtime.api_key
        model = init_chat_model(f"{runtime.provider}:{runtime.model}", **kwargs)
        message = model.invoke(
            [
                SystemMessage(content="Reply with JSON only. Do not include prices, counts, or dates."),
                HumanMessage(content=prompt),
            ]
        )
        content = message.content
        return content if isinstance(content, str) else str(content)
    except DraftFailed:
        raise
    except Exception as exc:
        raise DraftFailed(f"The {kind} could not be written ({type(exc).__name__}).", 502) from exc


def _rationales(gaps: list[dict]) -> dict[int, str]:
    prompt = _gap_prompt(gaps)
    raw = _call_phrase(prompt)
    return _parse_rationales(raw, gaps)


def _thanks_line(facts: dict) -> str:
    prompt = (
        "Write one thank-you sentence for a supplier tasting. Use no digits, prices, or counts.\n"
        f"SUPPLIER {facts['supplier']}\n"
        f"TITLE {facts['title']}\n"
        'Return JSON {"thanks":"..."}'
    )
    raw = _call_thanks(prompt)
    return _parse_thanks(raw)


def _call_phrase(prompt: str) -> str:
    try:
        if _phrase_override is not None:
            return _phrase_override(prompt)
        if demo_posture():
            return demo_phrase(prompt)
        return live_complete(prompt, kind="sourcing brief")
    except DraftFailed:
        raise
    except Exception as exc:
        raise DraftFailed(f"The sourcing brief could not be written ({type(exc).__name__}).", 502) from exc


def _call_thanks(prompt: str) -> str:
    try:
        if _thanks_override is not None:
            return _thanks_override(prompt)
        if demo_posture():
            return demo_thanks(prompt)
        return live_complete(prompt, kind="follow-up draft")
    except DraftFailed:
        raise
    except Exception as exc:
        raise DraftFailed(f"The follow-up draft could not be written ({type(exc).__name__}).", 502) from exc


def _gap_prompt(gaps: list[dict]) -> str:
    lines = ["Write a short rationale for each gap. Use no digits.", "GAPS"]
    for index, gap in enumerate(gaps):
        names = ", ".join(dish["name"] for dish in gap["dishes"] if dish.get("name")) or "the cellar"
        lines.append(f"{index}\t{gap['category']}\t{gap['style']}\t{gap['price_band']}\t{names}")
    lines.append("END")
    lines.append('Return JSON {"lines":[{"index":0,"rationale":"..."}]}')
    return "\n".join(lines)


def _parse_rationales(raw: str, gaps: list[dict]) -> dict[int, str]:
    found: dict[int, str] = {}
    blob = _json_object(raw)
    rows = blob.get("lines") if isinstance(blob, dict) else None
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            index = row.get("index")
            if not isinstance(index, int):
                continue
            text = _without_digits(str(row.get("rationale") or ""))
            if text:
                found[index] = text
    for index, gap in enumerate(gaps):
        if index not in found:
            found[index] = _fallback_rationale(gap)
    return found


def _parse_thanks(raw: str) -> str:
    blob = _json_object(raw)
    text = ""
    if isinstance(blob, dict):
        text = _without_digits(str(blob.get("thanks") or ""))
    if not text:
        text = "Thank you for pouring with us."
    return text


def _json_object(raw: str) -> dict:
    text = raw or ""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise DraftFailed("The model did not return a sourcing draft.", 502)
    try:
        blob = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise DraftFailed("The model did not return a sourcing draft.", 502) from exc
    if not isinstance(blob, dict):
        raise DraftFailed("The model did not return a sourcing draft.", 502)
    return blob


def _without_digits(value: str) -> str:
    return " ".join(re.sub(r"\d+", "", value or "").split())[:400]


def _fallback_rationale(gap: dict) -> str:
    names = ", ".join(dish["name"] for dish in gap["dishes"] if dish.get("name"))
    if names:
        return _without_digits(f"Covers {gap['style']} for {names}.")
    return _without_digits(f"Covers {gap['style']} in the {gap['price_band']} band.")


def _gap_rows(session: Session, venue: Venue) -> tuple[list[dict], uuid.UUID | None]:
    beverage = session.scalar(
        select(BeverageList)
        .where(BeverageList.venue_id == venue.id)
        .order_by(BeverageList.created_at.desc(), BeverageList.id.desc())
    )
    dishes = confirmed_dishes(session, venue.id)
    by_key: dict[tuple, list] = {}
    for dish in dishes:
        for cell in cells_for_dish(dish):
            bucket = by_key.setdefault(cell.key, [])
            if all(item.id != dish.id for item in bucket):
                bucket.append(dish)
    gaps = []
    if beverage is not None:
        from madira.domain.lists.service import _coverage

        for cell in _coverage(session, beverage)["suggestions"]:
            key = (cell["category"], cell["style"], cell["band"])
            linked = by_key.get(key, [])
            public = [{"dish_id": str(dish.id), "name": dish.name} for dish in linked]
            if not public and cell.get("dish_name"):
                public = [{"dish_id": "" if cell.get("dish_id") is None else str(cell["dish_id"]), "name": cell["dish_name"]}]
            gaps.append(_gap(cell["category"], cell["style"], cell["band"], public))
        return gaps, beverage.id
    for cell in matrix(session, venue.id):
        public = [{"dish_id": str(dish.id), "name": dish.name} for dish in by_key.get(cell.key, [])]
        gaps.append(_gap(cell.category, cell.style, cell.band, public))
    return gaps, None


def _gap(category: str, style: str, band: str, dishes: list[dict]) -> dict:
    quantity = len(dishes) if dishes else _HOUSE_CASE
    return {
        "category": category,
        "style": style,
        "price_band": band or "",
        "quantity_hint": quantity,
        "dishes": dishes,
    }


def _catalog(session: Session, venue: Venue) -> list[dict]:
    rows = []
    skus = session.scalars(select(Sku).where(Sku.venue_id == venue.id)).all()
    seen: set[uuid.UUID] = set()
    for sku in skus:
        product = None if sku.variant is None else sku.variant.product
        if product is None or product.organization_id != venue.organization_id or product.id in seen:
            continue
        seen.add(product.id)
        rows.append(
            {
                "product_id": product.id,
                "category": normalize_category(product.category),
                "style": drink_style(product),
            }
        )
    return rows


def _links(session: Session, venue_id: uuid.UUID, gap: dict, catalog: list[dict]) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    best: SupplierOffer | None = None
    product_id = None
    for row in catalog:
        if row["category"] != normalize_category(gap["category"]):
            continue
        if not style_match(gap["style"], row["style"]):
            continue
        offer = current_offer(session, venue_id, row["product_id"])
        if offer is None:
            continue
        if best is None or (int(offer.price_cents or 0), str(offer.id)) < (int(best.price_cents or 0), str(best.id)):
            best = offer
            product_id = row["product_id"]
    sample_id = None
    if product_id is not None:
        sample = session.scalar(
            select(Sample)
            .where(Sample.venue_id == venue_id, Sample.product_id == product_id)
            .order_by(Sample.created_at.desc(), Sample.id.desc())
        )
        if sample is not None:
            sample_id = sample.id
    return sample_id, None if best is None else best.id


def _buy(session: Session, venue: Venue, sample: Sample) -> None:
    if sample.po_line_id is not None:
        line = session.get(POLine, sample.po_line_id)
        order = None if line is None else session.get(PurchaseOrder, line.po_id)
        if line is not None and order is not None and order.venue_id == venue.id and order.status != "canceled":
            sample.purchase_order_id = order.id
            return
    sku = _sku_for(session, venue, sample)
    cost, _code = _cost(session, venue, sample)
    supplier_id = _supplier_for(session, sample)
    supplier = session.get(Supplier, supplier_id)
    if supplier is None or supplier.venue_id != venue.id:
        raise TastingError(_NO_SUPPLIER)
    product = session.get(Product, sample.product_id)
    raw = {
        "sku": sku.barcode,
        "sku_id": str(sku.id),
        "product_name": "" if product is None else product.name,
        "cases_ordered": 1,
        "case_size": int(supplier.default_case_size or 12),
        "unit_cost_cents": cost,
        "notes": f"Tasting sample {sample.id}",
    }
    try:
        order, line, _created = place_draft_line(
            session,
            venue.id,
            supplier.id,
            raw,
            current_request(),
            "Drafted from a tasting sample.",
        )
    except OrderError as exc:
        raise TastingError(exc.message, exc.status) from exc
    if order.status != "draft":
        raise TastingError("A tasting can only add a line to a draft purchase order.", 409)
    sample.purchase_order_id = order.id
    sample.po_line_id = line.id
    sample.sku_id = sku.id
    if sample.supplier_id is None:
        sample.supplier_id = supplier.id


def _list(session: Session, venue: Venue, sample: Sample) -> None:
    if sample.list_version_id is not None:
        pinned = session.get(ListVersion, sample.list_version_id)
        if pinned is not None and pinned.venue_id == venue.id:
            sample.list_id = pinned.list_id
            return
    sku = _sku_for(session, venue, sample)
    cost, code = _cost(session, venue, sample)
    beverage = session.scalar(
        select(BeverageList)
        .where(BeverageList.venue_id == venue.id)
        .order_by(BeverageList.created_at.desc(), BeverageList.id.desc())
    )
    if beverage is None:
        beverage = BeverageList(
            venue_id=venue.id,
            name="Tasting picks",
            budget=0,
            currency=venue.currency or DEFAULT_CURRENCY,
            target_margin=3.0,
            notes="Drafted from a tasting.",
        )
        session.add(beverage)
        session.flush()
    existing = session.scalar(
        select(ListItem).where(ListItem.venue_id == venue.id, ListItem.list_id == beverage.id, ListItem.sku_id == sku.id)
    )
    if existing is None:
        product = session.get(Product, sample.product_id)
        category = normalize_category(None if product is None else product.category)
        try:
            _guard_limits(session, beverage, cost, category)
        except DraftFailed as exc:
            raise TastingError(exc.message, exc.status) from exc
        ensure_default_rules(session, venue.id)
        rules = load_rules(session, venue.id)
        quote = price_for(cost, category, rules)
        label = section_name(category)
        group = _ensure_section(session, venue.id, beverage, label)
        position = 1 + max((int(item.position or 0) for item in beverage.items), default=0)
        item = ListItem(
            venue_id=venue.id,
            list_id=beverage.id,
            sku_id=sku.id,
            section=group.name,
            section_id=group.id,
            position=position,
            cost=cost,
            pour_price=quote["glass_price"],
            bottle_price=quote["bottle_price"],
            currency=code,
            margin_pct=0,
        )
        session.add(item)
        session.flush()
        record_audit_event(
            session,
            org_id=venue.organization_id,
            venue_id=venue.id,
            action="list.item_added",
            entity_type="list_item",
            entity_id=item.id,
            after={"list_id": str(beverage.id), "sku_id": str(sku.id), "product_id": str(sample.product_id), "cost": cost},
        )
    version = None
    drafts = session.scalars(
        select(ListVersion)
        .where(ListVersion.venue_id == venue.id, ListVersion.list_id == beverage.id, ListVersion.status == "draft")
        .order_by(ListVersion.number.desc(), ListVersion.id.desc())
    ).all()
    for draft in drafts:
        hit = session.scalar(
            select(ListEntry.id).where(ListEntry.version_id == draft.id, ListEntry.sku_id == sku.id)
        )
        if hit is not None:
            version = draft
            break
    if version is None:
        version = _insert_snapshot(session, beverage)
        if version.status != "draft":
            raise TastingError("A tasting can only add a bottle to a draft list version.", 409)
    sample.list_id = beverage.id
    sample.list_version_id = version.id
    sample.sku_id = sku.id


def _sku_for(session: Session, venue: Venue, sample: Sample) -> Sku:
    if sample.sku_id is not None:
        sku = session.get(Sku, sample.sku_id)
        if sku is not None and sku.venue_id == venue.id:
            return sku
    rows = session.scalars(select(Sku).where(Sku.venue_id == venue.id)).all()
    matches = []
    for sku in rows:
        variant = sku.variant
        if variant is not None and variant.product_id == sample.product_id:
            matches.append(sku)
    if not matches:
        raise TastingError(_NO_SKU)
    matches.sort(key=lambda sku: (sku.barcode or "", str(sku.id)))
    return matches[0]


def _cost(session: Session, venue: Venue, sample: Sample) -> tuple[int, str]:
    if sample.quoted_price_cents is not None:
        return int(sample.quoted_price_cents), sample.currency or venue.currency or DEFAULT_CURRENCY
    if sample.product_id is not None:
        offer = current_offer(session, venue.id, sample.product_id, sample.supplier_id)
        if offer is not None:
            return int(offer.price_cents or 0), offer.currency or venue.currency or DEFAULT_CURRENCY
    raise TastingError(_NO_PRICE)


def _supplier_for(session: Session, sample: Sample) -> uuid.UUID:
    if sample.supplier_id is not None:
        return sample.supplier_id
    from madira.models import TastingSession

    tasting_row = session.get(TastingSession, sample.session_id)
    if tasting_row is not None and tasting_row.supplier_id is not None:
        return tasting_row.supplier_id
    if sample.offer_id is not None:
        offer = session.get(SupplierOffer, sample.offer_id)
        if offer is not None and offer.supplier_id is not None:
            return offer.supplier_id
    raise TastingError(_NO_SUPPLIER)


def _already(sample: Sample, decision: str, reason: str | None) -> bool:
    if sample.decision != decision:
        return False
    if decision == "buy":
        return sample.po_line_id is not None
    if decision == "list":
        return sample.list_version_id is not None
    if decision == "pass":
        text = " ".join(str(reason or "").split())
        return bool(sample.pass_reason) and (not text or text == sample.pass_reason)
    return decision == "undecided"


def _stamp_decision(sample: Sample, decision: str) -> None:
    sample.decision = decision
    if decision == "undecided":
        sample.decided_by_user_id = None
        sample.decided_at = None
        sample.pass_reason = ""
        return
    actor = _actor()
    sample.decided_by_user_id = None if actor is None else actor[0]
    sample.decided_at = datetime.now(timezone.utc)
    if decision != "pass":
        sample.pass_reason = sample.pass_reason or ""


def _outcome(sample: Sample) -> dict:
    return {
        "decision": sample.decision,
        "pass_reason": sample.pass_reason or "",
        "purchase_order_id": sample.purchase_order_id,
        "po_line_id": sample.po_line_id,
        "list_id": sample.list_id,
        "list_version_id": sample.list_version_id,
        "decided_at": sample.decided_at,
    }


def _followup_facts(session: Session, venue: Venue, tasting) -> dict:
    supplier = None if tasting.supplier_id is None else session.get(Supplier, tasting.supplier_id)
    email = ""
    name = ""
    if supplier is not None and supplier.venue_id == venue.id:
        name = supplier.name
        email = (supplier.rep_email or supplier.contact_email or "").strip()
        if not email:
            contact = session.scalar(
                select(SupplierContact)
                .where(SupplierContact.supplier_id == supplier.id, SupplierContact.venue_id == venue.id)
                .order_by(SupplierContact.is_primary.desc(), SupplierContact.created_at)
            )
            if contact is not None:
                email = (contact.email or "").strip()
    lines = []
    po_id = None
    po_number = ""
    for sample in tasting.samples:
        product = sample.product
        if product is None and sample.product_id is not None:
            product = session.get(Product, sample.product_id)
        label = "Unmatched sample" if product is None else product.name
        score = "no score" if sample.score is None else f"score {sample.score}"
        extra = ""
        if sample.decision == "buy" and sample.purchase_order_id is not None:
            order = session.get(PurchaseOrder, sample.purchase_order_id)
            if order is not None and order.venue_id == venue.id:
                po_id = order.id
                po_number = order.po_number or ""
                extra = f" Draft purchase order {po_number}." if po_number else " Draft purchase order."
        elif sample.decision == "list" and sample.list_version_id is not None:
            version = session.get(ListVersion, sample.list_version_id)
            if version is not None and version.venue_id == venue.id:
                extra = f" Draft list version {int(version.number)}."
        elif sample.decision == "pass" and sample.pass_reason:
            extra = f" Passed: {sample.pass_reason}."
        lines.append(f"- {label}: {sample.decision}, {score}.{extra}")
    title = tasting.title or "Tasting"
    return {
        "supplier_id": None if supplier is None else supplier.id,
        "supplier": name,
        "to_email": email,
        "title": title,
        "when": format_wall(tasting.starts_at),
        "subject": f"Tasting follow-up: {title}"[:200],
        "lines": lines,
        "purchase_order_id": po_id,
        "purchase_order_number": po_number,
    }


def _followup_body(facts: dict, thanks: str) -> str:
    decisions = "\n".join(facts["lines"]) if facts["lines"] else "- No samples were recorded."
    return (
        f"{thanks}\n\n"
        f"{facts['title']}\n"
        f"{facts['when']}\n\n"
        f"{decisions}\n\n"
        "This note is a draft. Madira did not send it.\n"
    )


def _followup_public(session: Session, venue: Venue, row: RepFollowup) -> dict:
    supplier = ""
    if row.supplier_id is not None:
        found = session.get(Supplier, row.supplier_id)
        if found is not None and found.venue_id == venue.id:
            supplier = found.name
    number = ""
    if row.purchase_order_id is not None:
        order = session.get(PurchaseOrder, row.purchase_order_id)
        if order is not None and order.venue_id == venue.id:
            number = order.po_number or ""
    mailto = ""
    if row.to_email:
        mailto = f"mailto:{quote(row.to_email)}?subject={quote(row.subject)}&body={quote(row.body)}"
    return {
        "id": str(row.id),
        "session_id": str(row.session_id),
        "supplier_id": None if row.supplier_id is None else str(row.supplier_id),
        "supplier": supplier,
        "to_email": row.to_email or "",
        "subject": row.subject or "",
        "body": row.body or "",
        "purchase_order_id": None if row.purchase_order_id is None else str(row.purchase_order_id),
        "purchase_order_number": number,
        "mailto": mailto,
        "sent": False,
    }


def _brief_public(session: Session, brief: SourcingBrief) -> dict:
    items = session.scalars(
        select(WantItem).where(WantItem.brief_id == brief.id).order_by(WantItem.position, WantItem.id)
    ).all()
    return {
        "id": str(brief.id),
        "venue_id": str(brief.venue_id),
        "list_id": None if brief.list_id is None else str(brief.list_id),
        "title": brief.title,
        "status": brief.status,
        "created_at": brief.created_at.isoformat() if brief.created_at is not None else "",
        "items": [_item_public(item) for item in items],
    }


def _item_public(item: WantItem) -> dict:
    dishes = []
    for dish in item.dishes or []:
        if not isinstance(dish, dict):
            continue
        dishes.append({"dish_id": str(dish.get("dish_id") or ""), "name": str(dish.get("name") or "")})
    return {
        "id": str(item.id),
        "category": item.category,
        "style": item.style,
        "price_band": item.price_band or "",
        "quantity_hint": int(item.quantity_hint or 0),
        "dishes": dishes,
        "sample_id": None if item.sample_id is None else str(item.sample_id),
        "offer_id": None if item.offer_id is None else str(item.offer_id),
        "rationale": item.rationale or "",
        "position": int(item.position or 0),
    }


def _owned_brief(session: Session, venue_id: uuid.UUID, brief_id: uuid.UUID) -> SourcingBrief:
    row = session.get(SourcingBrief, brief_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("sourcing brief not found")
    return row


def _owned_item(session: Session, venue_id: uuid.UUID, item_id: uuid.UUID) -> WantItem:
    row = session.get(WantItem, item_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("want item not found")
    return row


def _sample_in_venue(session: Session, venue_id: uuid.UUID, sample_id) -> Sample:
    sample = session.get(Sample, _uuid(sample_id, "sample"))
    if sample is None or sample.venue_id != venue_id:
        raise NotFound("sample not found")
    return sample


def _uuid(value, label: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise NotFound(f"{label} not found") from exc


def _actor() -> tuple[uuid.UUID, str] | None:
    ctx = current_request()
    if ctx is None:
        return None
    return ctx.user_id, ctx.email or ""
