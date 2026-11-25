"""Live mode raises when a tool's backend is still the demo fixtures."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from madira.agents.tools import curate_beverage_list, get_inventory, parse_menu, recommend_pairings, start_roleplay
from madira.auth import SESSION_COOKIE, issue_session
from madira.db import init_db
from madira.domain.errors import DraftFailed, Unavailable
from madira.domain.menu.service import extract_upload_text
from madira.domain.training.service import briefing
from madira.llm_runtime import resolve_runtime
from madira.main import app
from madira.seed import seed
from madira.tenancy import DEMO_USER_SUB, bind, ensure_demo_tenant, reset

_FIXTURE_MARKERS = ("Muscadet", "Dungeness", "Maison Madira — Autumn")


def _live(monkeypatch) -> None:
    init_db()
    seed()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-not-a-fixture")
    assert resolve_runtime().demo_mode is False


def _block_pairing_fixtures(monkeypatch) -> None:
    def fixtures(*_args, **_kwargs):
        raise AssertionError("fixture pairings")

    def live_boom(_prompt: str) -> str:
        raise RuntimeError("connection refused")

    def demo_boom(*_args, **_kwargs):
        raise AssertionError("demo copy")

    monkeypatch.setattr("madira.agents.demo.fixtures.pairings_for_dishes", fixtures)
    monkeypatch.setattr("madira.domain.pairing.copy.live_complete", live_boom)
    monkeypatch.setattr("madira.domain.pairing.copy.demo_lines", demo_boom)


def test_live_tools_raise_instead_of_returning_fixtures(monkeypatch):
    _live(monkeypatch)
    _block_pairing_fixtures(monkeypatch)
    demo = ensure_demo_tenant()
    token = bind(demo)
    try:
        with pytest.raises(Unavailable) as raised:
            parse_menu("Dungeness crab, yuzu, truffle")
        message = raised.value.message
        assert "Sample menu substitution has no live backend yet" in message
        for marker in _FIXTURE_MARKERS:
            assert marker not in message
        paired = json.loads(recommend_pairings(""))
        assert "no live backend" not in json.dumps(paired)
        for marker in _FIXTURE_MARKERS:
            assert marker not in json.dumps(paired)
        if paired.get("error"):
            assert paired["error"] == "menu not found" or "pairing copy" in paired["error"]
            assert "connection refused" not in paired["error"]
        def notes_boom(_prompt: str) -> str:
            raise RuntimeError("connection refused")

        monkeypatch.setattr("madira.domain.lists.copy.live_complete", notes_boom)
        with pytest.raises(DraftFailed) as curated:
            curate_beverage_list()
        assert "The list notes failed (RuntimeError)." in curated.value.message
        for marker in _FIXTURE_MARKERS:
            assert marker not in curated.value.message
        def roleplay_boom(_prompt: str) -> str:
            raise RuntimeError("connection refused")

        def scripted_boom(*_args, **_kwargs):
            raise AssertionError("scripted guest")

        monkeypatch.setattr("madira.domain.training.roleplay.live_complete", roleplay_boom)
        monkeypatch.setattr("madira.domain.training.roleplay._scripted_guest", scripted_boom)
        played = json.loads(start_roleplay())
        assert played["error"] == "Roleplay failed (RuntimeError)."
        assert "skeptical of sommeliers" not in played["error"]
        with pytest.raises(DraftFailed) as photo:
            extract_upload_text("plate.png", b"\x89PNG\r\n")
        assert photo.value.status == 415
        assert "no live backend" not in photo.value.message
        for marker in _FIXTURE_MARKERS:
            assert marker not in photo.value.message
        inventory = json.loads(get_inventory())
        assert any(row["sku"] == "W-MUS-01" for row in inventory["items"])
        opened = briefing(demo.venue_id)
        assert opened["lessons"]
        assert opened["roleplay"] is None
    finally:
        reset(token)


def test_live_parse_route_returns_the_error(monkeypatch):
    _live(monkeypatch)
    monkeypatch.setenv("MADIRA_AUTH_SECRET", "live-mode-test-secret")
    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE, issue_session(DEMO_USER_SUB))
        response = client.post("/menus/parse", json={"text": "Dungeness crab, yuzu"})
    assert response.status_code == 501
    detail = response.json()["detail"]
    assert "Sample menu substitution has no live backend yet" in detail
    for marker in _FIXTURE_MARKERS:
        assert marker not in response.text


def test_live_line_parser_keeps_supplied_dishes(monkeypatch):
    _live(monkeypatch)
    demo = ensure_demo_tenant()
    token = bind(demo)
    try:
        with pytest.raises(Unavailable) as blank:
            parse_menu("   ")
        assert "Empty menu text has no live backend yet" in blank.value.message
        with pytest.raises(Unavailable) as short:
            parse_menu("Hi")
        assert "Sample menu substitution has no live backend yet" in short.value.message
        body = json.loads(parse_menu("Grilled octopus, chili, olive oil — 24\nLemon tart — 12", "pasted"))
    finally:
        reset(token)
    assert [dish["name"] for dish in body["dishes"]] == [
        "Grilled octopus, chili, olive oil",
        "Lemon tart",
    ]
    assert body["dishes"][0]["price"] == 2400
    assert body["dishes"][0]["flavor_profile"] == "savory, balanced"
    assert body["dishes"][1]["price"] == 1200
    assert body["dishes"][1]["flavor_profile"] == "citrus"
    for marker in _FIXTURE_MARKERS:
        assert marker not in json.dumps(body)
    token = bind(demo)
    _block_pairing_fixtures(monkeypatch)
    try:
        raw = recommend_pairings(str(body["menu_id"]))
    finally:
        reset(token)
    assert "no live backend" not in raw
    for marker in _FIXTURE_MARKERS:
        assert marker not in raw
    payload = json.loads(raw)
    if payload.get("error"):
        assert "RuntimeError" in payload["error"]
        assert "connection refused" not in payload["error"]
    else:
        assert payload["dishes"]


def test_live_parse_route_stores_supplied_text(monkeypatch):
    _live(monkeypatch)
    monkeypatch.setenv("MADIRA_AUTH_SECRET", "live-mode-test-secret")
    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE, issue_session(DEMO_USER_SUB))
        empty = client.post("/menus/parse", json={"text": ""})
        assert empty.status_code == 501
        assert "Empty menu text has no live backend yet" in empty.json()["detail"]
        created = client.post(
            "/menus/parse",
            json={"text": "Grilled octopus, chili, olive oil — 24", "source_name": "pasted"},
        )
    assert created.status_code == 200
    dish = created.json()["dishes"][0]
    assert dish["name"] == "Grilled octopus, chili, olive oil"
    assert dish["price"] == 2400
    for marker in _FIXTURE_MARKERS:
        assert marker not in created.text
