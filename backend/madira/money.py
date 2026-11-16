"""Money as integer minor units.

A price of $2.40 is 240. Arithmetic stays on those integers. Callers that show
a figure convert at the edge with ``format_whole`` (notes) or the frontend
currency formatter (tables).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

DEFAULT_CURRENCY = "USD"
_MINOR = 100
_CENT = Decimal("1")
_CENTI = Decimal("0.01")
_TENTH = Decimal("0.1")
_DOLLAR = Decimal("1")


def to_minor(amount: int | float | str | Decimal) -> int:
    """Round a major-unit amount to minor units, half away from zero."""

    if isinstance(amount, bool) or amount is None:
        raise TypeError("amount must be a number")
    if isinstance(amount, Decimal):
        dec = amount
    elif isinstance(amount, int):
        dec = Decimal(amount)
    else:
        dec = Decimal(str(amount).strip())
    return int((dec * _MINOR).quantize(_CENT, rounding=ROUND_HALF_UP))


def to_major(minor: int) -> float:
    """Minor units back to a major-unit float (downgrades and spot checks)."""

    return float(Decimal(int(minor)) / Decimal(_MINOR))


def format_whole(minor: int) -> str:
    """Whole dollars with grouping, half up. ``519760`` → ``5,198``."""

    whole = (Decimal(int(minor)) / Decimal(_MINOR)).quantize(_DOLLAR, rounding=ROUND_HALF_UP)
    return f"{int(whole):,}"


def _div_half_up(numer: int, denom: int) -> int:
    negative = (numer < 0) ^ (denom < 0)
    numer, denom = abs(int(numer)), abs(int(denom))
    if denom == 0:
        raise ZeroDivisionError
    quotient, remainder = divmod(numer, denom)
    if remainder * 2 >= denom:
        quotient += 1
    return -quotient if negative else quotient


def _multiple(numerator: int, denominator: int) -> Decimal:
    """``numerator / denominator`` rounded half-up to two decimal places."""

    if denominator <= 0:
        hundredths = 1
    else:
        hundredths = _div_half_up(numerator * _MINOR, denominator)
        if hundredths <= 0:
            hundredths = 1
    return (Decimal(hundredths) / Decimal(_MINOR)).quantize(_CENTI)


def pour_multiple(pour_minor: int, cost_minor: int) -> Decimal:
    """Glass multiple. A 750ml bottle is about five pours; both amounts are minor units."""

    if cost_minor < 5:
        return _multiple(pour_minor, 1)
    return _multiple(5 * pour_minor, cost_minor)


def bottle_multiple(bottle_minor: int, cost_minor: int) -> Decimal:
    return _multiple(bottle_minor, cost_minor)


def margin_percent(multiple: Decimal) -> Decimal:
    """``(1 - 1/multiple) * 100``, one decimal place, half up."""

    if multiple <= 0:
        return Decimal("0.0")
    return ((1 - (Decimal(1) / multiple)) * 100).quantize(_TENTH, rounding=ROUND_HALF_UP)


def within_buying_room(spent: int, line: int, budget: int) -> bool:
    """False when this line would push a list that is already past 60% over 102% of budget.

    Compared in integers: ``(spent + line) / budget > 1.02`` and ``spent / budget > 0.6``.
    """

    over = (spent + line) * 100 > budget * 102
    started = spent * 100 > budget * 60
    return not (over and started)
