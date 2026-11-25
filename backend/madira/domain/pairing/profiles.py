"""Structured drink profiles for pairing.

A product stores body, acidity, tannin, sweetness, oak, and intensity. An
approved tasting note for this venue wins when it has those fields. When
neither has them, a small typed map derives the same shape from the name,
style, grape, and category.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

_BODY = {"light": 1, "medium": 3, "full": 5}
_ACID = {"low": 1, "medium": 3, "high": 5}
_SWEET = {"bone-dry": 0, "dry": 1, "off-dry": 2, "medium-sweet": 4, "sweet": 5}
_TANNIN = {"none": 0, "low": 1, "medium": 3, "high": 5}
_LEVEL_FIELDS = ("body", "acidity", "tannin", "sweetness", "oak", "intensity")

# Specific bottles before broad categories. Tokens are accent-folded.
_RULES: tuple[tuple[tuple[str, ...], tuple[int, int, int, int, int, int, str]], ...] = (
    (("muscadet", "melon de bourgogne"), (1, 5, 0, 0, 2, 0, "a high-acid white")),
    (("chablis", "chardonnay", "sancerre", "sauvignon"), (2, 4, 0, 0, 1, 0, "a crisp white")),
    (("riesling",), (2, 5, 2, 0, 1, 0, "an aromatic white")),
    (("sauternes", "botrytis", "tokaj"), (4, 4, 5, 0, 1, 0, "a sweet wine")),
    (("banyuls", "port", "madeira"), (4, 3, 4, 0, 2, 2, "a sweet fortified wine")),
    (("barolo", "barbaresco", "nebbiolo"), (4, 4, 0, 0, 3, 5, "a structured red")),
    (("cote-rotie", "syrah", "shiraz"), (5, 3, 1, 1, 3, 3, "a full-bodied red")),
    (("pinot noir",), (3, 4, 0, 0, 3, 2, "a light red")),
    (("cabernet", "merlot"), (4, 3, 0, 0, 2, 4, "a full-bodied red")),
    (("kolsch", "pils", "lager"), (1, 3, 1, 0, 1, 0, "a light beer")),
    (("stout", "porter"), (5, 2, 2, 0, 3, 0, "a dark beer")),
    (("lambic", "kriek"), (2, 5, 3, 0, 1, 0, "a sour beer")),
    (("daiginjo", "dassai", "ginjo"), (2, 3, 2, 0, 3, 0, "a fragrant sake")),
    (("yamahai", "kimoto"), (3, 3, 1, 0, 5, 0, "a savory sake")),
    (("mezcal", "rye", "whisky", "whiskey", "bourbon"), (3, 1, 1, 2, 2, 0, "a spirit")),
    (("fino", "sherry"), (1, 4, 0, 0, 4, 0, "a dry sherry")),
)

_CATEGORY = {
    "wine": (3, 3, 1, 0, 2, 2, "a wine"),
    "beer": (2, 3, 1, 0, 1, 0, "a beer"),
    "spirit": (3, 1, 1, 1, 1, 0, "a spirit"),
    "sake": (2, 3, 1, 0, 4, 0, "a sake"),
}
_FALLBACK = (3, 3, 1, 0, 2, 1, "a balanced bottle")


@dataclass(frozen=True)
class DrinkProfile:
    richness: int
    acidity: int
    sweetness: int
    spice: int
    umami: int
    tannin: int
    label: str


def fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


def _clip(value: int) -> int:
    return max(0, min(5, int(value)))


def _pack(levels: tuple[int, int, int, int, int, int, str]) -> DrinkProfile:
    richness, acidity, sweetness, spice, umami, tannin, label = levels
    return DrinkProfile(
        richness=_clip(richness),
        acidity=_clip(acidity),
        sweetness=_clip(sweetness),
        spice=_clip(spice),
        umami=_clip(umami),
        tannin=_clip(tannin),
        label=label,
    )


def _label(richness: int, acidity: int, sweetness: int, tannin: int, category: str) -> str:
    if sweetness >= 4:
        return "a sweet wine"
    if category == "beer":
        return "a beer"
    if category == "sake":
        return "a sake"
    if category == "spirit":
        return "a spirit"
    if acidity >= 4 and richness <= 2:
        return "a high-acid white"
    if tannin >= 3 or richness >= 4:
        return "a full-bodied red"
    return "a balanced bottle"


def _from_levels(source, category: str) -> DrinkProfile | None:
    if not any(str(getattr(source, field, "") or "").strip() for field in _LEVEL_FIELDS):
        return None
    body = str(getattr(source, "body", "") or "").strip().lower()
    acidity = str(getattr(source, "acidity", "") or "").strip().lower()
    sweetness = str(getattr(source, "sweetness", "") or "").strip().lower()
    tannin = str(getattr(source, "tannin", "") or "").strip().lower()
    richness = _BODY.get(body, 3)
    acid = _ACID.get(acidity, 3)
    sweet = _SWEET.get(sweetness, 1)
    tan = _TANNIN.get(tannin, 1)
    return _pack((richness, acid, sweet, 0, 3 if tan >= 3 else 2, tan, _label(richness, acid, sweet, tan, category)))


def stored_profile(product, note=None) -> DrinkProfile | None:
    """The approved note or the product row, and only when those fields are filled in.

    Name and style rules are a pairing fallback. A sample that was never profiled
    stays unprofiled instead of borrowing a number from the name.
    """

    category = fold(getattr(product, "category", "") or "")
    for source in (note, product):
        if source is None:
            continue
        parsed = _from_levels(source, category)
        if parsed is not None:
            return parsed
    return None


def derive_profile(product, note=None) -> DrinkProfile:
    """Approved note, then the product row, then the name and style."""

    category = fold(getattr(product, "category", "") or "")
    for source in (note, product):
        if source is None:
            continue
        parsed = _from_levels(source, category)
        if parsed is not None:
            return parsed
    families = getattr(product, "aroma_families", None) or []
    blob = fold(
        " ".join(
            [
                getattr(product, "name", "") or "",
                getattr(product, "producer", "") or "",
                getattr(product, "style", "") or "",
                getattr(product, "grape", "") or "",
                getattr(product, "category", "") or "",
                " ".join(str(item) for item in families),
            ]
        )
    )
    for tokens, levels in _RULES:
        if any(token in blob for token in tokens):
            return _pack(levels)
    return _pack(_CATEGORY.get(category, _FALLBACK))
