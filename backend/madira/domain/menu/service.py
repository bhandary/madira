"""Menu and pairing rules. Persistence and arithmetic live here; surfaces do not.

A new capture is a draft menu version. Pairing uses the latest confirmed
version only. Unchanged dishes keep their stable id; a new or edited dish
is marked so a later pairing run can redo just those.
"""

from __future__ import annotations

import io
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from madira.auth import utcnow
from madira.domain.catalog.service import beverage_fields, ensure_sku
from madira.domain.errors import DraftFailed, NotFound, require_demo
from madira.domain.menu.extract import (
    classify_upload,
    fetch_menu_url,
    read_menu,
    source_text,
    store_menu_source,
    stored_name,
)
from madira.domain.menu.schemas import (
    EDITABLE_FIELDS,
    DishDraft,
    content_hash,
    low_confidence,
    normalize,
)
from madira.domain.session import session_scope
from madira.models import Dish, Menu, MenuVersion, Pairing
from madira.money import DEFAULT_CURRENCY, to_minor
from madira.tenancy import current_request, demo_posture


def extract_upload_text(filename: str, data: bytes) -> str:
    """Text and PDF only. Photos go through menu ingestion, and bad bytes are refused."""

    name = (filename or "").lower()
    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")) or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:2] == b"\xff\xd8":
        raise DraftFailed("This file is a photo. Menu ingestion reads it.", 415)
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise DraftFailed("This PDF could not be read.", 422) from exc
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DraftFailed("This file is not text.", 415) from exc


def coerce_parse_text(text: str | None) -> str:
    if text:
        return text
    require_demo("Empty menu text")
    from madira.agents.demo.fixtures import SAMPLE_MENU_TEXT

    return SAMPLE_MENU_TEXT


def coerce_upload_text(raw: str) -> str:
    if raw.strip():
        return raw
    require_demo("Empty menu text")
    from madira.agents.demo.fixtures import SAMPLE_MENU_TEXT

    return SAMPLE_MENU_TEXT


def _parse_text(text: str, source_name: str) -> dict:
    if demo_posture():
        from madira.agents.demo.fixtures import parse_menu_text

        return parse_menu_text(text, source_name=source_name)
    raw = (text or "").strip()
    if not raw:
        require_demo("Empty menu text")
    from madira.domain.menu.parsing import line_parse_menu, matches_sample_menu

    if matches_sample_menu(raw):
        require_demo("Sample menu substitution")

    parsed = line_parse_menu(raw, source_name)
    if not parsed["dishes"]:
        require_demo("Sample menu substitution")
    return parsed


def _actor_id() -> uuid.UUID:
    ctx = current_request()
    if ctx is not None:
        return ctx.user_id
    if demo_posture():
        from madira.tenancy import ensure_demo_tenant

        return ensure_demo_tenant().user_id
    raise DraftFailed("Sign in required.", 401)


def _sample_copy(name: str) -> tuple[str, str] | None:
    from madira.agents.demo.fixtures import SAMPLE_DISHES

    folded = normalize(name)
    for row in SAMPLE_DISHES:
        if normalize(row["name"]) == folded:
            return row["description"], row["flavor_profile"]
    return None


def _flavor_line(fields: dict) -> str:
    words = []
    if int(fields["richness"]) >= 4:
        words.append("rich")
    if int(fields["acidity"]) >= 4:
        words.append("bright acid")
    if int(fields["sweetness"]) >= 3:
        words.append("sweet")
    if int(fields["spice"]) >= 3:
        words.append("spice")
    if int(fields["umami"]) >= 4:
        words.append("umami")
    return ", ".join(words) or "savory, balanced"


def _description(fields: dict) -> str:
    parts = [fields["main_component"], fields["cooking_method"], fields["sauce"]]
    text = ", ".join(part for part in parts if part)
    return text or fields["name"]


def _draft_dict(draft: DishDraft) -> dict:
    return draft.model_dump()


