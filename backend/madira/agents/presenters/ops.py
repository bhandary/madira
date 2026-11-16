"""A2UI v0.9 helpers. Prefer CopilotKit's a2ui module; fall back to local builders."""

from __future__ import annotations

import json
from typing import Any

from madira.config import CATALOG_ID

try:
    from copilotkit import a2ui as _ck_a2ui
except Exception:  # pragma: no cover - optional at import time
    _ck_a2ui = None


def create_surface(surface_id: str, catalog_id: str = CATALOG_ID) -> dict[str, Any]:
    if _ck_a2ui is not None:
        return _ck_a2ui.create_surface(surface_id, catalog_id=catalog_id)
    return {
        "version": "v0.9",
        "createSurface": {"surfaceId": surface_id, "catalogId": catalog_id},
    }


def update_components(surface_id: str, components: list[dict[str, Any]]) -> dict[str, Any]:
    if _ck_a2ui is not None:
        return _ck_a2ui.update_components(surface_id, components)
    return {
        "version": "v0.9",
        "updateComponents": {"surfaceId": surface_id, "components": components},
    }


def update_data_model(surface_id: str, data: Any, path: str = "/") -> dict[str, Any]:
    if _ck_a2ui is not None:
        return _ck_a2ui.update_data_model(surface_id, data, path=path)
    return {
        "version": "v0.9",
        "updateDataModel": {"surfaceId": surface_id, "path": path, "value": data},
    }


def render(operations: list[dict[str, Any]]) -> str:
    if _ck_a2ui is not None:
        return _ck_a2ui.render(operations=operations)
    return json.dumps({"a2ui_operations": operations})


def parse_operations(payload: str | dict | list | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "a2ui_operations" in payload:
            return list(payload["a2ui_operations"])
        if any(k in payload for k in ("createSurface", "updateComponents", "updateDataModel")):
            return [payload]
        return []
    if isinstance(payload, str):
        try:
            return parse_operations(json.loads(payload))
        except json.JSONDecodeError:
            return []
    return []


def surface(surface_id: str, components: list[dict[str, Any]], data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        create_surface(surface_id),
        update_components(surface_id, components),
        update_data_model(surface_id, data),
    ]
