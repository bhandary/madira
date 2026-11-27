"""Pair a confirmed menu from the bottles the venue lists.

Unchanged dishes keep the pairings they already have. A dish flagged for
re-pair is scored again. Pins and swaps stay on their slot. A rejected bottle
is not suggested for that dish again. Prices come from the list row.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from madira.domain.catalog.service import beverage_fields
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.pairing.cache import digest, read_result, write_result
from madira.domain.pairing.copy import write_copy
from madira.domain.pairing.profiles import derive_profile
from madira.domain.pairing.slots import (
    SLOTS,
    Candidate,
    Choice,
    assign,
    confidence_for,
    dish_profile,
    score,
)
from madira.domain.session import session_scope
from madira.models import (
    BeverageList,
    Dish,
    InventoryItem,
    ListItem,
    ListVersion,
    Menu,
    MenuVersion,
    Pairing,
    PairingPreference,
    Sku,
    TastingNote,
)
from madira.money import DEFAULT_CURRENCY


def recommend(venue_id: uuid.UUID, menu_id: str | uuid.UUID | None = "") -> dict:
    key = _menu_key(menu_id)
    with session_scope() as session:
        menu = _menu(session, venue_id, key)
        if menu is None:
            return {"error": "menu not found"}
        version = _confirmed(session, menu)
        if version is None:
            return {"error": "This menu is not confirmed."}
        _pair_version(session, menu, version)
        payload = _grid(session, menu, version)
        session.commit()
        return payload


def grid(venue_id: uuid.UUID, menu_id: uuid.UUID) -> dict:
    with session_scope() as session:
        menu = _menu(session, venue_id, menu_id)
        if menu is None:
            raise NotFound("menu not found")
        version = _confirmed(session, menu)
        if version is None:
            raise DraftFailed("This menu is not confirmed.", 409)
        return _grid(session, menu, version)


def pin(venue_id: uuid.UUID, menu_id: uuid.UUID, pairing_id: uuid.UUID) -> dict:
    with session_scope() as session:
        pairing, dish = _owned_pairing(session, venue_id, menu_id, pairing_id)
        if pairing.sku_id is None or pairing.status == "gap":
            raise DraftFailed("There is no bottle to pin.", 409)
        _set_choice(session, venue_id, dish.stable_id, pairing.slot, pairing.sku_id, "pin")
        _clear_rejection(session, venue_id, dish.stable_id, pairing.sku_id)
        pairing.status = "pinned"
        payload = _grid(session, dish.version.menu, _shown_version(session, dish))
        session.commit()
        return payload


def reject(venue_id: uuid.UUID, menu_id: uuid.UUID, pairing_id: uuid.UUID) -> dict:
    with session_scope() as session:
        pairing, dish = _owned_pairing(session, venue_id, menu_id, pairing_id)
        if pairing.sku_id is None or pairing.status == "gap":
            raise DraftFailed("There is no bottle to reject.", 409)
        _add_rejection(session, venue_id, dish.stable_id, pairing.sku_id)
        _clear_choice_for_sku(session, venue_id, dish.stable_id, pairing.sku_id)
        pairing.status = "rejected"
        payload = _grid(session, dish.version.menu, _shown_version(session, dish))
        session.commit()
        return payload


def swap(venue_id: uuid.UUID, menu_id: uuid.UUID, pairing_id: uuid.UUID, sku_id: uuid.UUID) -> dict:
    with session_scope() as session:
        pairing, dish = _owned_pairing(session, venue_id, menu_id, pairing_id)
        if pairing.slot not in SLOTS:
            raise DraftFailed("That pairing has no slot.", 409)
        stock, listed = _stock_and_list(session, venue_id)
        if sku_id not in listed:
            raise NotFound("That bottle is not on the list.")
        if sku_id in stock and stock[sku_id] <= 0:
            raise DraftFailed("That bottle is out of stock.", 409)
        if _is_rejected(session, venue_id, dish.stable_id, sku_id):
            _clear_rejection(session, venue_id, dish.stable_id, sku_id)
        candidate = _candidate(session, venue_id, sku_id, listed[sku_id])
        if candidate is None:
            raise NotFound("That bottle is not on the list.")
        choice = Choice(pairing.slot, candidate, "swapped", "", "", "", "medium", True)
        texts = write_copy(dish_profile(dish), [choice])
        rationale, script = texts.get(pairing.slot, ("", ""))
        _set_choice(session, venue_id, dish.stable_id, pairing.slot, sku_id, "swap")
        pairing.sku_id = sku_id
        pairing.status = "swapped"
        pairing.rationale = rationale
        pairing.server_script = script
        pairing.confidence = "medium"
        pairing.gap = ""
        pairing.glass_price = candidate.glass_price
        pairing.bottle_price = candidate.bottle_price
        pairing.currency = candidate.currency
        pairing.price_tier = _tier(candidate.bottle_price, candidate.glass_price)
        payload = _grid(session, dish.version.menu, _shown_version(session, dish))
        session.commit()
        return payload


def dishes_for_profile(session: Session, venue_id: uuid.UUID, profile) -> list[dict]:
    """Current confirmed dishes this drink pairs with.

    The score is the same typed match the grid uses. A low score is left off
    the list. There is no model number in the result.
    """

    menu = _menu(session, venue_id, None)
    if menu is None:
        return []
    version = _confirmed(session, menu)
    if version is None:
        return []
    found: list[dict] = []
    for dish in _dishes(session, version):
        points = score(dish_profile(dish), profile)
        band = confidence_for(points)
        if band == "low":
            continue
        found.append(
            {
                "dish_id": str(dish.id),
                "name": dish.name,
                "course": dish.course or "",
                "score": points,
                "confidence": band,
            }
        )
    found.sort(key=lambda row: (-int(row["score"]), row["name"], row["dish_id"]))
    return found


def pairing_view(pairing: Pairing) -> dict:
    if pairing.sku is None:
        category = name = producer = region = style = ""
        sku_id = None
    else:
        fields = beverage_fields(pairing.sku)
        category = fields["category"]
        name = fields["name"]
        producer = fields["producer"]
        region = fields["region"]
        style = fields["style"]
        sku_id = pairing.sku_id
    return {
        "id": pairing.id,
        "slot": pairing.slot or "",
        "status": pairing.status or "suggested",
        "sku_id": sku_id,
        "category": category,
        "name": name,
        "producer": producer,
        "region": region,
        "style": style,
        "rationale": pairing.rationale or "",
        "server_script": pairing.server_script or "",
        "confidence": pairing.confidence or "",
        "price_tier": pairing.price_tier or "",
        "glass_price": pairing.glass_price,
        "bottle_price": pairing.bottle_price,
        "currency": pairing.currency,
        "gap": pairing.gap or "",
    }


def _pair_version(session: Session, menu: Menu, version: MenuVersion) -> None:
    stock, listed = _stock_and_list(session, menu.venue_id)
    notes = _notes(session, menu.venue_id)
    eligible = _eligible(session, menu.venue_id, listed, stock, notes, excluded=set())
    for dish in _dishes(session, version):
        existing = [row for row in _stored(session, dish) if row.slot in SLOTS]
        if not dish.needs_repairing and existing:
            continue
        if not dish.needs_repairing:
            prior = _prior_slotted(session, dish)
            if prior:
                _replace(session, dish, [_copy_row(dish, row) for row in prior])
                continue
        choices = _cached_or_score(session, dish, listed, stock, notes, eligible)
        texts = write_copy(dish_profile(dish), choices)
        rows = []
        for choice in choices:
            rationale, script = texts.get(choice.slot, (choice.rationale, choice.server_script))
            if choice.candidate is None:
                rows.append(
                    Pairing(
                        venue_id=dish.venue_id,
                        dish_id=dish.id,
                        sku_id=None,
                        slot=choice.slot,
                        status="gap",
                        rationale="",
                        server_script="",
                        confidence="",
                        gap=choice.gap,
                        price_tier="",
                        glass_price=0,
                        bottle_price=0,
                        currency=dish.currency or DEFAULT_CURRENCY,
                    )
                )
                continue
            confidence = choice.confidence or "medium"
            if choice.needs_copy:
                confidence = confidence_for(score(dish_profile(dish), choice.candidate.profile))
            rows.append(
                Pairing(
                    venue_id=dish.venue_id,
                    dish_id=dish.id,
                    sku_id=choice.candidate.sku_id,
                    slot=choice.slot,
                    status=choice.status,
                    rationale=rationale,
                    server_script=script,
                    confidence=confidence,
                    gap="",
                    price_tier=_tier(choice.candidate.bottle_price, choice.candidate.glass_price),
                    glass_price=choice.candidate.glass_price,
                    bottle_price=choice.candidate.bottle_price,
                    currency=choice.candidate.currency,
                )
            )
        _replace(session, dish, rows)


def _cached_or_score(session, dish: Dish, listed, stock, notes, eligible: list[Candidate]) -> list[Choice]:
    key, list_version_id = _cache_identity(session, dish, stock, notes, eligible)
    stored = read_result(session, dish.venue_id, dish.id, key)
    if stored is not None:
        loaded = _load_choices(session, dish, listed, notes, stored)
        if loaded is not None:
            return loaded
    choices = _choices_for(session, dish, listed, notes, eligible)
    write_result(
        session,
        venue_id=dish.venue_id,
        dish_id=dish.id,
        menu_version_id=dish.menu_version_id,
        list_version_id=list_version_id,
        cache_key=key,
        result=_dump_choices(choices),
    )
    return choices


def _cache_identity(session, dish: Dish, stock, notes, eligible: list[Candidate]) -> tuple[str, uuid.UUID | None]:
    rejected = _rejected_ids(session, dish.venue_id, dish.stable_id)
    prefs = _preferences(session, dish.venue_id, dish.stable_id)
    held = []
    for slot, (kind, sku_id) in sorted(prefs.items()):
        saved = _saved_copy(session, dish, slot, sku_id)
        held.append(
            {
                "slot": slot,
                "kind": kind,
                "sku_id": str(sku_id),
                "copy": None if saved is None else [saved[0], saved[1], saved[2]],
            }
        )
    versions = _published_versions(session, dish.venue_id)
    profile = dish_profile(dish)
    bottles = []
    for item in sorted(eligible, key=lambda row: str(row.sku_id)):
        drink = item.profile
        bottles.append(
            {
                "sku_id": str(item.sku_id),
                "glass": item.glass_price,
                "bottle": item.bottle_price,
                "currency": item.currency,
                "category": item.category,
                "style": item.style,
                "name": item.name,
                "profile": [
                    drink.richness,
                    drink.acidity,
                    drink.sweetness,
                    drink.spice,
                    drink.umami,
                    drink.tannin,
                    drink.label,
                ],
            }
        )
    note_rows = []
    for product_id, note in sorted(notes.items(), key=lambda item: str(item[0])):
        note_rows.append(
            {
                "product_id": str(product_id),
                "id": str(note.id),
                "body": note.body,
                "acidity": note.acidity,
                "tannin": note.tannin,
                "sweetness": note.sweetness,
                "oak": note.oak,
                "intensity": note.intensity,
            }
        )
    payload = {
        "venue_id": str(dish.venue_id),
        "dish_id": str(dish.id),
        "menu_version_id": str(dish.menu_version_id),
        "content_hash": dish.content_hash or "",
        "price": int(dish.price or 0),
        "dish": {
            "name": profile.name,
            "main_component": profile.main_component,
            "cooking_method": profile.cooking_method,
            "sauce": profile.sauce,
            "richness": profile.richness,
            "acidity": profile.acidity,
            "sweetness": profile.sweetness,
            "spice": profile.spice,
            "umami": profile.umami,
        },
        "list_versions": versions,
        "bottles": bottles,
        "notes": note_rows,
        "rejected": sorted(str(item) for item in rejected),
        "prefs": held,
        "stock_out": sorted(str(sku) for sku, qty in stock.items() if int(qty) <= 0),
    }
    list_version_id = uuid.UUID(versions[-1][0]) if versions else None
    return digest(payload), list_version_id


def _published_versions(session: Session, venue_id: uuid.UUID) -> list[list]:
    rows = session.scalars(
        select(ListVersion)
        .where(ListVersion.venue_id == venue_id, ListVersion.status == "published")
        .order_by(ListVersion.list_id, ListVersion.number, ListVersion.id)
    ).all()
    return [[str(row.id), int(row.number), str(row.list_id)] for row in rows]


def _dump_choices(choices: list[Choice]) -> list[dict]:
    dumped = []
    for choice in choices:
        dumped.append(
            {
                "slot": choice.slot,
                "sku_id": None if choice.candidate is None else str(choice.candidate.sku_id),
                "status": choice.status,
                "gap": choice.gap,
                "rationale": choice.rationale,
                "server_script": choice.server_script,
                "confidence": choice.confidence,
                "needs_copy": bool(choice.needs_copy),
            }
        )
    return dumped


def _load_choices(session, dish: Dish, listed, notes, dumped: list) -> list[Choice] | None:
    if len(dumped) != len(SLOTS):
        return None
    choices = []
    for item in dumped:
        if not isinstance(item, dict) or item.get("slot") not in SLOTS:
            return None
        raw_sku = item.get("sku_id")
        candidate = None
        if raw_sku:
            try:
                sku_id = uuid.UUID(str(raw_sku))
            except ValueError:
                return None
            candidate = _candidate(session, dish.venue_id, sku_id, listed.get(sku_id), notes)
            if candidate is None:
                return None
        elif item.get("status") != "gap":
            return None
        choices.append(
            Choice(
                item["slot"],
                candidate,
                str(item.get("status") or "suggested"),
                str(item.get("gap") or ""),
                str(item.get("rationale") or ""),
                str(item.get("server_script") or ""),
                str(item.get("confidence") or ""),
                bool(item.get("needs_copy")),
            )
        )
    if [row.slot for row in choices] != list(SLOTS):
        return None
    return choices


def _choices_for(session, dish: Dish, listed, notes, eligible: list[Candidate]) -> list[Choice]:
    rejected = _rejected_ids(session, dish.venue_id, dish.stable_id)
    prefs = _preferences(session, dish.venue_id, dish.stable_id)
    held: dict[str, tuple[Candidate, str, tuple[str, str, str] | None]] = {}
    for slot, (kind, sku_id) in prefs.items():
        if sku_id in rejected:
            continue
        candidate = _candidate(session, dish.venue_id, sku_id, listed.get(sku_id), notes)
        if candidate is None:
            continue
        saved = _saved_copy(session, dish, slot, sku_id)
        status = "pinned" if kind == "pin" else "swapped"
        held[slot] = (candidate, status, saved)
    pool = [item for item in eligible if item.sku_id not in rejected]
    return assign(dish_profile(dish), pool, held)


def _grid(session: Session, menu: Menu, version: MenuVersion) -> dict:
    stock, listed = _stock_and_list(session, menu.venue_id)
    notes = _notes(session, menu.venue_id)
    dishes = []
    for dish in _dishes(session, version):
        rejected = _rejected_ids(session, menu.venue_id, dish.stable_id)
        options = []
        for item in _eligible(session, menu.venue_id, listed, stock, notes, rejected):
            options.append(
                {
                    "sku_id": item.sku_id,
                    "name": item.name,
                    "producer": item.producer,
                    "category": item.category,
                    "style": item.style,
                }
            )
        pairings = [pairing_view(row) for row in _ordered(_stored(session, dish))]
        dishes.append(
            {
                "id": dish.id,
                "stable_id": dish.stable_id,
                "name": dish.name,
                "dish": dish.name,
                "course": dish.course,
                "flavor_profile": dish.flavor_profile,
                "price": dish.price,
                "currency": dish.currency,
                "needs_repairing": bool(dish.needs_repairing),
                "options": options,
                "pairings": pairings,
            }
        )
    return {"menu_id": menu.id, "menu_name": menu.name, "dishes": dishes}


def _eligible(session, venue_id, listed, stock, notes, excluded: set[uuid.UUID]) -> list[Candidate]:
    found = []
    for sku_id, prices in listed.items():
        if sku_id in excluded:
            continue
        if sku_id in stock and stock[sku_id] <= 0:
            continue
        candidate = _candidate(session, venue_id, sku_id, prices, notes)
        if candidate is not None:
            found.append(candidate)
    return found


def _candidate(session, venue_id, sku_id, prices, notes=None) -> Candidate | None:
    sku = session.get(Sku, sku_id)
    if sku is None or sku.venue_id != venue_id:
        return None
    product = sku.variant.product
    note = None if notes is None else notes.get(product.id)
    fields = beverage_fields(sku)
    glass, bottle, currency = (0, 0, sku.currency or DEFAULT_CURRENCY)
    if prices is not None:
        glass, bottle, currency = prices
    return Candidate(
        sku_id=sku.id,
        name=fields["name"],
        producer=fields["producer"],
        region=fields["region"],
        style=fields["style"],
        category=fields["category"],
        glass_price=glass,
        bottle_price=bottle,
        currency=currency or DEFAULT_CURRENCY,
        profile=derive_profile(product, note),
    )


def _stock_and_list(session: Session, venue_id: uuid.UUID):
    stock: dict[uuid.UUID, int] = {}
    rows = session.scalars(select(InventoryItem).where(InventoryItem.venue_id == venue_id)).all()
    for row in rows:
        stock[row.sku_id] = stock.get(row.sku_id, 0) + int(row.on_hand or 0)
    listed: dict[uuid.UUID, tuple[int, int, str]] = {}
    items = session.scalars(
        select(ListItem)
        .join(BeverageList, BeverageList.id == ListItem.list_id)
        .where(ListItem.venue_id == venue_id)
        .order_by(BeverageList.created_at.desc(), ListItem.position.asc(), ListItem.id.asc())
    ).all()
    for item in items:
        if item.sku_id in listed:
            continue
        listed[item.sku_id] = (int(item.pour_price or 0), int(item.bottle_price or 0), item.currency or DEFAULT_CURRENCY)
    return stock, listed


def _notes(session: Session, venue_id: uuid.UUID) -> dict[uuid.UUID, TastingNote]:
    rows = session.scalars(
        select(TastingNote)
        .where(TastingNote.venue_id == venue_id, TastingNote.status == "approved")
        .order_by(TastingNote.approved_at.desc(), TastingNote.id.desc())
    ).all()
    found: dict[uuid.UUID, TastingNote] = {}
    for row in rows:
        found.setdefault(row.product_id, row)
    return found


def _preferences(session: Session, venue_id: uuid.UUID, stable_id: uuid.UUID) -> dict[str, tuple[str, uuid.UUID]]:
    rows = session.scalars(
        select(PairingPreference).where(
            PairingPreference.venue_id == venue_id,
            PairingPreference.dish_stable_id == stable_id,
            PairingPreference.kind.in_(("pin", "swap")),
        )
    ).all()
    found = {}
    for row in rows:
        if row.slot in SLOTS:
            found[row.slot] = (row.kind, row.sku_id)
    return found


def _rejected_ids(session: Session, venue_id: uuid.UUID, stable_id: uuid.UUID) -> set[uuid.UUID]:
    rows = session.scalars(
        select(PairingPreference.sku_id).where(
            PairingPreference.venue_id == venue_id,
            PairingPreference.dish_stable_id == stable_id,
            PairingPreference.kind == "reject",
        )
    ).all()
    return set(rows)


def _is_rejected(session, venue_id, stable_id, sku_id) -> bool:
    return sku_id in _rejected_ids(session, venue_id, stable_id)


def _saved_copy(session, dish: Dish, slot: str, sku_id: uuid.UUID):
    row = session.scalar(
        select(Pairing)
        .join(Dish, Pairing.dish_id == Dish.id)
        .join(MenuVersion, Dish.menu_version_id == MenuVersion.id)
        .where(
            Dish.venue_id == dish.venue_id,
            Dish.stable_id == dish.stable_id,
            Dish.menu_id == dish.menu_id,
            Pairing.slot == slot,
            Pairing.sku_id == sku_id,
            Pairing.rationale != "",
        )
        .order_by(MenuVersion.number.desc(), Pairing.id.desc())
    )
    if row is None:
        return None
    return row.rationale, row.server_script, row.confidence


def _prior_slotted(session: Session, dish: Dish) -> list[Pairing]:
    previous = session.scalars(
        select(Dish)
        .join(MenuVersion, Dish.menu_version_id == MenuVersion.id)
        .where(
            Dish.venue_id == dish.venue_id,
            Dish.menu_id == dish.menu_id,
            Dish.stable_id == dish.stable_id,
            Dish.id != dish.id,
            MenuVersion.number < dish.version.number,
        )
        .order_by(MenuVersion.number.desc())
    ).all()
    for old in previous:
        slotted = _ordered(_stored(session, old))
        if slotted:
            return slotted
    return []


def _stored(session: Session, dish: Dish) -> list[Pairing]:
    return list(
        session.scalars(select(Pairing).where(Pairing.dish_id == dish.id, Pairing.venue_id == dish.venue_id)).all()
    )


def _ordered(pairings) -> list[Pairing]:
    order = {name: index for index, name in enumerate(SLOTS)}
    rows = [row for row in pairings if row.slot in SLOTS]
    rows.sort(key=lambda row: (order[row.slot], str(row.id)))
    return rows


def _copy_row(dish: Dish, row: Pairing) -> Pairing:
    return Pairing(
        venue_id=dish.venue_id,
        dish_id=dish.id,
        sku_id=row.sku_id,
        slot=row.slot,
        status=row.status,
        rationale=row.rationale,
        server_script=row.server_script,
        confidence=row.confidence,
        gap=row.gap,
        price_tier=row.price_tier,
        glass_price=row.glass_price,
        bottle_price=row.bottle_price,
        currency=row.currency,
    )


def _replace(session: Session, dish: Dish, rows: list[Pairing]) -> None:
    session.execute(delete(Pairing).where(Pairing.dish_id == dish.id, Pairing.venue_id == dish.venue_id))
    session.flush()
    for row in rows:
        session.add(row)
    session.flush()


def _set_choice(session, venue_id, stable_id, slot, sku_id, kind: str) -> None:
    rows = session.scalars(
        select(PairingPreference).where(
            PairingPreference.venue_id == venue_id,
            PairingPreference.dish_stable_id == stable_id,
            PairingPreference.slot == slot,
            PairingPreference.kind.in_(("pin", "swap")),
        )
    ).all()
    for row in rows:
        session.delete(row)
    session.flush()
    session.add(
        PairingPreference(
            venue_id=venue_id,
            dish_stable_id=stable_id,
            slot=slot,
            kind=kind,
            sku_id=sku_id,
        )
    )
    session.flush()


def _add_rejection(session, venue_id, stable_id, sku_id) -> None:
    existing = session.scalar(
        select(PairingPreference).where(
            PairingPreference.venue_id == venue_id,
            PairingPreference.dish_stable_id == stable_id,
            PairingPreference.kind == "reject",
            PairingPreference.sku_id == sku_id,
        )
    )
    if existing is None:
        session.add(
            PairingPreference(
                venue_id=venue_id,
                dish_stable_id=stable_id,
                slot="",
                kind="reject",
                sku_id=sku_id,
            )
        )
        session.flush()


def _clear_rejection(session, venue_id, stable_id, sku_id) -> None:
    session.execute(
        delete(PairingPreference).where(
            PairingPreference.venue_id == venue_id,
            PairingPreference.dish_stable_id == stable_id,
            PairingPreference.kind == "reject",
            PairingPreference.sku_id == sku_id,
        )
    )


def _clear_choice_for_sku(session, venue_id, stable_id, sku_id) -> None:
    session.execute(
        delete(PairingPreference).where(
            PairingPreference.venue_id == venue_id,
            PairingPreference.dish_stable_id == stable_id,
            PairingPreference.kind.in_(("pin", "swap")),
            PairingPreference.sku_id == sku_id,
        )
    )


def _owned_pairing(session, venue_id, menu_id, pairing_id) -> tuple[Pairing, Dish]:
    pairing = session.get(Pairing, pairing_id)
    if pairing is None or pairing.venue_id != venue_id:
        raise NotFound("pairing not found")
    dish = session.get(Dish, pairing.dish_id)
    if dish is None or dish.venue_id != venue_id or dish.menu_id != menu_id:
        raise NotFound("pairing not found")
    return pairing, dish


def _menu(session: Session, venue_id: uuid.UUID, menu_id: uuid.UUID | None) -> Menu | None:
    if menu_id is None:
        version = session.scalar(
            select(MenuVersion)
            .where(MenuVersion.venue_id == venue_id, MenuVersion.status == "confirmed")
            .order_by(MenuVersion.confirmed_at.desc(), MenuVersion.number.desc())
        )
        if version is None:
            return None
        menu = session.get(Menu, version.menu_id)
        if menu is None or menu.venue_id != venue_id:
            return None
        return menu
    menu = session.get(Menu, menu_id)
    if menu is None or menu.venue_id != venue_id:
        return None
    return menu


def _confirmed(session: Session, menu: Menu) -> MenuVersion | None:
    return session.scalar(
        select(MenuVersion)
        .where(
            MenuVersion.menu_id == menu.id,
            MenuVersion.venue_id == menu.venue_id,
            MenuVersion.status == "confirmed",
        )
        .order_by(MenuVersion.number.desc())
    )


def _shown_version(session: Session, dish: Dish) -> MenuVersion:
    version = _confirmed(session, dish.version.menu)
    if version is None:
        return dish.version
    return version


def _dishes(session: Session, version: MenuVersion) -> list[Dish]:
    return list(
        session.scalars(
            select(Dish)
            .where(Dish.menu_version_id == version.id, Dish.venue_id == version.venue_id)
            .order_by(Dish.position, Dish.id)
        )
    )


def _menu_key(menu_id) -> uuid.UUID | None:
    if menu_id is None or menu_id == "":
        return None
    if isinstance(menu_id, uuid.UUID):
        return menu_id
    return uuid.UUID(str(menu_id))


def _tier(bottle: int, glass: int) -> str:
    amount = bottle or glass
    if amount <= 0:
        return ""
    if amount < 7500:
        return "value"
    if amount < 13000:
        return "mid"
    return "reserve"