def _annotate(fields: dict) -> dict:
    copied = dict(fields)
    sample = _sample_copy(copied["name"])
    if sample is not None:
        copied["description"], copied["flavor_profile"] = sample
    else:
        copied["description"] = _description(copied)
        copied["flavor_profile"] = copied.get("flavor_profile") or _flavor_line(copied)
    copied["content_hash"] = content_hash(copied)
    return copied


def _from_parsed_row(row: dict) -> dict:
    from madira.agents.demo.menu import sample_payload

    folded = normalize(row["name"])
    minor = to_minor(row["price"])
    for dish in sample_payload()["dishes"]:
        if normalize(dish["name"]) == folded:
            fields = dict(dish)
            fields["price"] = minor
            return _annotate(fields)
    component = row["name"].split(",")[0].strip()[:200]
    confidence = {field: 0.9 for field in EDITABLE_FIELDS}
    confidence["cooking_method"] = 0.4
    confidence["sauce"] = 0.4
    return _annotate(
        {
            "name": row["name"],
            "course": row.get("course") or "",
            "price": minor,
            "main_component": component,
            "cooking_method": "",
            "sauce": "",
            "richness": 2,
            "acidity": 2,
            "sweetness": 1,
            "spice": 0,
            "umami": 2,
            "allergens": [],
            "confidence": confidence,
            "flavor_profile": row.get("flavor_profile") or "",
        }
    )


def parse_menu(venue_id: uuid.UUID, text: str, source_name: str = "pasted") -> dict:
    parsed = _parse_text(text, source_name)
    dishes = [_from_parsed_row(row) for row in parsed["dishes"]]
    saved = _save(
        venue_id,
        menu_id=None,
        name=parsed["name"],
        cuisine=parsed["cuisine"],
        price_tier=parsed["price_tier"],
        source_type="text",
        raw_text=parsed["raw_text"],
        filename=source_name,
        source_key="",
        source_url="",
        dishes=dishes,
        confirm=True,
    )
    return {
        "menu_id": saved["menu_id"],
        "name": saved["name"],
        "cuisine": saved["cuisine"],
        "price_tier": saved["price_tier"],
        "dishes": [_agent_dish(row) for row in saved["dishes"]],
    }


def ingest_menu(
    venue_id: uuid.UUID,
    *,
    filename: str = "",
    body: bytes = b"",
    content_type: str | None = None,
    text: str = "",
    url: str = "",
    menu_id: uuid.UUID | None = None,
) -> dict:
    source_url = ""
    if body:
        _kind, media = classify_upload(body, content_type, filename)
    elif url.strip():
        body, fetched_type = fetch_menu_url(url)
        _kind, media = classify_upload(body, fetched_type, filename)
        source_url = url.strip()
    elif text.strip():
        body = text.strip().encode("utf-8")
        kind, media = classify_upload(body, "text/plain", filename or "menu.txt")
    else:
        raise DraftFailed("Add a photo, PDF, link, or menu text.", 400)
    name = stored_name(filename, media)
    stored = store_menu_source(venue_id, body, media, name)
    read_kind = _kind_for_media(media)
    extracted = source_text(read_kind, body)
    draft = read_menu(kind=read_kind, media=media, filename=name, body=body, text=extracted)
    dishes = [_annotate(_draft_dict(dish)) for dish in draft.dishes]
    if source_url:
        stored_type = "url"
    elif read_kind == "photo":
        stored_type = "photo"
    elif read_kind == "pdf":
        stored_type = "pdf"
    else:
        stored_type = "text"
    return _save(
        venue_id,
        menu_id=menu_id,
        name=draft.name,
        cuisine=draft.cuisine,
        price_tier=draft.price_tier,
        source_type=stored_type,
        raw_text=extracted,
        filename=name,
        source_key=stored.key,
        source_url=source_url,
        dishes=dishes,
        confirm=False,
    )


