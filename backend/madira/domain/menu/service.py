"""Menu and pairing rules. Persistence and arithmetic live here; surfaces do not."""

from __future__ import annotations

import io
import uuid

from sqlalchemy import delete, select

from madira.domain.catalog.service import beverage_fields, ensure_sku
from madira.domain.errors import NotFound, require_demo
from madira.domain.session import session_scope
from madira.models import Dish, Menu, Pairing
from madira.money import DEFAULT_CURRENCY, to_minor


def extract_upload_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        require_demo("Image menu extraction")
        from madira.agents.demo.fixtures import SAMPLE_MENU_TEXT

        return SAMPLE_MENU_TEXT + "\n\n[image upload in demo mode — using Maison Madira fixture]"
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        require_demo("Unreadable menu text")
        from madira.agents.demo.fixtures import SAMPLE_MENU_TEXT

        return SAMPLE_MENU_TEXT


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
    from madira.tenancy import demo_posture

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


def parse_menu(venue_id: uuid.UUID, text: str, source_name: str = "pasted") -> dict:
    parsed = _parse_text(text, source_name)
    with session_scope() as session:
        menu = Menu(
            venue_id=venue_id,
            name=parsed["name"],
            source_type=parsed["source_type"],
            raw_text=parsed["raw_text"],
            cuisine=parsed["cuisine"],
            price_tier=parsed["price_tier"],
        )
        session.add(menu)
        session.flush()
        dishes_out = []
        for row in parsed["dishes"]:
            dish = Dish(venue_id=venue_id, menu_id=menu.id, **_priced(row, "price"))
            session.add(dish)
            session.flush()
            dishes_out.append(
                {
                    "id": dish.id,
                    "name": dish.name,
                    "course": dish.course,
                    "description": dish.description,
                    "flavor_profile": dish.flavor_profile,
                    "price": dish.price,
                    "currency": dish.currency,
                }
            )
        session.commit()
        return {
            "menu_id": menu.id,
            "name": menu.name,
            "cuisine": menu.cuisine,
            "price_tier": menu.price_tier,
            "dishes": dishes_out,
        }


def list_menus(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        menus = session.scalars(
            select(Menu).where(Menu.venue_id == venue_id).order_by(Menu.created_at.desc(), Menu.id.desc())
        ).all()
        return {
            "menus": [
                {
                    "id": menu.id,
                    "name": menu.name,
                    "cuisine": menu.cuisine,
                    "price_tier": menu.price_tier,
                    "dish_count": len(menu.dishes),
                }
                for menu in menus
            ]
        }


def get_menu(venue_id: uuid.UUID, menu_id: uuid.UUID) -> dict:
    with session_scope() as session:
        menu = _owned_menu(session, venue_id, menu_id)
        if menu is None:
            raise NotFound("menu not found")
        dishes = []
        for dish in menu.dishes:
            dishes.append(
                {
                    "id": dish.id,
                    "name": dish.name,
                    "course": dish.course,
                    "flavor_profile": dish.flavor_profile,
                    "price": dish.price,
                    "currency": dish.currency,
                    "pairings": [_pairing_view(pairing) for pairing in dish.pairings],
                }
            )
        return {
            "id": menu.id,
            "name": menu.name,
            "cuisine": menu.cuisine,
            "price_tier": menu.price_tier,
            "raw_text": menu.raw_text,
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
        menu = _latest_menu(session, venue_id)
        return None if menu is None else menu.id


def recommend_pairings(venue_id: uuid.UUID, menu_id: str = "") -> dict:
    """Pair the requested menu. An empty id with no menu yet stores the sample menu first."""
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
            menu = _latest_menu(session, venue_id)
        if menu is None:
            return {"error": "menu not found"}
        dishes = list(menu.dishes)
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


def _owned_menu(session, venue_id: uuid.UUID, menu_id: uuid.UUID) -> Menu | None:
    menu = session.get(Menu, menu_id)
    if menu is None or menu.venue_id != venue_id:
        return None
    return menu


def _latest_menu(session, venue_id: uuid.UUID) -> Menu | None:
    return session.scalar(
        select(Menu).where(Menu.venue_id == venue_id).order_by(Menu.created_at.desc(), Menu.id.desc())
    )


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
