"""Menu and pairing surfaces. Numbers in the data model come from the menu service."""

from __future__ import annotations

from typing import Any

from madira.agents.presenters.ops import surface

PAIRING_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "grid"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "grid", "component": "PairingGrid", "dishes": {"path": "/dishes"}},
]

DISH_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "dishes"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "dishes", "component": "DishList", "dishes": {"path": "/dishes"}},
]


def dishes_surface(title: str, dishes: list[dict], cuisine: str, price_tier: str) -> list[dict[str, Any]]:
    return surface(
        "dishes",
        DISH_SCHEMA,
        {"title": title, "dishes": dishes, "cuisine": cuisine, "price_tier": price_tier},
    )


def pairings_surface(title: str, dishes: list[dict]) -> list[dict[str, Any]]:
    return surface("pairings", PAIRING_SCHEMA, {"title": title, "dishes": dishes})


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
    body = {"menu_id": payload["menu_id"], "dishes": payload["dishes"]}
    body["a2ui_operations"] = pairings_surface(f"Pairings · {payload['menu_name']}", payload["dishes"])
    return body
