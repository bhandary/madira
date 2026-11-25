"""Tasting, offer, and price-history surfaces. Calendar text is built for download only."""

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
        "sessions": payload.get("sessions", tastings),
        "tastings": tastings,
        "a2ui_operations": tasting_surface("Supplier calendar", {}, tastings),
    }


def with_scheduled(payload: dict) -> dict:
    tastings = payload["tastings"]
    return {
        "draft": payload["draft"],
        "sessions": payload.get("sessions", tastings),
        "tastings": tastings,
        "a2ui_operations": tasting_surface("Tasting scheduled (draft)", payload["draft"], tastings),
    }


SAMPLE_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "card"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "card", "component": "SampleCard", "sample": {"path": "/sample"}},
]

SESSION_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "form"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "form", "component": "ScheduleForm", "draft": {"path": "/session"}},
]


def with_session(payload: dict) -> dict:
    tasting = payload["session"]
    samples = payload.get("samples") or []
    operations = surface("tasting-session", SESSION_SCHEMA, {"title": tasting.get("title") or "Tasting", "session": tasting})
    for sample in samples:
        label = sample.get("product_name") or "Unmatched sample"
        operations.extend(
            surface(
                f"sample-{sample['id']}",
                SAMPLE_SCHEMA,
                {"title": label, "sample": sample},
            )
        )
    return {**payload, "a2ui_operations": operations}


def with_sample(payload: dict) -> dict:
    sample = payload["sample"]
    label = sample.get("product_name") or "Unmatched sample"
    return {
        **payload,
        "a2ui_operations": surface("sample-card", SAMPLE_SCHEMA, {"title": label, "sample": sample}),
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
