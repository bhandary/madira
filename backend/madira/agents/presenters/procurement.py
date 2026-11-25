"""Tasting surfaces. The draft calendar text comes from the procurement service."""

from __future__ import annotations

from typing import Any

from madira.agents.presenters.ops import surface

TASTING_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "form", "cal"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "form", "component": "ScheduleForm", "draft": {"path": "/draft"}},
    {"id": "cal", "component": "TastingCalendar", "tastings": {"path": "/tastings"}},
]


def tasting_surface(title: str, draft: dict, tastings: list[dict]) -> list[dict[str, Any]]:
    return surface("tasting", TASTING_SCHEMA, {"title": title, "draft": draft, "tastings": tastings})


def with_tasting_list(payload: dict) -> dict:
    tastings = payload["tastings"]
    return {
        "tastings": tastings,
        "a2ui_operations": tasting_surface("Supplier calendar", {}, tastings),
    }


def with_scheduled(payload: dict) -> dict:
    return {
        "draft": payload["draft"],
        "tastings": payload["tastings"],
        "a2ui_operations": tasting_surface("Tasting scheduled (draft)", payload["draft"], payload["tastings"]),
    }


OFFER_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "offers"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "offers", "component": "SupplierOffers", "offers": {"path": "/offers"}, "supplier": {"path": "/supplier"}},
]

HISTORY_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "history"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "history", "component": "PriceHistory", "product": {"path": "/product"}, "points": {"path": "/points"}},
]


def with_offers(payload: dict) -> dict:
    data = {
        "title": payload.get("title") or "Current supplier offers",
        "supplier": payload.get("supplier") or "",
        "product": payload.get("product") or "",
        "offers": payload.get("offers") or [],
    }
    return {**data, "a2ui_operations": surface("supplier-offers", OFFER_SCHEMA, data)}


def with_price_history(payload: dict) -> dict:
    data = {
        "title": payload.get("title") or "Price history",
        "product": payload.get("product") or {},
        "points": payload.get("points") or [],
    }
    return {**data, "a2ui_operations": surface("price-history", HISTORY_SCHEMA, data)}
