"""Find or create catalog rows, and read them for the current venue.

Products belong to the organization. SKUs belong to one venue. A second call
with the same identity returns the row that is already there.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from madira.domain.catalog.identity import clean, norm, product_key, variant_key
from madira.domain.errors import NotFound
from madira.domain.session import session_scope
from madira.models import Product, ProductVariant, Sku, Venue
from madira.money import DEFAULT_CURRENCY


def _code(value: str | None) -> str:
    return clean(value).upper()


def _families(value) -> list:
    if isinstance(value, list):
        return list(value)
    return []


def _organization_id(session: Session, venue_id: uuid.UUID) -> uuid.UUID:
    venue = session.get(Venue, venue_id)
    if venue is None:
        raise NotFound("venue not found")
    return venue.organization_id


def _find_product(session: Session, organization_id: uuid.UUID, key: tuple[str, ...]) -> Product | None:
    rows = session.scalars(select(Product).where(Product.organization_id == organization_id)).all()
    for row in rows:
        if (
            product_key(
                category=row.category,
                producer=row.producer,
                name=row.name,
                region=row.region,
                country=row.country,
                style=row.style,
                grape=row.grape,
            )
            == key
        ):
            return row
    return None


def _find_variant(session: Session, product_id: uuid.UUID, key: tuple[str, str]) -> ProductVariant | None:
    rows = session.scalars(select(ProductVariant).where(ProductVariant.product_id == product_id)).all()
    for row in rows:
        if variant_key(vintage=row.vintage, bottle_size=row.bottle_size) == key:
            return row
    return None


def ensure_sku(
    session: Session,
    venue_id: uuid.UUID,
    *,
    category: str = "",
    producer: str = "",
    name: str,
    region: str = "",
    country: str = "",
    style: str = "",
    grape: str = "",
    vintage: str = "",
    bottle_size: str = "",
    body: str = "",
    acidity: str = "",
    tannin: str = "",
    sweetness: str = "",
    oak: str = "",
    intensity: str = "",
    aroma_families: list | None = None,
    barcode: str | None = None,
    bin_label: str | None = None,
    par: int | None = None,
    cost: int | None = None,
    currency: str | None = None,
) -> Sku:
    """Return the venue's SKU for this drink, creating the catalog rows if needed."""

    organization_id = _organization_id(session, venue_id)
    key = product_key(
        category=category,
        producer=producer,
        name=name,
        region=region,
        country=country,
        style=style,
        grape=grape,
    )
    product = _find_product(session, organization_id, key)
    if product is None:
        product = Product(
            organization_id=organization_id,
            category=clean(category),
            producer=clean(producer),
            name=clean(name),
            region=clean(region),
            country=clean(country),
            style=clean(style),
            grape=clean(grape),
            body=clean(body),
            acidity=clean(acidity),
            tannin=clean(tannin),
            sweetness=clean(sweetness),
            oak=clean(oak),
            intensity=clean(intensity),
            aroma_families=_families(aroma_families),
        )
        session.add(product)
        session.flush()

    vkey = variant_key(vintage=vintage, bottle_size=bottle_size)
    variant = _find_variant(session, product.id, vkey)
    if variant is None:
        variant = ProductVariant(
            product_id=product.id,
            vintage=clean(vintage),
            bottle_size=clean(bottle_size),
        )
        session.add(variant)
        session.flush()

    sku = session.scalar(
        select(Sku).where(Sku.venue_id == venue_id, Sku.product_variant_id == variant.id)
    )
    if sku is None:
        sku = Sku(
            venue_id=venue_id,
            product_variant_id=variant.id,
            barcode=_code(barcode) if barcode else "",
            bin_label=clean(bin_label) if bin_label else "",
            par=0 if par is None else int(par),
            cost=0 if cost is None else int(cost),
            currency=currency or DEFAULT_CURRENCY,
        )
        session.add(sku)
        session.flush()
        _mark_embed(session, venue_id, organization_id, sku.id)
        return sku

    incoming = _code(barcode) if barcode else ""
    if incoming and not sku.barcode:
        sku.barcode = incoming
    if bin_label and not sku.bin_label:
        sku.bin_label = clean(bin_label)
    if par is not None:
        sku.par = int(par)
    if cost is not None:
        sku.cost = int(cost)
    if currency:
        sku.currency = currency
    session.flush()
    _mark_embed(session, venue_id, organization_id, sku.id)
    return sku


