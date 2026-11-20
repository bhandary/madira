"""Menu and pairing surfaces. Numbers in the data model come from the menu service."""

from __future__ import annotations

from typing import Any

from madira.agents.presenters.ops import surface

PAIRING_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "grid"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "grid", "component": "PairingGrid", "menu_id": {"path": "/menu_id"}, "dishes": {"path": "/dishes"}},
]

DISH_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "dishes"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "dishes", "component": "DishList", "dishes": {"path": "/dishes"}},
]

REVIEW_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "review"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "review", "component": "DishReview", "review": {"path": "/review"}},
]

_REVIEW_FIELDS = (
    "menu_id",
    "version_id",
    "name",
    "number",
    "status",
    "cuisine",
    "price_tier",
    "dishes",
)

_DISH_FIELDS = (
    "id",
    "stable_id",
    "name",
    "course",
    "price",
    "currency",
    "main_component",
    "cooking_method",
    "sauce",
    "richness",
    "acidity",
    "sweetness",
    "spice",
    "umami",
    "allergens",
    "confidence",
    "low_confidence",
    "needs_repairing",
)


def dishes_surface(title: str, dishes: list[dict], cuisine: str, price_tier: str) -> list[dict[str, Any]]:
    return surface(
        "dishes",
        DISH_SCHEMA,
        {"title": title, "dishes": dishes, "cuisine": cuisine, "price_tier": price_tier},
    )


def pairings_surface(title: str, menu_id: str, dishes: list[dict]) -> list[dict[str, Any]]:
    return surface("pairings", PAIRING_SCHEMA, {"title": title, "menu_id": str(menu_id), "dishes": dishes})


def present_review(payload: dict) -> dict:
    dishes = []
    for row in payload["dishes"]:
        dishes.append({field: row[field] for field in _DISH_FIELDS})
    review = {field: payload[field] for field in _REVIEW_FIELDS if field != "dishes"}
    review["dishes"] = dishes
    return review


def review_surface(review: dict) -> list[dict[str, Any]]:
    return surface(
        "menu-review",
        REVIEW_SCHEMA,
        {"title": f"Review · {review['name']}", "review": review},
    )


def with_review(payload: dict) -> dict:
    review = present_review(payload)
    body = {
        "menu_id": review["menu_id"],
        "version_id": review["version_id"],
        "name": review["name"],
        "status": review["status"],
        "review": review,
    }
    body["a2ui_operations"] = review_surface(review)
    return body


def with_dishes(payload: dict) -> dict:
    body = {
        "menu_id": payload["menu_id"],
        "name": payload["name"],
        "cuisine": payload["cuisine"],
        "price_tier": payload["price_tier"],
        "dishes": payload["dishes"],
    }
    body["a2ui_operations"] = dishes_surface(
        f"Parsed · {payload['name']}",
        payload["dishes"],
        payload["cuisine"],
        payload["price_tier"],
    )
    return body


def with_pairings(payload: dict) -> dict:
    body = {
        "menu_id": payload["menu_id"],
        "menu_name": payload.get("menu_name", ""),
        "dishes": payload["dishes"],
    }
    body["a2ui_operations"] = pairings_surface(
        f"Pairings · {payload.get('menu_name', '')}",
        str(payload["menu_id"]),
        payload["dishes"],
    )
    return body
