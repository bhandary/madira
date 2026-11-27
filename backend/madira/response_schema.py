"""Publish response models into the OpenAPI document.

Handlers keep returning the dicts they build today. Nothing in this module
validates or rewrites a response body. ``make types`` reads the document
``app.openapi()`` returns after this step.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from madira.response_models import RESPONSE_MODELS, STARTUP_AGUI_PATHS, UNMODELED_ROUTES

_METHODS = {"get", "post", "put", "patch", "delete"}


def install_response_models(app: FastAPI) -> None:
    original = app.openapi

    def openapi() -> dict[str, Any]:
        schema = original()
        _apply(schema)
        return schema

    app.openapi = openapi


def _apply(schema: dict[str, Any]) -> None:
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    published: set[str] = set()
    for (method, path), model in RESPONSE_MODELS.items():
        _publish(model, components, published)
        operation = schema.get("paths", {}).get(path, {}).get(method)
        if not isinstance(operation, dict):
            raise RuntimeError(f"No OpenAPI operation for {method.upper()} {path}")
        _point_at_model(operation, model.__name__)
    missing = []
    for path, operations in schema.get("paths", {}).items():
        for method, operation in operations.items():
            if method not in _METHODS:
                continue
            if path in STARTUP_AGUI_PATHS or (method, path) in UNMODELED_ROUTES:
                continue
            if (method, path) not in RESPONSE_MODELS:
                missing.append(f"{method.upper()} {path}")
    if missing:
        raise RuntimeError("JSON routes without a response model:\n" + "\n".join(missing))


def _publish(model: type[BaseModel], components: dict[str, Any], published: set[str]) -> None:
    name = model.__name__
    if name in published:
        return
    body = model.model_json_schema(ref_template="#/components/schemas/{model}")
    defs = body.pop("$defs", {})
    for def_name, def_schema in defs.items():
        components[def_name] = def_schema
        published.add(def_name)
    components[name] = body
    published.add(name)


def _point_at_model(operation: dict[str, Any], name: str) -> None:
    responses = operation.setdefault("responses", {})
    codes = sorted(code for code in responses if str(code).startswith("2"))
    if not codes:
        raise RuntimeError(f"{operation.get('operationId')} has no 2xx response")
    success = responses[codes[0]]
    content = success.setdefault("content", {})
    json_body = content.setdefault("application/json", {})
    json_body["schema"] = {"$ref": f"#/components/schemas/{name}"}
