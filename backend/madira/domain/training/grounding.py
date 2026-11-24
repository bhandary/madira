"""On-list bottles a lesson or a quiz may cite. Prices never leave this module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from madira.auth import utcnow
from madira.models import (
    BeverageList,
    Dish,
    ListItem,
    ListSection,
    Pairing,
    ProductVariant,
    ServiceCard,
    Sku,
    TastingNote,
)

_GLASSES = ("White wine glass", "Bordeaux glass", "Burgundy glass", "Flute")
_TEMPS = ("8–10°C", "10–12°C", "16–18°C", "6–8°C")
_POURS = ("150 ml", "125 ml", "60 ml", "90 ml")
_DECANTS = ("No decant", "Decant 30 minutes", "Decant 60 minutes", "No decant")


@dataclass
class BottleFact:
    sku_id: uuid.UUID
    name: str
    producer: str
    region: str
    grape: str
    category: str
    glassware: str = ""
    serving_temperature: str = ""
    pour_size: str = ""
    decanting: str = ""
    server_hook: str = ""
    guest_description: str = ""
    technical_note: str = ""
    note_approved: bool = False
    card_approved: bool = False
    pins: list[str] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        return self.note_approved and self.card_approved


def current_list_id(session: Session, venue_id: uuid.UUID) -> uuid.UUID | None:
    return session.scalar(
        select(BeverageList.id)
        .where(BeverageList.venue_id == venue_id)
        .order_by(BeverageList.created_at.desc(), BeverageList.id.desc())
        .limit(1)
    )


def on_list_facts(session: Session, venue_id: uuid.UUID) -> list[BottleFact]:
    """Bottles on the newest list, with approved notes, cards, and pinned dishes. No money."""

    list_id = current_list_id(session, venue_id)
    if list_id is None:
        return []
    sku_ids = list(
        dict.fromkeys(
            session.scalars(select(ListItem.sku_id).where(ListItem.venue_id == venue_id, ListItem.list_id == list_id)).all()
        )
    )
    if not sku_ids:
        return []
    skus = session.scalars(
        select(Sku)
        .where(Sku.venue_id == venue_id, Sku.id.in_(sku_ids))
        .options(joinedload(Sku.variant).joinedload(ProductVariant.product))
    ).unique().all()
    by_id = {sku.id: sku for sku in skus}
    product_ids = [by_id[sku_id].variant.product_id for sku_id in sku_ids if sku_id in by_id]
    notes = session.scalars(
        select(TastingNote).where(
            TastingNote.venue_id == venue_id,
            TastingNote.product_id.in_(product_ids),
            TastingNote.status == "approved",
        )
    ).all()
    cards = session.scalars(
        select(ServiceCard).where(
            ServiceCard.venue_id == venue_id,
            ServiceCard.product_id.in_(product_ids),
            ServiceCard.status == "approved",
        )
    ).all()
    note_for = _latest(notes)
    card_for = _latest(cards)
    pins = _pins(session, venue_id, sku_ids)
    facts: list[BottleFact] = []
    for sku_id in sku_ids:
        sku = by_id.get(sku_id)
        if sku is None:
            continue
        product = sku.variant.product
        note = note_for.get(product.id)
        card = card_for.get(product.id)
        facts.append(
            BottleFact(
                sku_id=sku.id,
                name=product.name,
                producer=product.producer or "",
                region=product.region or "",
                grape=product.grape or "",
                category=product.category or "",
                glassware=(card.glassware if card else "") or "",
                serving_temperature=(card.serving_temperature if card else "") or "",
                pour_size=(card.pour_size if card else "") or "",
                decanting=(card.decanting if card else "") or "",
                server_hook=(note.server_hook if note else "") or "",
                guest_description=(note.guest_description if note else "") or "",
                technical_note=(note.technical_note if note else "") or "",
                note_approved=note is not None,
                card_approved=card is not None,
                pins=list(pins.get(sku.id, ())),
            )
        )
    return facts


def grounded_bottles(session: Session, venue_id: uuid.UUID) -> list[BottleFact]:
    return [fact for fact in on_list_facts(session, venue_id) if fact.grounded]


def _latest(rows) -> dict:
    chosen: dict = {}
    for row in rows:
        current = chosen.get(row.product_id)
        if current is None or (row.approved_at or row.created_at) >= (current.approved_at or current.created_at):
            chosen[row.product_id] = row
    return chosen


def _pins(session: Session, venue_id: uuid.UUID, sku_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    rows = session.execute(
        select(Pairing.sku_id, Dish.name)
        .join(Dish, Dish.id == Pairing.dish_id)
        .where(Pairing.venue_id == venue_id, Pairing.status == "pinned", Pairing.sku_id.in_(sku_ids))
        .order_by(Dish.name.asc())
    ).all()
    found: dict[uuid.UUID, list[str]] = {}
    for sku_id, name in rows:
        if not sku_id or not name:
            continue
        bucket = found.setdefault(sku_id, [])
        if name not in bucket:
            bucket.append(name)
    return found


def ensure_card(
    session: Session,
    venue_id: uuid.UUID,
    sku: Sku,
    *,
    actor_id: uuid.UUID,
    glassware: str,
    serving_temperature: str,
    decanting: str,
    pour_size: str,
    server_hook: str,
    guest_description: str,
) -> None:
    """Add an approved note and service card when the product does not have one yet."""

    product = sku.variant.product
    note = session.scalar(
        select(TastingNote).where(
            TastingNote.venue_id == venue_id,
            TastingNote.product_id == product.id,
            TastingNote.status == "approved",
        )
    )
    now = utcnow()
    if note is None:
        note = TastingNote(
            venue_id=venue_id,
            product_id=product.id,
            server_hook=server_hook,
            guest_description=guest_description,
            technical_note=server_hook,
            source="staff",
            status="approved",
            approved_by=actor_id,
            approved_at=now,
            created_at=now,
        )
        session.add(note)
        session.flush()
    card = session.scalar(select(ServiceCard).where(ServiceCard.tasting_note_id == note.id))
    if card is None:
        session.add(
            ServiceCard(
                venue_id=venue_id,
                product_id=product.id,
                tasting_note_id=note.id,
                serving_temperature=serving_temperature,
                glassware=glassware,
                decanting=decanting,
                pour_size=pour_size,
                source="staff",
                status="approved",
                approved_by=actor_id,
                approved_at=now,
                created_at=now,
            )
        )
        session.flush()


def ensure_floor_cards(session: Session, venue_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    """Give every bottle on the current list an approved card when it has none.

    Glass, temperature, and pour rotate across the list so a quiz has real distractors.
    Catalog region and grape are left as they are.
    """

    list_id = current_list_id(session, venue_id)
    if list_id is None:
        return
    sku_ids = list(
        dict.fromkeys(
            session.scalars(
                select(ListItem.sku_id).where(ListItem.venue_id == venue_id, ListItem.list_id == list_id)
            ).all()
        )
    )
    skus = session.scalars(
        select(Sku)
        .where(Sku.venue_id == venue_id, Sku.id.in_(sku_ids))
        .options(joinedload(Sku.variant).joinedload(ProductVariant.product))
    ).unique().all()
    by_id = {sku.id: sku for sku in skus}
    for index, sku_id in enumerate(sku_ids):
        sku = by_id.get(sku_id)
        if sku is None:
            continue
        name = sku.variant.product.name
        ensure_card(
            session,
            venue_id,
            sku,
            actor_id=actor_id,
            glassware=_GLASSES[index % len(_GLASSES)],
            serving_temperature=_TEMPS[index % len(_TEMPS)],
            decanting=_DECANTS[index % len(_DECANTS)],
            pour_size=_POURS[index % len(_POURS)],
            server_hook=f"{name} follows the service card.",
            guest_description=f"Tell the guest what {name} tastes like, then the glass and the temperature.",
        )


def ensure_house_list(session: Session, venue_id: uuid.UUID, actor_id: uuid.UUID, rows: list[dict]) -> None:
    """A short service list for the demo floor, only when the venue has no list yet."""

    if current_list_id(session, venue_id) is not None:
        for row in rows:
            sku = session.scalar(select(Sku).where(Sku.venue_id == venue_id, Sku.barcode == row["barcode"]))
            if sku is None:
                continue
            sku = session.scalar(
                select(Sku)
                .where(Sku.id == sku.id)
                .options(joinedload(Sku.variant).joinedload(ProductVariant.product))
            )
            ensure_card(session, venue_id, sku, actor_id=actor_id, **{key: row[key] for key in row if key != "barcode"})
        return
    beverage = BeverageList(
        venue_id=venue_id,
        name="House service list",
        budget=500_000,
        currency="USD",
        target_margin=3.0,
        notes="Service floor for lessons.",
    )
    session.add(beverage)
    session.flush()
    section = ListSection(venue_id=venue_id, list_id=beverage.id, name="Service", position=1)
    session.add(section)
    session.flush()
    for index, row in enumerate(rows, start=1):
        sku = session.scalar(
            select(Sku)
            .where(Sku.venue_id == venue_id, Sku.barcode == row["barcode"])
            .options(joinedload(Sku.variant).joinedload(ProductVariant.product))
        )
        if sku is None:
            continue
        session.add(
            ListItem(
                venue_id=venue_id,
                list_id=beverage.id,
                sku_id=sku.id,
                section=section.name,
                section_id=section.id,
                position=index,
                cost=int(sku.cost or 0),
                pour_price=int(sku.cost or 0),
                bottle_price=int(sku.cost or 0) * 3,
                currency="USD",
                margin_pct=0,
            )
        )
        ensure_card(session, venue_id, sku, actor_id=actor_id, **{key: row[key] for key in row if key != "barcode"})
    session.flush()
