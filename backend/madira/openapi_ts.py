"""Generate TypeScript types from the FastAPI OpenAPI schema.

The live handlers are unchanged. Response models are published into
``app.openapi()`` by ``madira.response_schema`` and this module turns that
document into one TypeScript file.

Regenerate with ``make types``.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

METHODS = ("get", "post", "put", "patch", "delete")
HEADER = """\
/**
 * Generated from the FastAPI OpenAPI schema (`app.openapi()`). Do not edit.
 * Regenerate with `make types`.
 */
"""


def generate_typescript(spec: dict[str, Any]) -> str:
    """Render ``spec`` as a deterministic TypeScript module."""

    spec = _stable_spec(spec)
    schemas: dict[str, Any] = spec.get("components", {}).get("schemas", {})
    chunks = [HEADER.rstrip(), ""]
    for name in sorted(schemas):
        chunks.append(_export(name, schemas[name]))
        chunks.append("")
    aliases = []
    for path in sorted(spec.get("paths", {})):
        operations = spec["paths"][path]
        for method in sorted(key for key in operations if key in METHODS):
            operation = operations[method]
            schema = success_schema(operation)
            if schema is None:
                continue
            alias = response_type_name(operation["operationId"])
            aliases.append(f"export type {alias} = {_render(schema)};")
    chunks.extend(aliases)
    text = "\n".join(chunks).rstrip() + "\n"
    return text


def success_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    """JSON schema for the lowest 2xx response, when the operation declares one."""

    responses = operation.get("responses") or {}
    codes = sorted(code for code in responses if str(code).startswith("2"))
    if not codes:
        return None
    content = (responses[codes[0]].get("content") or {})
    body = content.get("application/json")
    if not isinstance(body, dict):
        return None
    schema = body.get("schema")
    if not isinstance(schema, dict):
        return None
    return schema


def response_type_name(operation_id: str) -> str:
    return _pascal(operation_id) + "Response"


def _stable_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Drop startup-mounted AG-UI routes so generation does not depend on them.

    ``POST /ag-ui`` and ``GET /ag-ui/health`` are registered when the process
    starts, not at import. Schemas that only those routes reference are dropped
    with them.
    """

    from madira.response_models import STARTUP_AGUI_PATHS

    paths = {
        path: operations
        for path, operations in spec.get("paths", {}).items()
        if path not in STARTUP_AGUI_PATHS
    }
    schemas = dict(spec.get("components", {}).get("schemas", {}))
    reachable = _reachable_schemas({"paths": paths, "components": {"schemas": schemas}})
    kept = {name: schemas[name] for name in schemas if name in reachable}
    return {
        "paths": paths,
        "components": {"schemas": kept},
    }


def _reachable_schemas(spec: dict[str, Any]) -> set[str]:
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[-1]
                if name not in found:
                    found.add(name)
                    walk(spec.get("components", {}).get("schemas", {}).get(name, {}))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(spec.get("paths", {}))
    return found


def write_types(path: Path) -> str:
    from madira.main import app

    text = generate_typescript(app.openapi())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return text


def _export(name: str, schema: dict[str, Any]) -> str:
    ident = _ident(name)
    rendered = _render(schema)
    if rendered.startswith("{"):
        return f"export type {ident} = {rendered};"
    return f"export type {ident} = {rendered};"


def _render(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return _ident(schema["$ref"].rsplit("/", 1)[-1])
    if "allOf" in schema:
        parts = [_render(part) for part in schema["allOf"]]
        parts = [part for part in parts if part != "unknown"]
        if not parts:
            return "unknown"
        if len(parts) == 1:
            return parts[0]
        return " & ".join(f"({part})" if " | " in part or "&" in part else part for part in parts)
    union = schema.get("anyOf") or schema.get("oneOf")
    if union:
        return _union(union)
    if "enum" in schema:
        return _union_literals(schema["enum"])
    if "const" in schema:
        return _literal(schema["const"])
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return _union([{"type": item} if item != "null" else {"type": "null"} for item in schema_type])
    if schema_type == "array":
        return _array(_render(schema.get("items") or {}))
    if schema_type == "object" or "properties" in schema or "additionalProperties" in schema:
        return _object(schema)
    if schema_type == "string":
        return "string"
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    return "unknown"


def _object(schema: dict[str, Any]) -> str:
    properties: dict[str, Any] = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    additional = schema.get("additionalProperties", None)
    if not properties:
        if additional is True:
            return "Record<string, unknown>"
        if isinstance(additional, dict):
            return f"Record<string, {_render(additional)}>"
        if schema.get("type") == "object" and not additional:
            return "Record<string, unknown>"
        return "unknown"
    lines = ["{"]
    for key, prop in properties.items():
        optional = key not in required
        lines.append(f"  {_prop(key)}{':' if not optional else '?:'} {_render(prop)};")
    lines.append("}")
    body = "\n".join(lines)
    if additional is True:
        return f"({body} & Record<string, unknown>)"
    if isinstance(additional, dict):
        return f"({body} & Record<string, {_render(additional)}>)"
    return body


def _array(item: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item):
        return f"{item}[]"
    return f"Array<{item}>"


def _union(options: list[dict[str, Any]]) -> str:
    rendered = []
    seen = set()
    for option in options:
        part = _render(option)
        if part in seen:
            continue
        seen.add(part)
        rendered.append(part)
    if not rendered:
        return "unknown"
    if len(rendered) == 1:
        return rendered[0]
    return " | ".join(rendered)


def _union_literals(values: list[Any]) -> str:
    return " | ".join(_literal(value) for value in values)


def _literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return str(value)
    return "unknown"


def _prop(key: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return key
    return json.dumps(key, ensure_ascii=False)


def _pascal(value: str) -> str:
    parts = [part for part in re.split(r"[^0-9A-Za-z]+", value) if part]
    name = "".join(part[:1].upper() + part[1:] for part in parts)
    if not name or name[0].isdigit():
        name = "Type" + name
    return name


def _ident(name: str) -> str:
    ident = re.sub(r"[^0-9A-Za-z_]", "_", name)
    if not ident or ident[0].isdigit():
        ident = "Type" + ident
    return ident


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate frontend/src/lib/api-types.gen.ts")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    write_types(args.out)


if __name__ == "__main__":
    main()
