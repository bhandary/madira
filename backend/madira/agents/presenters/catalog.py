"""Catalog read shapes for the current venue.

Menu, list, and cellar surfaces keep the field names they already render.
This presenter is the read API for the catalog itself.
"""

from __future__ import annotations

_PRODUCT_FIELDS = (
    "id",
    "category",
    "producer",
    "name",
    "region",
    "country",
    "style",
    "grape",
    "body",
    "acidity",
    "tannin",
    "sweetness",
    "oak",
    "intensity",
    "aroma_families",
)

_VARIANT_FIELDS = ("id", "vintage", "bottle_size", "sku_id")

_SKU_FIELDS = (
    "id",
    "product_id",
    "variant_id",
    "barcode",
    "bin_label",
    "par",
    "cost",
    "currency",
    "vintage",
    "bottle_size",
    "category",
    "producer",
    "name",
    "region",
    "country",
    "style",
    "grape",
    "body",
    "acidity",
    "tannin",
    "sweetness",
    "oak",
    "intensity",
    "aroma_families",
)


def present_product(product: dict) -> dict:
    body = {field: product[field] for field in _PRODUCT_FIELDS}
    body["variants"] = [{field: variant[field] for field in _VARIANT_FIELDS} for variant in product["variants"]]
    return body


def present_products(payload: dict) -> dict:
    return {"products": [present_product(product) for product in payload["products"]]}


def present_sku(sku: dict) -> dict:
    return {field: sku[field] for field in _SKU_FIELDS}


def present_skus(payload: dict) -> dict:
    return {"skus": [present_sku(sku) for sku in payload["skus"]]}
