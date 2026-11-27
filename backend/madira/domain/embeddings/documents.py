"""Text that goes into a catalog embedding. The name is repeated so a search for it ranks higher."""

from __future__ import annotations

def _bits(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def sku_document(sku, notes: list) -> str:
    product = sku.variant.product
    variant = sku.variant
    name = product.name or ""
    families = " ".join(str(item) for item in (product.aroma_families or []))
    note_text = " ".join(
        _bits(note.server_hook, note.guest_description, note.technical_note)
        for note in notes
    )
    body = _bits(
        name,
        name,
        name,
        product.producer,
        product.region,
        product.country,
        product.category,
        product.style,
        product.grape,
        variant.vintage,
        sku.barcode,
        product.body,
        product.acidity,
        product.tannin,
        product.sweetness,
        product.oak,
        product.intensity,
        families,
        note_text,
    )
    return body


def note_document(product, note) -> str:
    return _bits(
        product.name,
        product.name,
        product.producer,
        product.region,
        product.style,
        product.grape,
        note.server_hook,
        note.guest_description,
        note.technical_note,
    )


def dish_document(dish) -> str:
    return _bits(
        dish.name,
        dish.flavor_profile,
        dish.description,
        dish.main_component,
        dish.cooking_method,
        dish.sauce,
        f"richness {int(dish.richness or 0)}",
        f"acidity {int(dish.acidity or 0)}",
        f"sweetness {int(dish.sweetness or 0)}",
        f"spice {int(dish.spice or 0)}",
        f"umami {int(dish.umami or 0)}",
    )

