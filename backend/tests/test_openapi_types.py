"""The OpenAPI TypeScript generator stays deterministic and names every route."""

from __future__ import annotations

from pathlib import Path

from madira.main import app
from madira.openapi_ts import generate_typescript, response_type_name, success_schema
from madira.response_models import STARTUP_AGUI_PATHS, UNMODELED_ROUTES

_METHODS = {"get", "post", "put", "patch", "delete"}
_GENERATED = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "api-types.gen.ts"


def test_generator_is_deterministic_and_covers_every_route():
    spec = app.openapi()
    first = generate_typescript(spec)
    second = generate_typescript(app.openapi())
    assert first == second
    assert _GENERATED.read_text() == first

    for path, operations in spec["paths"].items():
        if path in STARTUP_AGUI_PATHS:
            continue
        for method, operation in operations.items():
            if method not in _METHODS:
                continue
            schema = success_schema(operation)
            assert schema is not None, f"{method.upper()} {path} has no JSON success schema"
            alias = response_type_name(operation["operationId"])
            assert f"export type {alias} = " in first
            if (method, path) in UNMODELED_ROUTES:
                continue
            ref = schema.get("$ref", "")
            assert ref.startswith("#/components/schemas/"), f"{method.upper()} {path} is not a named model"
            name = ref.rsplit("/", 1)[-1]
            body = spec["components"]["schemas"][name]
            assert body.get("type") == "object"
            assert body.get("additionalProperties") is not True or body.get("properties")