def _kind_for_media(media: str) -> str:
    if media == "application/pdf":
        return "pdf"
    if media.startswith("image/"):
        return "photo"
    return "text"


def edit_dish(
    venue_id: uuid.UUID,
    menu_id: uuid.UUID,
    version_id: uuid.UUID,
    dish_id: uuid.UUID,
    field: str,
    value,
) -> dict:
    if field not in EDITABLE_FIELDS:
        raise DraftFailed("That field cannot be edited.", 422)
    with session_scope() as session:
        version = _owned_version(session, venue_id, menu_id, version_id)
        if version is None:
            raise NotFound("menu not found")
        if version.status != "draft":
            raise DraftFailed("This menu version is already confirmed.", 409)
        dish = _owned_dish(session, version, dish_id)
        if dish is None:
            raise NotFound("dish not found")
        updated = _apply_field(dish, field, value)
        for key, item in updated.items():
            setattr(dish, key, item)
        dish.needs_repairing = _needs_repair(session, version, dish.stable_id, dish.content_hash)
        payload = _review(session, version.menu, version)
        session.commit()
        return payload


def confirm_version(venue_id: uuid.UUID, menu_id: uuid.UUID, version_id: uuid.UUID) -> dict:
    with session_scope() as session:
        version = _owned_version(session, venue_id, menu_id, version_id)
        if version is None:
            raise NotFound("menu not found")
        if version.status != "confirmed":
            version.status = "confirmed"
            version.confirmed_by = _actor_id()
            version.confirmed_at = utcnow()
        payload = _review(session, version.menu, version)
        session.commit()
        return payload


def _apply_field(dish: Dish, field: str, value) -> dict:
    current = _dish_fields(dish)
    if field == "allergens" and isinstance(value, str):
        value = [part.strip() for part in value.split(",") if part.strip()]
    if field in {"price", "richness", "acidity", "sweetness", "spice", "umami"} and isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            value = int(stripped)
    current[field] = value
    confidence = dict(current["confidence"])
    confidence[field] = 1.0
    current["confidence"] = confidence
    try:
        draft = DishDraft.model_validate(current)
    except Exception as exc:
        raise DraftFailed("That value does not fit this field.", 422) from exc
    annotated = _annotate(_draft_dict(draft))
    return {
        "name": annotated["name"],
        "course": annotated["course"],
        "price": annotated["price"],
        "main_component": annotated["main_component"],
        "cooking_method": annotated["cooking_method"],
        "sauce": annotated["sauce"],
        "richness": annotated["richness"],
        "acidity": annotated["acidity"],
        "sweetness": annotated["sweetness"],
        "spice": annotated["spice"],
        "umami": annotated["umami"],
        "allergens": annotated["allergens"],
        "confidence": annotated["confidence"],
        "content_hash": annotated["content_hash"],
        "description": annotated["description"],
        "flavor_profile": annotated["flavor_profile"],
    }


def _dish_fields(dish: Dish) -> dict:
    return {
        "name": dish.name,
        "course": dish.course,
        "price": dish.price,
        "main_component": dish.main_component,
        "cooking_method": dish.cooking_method,
        "sauce": dish.sauce,
        "richness": dish.richness,
        "acidity": dish.acidity,
        "sweetness": dish.sweetness,
        "spice": dish.spice,
        "umami": dish.umami,
        "allergens": list(dish.allergens or []),
        "confidence": dict(dish.confidence or {}),
    }


