"""Choose four slots from bottles the venue already lists.

The slots are best by the glass, best bottle, a value pick, and an adventurous
pick. Matching is a typed score on the structured profiles. A slot with no
listed bottle becomes a gap that names what is missing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from madira.domain.pairing.profiles import DrinkProfile, fold

SLOTS = ("best_by_the_glass", "best_bottle", "value", "adventurous")

SLOT_LABELS = {
    "best_by_the_glass": "Best by the glass",
    "best_bottle": "Best bottle",
    "value": "Value pick",
    "adventurous": "Adventurous pick",
}


@dataclass(frozen=True)
class DishProfile:
    name: str
    main_component: str
    cooking_method: str
    sauce: str
    richness: int
    acidity: int
    sweetness: int
    spice: int
    umami: int


@dataclass(frozen=True)
class Candidate:
    sku_id: uuid.UUID
    name: str
    producer: str
    region: str
    style: str
    category: str
    glass_price: int
    bottle_price: int
    currency: str
    profile: DrinkProfile


@dataclass
class Choice:
    slot: str
    candidate: Candidate | None
    status: str
    gap: str
    rationale: str
    server_script: str
    confidence: str
    needs_copy: bool


def dish_profile(dish) -> DishProfile:
    return DishProfile(
        name=dish.name,
        main_component=dish.main_component or "",
        cooking_method=dish.cooking_method or "",
        sauce=dish.sauce or "",
        richness=int(dish.richness or 0),
        acidity=int(dish.acidity or 0),
        sweetness=int(dish.sweetness or 0),
        spice=int(dish.spice or 0),
        umami=int(dish.umami or 0),
    )


def score(dish: DishProfile, drink: DrinkProfile) -> int:
    points = (5 - abs(dish.acidity - drink.acidity)) * 3
    if dish.richness >= 4:
        points += max(drink.acidity, drink.richness) * 2
    else:
        points += (5 - abs(dish.richness - drink.richness)) * 2
    if dish.sweetness >= 3:
        points += drink.sweetness * 3
    else:
        points += (5 - abs(dish.sweetness - drink.sweetness)) * 2
        if drink.sweetness >= 4:
            points -= 8
    if dish.spice >= 3:
        if drink.sweetness >= 2:
            points += 6
        if drink.tannin >= 4:
            points -= 8
        points += 5 - abs(dish.spice - drink.spice)
    else:
        points += 5 - min(dish.spice, drink.spice)
    points += (5 - abs(dish.umami - drink.umami)) * 2
    blob = fold(f"{dish.main_component} {dish.cooking_method} {dish.sauce} {dish.name}")
    if any(word in blob for word in ("crab", "oyster", "shellfish", "yuzu", "citrus", "octopus")):
        if drink.acidity >= 4 and drink.richness <= 2:
            points += 6
    if any(word in blob for word in ("beef", "ribeye", "lamb", "marrow")) and drink.tannin >= 3:
        points += 6
    if "chocolate" in blob and drink.sweetness >= 3:
        points += 6
    return points


def confidence_for(points: int) -> str:
    if points >= 42:
        return "high"
    if points >= 30:
        return "medium"
    return "low"


def wanted(dish: DishProfile) -> str:
    if dish.sweetness >= 3:
        return "a sweet wine"
    if dish.spice >= 3:
        return "an off-dry aromatic bottle"
    if dish.richness >= 4 and dish.umami >= 4:
        return "a full-bodied savory bottle"
    if dish.acidity >= 4 and dish.richness <= 3:
        return "a high-acid white"
    if dish.umami >= 4:
        return "a savory bottle"
    return "a balanced bottle"


def gap_line(slot: str, dish: DishProfile) -> str:
    role = {
        "best_by_the_glass": "by the glass",
        "best_bottle": "by the bottle",
        "value": "at a value price",
        "adventurous": "in a different style",
    }[slot]
    return f"No listed bottle fits {SLOT_LABELS[slot]}. Missing {wanted(dish)} {role}."


def _rank(dish: DishProfile, pool: list[Candidate]) -> list[Candidate]:
    return sorted(pool, key=lambda item: (-score(dish, item.profile), str(item.sku_id)))


def _ask(item: Candidate) -> int:
    if item.bottle_price > 0:
        return item.bottle_price
    if item.glass_price > 0:
        return item.glass_price
    return 10**9


def _distance(left: DrinkProfile, right: DrinkProfile) -> int:
    return (
        abs(left.richness - right.richness)
        + abs(left.acidity - right.acidity)
        + abs(left.sweetness - right.sweetness)
        + abs(left.spice - right.spice)
        + abs(left.umami - right.umami)
        + abs(left.tannin - right.tannin)
    )


def _gap(slot: str, dish: DishProfile) -> Choice:
    return Choice(slot, None, "gap", gap_line(slot, dish), "", "", "", False)


def _kept(slot: str, candidate: Candidate, status: str, saved: tuple[str, str, str] | None) -> Choice:
    if saved is None:
        return Choice(slot, candidate, status, "", "", "", confidence_for(0), True)
    rationale, script, confidence = saved
    return Choice(slot, candidate, status, "", rationale, script, confidence or "medium", False)


def assign(
    dish: DishProfile,
    candidates: list[Candidate],
    held: dict[str, tuple[Candidate, str, tuple[str, str, str] | None]],
) -> list[Choice]:
    """Fill the four slots. `held` is a pin or swap already chosen for a slot."""

    used: set[uuid.UUID] = set()
    placed: dict[str, Choice] = {}
    for slot, (candidate, status, saved) in held.items():
        placed[slot] = _kept(slot, candidate, status, saved)
        used.add(candidate.sku_id)
    pool = [item for item in candidates if item.sku_id not in used]

    def take(slot: str, pick: Candidate | None) -> None:
        if pick is None:
            placed[slot] = _gap(slot, dish)
            return
        used.add(pick.sku_id)
        placed[slot] = Choice(
            slot,
            pick,
            "suggested",
            "",
            "",
            "",
            confidence_for(score(dish, pick.profile)),
            True,
        )

    if "best_by_the_glass" not in placed:
        take("best_by_the_glass", next((item for item in _rank(dish, pool) if item.glass_price > 0), None))
        pool = [item for item in pool if item.sku_id not in used]
    if "best_bottle" not in placed:
        take("best_bottle", next((item for item in _rank(dish, pool) if item.bottle_price > 0), None))
        pool = [item for item in pool if item.sku_id not in used]
    if "value" not in placed:
        cheapest = sorted(pool, key=lambda item: (_ask(item), -score(dish, item.profile), str(item.sku_id)))
        take("value", cheapest[0] if cheapest else None)
        pool = [item for item in pool if item.sku_id not in used]
    if "adventurous" not in placed:
        anchor = placed.get("best_bottle") or placed.get("best_by_the_glass")
        anchor_category = ""
        anchor_profile = None
        if anchor is not None and anchor.candidate is not None:
            anchor_category = anchor.candidate.category
            anchor_profile = anchor.candidate.profile

        def adventurous_key(item: Candidate):
            distance = 0 if anchor_profile is None else _distance(anchor_profile, item.profile)
            return (
                0 if item.category != anchor_category else 1,
                -distance,
                -score(dish, item.profile),
                str(item.sku_id),
            )

        ordered = sorted(pool, key=adventurous_key)
        take("adventurous", ordered[0] if ordered else None)
    return [placed[slot] for slot in SLOTS]


def demo_copy(dish: DishProfile, choice: Choice) -> tuple[str, str]:
    """Deterministic rationale and server script. The bottle was already chosen."""

    candidate = choice.candidate
    if candidate is None:
        return "", ""
    label = SLOT_LABELS[choice.slot]
    bits = []
    if dish.richness >= 4:
        bits.append("rich")
    if dish.acidity >= 4:
        bits.append("high-acid")
    if dish.sweetness >= 3:
        bits.append("sweet")
    if dish.spice >= 3:
        bits.append("spicy")
    if dish.umami >= 4:
        bits.append("savory")
    if dish.main_component:
        bits.append(dish.main_component)
    character = ", ".join(bits) or "balanced"
    rationale = (
        f"{label}: {candidate.name} with {dish.name}. "
        f"The dish is {character}; the bottle is {candidate.profile.label}."
    )
    script = f"If they order the {dish.name}, offer the {candidate.name}. It is {candidate.profile.label}."
    return rationale, script