def _mark_embed(session: Session, venue_id: uuid.UUID, organization_id: uuid.UUID, sku_id: uuid.UUID) -> None:
    from madira.domain.embeddings.schedule import mark

    mark(session, venue_id, organization_id, "sku", sku_id)


def beverage_fields(sku: Sku) -> dict[str, str]:
    """Product text the menu, list, and cellar surfaces already show."""

    product = sku.variant.product
    return {
        "category": product.category,
        "producer": product.producer,
        "name": product.name,
        "region": product.region,
        "style": product.style,
        "vintage": sku.variant.vintage,
    }


def _product_dict(product: Product, variants: list[dict]) -> dict:
    return {
        "id": product.id,
        "category": product.category,
        "producer": product.producer,
        "name": product.name,
        "region": product.region,
        "country": product.country,
        "style": product.style,
        "grape": product.grape,
        "body": product.body,
        "acidity": product.acidity,
        "tannin": product.tannin,
        "sweetness": product.sweetness,
        "oak": product.oak,
        "intensity": product.intensity,
        "aroma_families": _families(product.aroma_families),
        "variants": variants,
    }


def _variant_dict(variant: ProductVariant, sku_id: uuid.UUID) -> dict:
    return {
        "id": variant.id,
        "vintage": variant.vintage,
        "bottle_size": variant.bottle_size,
        "sku_id": sku_id,
    }


def _sku_dict(sku: Sku) -> dict:
    product = sku.variant.product
    variant = sku.variant
    return {
        "id": sku.id,
        "product_id": product.id,
        "variant_id": variant.id,
        "barcode": sku.barcode,
        "bin_label": sku.bin_label,
        "par": sku.par,
        "cost": sku.cost,
        "currency": sku.currency,
        "vintage": variant.vintage,
        "bottle_size": variant.bottle_size,
        "category": product.category,
        "producer": product.producer,
        "name": product.name,
        "region": product.region,
        "country": product.country,
        "style": product.style,
        "grape": product.grape,
        "body": product.body,
        "acidity": product.acidity,
        "tannin": product.tannin,
        "sweetness": product.sweetness,
        "oak": product.oak,
        "intensity": product.intensity,
        "aroma_families": _families(product.aroma_families),
    }


def _skus_for_venue(session: Session, venue_id: uuid.UUID) -> list[Sku]:
    return list(
        session.scalars(
            select(Sku)
            .where(Sku.venue_id == venue_id)
            .order_by(func.upper(Sku.barcode), Sku.id)
        ).all()
    )


def list_products(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        grouped: dict[uuid.UUID, tuple[Product, list[dict]]] = {}
        for sku in _skus_for_venue(session, venue_id):
            product = sku.variant.product
            variants = grouped.setdefault(product.id, (product, []))[1]
            variants.append(_variant_dict(sku.variant, sku.id))
        products = [
            _product_dict(product, variants)
            for product, variants in sorted(grouped.values(), key=lambda item: (norm(item[0].name), str(item[0].id)))
        ]
        for product in products:
            product["variants"].sort(key=lambda row: (norm(row["vintage"]), norm(row["bottle_size"]), str(row["id"])))
        return {"products": products}


def get_product(venue_id: uuid.UUID, product_id: uuid.UUID) -> dict:
    with session_scope() as session:
        product = session.get(Product, product_id)
        organization_id = _organization_id(session, venue_id)
        if product is None or product.organization_id != organization_id:
            raise NotFound("product not found")
        variants = [
            _variant_dict(sku.variant, sku.id)
            for sku in _skus_for_venue(session, venue_id)
            if sku.variant.product_id == product.id
        ]
        if not variants:
            raise NotFound("product not found")
        variants.sort(key=lambda row: (norm(row["vintage"]), norm(row["bottle_size"]), str(row["id"])))
        return _product_dict(product, variants)


def list_skus(venue_id: uuid.UUID) -> dict:
    with session_scope() as session:
        return {"skus": [_sku_dict(sku) for sku in _skus_for_venue(session, venue_id)]}


def get_sku(venue_id: uuid.UUID, sku_id: uuid.UUID) -> dict:
    with session_scope() as session:
        sku = session.get(Sku, sku_id)
        if sku is None or sku.venue_id != venue_id:
            raise NotFound("sku not found")
        return _sku_dict(sku)
