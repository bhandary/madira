"""SquarePosDriver against recorded Square response shapes. No network."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from madira.domain.pos.adapter import PosError
from madira.domain.pos.square import SquarePosDriver, square_base_url

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "square"
TOKEN = "sq0atp-recorded-fixture-token"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_square_pages_catalog_and_orders_and_sends_the_version_header(monkeypatch):
    monkeypatch.setenv("MADIRA_SQUARE_ENV", "sandbox")
    monkeypatch.delenv("MADIRA_SQUARE_BASE_URL", raising=False)
    monkeypatch.setenv("MADIRA_SQUARE_VERSION", "2026-11-18")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path == "/v2/locations":
            return httpx.Response(200, json=_load("locations.json"))
        if path == "/v2/catalog/list":
            cursor = request.url.params.get("cursor")
            name = "catalog_page_2.json" if cursor == "catalog-page-2" else "catalog_page_1.json"
            return httpx.Response(200, json=_load(name))
        if path == "/v2/orders/search":
            body = json.loads(request.content.decode())
            name = "orders_page_2.json" if body.get("cursor") == "orders-page-2" else "orders_page_1.json"
            return httpx.Response(200, json=_load(name))
        return httpx.Response(404, json={"errors": [{"code": "NOT_FOUND"}]})

    driver = SquarePosDriver(TOKEN, client=_client(handler))
    locations = driver.list_locations()
    assert [row.location_id for row in locations] == ["L8H2K0DEMO01"]
    assert locations[0].name == "Maison bar"

    variations = {row.variation_id: row for row in driver.list_variations()}
    assert variations["VAR_MUSCADET"].name == "Muscadet Domaine de l'Ecu"
    assert variations["VAR_MUSCADET"].sku == "W-MUS-01"
    assert variations["VAR_GLASS"].item_id == "ITEM_UNKNOWN"
    assert variations["VAR_GLASS"].variation_name == "Glass"

    lines = driver.search_sales("L8H2K0DEMO01", "2026-11-01T00:00:00+00:00", "2026-11-25T00:00:00+00:00")
    assert [(line.order_id, line.line_uid, line.variation_id, line.quantity) for line in lines] == [
        ("ORDER_1", "LINE_MUSCADET", "VAR_MUSCADET", "1"),
        ("ORDER_2", "LINE_GLASS", "VAR_GLASS", "2"),
    ]
    assert lines[0].external_line_id == "ORDER_1:LINE_MUSCADET"

    catalog_calls = [row for row in seen if row.url.path == "/v2/catalog/list"]
    order_calls = [row for row in seen if row.url.path == "/v2/orders/search"]
    assert len(catalog_calls) == 2
    assert catalog_calls[1].url.params.get("cursor") == "catalog-page-2"
    assert len(order_calls) == 2
    second = json.loads(order_calls[1].content.decode())
    assert second["cursor"] == "orders-page-2"
    first = json.loads(order_calls[0].content.decode())
    assert first["location_ids"] == ["L8H2K0DEMO01"]
    assert first["query"]["filter"]["state_filter"]["states"] == ["COMPLETED"]
    assert first["query"]["filter"]["date_time_filter"]["closed_at"]["start_at"] == "2026-11-01T00:00:00+00:00"
    assert first["query"]["sort"] == {"sort_field": "CLOSED_AT", "sort_order": "ASC"}
    for request in seen:
        assert request.url.host == "connect.squareupsandbox.com"
        assert request.headers["Square-Version"] == "2026-11-18"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in str(request.url)


def test_square_production_base_url_comes_from_config(monkeypatch):
    monkeypatch.setenv("MADIRA_SQUARE_ENV", "production")
    monkeypatch.delenv("MADIRA_SQUARE_BASE_URL", raising=False)
    assert square_base_url() == "https://connect.squareup.com"
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"locations": []})

    SquarePosDriver(TOKEN, client=_client(handler)).list_locations()
    assert seen == ["https://connect.squareup.com/v2/locations"]


def test_square_error_does_not_echo_the_token():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"errors": [{"category": "AUTHENTICATION_ERROR", "code": "UNAUTHORIZED", "detail": TOKEN}]},
        )

    driver = SquarePosDriver(TOKEN, client=_client(handler))
    try:
        driver.list_locations()
    except PosError as exc:
        assert TOKEN not in exc.message
        assert "UNAUTHORIZED" in exc.message
    else:
        raise AssertionError("expected Square to fail")


def test_square_without_a_token_does_not_call_the_network():
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    try:
        SquarePosDriver("  ", client=_client(handler)).list_locations()
    except PosError as exc:
        assert "access token" in exc.message
    else:
        raise AssertionError("expected a missing token to fail")
    assert called is False
