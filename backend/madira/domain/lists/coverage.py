"""Coverage matrix: category x style x price band.

Cells come from the confirmed menu. Each dish profile, from the same shape
pairing uses, asks for a wine style and the beer, sake, or spirit styles that
sit beside it. The price band is the pairing tier of the dish price. A cellar
with no confirmed menu uses a house matrix so curation still has cells to fill.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from madira.domain.pairing.profiles import derive_profile
from madira.domain.pairing.service import _tier
from madira.domain.pairing.slots import dish_profile, wanted
from madira.models import Dish, Menu, MenuVersion

HOUSE_CELLS: tuple[tuple[str, str, str], ...] = (
    ("wine", "a high-acid white", "value"),
    ("wine", "a crisp white", "mid"),
    ("wine", "a structured red", "mid"),
    ("wine", "a full-bodied red", "reserve"),
    ("wine", "a sweet wine", "mid"),
    ("beer", "a light beer", "value"),
    ("beer", "a dark beer", "value"),
    ("spirits", "a spirit", "mid"),
    ("sake", "a fragrant sake", "mid"),
    ("sake", "a savory sake", "mid"),
)

# Dish styles from slots.wanted, opened onto the drink labels profiles.py emits.
STYLE_FAMILIES: dict[str, frozenset[str]] = {
    "a high-acid white": frozenset({"a high-acid white", "a crisp white"}),
    "a sweet wine": frozenset({"a sweet wine", "a sweet fortified wine"}),
    "a full-bodied savory bottle": frozenset({"a full-bodied red", "a structured red"}),
    "a balanced bottle": frozenset({"a balanced bottle", "a wine", "a light red", "a crisp white"}),
    "an off-dry aromatic bottle": frozenset({"an aromatic white", "a fragrant sake"}),
    "a savory bottle": frozenset({"a savory sake", "a dry sherry", "a structured red"}),
}


@dataclass(frozen=True)
class Cell:
    category: str
    style: str
    band: str
    dish_id: uuid.UUID | None = None
    dish_name: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.category, self.style, self.band)


def style_match(cell_style: str, drink_style: str) -> bool:
    if cell_style == drink_style:
        return True
    family = STYLE_FAMILIES.get(cell_style)
    return family is not None and drink_style in family


def _band(price: int) -> str:
    return _tier(int(price or 0), 0) or "value"


def cells_for_dish(dish: Dish) -> list[Cell]:
    profile = dish_profile(dish)
    band = _band(int(dish.price or 0))
    cells = [Cell("wine", wanted(profile), band, dish.id, dish.name)]
    if profile.richness <= 2 or profile.acidity >= 4:
        cells.append(Cell("beer", "a light beer", "value", dish.id, dish.name))
    elif profile.richness >= 4:
        cells.append(Cell("beer", "a dark beer", "value", dish.id, dish.name))
    if profile.umami >= 4:
        sake = "a fragrant sake" if profile.acidity >= 3 else "a savory sake"
        cells.append(Cell("sake", sake, band, dish.id, dish.name))
    if profile.richness >= 4 or profile.spice >= 3:
        cells.append(Cell("spirits", "a spirit", "mid", dish.id, dish.name))
    return cells


def confirmed_dishes(session: Session, venue_id: uuid.UUID, menu_id: uuid.UUID | None = None) -> list[Dish]:
    if menu_id is None:
        version = session.scalar(
            select(MenuVersion)
            .where(MenuVersion.venue_id == venue_id, MenuVersion.status == "confirmed")
            .order_by(MenuVersion.confirmed_at.desc(), MenuVersion.number.desc(), MenuVersion.id.desc())
        )
    else:
        menu = session.get(Menu, menu_id)
        if menu is None or menu.venue_id != venue_id:
            return []
        version = session.scalar(
            select(MenuVersion)
            .where(
                MenuVersion.menu_id == menu.id,
                MenuVersion.venue_id == venue_id,
                MenuVersion.status == "confirmed",
            )
            .order_by(MenuVersion.number.desc())
        )
    if version is None:
        return []
    return list(
        session.scalars(
            select(Dish)
            .where(Dish.menu_version_id == version.id, Dish.venue_id == venue_id)
            .order_by(Dish.position, Dish.id)
        )
    )


def matrix(session: Session, venue_id: uuid.UUID, menu_id: uuid.UUID | None = None) -> list[Cell]:
    dishes = confirmed_dishes(session, venue_id, menu_id)
    found: list[Cell] = []
    seen: set[tuple[str, str, str]] = set()
    for dish in dishes:
        for cell in cells_for_dish(dish):
            if cell.key in seen:
                continue
            seen.add(cell.key)
            found.append(cell)
    if found:
        return found
    return [Cell(category, style, band) for category, style, band in HOUSE_CELLS]


def drink_style(product, note=None) -> str:
    return derive_profile(product, note).label
