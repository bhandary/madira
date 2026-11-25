"""Suppliers, case-rounded purchase orders, and Owner-only approval.

The original reorder draft in ``domain.purchasing`` still prices by the bottle.
This module rounds bottles up to a case, keeps the Owner decision on every
order, and archives the PDF instead of emailing it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from madira.domain.compliance.service import get_document_bytes, record_audit_event, store_document
from madira.domain.errors import NotFound
from madira.domain.inventory.ledger import public_qty
from madira.domain.inventory.service import rows as inventory_rows
from madira.domain.procurement.email_adapter import get_po_email_adapter
from madira.domain.procurement.pdf import render_purchase_order_pdf
from madira.domain.session import session_scope
from madira.models import Approval, POLine, PurchaseOrder, Sku, Supplier, SupplierContact, Venue
from madira.money import DEFAULT_CURRENCY
from madira.storage import get_storage
from madira.tenancy import OWNER, current_request

PO_ENTITY = "purchase_order"
REQUIRED_ROLE = "owner"

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_DAY_ALIASES = {
    "mon": "Mon",
    "monday": "Mon",
    "tue": "Tue",
    "tues": "Tue",
    "tuesday": "Tue",
    "wed": "Wed",
    "wednesday": "Wed",
    "thu": "Thu",
    "thur": "Thu",
    "thurs": "Thu",
    "thursday": "Thu",
    "fri": "Fri",
    "friday": "Fri",
    "sat": "Sat",
    "saturday": "Sat",
    "sun": "Sun",
    "sunday": "Sun",
}

# approved and sent are not in this map. Those steps go through approve and send.
_TRANSITIONS = {
    "draft": {"canceled"},
    "approved": {"canceled"},
    "sent": {"part_received", "received"},
    "part_received": {"received"},
    "received": {"closed"},
    "closed": set(),
    "canceled": set(),
}


class OrderError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def normalize_delivery_days(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace("/", ",").split(",")]
    elif isinstance(value, (list, tuple)):
        parts = [str(part).strip() for part in value]
    else:
        raise OrderError("Delivery days must be a list of weekdays.")
    days: list[str] = []
    for part in parts:
        if not part:
            continue
        label = _DAY_ALIASES.get(part.lower())
        if label is None:
            raise OrderError("Delivery days must be weekdays such as Tue or Thu.")
        if label not in days:
            days.append(label)
    return days


def next_delivery_date(delivery_days, lead_time_days: int = 7, today: date | None = None) -> date:
    """Earliest delivery day on or after today plus lead time."""

    start = (today or datetime.now(timezone.utc).date()) + timedelta(days=max(int(lead_time_days or 0), 0))
    allowed = normalize_delivery_days(delivery_days)
    if not allowed:
        return start
    for offset in range(21):
        candidate = start + timedelta(days=offset)
        if _WEEKDAYS[candidate.weekday()] in allowed:
            return candidate
    return start


def cases_for_bottles(bottles: int, case_size: int) -> tuple[int, int]:
    """Round a bottle count up to whole cases. Returns (cases, bottles)."""

    size = int(case_size)
    if size < 1:
        raise OrderError("Case size must be at least 1.")
    need = int(bottles)
    if need < 0:
        raise OrderError("Quantity cannot be negative.")
    if need == 0:
        return 0, 0
    cases = (need + size - 1) // size
    return cases, cases * size


def list_supplier_directory(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        rows = session.scalars(
            select(Supplier).where(Supplier.venue_id == venue_id).order_by(Supplier.name, Supplier.id)
        ).all()
        return {"suppliers": [_supplier_public(session, row) for row in rows]}


def create_supplier(venue_id: uuid.UUID, payload: dict) -> dict:
    name = _required_text(payload.get("name"), "Supplier name")
    days = normalize_delivery_days(payload.get("delivery_days") or [])
    case_size = _positive_int(payload.get("default_case_size", 12), "Case size")
    minimum = _nonnegative_int(payload.get("order_minimum_cents", 0), "Order minimum")
    lead = _nonnegative_int(payload.get("lead_time_days", 7), "Lead time")
    with session_scope() as session:
        _venue(session, venue_id)
        row = Supplier(
            venue_id=venue_id,
            name=name,
            kind=_text(payload.get("kind"), "distributor") or "distributor",
            contact_email=_text(payload.get("contact_email"), ""),
            account_number=_optional_text(payload.get("account_number")),
            order_minimum_cents=minimum,
            default_case_size=case_size,
            delivery_days=days,
            lead_time_days=lead,
            payment_terms=_optional_text(payload.get("payment_terms")),
            notes=_text(payload.get("notes"), ""),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError as exc:
            session.rollback()
            raise OrderError("A supplier with that name already exists.", 409) from exc
        body = _supplier_public(session, row)
        session.commit()
        return {"supplier": body}


def add_supplier_contact(venue_id: uuid.UUID, supplier_id: uuid.UUID, payload: dict) -> dict:
    name = _required_text(payload.get("name"), "Contact name")
    email = _required_text(payload.get("email"), "Contact email")
    with session_scope() as session:
        supplier = _supplier(session, venue_id, supplier_id)
        primary = bool(payload.get("is_primary"))
        if primary:
            for existing in supplier.contacts:
                existing.is_primary = False
        contact = SupplierContact(
            venue_id=venue_id,
            supplier_id=supplier.id,
            name=name,
            role=_optional_text(payload.get("role")),
            email=email,
            phone=_optional_text(payload.get("phone")),
            is_primary=primary,
        )
        session.add(contact)
        session.flush()
        if primary and not supplier.contact_email:
            supplier.contact_email = email
        body = _contact_public(contact)
        supplier_body = _supplier_public(session, supplier)
        session.commit()
        return {"contact": body, "supplier": supplier_body}


def create_purchase_order(venue_id: uuid.UUID, supplier_id: uuid.UUID, lines: list[dict], actor, notes: str | None = None) -> dict:
    with session_scope() as session:
        order = _create_in_session(session, venue_id, supplier_id, lines, actor, notes)
        body = _order_public(session, order)
        session.commit()
        return body


def draft_orders_from_reorder(venue_id: uuid.UUID, actor) -> dict:
    with session_scope() as session:
        _venue(session, venue_id)
        lows = [item for item in inventory_rows(session, venue_id) if item["low"] and item["reorder_qty"] > 0 and item["supplier_id"]]
        grouped: dict[uuid.UUID, list[dict]] = {}
        for item in lows:
            grouped.setdefault(item["supplier_id"], []).append(item)
        orders = []
        for supplier_id, items in grouped.items():
            supplier = _supplier(session, venue_id, supplier_id)
            size = int(supplier.default_case_size or 12)
            drafted = []
            for item in items:
                cases, bottles = cases_for_bottles(int(item["reorder_qty"]), size)
                if cases < 1:
                    continue
                drafted.append(
                    {
                        "sku": item["sku"],
                        "product_name": item["name"],
                        "cases_ordered": cases,
                        "case_size": size,
                        "unit_cost_cents": int(item["unit_cost"] or 0),
                    }
                )
            if not drafted:
                continue
            order = _create_in_session(session, venue_id, supplier.id, drafted, actor, "Drafted from stock below par.")
            orders.append(_order_public(session, order))
        session.commit()
        return {"orders": orders}


def list_purchase_orders(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        rows = session.scalars(
            select(PurchaseOrder)
            .where(PurchaseOrder.venue_id == venue_id)
            .order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc())
        ).all()
        return {"orders": [_order_public(session, row) for row in rows]}


def get_purchase_order(venue_id: uuid.UUID, po_id: uuid.UUID) -> dict:
    with session_scope() as session:
        return _order_public(session, _order(session, venue_id, po_id))


def approve_purchase_order(venue_id: uuid.UUID, po_id: uuid.UUID, actor, comment: str | None = None) -> dict:
    _require_owner(actor)
    return _decide(venue_id, po_id, actor, "approved", comment)


def reject_purchase_order(venue_id: uuid.UUID, po_id: uuid.UUID, actor, comment: str | None = None) -> dict:
    _require_owner(actor)
    return _decide(venue_id, po_id, actor, "rejected", comment)


def send_purchase_order(venue_id: uuid.UUID, po_id: uuid.UUID, actor) -> dict:
    with session_scope() as session:
        order = _order(session, venue_id, po_id)
        if order.status != "approved":
            raise OrderError("Only an approved purchase order can be sent.", 409)
        venue = _venue(session, venue_id)
        supplier = order.supplier
        contact = _primary_contact(session, supplier)
        approval = _ensure_approval(session, order)
        user_id, email, _role = _actor_bits(actor)
        pdf = render_purchase_order_pdf(
            order,
            supplier,
            contact,
            list(order.lines),
            venue,
            _pdf_approval(session, approval),
        )
        if not pdf.startswith(b"%PDF-"):
            raise OrderError("The purchase order PDF could not be rendered.", 500)
        filename = f"{order.po_number or order.id}.pdf"
        try:
            document = store_document(
                session,
                org_id=venue.organization_id,
                venue_id=venue_id,
                doc_type="purchase_order",
                filename=filename,
                content_type="application/pdf",
                body=pdf,
                linked_entity_type=PO_ENTITY,
                linked_entity_id=order.id,
                uploaded_by_user_id=user_id,
                actor_email=email,
            )
            adapter = get_po_email_adapter()
            recipient = contact.email if contact is not None else None
            reference = adapter.deliver(po_number=order.po_number or str(order.id), pdf=pdf, recipient=recipient)
            previous = order.status
            now = datetime.now(timezone.utc)
            order.pdf_document_id = document.id
            order.status = "sent"
            order.sent_at = now
            order.sent_via = adapter.sent_via
            order.delivery_adapter_ref = reference
            order.updated_at = now
            _audit(
                session,
                venue,
                order,
                "purchase_order.sent",
                actor,
                before={"status": previous},
                after={
                    "status": "sent",
                    "po_number": order.po_number,
                    "sent_via": adapter.sent_via,
                    "delivery_adapter_ref": reference,
                    "pdf_document_id": str(document.id),
                },
            )
            body = _order_public(session, order)
            session.commit()
            return body
        except Exception:
            key = None
            if "document" in locals():
                key = document.storage_key
            session.rollback()
            if key:
                try:
                    get_storage().delete(key)
                except Exception:
                    pass
            raise


def close_purchase_order(venue_id: uuid.UUID, po_id: uuid.UUID, actor) -> dict:
    return transition_purchase_order(venue_id, po_id, "closed", actor)


def cancel_purchase_order(venue_id: uuid.UUID, po_id: uuid.UUID, actor) -> dict:
    return transition_purchase_order(venue_id, po_id, "canceled", actor)


def mark_part_received(venue_id: uuid.UUID, po_id: uuid.UUID, actor) -> dict:
    return transition_purchase_order(venue_id, po_id, "part_received", actor)


def mark_received(venue_id: uuid.UUID, po_id: uuid.UUID, actor) -> dict:
    return transition_purchase_order(venue_id, po_id, "received", actor)


def transition_purchase_order(venue_id: uuid.UUID, po_id: uuid.UUID, target: str, actor) -> dict:
    with session_scope() as session:
        order = _order(session, venue_id, po_id)
        _move(session, order, target, actor)
        body = _order_public(session, order)
        session.commit()
        return body


def purchase_order_pdf(venue_id: uuid.UUID, po_id: uuid.UUID) -> tuple[str, bytes]:
    with session_scope() as session:
        order = _order(session, venue_id, po_id)
        if order.pdf_document_id is None:
            raise NotFound("purchase order pdf not found")
        document, payload = get_document_bytes(session, venue_id, order.pdf_document_id)
        return document.filename, payload


def finalize_legacy_draft(session: Session, order: PurchaseOrder, supplier: Supplier, total_cents: int) -> dict:
    """Fill lifecycle columns on a bottle-priced draft without changing its totals."""

    venue = _venue(session, order.venue_id)
    if not order.po_number:
        order.po_number = _next_po_number(session, order.venue_id)
    order.subtotal_cents = int(total_cents)
    order.order_minimum_cents = int(supplier.order_minimum_cents or 0)
    order.minimum_met = order.subtotal_cents >= order.order_minimum_cents
    order.expected_delivery_date = next_delivery_date(supplier.delivery_days or [], supplier.lead_time_days or 0).isoformat()
    order.updated_at = datetime.now(timezone.utc)
    approval = _ensure_approval(session, order)
    session.flush()
    _audit(
        session,
        venue,
        order,
        "purchase_order.drafted",
        None,
        after={
            "status": "draft",
            "po_number": order.po_number,
            "subtotal_cents": order.subtotal_cents,
            "minimum_met": order.minimum_met,
            "shortfall_cents": _shortfall(order),
        },
    )
    return {
        "po_number": order.po_number,
        "minimum_met": order.minimum_met,
        "shortfall_cents": _shortfall(order),
        "expected_delivery_date": order.expected_delivery_date,
        "approval": _approval_public(approval),
    }


def _create_in_session(session: Session, venue_id: uuid.UUID, supplier_id: uuid.UUID, lines: list[dict], actor, notes: str | None) -> PurchaseOrder:
    venue = _venue(session, venue_id)
    supplier = _supplier(session, venue_id, supplier_id)
    if not lines:
        raise OrderError("A purchase order needs at least one line.")
    user_id, _email, _role = _actor_bits(actor)
    order = PurchaseOrder(
        venue_id=venue_id,
        supplier_id=supplier.id,
        po_number=_next_po_number(session, venue_id),
        status="draft",
        notes=_text(notes, ""),
        created_by_user_id=user_id,
        order_minimum_cents=int(supplier.order_minimum_cents or 0),
        expected_delivery_date=next_delivery_date(supplier.delivery_days or [], int(supplier.lead_time_days or 0)).isoformat(),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(order)
    session.flush()
    subtotal = 0
    for raw in lines:
        built = _build_line(session, venue_id, supplier, raw)
        built.po_id = order.id
        session.add(built)
        subtotal += int(built.line_total_cents or 0)
    order.subtotal_cents = subtotal
    order.minimum_met = subtotal >= int(order.order_minimum_cents or 0)
    _ensure_approval(session, order)
    _audit(
        session,
        venue,
        order,
        "purchase_order.drafted",
        actor,
        after={
            "status": "draft",
            "po_number": order.po_number,
            "supplier_id": str(supplier.id),
            "subtotal_cents": subtotal,
            "order_minimum_cents": int(order.order_minimum_cents or 0),
            "minimum_met": order.minimum_met,
            "shortfall_cents": _shortfall(order),
            "expected_delivery_date": order.expected_delivery_date,
        },
    )
    session.flush()
    return order


def _build_line(session: Session, venue_id: uuid.UUID, supplier: Supplier, raw: dict) -> POLine:
    sku_code = _required_text(raw.get("sku"), "SKU")
    stock = session.scalar(select(Sku).where(Sku.venue_id == venue_id, func.upper(Sku.barcode) == sku_code.upper()))
    if raw.get("sku_id") and (stock is None or stock.id != _uuid(raw.get("sku_id"), "sku_id")):
        stock = session.get(Sku, _uuid(raw.get("sku_id"), "sku_id"))
        if stock is None or stock.venue_id != venue_id:
            raise NotFound("sku not found")
    case_size = raw.get("case_size")
    if case_size is None:
        case_size = int(supplier.default_case_size or 12)
    size = _positive_int(case_size, "Case size")
    cases, bottles = _quantities(raw, size)
    if raw.get("unit_cost_cents") is None and stock is not None:
        unit = int(stock.cost or 0)
    else:
        unit = _nonnegative_int(raw.get("unit_cost_cents", 0), "Unit cost")
    product_name = _text(raw.get("product_name"), "")
    if not product_name and stock is not None:
        product_name = stock.variant.product.name
    if not product_name:
        product_name = sku_code
    vintage = _optional_text(raw.get("vintage"))
    if vintage is None and stock is not None and stock.variant.vintage:
        vintage = stock.variant.vintage
    quantity = Decimal(bottles)
    total = int((quantity * Decimal(unit)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return POLine(
        venue_id=venue_id,
        sku=stock.barcode if stock is not None else sku_code,
        sku_id=None if stock is None else stock.id,
        name=product_name,
        product_name=product_name,
        qty=bottles,
        case_size=size,
        cases_ordered=cases,
        quantity_ordered=quantity,
        quantity_received=Decimal("0"),
        unit_cost=unit,
        unit_cost_cents=unit,
        line_total_cents=total,
        currency=stock.currency if stock is not None and stock.currency else DEFAULT_CURRENCY,
        vintage=vintage,
        notes=_optional_text(raw.get("notes")),
    )


def _quantities(raw: dict, case_size: int) -> tuple[int, int]:
    if raw.get("cases_ordered") is not None:
        cases = _positive_int(raw.get("cases_ordered"), "Cases")
        return cases, cases * case_size
    if raw.get("bottles") is not None:
        cases, bottles = cases_for_bottles(_nonnegative_int(raw.get("bottles"), "Bottles"), case_size)
        if cases < 1:
            raise OrderError("Quantity must be at least 1 bottle.")
        return cases, bottles
    if raw.get("quantity_ordered") is not None:
        try:
            needed = Decimal(str(raw.get("quantity_ordered")))
        except Exception as exc:
            raise OrderError("Quantity must be a number.") from exc
        if needed <= 0:
            raise OrderError("Quantity must be at least 1 bottle.")
        whole = int(needed.to_integral_value(rounding=ROUND_CEILING))
        cases, bottles = cases_for_bottles(whole, case_size)
        return cases, bottles
    raise OrderError("A line needs bottles, cases_ordered, or quantity_ordered.")


def _decide(venue_id: uuid.UUID, po_id: uuid.UUID, actor, decision: str, comment: str | None) -> dict:
    with session_scope() as session:
        order = _order(session, venue_id, po_id)
        if order.status != "draft":
            verb = "approved" if decision == "approved" else "rejected"
            raise OrderError(f"Only a draft purchase order can be {verb}.", 409)
        approval = _ensure_approval(session, order)
        user_id, email, _role = _actor_bits(actor)
        now = datetime.now(timezone.utc)
        previous = order.status
        approval.decision = decision
        approval.decided_by_user_id = user_id
        approval.decided_at = now
        approval.comment = _optional_text(comment)
        if decision == "approved":
            order.status = "approved"
            action = "purchase_order.approved"
        else:
            order.status = "canceled"
            action = "purchase_order.rejected"
        order.updated_at = now
        venue = _venue(session, venue_id)
        _audit(
            session,
            venue,
            order,
            action,
            actor,
            before={"status": previous, "decision": "pending"},
            after={
                "status": order.status,
                "decision": decision,
                "required_role": REQUIRED_ROLE,
                "comment": approval.comment or "",
                "decided_by": email,
            },
        )
        body = _order_public(session, order)
        session.commit()
        return body


def _move(session: Session, order: PurchaseOrder, target: str, actor) -> None:
    allowed = _TRANSITIONS.get(order.status, set())
    if target not in allowed:
        raise OrderError(f"Cannot move a {order.status} purchase order to {target}.", 409)
    venue = _venue(session, order.venue_id)
    previous = order.status
    order.status = target
    order.updated_at = datetime.now(timezone.utc)
    _audit(
        session,
        venue,
        order,
        f"purchase_order.{target}",
        actor,
        before={"status": previous},
        after={"status": target, "po_number": order.po_number},
    )


def _require_owner(actor) -> None:
    _user_id, _email, role = _actor_bits(actor)
    if (role or "").strip().lower() != OWNER.lower():
        raise OrderError("Only the Owner can approve or reject a purchase order.", 403)


def _actor_bits(actor) -> tuple[uuid.UUID | None, str, str]:
    user_id = getattr(actor, "user_id", None) if actor is not None else None
    email = getattr(actor, "email", None) if actor is not None else None
    role = getattr(actor, "role", None) if actor is not None else None
    ctx = current_request()
    if ctx is not None:
        if user_id is None:
            user_id = ctx.user_id
        if not email:
            email = ctx.email
        if not role:
            role = ctx.role
    return user_id, email or "", role or ""


def _audit(session: Session, venue: Venue, order: PurchaseOrder, action: str, actor, before=None, after=None) -> None:
    user_id, email, _role = _actor_bits(actor)
    record_audit_event(
        session,
        org_id=venue.organization_id,
        venue_id=venue.id,
        action=action,
        entity_type=PO_ENTITY,
        entity_id=order.id,
        before=before,
        after=after,
        actor_user_id=user_id,
        actor_email=email,
    )


def _find_approval(session: Session, order: PurchaseOrder) -> Approval | None:
    return session.scalar(
        select(Approval)
        .where(
            Approval.venue_id == order.venue_id,
            Approval.entity_type == PO_ENTITY,
            Approval.entity_id == order.id,
        )
        .order_by(Approval.created_at.desc())
    )


def _pending_approval(order: PurchaseOrder) -> dict:
    return {
        "id": "",
        "entity_type": PO_ENTITY,
        "entity_id": str(order.id),
        "decision": "pending",
        "required_role": REQUIRED_ROLE,
        "decided_by_user_id": None,
        "decided_at": None,
        "comment": None,
    }


def _ensure_approval(session: Session, order: PurchaseOrder) -> Approval:
    row = _find_approval(session, order)
    if row is not None:
        return row
    row = Approval(
        venue_id=order.venue_id,
        entity_type=PO_ENTITY,
        entity_id=order.id,
        decision="pending",
        required_role=REQUIRED_ROLE,
    )
    session.add(row)
    session.flush()
    return row


def _pdf_approval(session: Session, approval: Approval):
    from types import SimpleNamespace

    from madira.models import User

    email = ""
    if approval.decided_by_user_id is not None:
        user = session.get(User, approval.decided_by_user_id)
        email = user.email if user is not None else ""
    return SimpleNamespace(
        decision=approval.decision,
        required_role=approval.required_role,
        decided_by_user_id=approval.decided_by_user_id,
        decided_by_email=email,
        decided_at=approval.decided_at,
        comment=approval.comment,
    )


def _next_po_number(session: Session, venue_id: uuid.UUID) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"PO-{year}-"
    rows = session.scalars(
        select(PurchaseOrder.po_number).where(
            PurchaseOrder.venue_id == venue_id,
            PurchaseOrder.po_number.is_not(None),
        )
    ).all()
    highest = 0
    for value in rows:
        text = value or ""
        if not text.startswith(prefix):
            continue
        try:
            highest = max(highest, int(text.rsplit("-", 1)[-1]))
        except ValueError:
            continue
    return f"{prefix}{highest + 1:04d}"


def _venue(session: Session, venue_id: uuid.UUID) -> Venue:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue


def _supplier(session: Session, venue_id: uuid.UUID, supplier_id: uuid.UUID) -> Supplier:
    row = session.get(Supplier, supplier_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("supplier not found")
    return row


def _order(session: Session, venue_id: uuid.UUID, po_id: uuid.UUID) -> PurchaseOrder:
    row = session.get(PurchaseOrder, po_id)
    if row is None or row.venue_id != venue_id:
        raise NotFound("purchase order not found")
    return row


def _primary_contact(session: Session, supplier: Supplier) -> SupplierContact | None:
    del session
    contacts = list(supplier.contacts)
    if not contacts:
        return None
    contacts.sort(key=lambda row: (not row.is_primary, row.name or ""))
    return contacts[0]


def _shortfall(order: PurchaseOrder) -> int:
    return max(0, int(order.order_minimum_cents or 0) - int(order.subtotal_cents or 0))


def _supplier_public(session: Session, row: Supplier) -> dict:
    contacts = session.scalars(
        select(SupplierContact)
        .where(SupplierContact.supplier_id == row.id, SupplierContact.venue_id == row.venue_id)
        .order_by(SupplierContact.is_primary.desc(), SupplierContact.name)
    ).all()
    return {
        "id": str(row.id),
        "name": row.name,
        "kind": row.kind,
        "contact_email": row.contact_email or "",
        "account_number": row.account_number,
        "order_minimum_cents": int(row.order_minimum_cents or 0),
        "default_case_size": int(row.default_case_size or 12),
        "delivery_days": list(row.delivery_days or []),
        "lead_time_days": int(row.lead_time_days or 0),
        "payment_terms": row.payment_terms,
        "notes": row.notes or "",
        "rep_name": row.rep_name or "",
        "rep_email": row.rep_email or "",
        "rep_phone": row.rep_phone,
        "order_minimum_currency": row.order_minimum_currency or DEFAULT_CURRENCY,
        "created_at": _iso(row.created_at),
        "contacts": [_contact_public(contact) for contact in contacts],
    }


def _contact_public(row: SupplierContact) -> dict:
    return {
        "id": str(row.id),
        "supplier_id": str(row.supplier_id),
        "name": row.name,
        "role": row.role,
        "email": row.email,
        "phone": row.phone,
        "is_primary": bool(row.is_primary),
    }


def _order_public(session: Session, order: PurchaseOrder) -> dict:
    approval = _find_approval(session, order)
    supplier = order.supplier
    contact = _primary_contact(session, supplier) if supplier is not None else None
    lines = []
    for line in order.lines:
        lines.append(_line_public(line))
    return {
        "id": str(order.id),
        "po_number": order.po_number,
        "status": order.status,
        "supplier_id": str(order.supplier_id),
        "supplier": supplier.name if supplier is not None else "",
        "contact": None if contact is None else _contact_public(contact),
        "expected_delivery_date": order.expected_delivery_date,
        "subtotal_cents": int(order.subtotal_cents or 0),
        "total": int(order.subtotal_cents or 0),
        "currency": DEFAULT_CURRENCY,
        "order_minimum_cents": int(order.order_minimum_cents or 0),
        "minimum_met": bool(order.minimum_met),
        "shortfall_cents": _shortfall(order),
        "pdf_document_id": None if order.pdf_document_id is None else str(order.pdf_document_id),
        "sent_at": _iso(order.sent_at),
        "sent_via": order.sent_via,
        "delivery_adapter_ref": order.delivery_adapter_ref,
        "notes": order.notes or "",
        "created_at": _iso(order.created_at),
        "updated_at": _iso(order.updated_at),
        "lines": lines,
        "approval": _approval_public(approval) if approval is not None else _pending_approval(order),
    }


def _line_public(line: POLine) -> dict:
    name = line.product_name or line.name
    return {
        "id": str(line.id),
        "sku": line.sku,
        "sku_id": None if line.sku_id is None else str(line.sku_id),
        "name": name,
        "product_name": name,
        "case_size": int(line.case_size or 0),
        "cases_ordered": int(line.cases_ordered or 0),
        "quantity_ordered": public_qty(line.quantity_ordered or 0),
        "quantity_received": public_qty(line.quantity_received or 0),
        "qty": int(line.qty or 0),
        "unit_cost": int(line.unit_cost or 0),
        "unit_cost_cents": int(line.unit_cost_cents or line.unit_cost or 0),
        "line_total_cents": int(line.line_total_cents or 0),
        "line_cost": int(line.line_total_cents or (line.unit_cost or 0) * (line.qty or 0)),
        "currency": line.currency or DEFAULT_CURRENCY,
        "vintage": line.vintage,
        "notes": line.notes,
    }


def _approval_public(row: Approval) -> dict:
    return {
        "id": str(row.id),
        "entity_type": row.entity_type,
        "entity_id": str(row.entity_id),
        "decision": row.decision,
        "required_role": row.required_role,
        "decided_by_user_id": None if row.decided_by_user_id is None else str(row.decided_by_user_id),
        "decided_at": _iso(row.decided_at),
        "comment": row.comment,
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _text(value, default: str) -> str:
    if value is None:
        return default
    return str(value).strip()


def _optional_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(value, label: str) -> str:
    text = _text(value, "")
    if not text:
        raise OrderError(f"{label} is required.")
    return text


def _nonnegative_int(value, label: str) -> int:
    if isinstance(value, bool) or value is None:
        raise OrderError(f"{label} must be a whole number.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise OrderError(f"{label} must be a whole number.") from exc
    if number < 0:
        raise OrderError(f"{label} cannot be negative.")
    return number


def _positive_int(value, label: str) -> int:
    number = _nonnegative_int(value, label)
    if number < 1:
        raise OrderError(f"{label} must be at least 1.")
    return number


def _uuid(value, label: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise OrderError(f"{label} must be a UUID.") from exc