def _save(
    venue_id: uuid.UUID,
    *,
    menu_id: uuid.UUID | None,
    name: str,
    cuisine: str,
    price_tier: str,
    source_type: str,
    raw_text: str,
    filename: str,
    source_key: str,
    source_url: str,
    dishes: list[dict],
    confirm: bool,
) -> dict:
    with session_scope() as session:
        if menu_id is None:
            menu = Menu(
                venue_id=venue_id,
                name=name,
                source_type=source_type,
                raw_text=raw_text,
                cuisine=cuisine,
                price_tier=price_tier,
            )
            session.add(menu)
            session.flush()
            prior = None
            number = 1
        else:
            menu = _owned_menu(session, venue_id, menu_id)
            if menu is None:
                raise NotFound("menu not found")
            prior = _latest_version(session, menu)
            number = 1 if prior is None else prior.number + 1
            menu.raw_text = raw_text
            menu.source_type = source_type
        version = MenuVersion(
            venue_id=venue_id,
            menu_id=menu.id,
            number=number,
            source_type=source_type,
            source_key=source_key,
            source_filename=(filename or "")[:300],
            source_url=(source_url or "")[:1000],
            raw_text=raw_text,
            status="draft",
        )
        if confirm:
            version.status = "confirmed"
            version.confirmed_by = _actor_id()
            version.confirmed_at = utcnow()
        session.add(version)
        session.flush()
        prior_by_name = {}
        if prior is not None:
            for old in _version_dishes(session, prior):
                prior_by_name.setdefault(normalize(old.name), old)
        for position, fields in enumerate(dishes):
            matched = prior_by_name.get(normalize(fields["name"]))
            stable_id = matched.stable_id if matched is not None else uuid.uuid4()
            digest = fields["content_hash"]
            repairing = matched is None or matched.content_hash != digest
            session.add(
                Dish(
                    venue_id=venue_id,
                    menu_id=menu.id,
                    menu_version_id=version.id,
                    stable_id=stable_id,
                    position=position,
                    name=fields["name"],
                    course=fields["course"],
                    description=fields["description"],
                    flavor_profile=fields["flavor_profile"],
                    price=fields["price"],
                    currency=DEFAULT_CURRENCY,
                    main_component=fields["main_component"],
                    cooking_method=fields["cooking_method"],
                    sauce=fields["sauce"],
                    richness=fields["richness"],
                    acidity=fields["acidity"],
                    sweetness=fields["sweetness"],
                    spice=fields["spice"],
                    umami=fields["umami"],
                    allergens=list(fields["allergens"]),
                    confidence=dict(fields["confidence"]),
                    content_hash=digest,
                    needs_repairing=repairing,
                )
            )
        session.flush()
        payload = _review(session, menu, version)
        session.commit()
        return payload


