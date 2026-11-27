"""Square REST driver. Endpoints and fields follow Square's public reference.

* GET /v2/locations
* GET /v2/catalog/list
* POST /v2/orders/search

No call is made without an access token. Tests pass an ``httpx.Client`` so
nothing here opens a socket.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from madira.domain.pos.adapter import CatalogVariation, PosError, PosLocation, SaleLine

SQUARE_VERSION = os.environ.get("MADIRA_SQUARE_VERSION", "2026-11-18")
_PAGE_CAP = 50


def square_base_url() -> str:
    override = os.environ.get("MADIRA_SQUARE_BASE_URL", "").strip().rstrip("/")
    if override:
        return override
    env = os.environ.get("MADIRA_SQUARE_ENV", "sandbox").strip().lower()
    if env == "production":
        return "https://connect.squareup.com"
    if env == "sandbox":
        return "https://connect.squareupsandbox.com"
    raise PosError("MADIRA_SQUARE_ENV must be sandbox or production.", 422)


def _version() -> str:
    version = os.environ.get("MADIRA_SQUARE_VERSION", SQUARE_VERSION).strip()
    if not version:
        raise PosError("Square-Version is empty.", 422)
    return version


class SquarePosDriver:
    def __init__(self, access_token: str, client: httpx.Client | None = None) -> None:
        token = (access_token or "").strip()
        if not token:
            raise PosError("Square needs an access token.", 422)
        self._token = token
        self._client = client

    def list_locations(self) -> list[PosLocation]:
        body = self._send("GET", "/v2/locations")
        found: list[PosLocation] = []
        for row in body.get("locations") or []:
            if not isinstance(row, dict):
                continue
            if str(row.get("status") or "") != "ACTIVE":
                continue
            location_id = str(row.get("id") or "").strip()
            if not location_id:
                continue
            found.append(PosLocation(location_id, str(row.get("name") or location_id)))
        return found

    def list_variations(self) -> list[CatalogVariation]:
        cursor = ""
        seen: dict[str, CatalogVariation] = {}
        for _ in range(_PAGE_CAP):
            params = {"types": "ITEM,ITEM_VARIATION"}
            if cursor:
                params["cursor"] = cursor
            body = self._send("GET", "/v2/catalog/list", params=params)
            for item in _variations(body.get("objects") or []):
                seen[item.variation_id] = item
            nxt = str(body.get("cursor") or "")
            if not nxt or nxt == cursor:
                return list(seen.values())
            cursor = nxt
        raise PosError("Square catalog pagination did not finish.", 502)

    def search_sales(self, location_id: str, start_at: str, end_at: str) -> list[SaleLine]:
        place = (location_id or "").strip()
        if not place:
            raise PosError("Square needs a location id.", 422)
        cursor = ""
        lines: list[SaleLine] = []
        for _ in range(_PAGE_CAP):
            payload: dict[str, Any] = {
                "location_ids": [place],
                "limit": 100,
                "query": {
                    "filter": {
                        "state_filter": {"states": ["COMPLETED"]},
                        "date_time_filter": {"closed_at": {"start_at": start_at, "end_at": end_at}},
                    },
                    "sort": {"sort_field": "CLOSED_AT", "sort_order": "ASC"},
                },
            }
            if cursor:
                payload["cursor"] = cursor
            body = self._send("POST", "/v2/orders/search", json=payload)
            lines.extend(_lines(body.get("orders") or []))
            nxt = str(body.get("cursor") or "")
            if not nxt or nxt == cursor:
                return lines
            cursor = nxt
        raise PosError("Square order pagination did not finish.", 502)

    def _send(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = square_base_url() + path
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Square-Version": _version(),
            "Content-Type": "application/json",
        }
        own = self._client is None
        client = self._client or httpx.Client(timeout=30.0)
        try:
            response = client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise PosError("Square could not be reached.", 502) from exc
        finally:
            if own:
                client.close()
        if response.status_code >= 400:
            raise PosError(_square_failure(response, self._token), 502)
        try:
            body = response.json()
        except ValueError as exc:
            raise PosError("Square returned a response that was not JSON.", 502) from exc
        if not isinstance(body, dict):
            raise PosError("Square returned a response that was not JSON.", 502)
        return body


def _square_failure(response: httpx.Response, token: str) -> str:
    code = ""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        errors = body.get("errors") or []
        if errors and isinstance(errors[0], dict):
            code = str(errors[0].get("code") or "")
    message = f"Square returned {response.status_code}"
    if code and token not in code:
        message = f"{message} {code}"
    return message + "."


def _variations(objects: list) -> list[CatalogVariation]:
    found: list[CatalogVariation] = []
    for obj in objects:
        if not isinstance(obj, dict) or obj.get("is_deleted"):
            continue
        kind = obj.get("type")
        if kind == "ITEM":
            data = obj.get("item_data") or {}
            item_name = str(data.get("name") or "")
            item_id = str(obj.get("id") or "")
            for child in data.get("variations") or []:
                parsed = _variation(child, item_name, item_id)
                if parsed is not None:
                    found.append(parsed)
        elif kind == "ITEM_VARIATION":
            parsed = _variation(obj, "", "")
            if parsed is not None:
                found.append(parsed)
    return found


def _variation(obj: dict, item_name: str, item_id: str) -> CatalogVariation | None:
    if not isinstance(obj, dict) or obj.get("type") != "ITEM_VARIATION" or obj.get("is_deleted"):
        return None
    data = obj.get("item_variation_data") or {}
    variation_id = str(obj.get("id") or "").strip()
    if not variation_id:
        return None
    parent = str(data.get("item_id") or item_id or "")
    name = item_name or str(data.get("name") or variation_id)
    return CatalogVariation(
        item_id=parent,
        variation_id=variation_id,
        name=name,
        variation_name=str(data.get("name") or ""),
        sku=str(data.get("sku") or ""),
    )


def _lines(orders: list) -> list[SaleLine]:
    found: list[SaleLine] = []
    for order in orders:
        if not isinstance(order, dict):
            continue
        if str(order.get("state") or "") != "COMPLETED":
            continue
        order_id = str(order.get("id") or "").strip()
        closed = str(order.get("closed_at") or "").strip()
        if not order_id or not closed:
            continue
        for line in order.get("line_items") or []:
            if not isinstance(line, dict):
                continue
            uid = str(line.get("uid") or "").strip()
            if not uid:
                continue
            found.append(
                SaleLine(
                    order_id=order_id,
                    line_uid=uid,
                    item_id="",
                    variation_id=str(line.get("catalog_object_id") or ""),
                    name=str(line.get("name") or ""),
                    quantity=str(line.get("quantity") or "0"),
                    closed_at=closed,
                )
            )
    return found
