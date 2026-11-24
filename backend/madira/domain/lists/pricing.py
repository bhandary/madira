"""Integer-cent list prices from a venue's category and cost-band rules.

Bottle and glass prices are rounded to the rule's step. Margin and beverage
cost percent are computed when a row is read. They are not stored.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from madira.domain.errors import DraftFailed
from madira.models import PRICING_CATEGORIES, PricingRule

_CENT = Decimal("1")
_TENTH = Decimal("0.1")
_STEP = Decimal("1")

# cost_max_cents is an exclusive upper bound. None means no ceiling.
# Spirits use a 4x bottle multiple and a 1.0 glass multiple, so the glass is
# four times the pour cost (bottle / 5). Wine, beer, and sake use glass =
# bottle / 5 x 1.2, rounded to the nearest dollar.
DEFAULT_RULES: tuple[tuple[str, int, int | None, str, int, str, int], ...] = (
    ("wine", 0, 1500, "3.5", 5, "1.2", 100),
    ("wine", 1500, 4000, "3.0", 5, "1.2", 100),
    ("wine", 4000, 10000, "2.5", 5, "1.2", 100),
    ("wine", 10000, None, "2.0", 5, "1.2", 100),
    ("beer", 0, None, "3.0", 5, "1.2", 100),
    ("sake", 0, None, "3.0", 5, "1.2", 100),
    ("spirits", 0, None, "4.0", 5, "1.0", 100),
    ("other", 0, None, "3.0", 5, "1.2", 100),
    ("*", 0, None, "3.0", 5, "1.2", 100),
)

SECTION_SHARES: dict[str, int] = {
    "wine": 55,
    "beer": 15,
    "spirits": 15,
    "sake": 15,
}


def normalize_category(value: str | None) -> str:
    text = " ".join(str(value or "").casefold().split())
    if text in {"wine", "wines"}:
        return "wine"
    if text in {"beer", "beers"}:
        return "beer"
    if text in {"spirit", "spirits"}:
        return "spirits"
    if text in {"sake"}:
        return "sake"
    if text == "*":
        return "*"
    return "other"


def section_name(category: str) -> str:
    label = normalize_category(category)
    return {
        "wine": "Wine",
        "beer": "Beer",
        "spirits": "Spirits",
        "sake": "Sake",
        "other": "Other",
    }.get(label, "Other")


def round_cents(amount: Decimal, step: int) -> int:
    """Half-up to the nearest ``step`` cents. A step of 100 is the nearest dollar."""

    width = max(1, int(step))
    units = (amount / Decimal(width)).quantize(_STEP, rounding=ROUND_HALF_UP)
    return int(units) * width


def _rule_dict(row) -> dict:
    return {
        "id": getattr(row, "id", None),
        "category": row.category,
        "cost_min_cents": int(row.cost_min_cents),
        "cost_max_cents": None if row.cost_max_cents is None else int(row.cost_max_cents),
        "bottle_multiple": Decimal(row.bottle_multiple),
        "glass_pours_per_bottle": int(row.glass_pours_per_bottle),
        "glass_multiple": Decimal(row.glass_multiple),
        "round_to_cents": int(row.round_to_cents),
    }


def default_rules() -> list[dict]:
    found = []
    for category, low, high, bottle, pours, glass, step in DEFAULT_RULES:
        found.append(
            {
                "id": None,
                "category": category,
                "cost_min_cents": low,
                "cost_max_cents": high,
                "bottle_multiple": Decimal(bottle),
                "glass_pours_per_bottle": pours,
                "glass_multiple": Decimal(glass),
                "round_to_cents": step,
            }
        )
    return found


def load_rules(session: Session, venue_id: uuid.UUID) -> list[dict]:
    rows = session.scalars(
        select(PricingRule)
        .where(PricingRule.venue_id == venue_id)
        .order_by(PricingRule.category, PricingRule.cost_min_cents, PricingRule.id)
    ).all()
    if not rows:
        return default_rules()
    return [_rule_dict(row) for row in rows]


def ensure_default_rules(session: Session, venue_id: uuid.UUID) -> list[PricingRule]:
    """Insert the house bands when this venue has none. A second call is a no-op."""

    existing = session.scalars(select(PricingRule).where(PricingRule.venue_id == venue_id)).all()
    if existing:
        return list(existing)
    created = []
    for rule in default_rules():
        row = PricingRule(
            venue_id=venue_id,
            category=rule["category"],
            cost_min_cents=rule["cost_min_cents"],
            cost_max_cents=rule["cost_max_cents"],
            bottle_multiple=rule["bottle_multiple"],
            glass_pours_per_bottle=rule["glass_pours_per_bottle"],
            glass_multiple=rule["glass_multiple"],
            round_to_cents=rule["round_to_cents"],
        )
        session.add(row)
        created.append(row)
    session.flush()
    return created


def _covers(rule: dict, cost: int) -> bool:
    if cost < int(rule["cost_min_cents"]):
        return False
    high = rule["cost_max_cents"]
    return high is None or cost < int(high)


def match_rule(cost: int, category: str, rules: list[dict]) -> dict:
    label = normalize_category(category)
    pool = [rule for rule in rules if rule["category"] == label and _covers(rule, cost)]
    if not pool:
        pool = [rule for rule in rules if rule["category"] == "*" and _covers(rule, cost)]
    if not pool:
        pool = [rule for rule in default_rules() if rule["category"] == label and _covers(rule, cost)]
    if not pool:
        pool = [rule for rule in default_rules() if rule["category"] == "*"]
    pool.sort(key=lambda rule: (-int(rule["cost_min_cents"]), str(rule.get("id") or "")))
    return pool[0]


def price_for(cost: int, category: str, rules: list[dict] | None = None) -> dict:
    """Bottle and glass prices for one wholesale cost, in integer cents."""

    wholesale = max(0, int(cost))
    rule = match_rule(wholesale, category, rules if rules is not None else default_rules())
    pours = max(1, int(rule["glass_pours_per_bottle"]))
    step = max(1, int(rule["round_to_cents"]))
    bottle = round_cents(Decimal(wholesale) * Decimal(rule["bottle_multiple"]), step) if wholesale else 0
    glass_raw = (Decimal(bottle) / Decimal(pours)) * Decimal(rule["glass_multiple"])
    glass = round_cents(glass_raw, step) if bottle else 0
    return {
        "bottle_price": bottle,
        "glass_price": glass,
        "category": normalize_category(category),
        "bottle_multiple": Decimal(rule["bottle_multiple"]),
        "glass_multiple": Decimal(rule["glass_multiple"]),
        "glass_pours_per_bottle": pours,
        "round_to_cents": step,
        "rule_id": rule.get("id"),
    }


def economics(cost: int, bottle_price: int, glass_price: int) -> dict:
    """Margin and beverage cost percent from the selling price, computed now."""

    wholesale = max(0, int(cost))
    price = int(bottle_price) if int(bottle_price) > 0 else int(glass_price)
    if price <= 0:
        return {"margin_pct": 0.0, "beverage_cost_pct": 0.0, "selling_price": 0}
    beverage = (Decimal(wholesale) * Decimal(100) / Decimal(price)).quantize(_TENTH, rounding=ROUND_HALF_UP)
    margin = (Decimal(100) - beverage).quantize(_TENTH, rounding=ROUND_HALF_UP)
    return {
        "margin_pct": float(margin),
        "beverage_cost_pct": float(beverage),
        "selling_price": price,
    }


def blended(costs: list[int], prices: list[int]) -> dict:
    """Section margin from the sum of costs and the sum of selling prices."""

    wholesale = sum(int(cost) for cost in costs)
    price = sum(int(amount) for amount in prices)
    return economics(wholesale, price, 0)


def public_rule(rule: dict) -> dict:
    return {
        "id": None if rule.get("id") is None else str(rule["id"]),
        "category": rule["category"],
        "cost_min_cents": int(rule["cost_min_cents"]),
        "cost_max_cents": None if rule["cost_max_cents"] is None else int(rule["cost_max_cents"]),
        "bottle_multiple": float(rule["bottle_multiple"]),
        "glass_pours_per_bottle": int(rule["glass_pours_per_bottle"]),
        "glass_multiple": float(rule["glass_multiple"]),
        "round_to_cents": int(rule["round_to_cents"]),
    }


def validate_rules(raw: list[dict]) -> list[dict]:
    """Check a replacement set. Bands in one category must not overlap."""

    if not raw:
        raise DraftFailed("Add at least one pricing rule.", 422)
    cleaned = []
    for index, row in enumerate(raw):
        category = normalize_category(str(row.get("category") or ""))
        if category not in PRICING_CATEGORIES:
            raise DraftFailed("That pricing category is not recognized.", 422)
        try:
            low = int(row.get("cost_min_cents"))
            high_raw = row.get("cost_max_cents")
            high = None if high_raw is None or high_raw == "" else int(high_raw)
            pours = int(row.get("glass_pours_per_bottle") or 5)
            step = int(row.get("round_to_cents") or 100)
            bottle = Decimal(str(row.get("bottle_multiple")))
            glass = Decimal(str(row.get("glass_multiple") if row.get("glass_multiple") is not None else "1.2"))
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise DraftFailed("A pricing rule has a value that is not a number.", 422) from exc
        if low < 0 or (high is not None and high <= low):
            raise DraftFailed("A cost band must start at zero or above and end above where it starts.", 422)
        if pours < 1 or step < 1 or bottle <= 0 or glass <= 0:
            raise DraftFailed("Multiples, pours, and the rounding step must be greater than zero.", 422)
        cleaned.append(
            {
                "category": category,
                "cost_min_cents": low,
                "cost_max_cents": high,
                "bottle_multiple": bottle.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "glass_pours_per_bottle": pours,
                "glass_multiple": glass.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "round_to_cents": step,
            }
        )
        _ = index
    by_category: dict[str, list[dict]] = {}
    for rule in cleaned:
        by_category.setdefault(rule["category"], []).append(rule)
    for rules in by_category.values():
        rules.sort(key=lambda rule: (rule["cost_min_cents"], rule["cost_max_cents"] or 10**12))
        previous = None
        for rule in rules:
            if previous is not None:
                if previous["cost_max_cents"] is None or rule["cost_min_cents"] < previous["cost_max_cents"]:
                    raise DraftFailed("Cost bands in one category cannot overlap.", 422)
            previous = rule
    return cleaned


def replace_rules(session: Session, venue_id: uuid.UUID, raw: list[dict]) -> list[dict]:
    cleaned = validate_rules(raw)
    session.execute(delete(PricingRule).where(PricingRule.venue_id == venue_id))
    created = []
    for rule in cleaned:
        row = PricingRule(venue_id=venue_id, **rule)
        session.add(row)
        created.append(row)
    session.flush()
    return [_rule_dict(row) for row in created]