def list_menus(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        menus = session.scalars(
            select(Menu).where(Menu.venue_id == venue_id).order_by(Menu.created_at.desc(), Menu.id.desc())
        ).all()
        rows = []
        for menu in menus:
            version = _latest_version(session, menu)
            count = 0
            status = ""
            if version is not None:
                status = version.status
                count = session.scalar(
                    select(func.count()).select_from(Dish).where(Dish.menu_version_id == version.id)
                )
            rows.append(
                {
                    "id": menu.id,
                    "name": menu.name,
                    "cuisine": menu.cuisine,
                    "price_tier": menu.price_tier,
                    "dish_count": int(count or 0),
                    "status": status,
                }
            )
        return {"menus": rows}


def get_menu(venue_id: uuid.UUID, menu_id: uuid.UUID) -> dict:
    with session_scope() as session:
        menu = _owned_menu(session, venue_id, menu_id)
        if menu is None:
            raise NotFound("menu not found")
        version = _latest_version(session, menu)
        dishes = []
        if version is not None:
            for dish in _version_dishes(session, version):
                view = _public_dish(dish)
                view["pairings"] = [_pairing_view(pairing) for pairing in dish.pairings]
                dishes.append(view)
        return {
            "id": menu.id,
            "name": menu.name,
            "cuisine": menu.cuisine,
            "price_tier": menu.price_tier,
            "raw_text": menu.raw_text,
            "version_id": None if version is None else version.id,
            "version_number": None if version is None else version.number,
            "status": "" if version is None else version.status,
            "dishes": dishes,
        }


def menu_key(menu_id: str | uuid.UUID | None) -> uuid.UUID | None:
    if menu_id is None or menu_id == "":
        return None
    if isinstance(menu_id, uuid.UUID):
        return menu_id
    return uuid.UUID(str(menu_id))


def latest_menu_id(venue_id: uuid.UUID) -> uuid.UUID | None:
    with session_scope() as session:
        menu = _latest_confirmed_menu(session, venue_id)
        return None if menu is None else menu.id


def recommend_pairings(venue_id: uuid.UUID, menu_id: str = "") -> dict:
    """Pair the latest confirmed version. An empty id with no confirmed menu stores the sample first."""
    require_demo("Pairing recommendations")
    from madira.agents.demo.fixtures import pairings_for_dishes

    created = None
    if menu_key(menu_id) is None and latest_menu_id(venue_id) is None:
        created = parse_menu(venue_id, "", "demo")
    with session_scope() as session:
        key = menu_key(menu_id)
        if key is not None:
            menu = _owned_menu(session, venue_id, key)
            if menu is None:
                return {"error": "menu not found"}
        else:
            menu = _latest_confirmed_menu(session, venue_id)
        if menu is None:
            return {"error": "menu not found"}
        version = _confirmed_version(session, menu)
        if version is None:
            return {"error": "This menu is not confirmed."}
        dishes = _version_dishes(session, version)
        dish_payload = [
            {"name": dish.name, "flavor_profile": dish.flavor_profile, "price": dish.price, "course": dish.course}
            for dish in dishes
        ]
        planned = pairings_for_dishes(dish_payload)
        cards = []
        for dish, block in zip(dishes, planned):
            session.execute(delete(Pairing).where(Pairing.dish_id == dish.id, Pairing.venue_id == venue_id))
            stored = []
            for raw in block["pairings"]:
                view = _priced(raw, "glass_price", "bottle_price")
                stock = ensure_sku(
                    session,
                    venue_id,
                    category=view.get("category", ""),
                    name=view["name"],
                    producer=view.get("producer", ""),
                    region=view.get("region", ""),
                    style=view.get("style", ""),
                    vintage=view.get("vintage", ""),
                )
                session.add(
                    Pairing(
                        venue_id=venue_id,
                        dish_id=dish.id,
                        sku_id=stock.id,
                        rationale=view.get("rationale", ""),
                        price_tier=view.get("price_tier", ""),
                        glass_price=view["glass_price"],
                        bottle_price=view["bottle_price"],
                        currency=view["currency"],
                    )
                )
                stored.append(view)
            cards.append(
                {
                    "dish": dish.name,
                    "course": dish.course,
                    "flavor_profile": dish.flavor_profile,
                    "price": dish.price,
                    "currency": dish.currency,
                    "pairings": stored,
                }
            )
        session.commit()
        payload = {"menu_id": menu.id, "menu_name": menu.name, "dishes": cards}
        if created is not None:
            payload["created_menu"] = created
        return payload


def _owned_menu(session: Session, venue_id: uuid.UUID, menu_id: uuid.UUID) -> Menu | None:
    menu = session.get(Menu, menu_id)
    if menu is None or menu.venue_id != venue_id:
        return None
    return menu


def _owned_version(session: Session, venue_id: uuid.UUID, menu_id: uuid.UUID, version_id: uuid.UUID) -> MenuVersion | None:
    version = session.get(MenuVersion, version_id)
    if version is None or version.venue_id != venue_id or version.menu_id != menu_id:
        return None
    return version


def _owned_dish(session: Session, version: MenuVersion, dish_id: uuid.UUID) -> Dish | None:
    dish = session.get(Dish, dish_id)
    if dish is None or dish.menu_version_id != version.id or dish.venue_id != version.venue_id:
        return None
    return dish


def _latest_version(session: Session, menu: Menu) -> MenuVersion | None:
    return session.scalar(
        select(MenuVersion)
        .where(MenuVersion.menu_id == menu.id, MenuVersion.venue_id == menu.venue_id)
        .order_by(MenuVersion.number.desc())
    )


def _confirmed_version(session: Session, menu: Menu) -> MenuVersion | None:
    return session.scalar(
        select(MenuVersion)
        .where(
            MenuVersion.menu_id == menu.id,
            MenuVersion.venue_id == menu.venue_id,
            MenuVersion.status == "confirmed",
        )
        .order_by(MenuVersion.number.desc())
    )


def _latest_confirmed_menu(session: Session, venue_id: uuid.UUID) -> Menu | None:
    version = session.scalar(
        select(MenuVersion)
        .where(MenuVersion.venue_id == venue_id, MenuVersion.status == "confirmed")
        .order_by(MenuVersion.confirmed_at.desc(), MenuVersion.number.desc())
    )
    if version is None:
        return None
    return _owned_menu(session, venue_id, version.menu_id)


def _version_dishes(session: Session, version: MenuVersion) -> list[Dish]:
    return list(
        session.scalars(
            select(Dish)
            .where(Dish.menu_version_id == version.id, Dish.venue_id == version.venue_id)
            .order_by(Dish.position, Dish.id)
        )
    )


def _needs_repair(session: Session, version: MenuVersion, stable_id: uuid.UUID, digest: str) -> bool:
    prior = session.scalar(
        select(MenuVersion)
        .where(
            MenuVersion.menu_id == version.menu_id,
            MenuVersion.venue_id == version.venue_id,
            MenuVersion.number < version.number,
        )
        .order_by(MenuVersion.number.desc())
    )
    if prior is None:
        return True
    previous = session.scalar(
        select(Dish).where(
            Dish.menu_version_id == prior.id,
            Dish.stable_id == stable_id,
            Dish.venue_id == version.venue_id,
        )
    )
    if previous is None:
        return True
    return previous.content_hash != digest


def _review(session: Session, menu: Menu, version: MenuVersion) -> dict:
    return {
        "menu_id": menu.id,
        "version_id": version.id,
        "name": menu.name,
        "number": version.number,
        "status": version.status,
        "cuisine": menu.cuisine,
        "price_tier": menu.price_tier,
        "dishes": [_public_dish(dish) for dish in _version_dishes(session, version)],
    }


def _public_dish(dish: Dish) -> dict:
    confidence = dict(dish.confidence or {})
    return {
        "id": dish.id,
        "stable_id": dish.stable_id,
        "name": dish.name,
        "course": dish.course,
        "description": dish.description,
        "flavor_profile": dish.flavor_profile,
        "price": dish.price,
        "currency": dish.currency,
        "main_component": dish.main_component,
        "cooking_method": dish.cooking_method,
        "sauce": dish.sauce,
        "richness": dish.richness,
        "acidity": dish.acidity,
        "sweetness": dish.sweetness,
        "spice": dish.spice,
        "umami": dish.umami,
        "allergens": list(dish.allergens or []),
        "confidence": confidence,
        "low_confidence": low_confidence(confidence),
        "needs_repairing": bool(dish.needs_repairing),
        "content_hash": dish.content_hash,
    }


def _agent_dish(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "course": row["course"],
        "description": row["description"],
        "flavor_profile": row["flavor_profile"],
        "price": row["price"],
        "currency": row["currency"],
    }


def _pairing_view(pairing: Pairing) -> dict:
    fields = beverage_fields(pairing.sku)
    return {
        "category": fields["category"],
        "name": fields["name"],
        "producer": fields["producer"],
        "region": fields["region"],
        "style": fields["style"],
        "rationale": pairing.rationale,
        "price_tier": pairing.price_tier,
        "glass_price": pairing.glass_price,
        "bottle_price": pairing.bottle_price,
        "currency": pairing.currency,
    }


def _priced(row: dict, *fields: str) -> dict:
    copied = dict(row)
    for field in fields:
        copied[field] = to_minor(copied.get(field) or 0)
    copied["currency"] = DEFAULT_CURRENCY
    return copied
