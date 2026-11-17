"""Identity keys for a product and a variant.

The same drink is one product inside an organization when category, producer,
name, region, country, style, and grape agree after whitespace and case are
folded. Vintage and bottle size pick the variant.
"""

from __future__ import annotations


def clean(value: str | None) -> str:
    return " ".join(str(value or "").split())


def norm(value: str | None) -> str:
    return clean(value).casefold()


def product_key(
    *,
    category: str | None,
    producer: str | None,
    name: str | None,
    region: str | None,
    country: str | None,
    style: str | None,
    grape: str | None,
) -> tuple[str, ...]:
    return tuple(norm(value) for value in (category, producer, name, region, country, style, grape))


def variant_key(*, vintage: str | None, bottle_size: str | None) -> tuple[str, str]:
    return (norm(vintage), norm(bottle_size))
