from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from madira.agents.presenters.catalog import present_product, present_products, present_sku, present_skus
from madira.domain.catalog.service import get_product, get_sku, list_products, list_skus
from madira.domain.errors import NotFound
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter()


@router.get("/products", dependencies=[require(Capability.FLOOR)])
def products() -> dict[str, Any]:
    return present_products(list_products(active_venue_id()))


@router.get("/products/{product_id}", dependencies=[require(Capability.FLOOR)])
def product(product_id: uuid.UUID) -> dict[str, Any]:
    try:
        return present_product(get_product(active_venue_id(), product_id))
    except NotFound as exc:
        raise HTTPException(404, exc.message) from exc


@router.get("/skus", dependencies=[require(Capability.RECORDS)])
def skus() -> dict[str, Any]:
    return present_skus(list_skus(active_venue_id()))


@router.get("/skus/{sku_id}", dependencies=[require(Capability.RECORDS)])
def sku(sku_id: uuid.UUID) -> dict[str, Any]:
    try:
        return present_sku(get_sku(active_venue_id(), sku_id))
    except NotFound as exc:
        raise HTTPException(404, exc.message) from exc
