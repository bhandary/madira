"""Roleplay scores come from the service. Fabricated evidence does not count."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage

from madira.agents.demo.model import DemoChatModel
from madira.db import init_db
from madira.domain.errors import DraftFailed
from madira.domain.session import session_scope
from madira.domain.training.roleplay import catalog_for, finish, reply, set_roleplay_completers, start
from madira.main import app
from madira.seed import seed
from madira.tenancy import bind, ensure_demo_tenant, reset


@pytest.fixture(autouse=True)
def _clear_completers():
    set_roleplay_completers()
    yield
    set_roleplay_completers()


def _ready():
    init_db()
    seed()
    return ensure_demo_tenant()


def _criterion(passed: bool, evidence: str) -> dict:
    return {"pass": passed, "evidence": evidence}


def _score(listened, options, structure, price, total=4) -> str:
    return json.dumps(
        {
            "score": total,
            "listened": listened,
            "offered_two_options": options,
            "described_structure": structure,
            "handled_price": price,
        }
    )


def test_demo_heuristic_scores_only_what_the_staff_said():
    _ready()
    opened = start("skeptic")
    assert opened["status"] == "open"
    assert opened["score"] is None
    assert opened["transcript"][0]["role"] == "guest"
    assert "wine lists" in opened["transcript"][0]["text"]
    continued = reply(uuid.UUID(opened["id"]), "I hear you.")
    staff = next(turn["text"] for turn in continued["transcript"] if turn["role"] == "staff")
    assert staff == "I hear you."
    scored = finish(uuid.UUID(opened["id"]))
    assert scored["status"] == "scored"
    assert scored["rubric"]["listened"]["pass"] is True
    assert scored["rubric"]["listened"]["evidence"] == "I hear you."
    assert scored["rubric"]["offered_two_options"]["pass"] is False
    assert scored["score"] == sum(1 for item in scored["rubric"].values() if item["pass"])
    assert scored["score"] == 1


def test_fabricated_evidence_fails_and_the_service_computes_the_score():
    _ready()
    opened = start("budget-conscious")
    session_id = uuid.UUID(opened["id"])
    continued = reply(session_id, "I hear you. The glass is the easier price.")
    staff = next(turn["text"] for turn in continued["transcript"] if turn["role"] == "staff")

    def fake(_prompt: str) -> str:
        return _score(
            _criterion(True, "I invented this quote."),
            _criterion(True, "also invented"),
            _criterion(True, ""),
            _criterion(True, "not in the transcript"),
        )

    set_roleplay_completers(scorer=fake)
    scored = finish(session_id)
    assert scored["score"] == 0
    assert all(item["pass"] is False and item["evidence"] == "" for item in scored["rubric"].values())

    opened_again = start("connoisseur")
    again_id = uuid.UUID(opened_again["id"])
    continued = reply(again_id, staff)

    def mixed(_prompt: str) -> str:
        return _score(
            _criterion(True, staff),
            _criterion(True, "a bottle I made up"),
            _criterion(True, "tannin that was never said"),
            _criterion(True, "four dollars even"),
            total=4,
        )

    set_roleplay_completers(scorer=mixed)
    scored = finish(again_id)
    assert scored["score"] == 1
    assert scored["rubric"]["listened"]["pass"] is True
    assert scored["rubric"]["listened"]["evidence"] == staff
    assert scored["rubric"]["handled_price"]["pass"] is False
    calls = {"n": 0}

    def once(_prompt: str) -> str:
        calls["n"] += 1
        return _score(_criterion(False, ""), _criterion(False, ""), _criterion(False, ""), _criterion(False, ""), total=9)

    set_roleplay_completers(scorer=once)
    fresh = uuid.UUID(start("celebration")["id"])
    reply(fresh, "I hear you.")
    finish(fresh)
    finish(fresh)
    assert calls["n"] == 1


def test_products_in_a_guest_line_must_resolve():
    demo = _ready()
    with session_scope() as session:
        catalog = catalog_for(session, demo.venue_id)
    assert len(catalog) >= 1
    product = catalog[0]
    opened = start("skeptic")
    session_id = uuid.UUID(opened["id"])

    def missing(_prompt: str) -> str:
        return json.dumps({"text": f"What about {product['name']}?", "product_ids": []})

    set_roleplay_completers(guest=missing)
    with pytest.raises(DraftFailed) as missing_id:
        reply(session_id, "I hear you.")
    assert missing_id.value.message == "A product in the reply does not resolve to a catalog id."

    def unknown(_prompt: str) -> str:
        return json.dumps({"text": "Something off the list.", "product_ids": [str(uuid.uuid4())]})

    set_roleplay_completers(guest=unknown)
    with pytest.raises(DraftFailed) as unknown_id:
        reply(session_id, "I hear you.")
    assert unknown_id.value.message == "A product in the reply does not resolve to a catalog id."

    def resolved(_prompt: str) -> str:
        return json.dumps({"text": f"What about {product['name']}?", "product_ids": [product["id"]]})

    set_roleplay_completers(guest=resolved)
    continued = reply(session_id, "I hear you.")
    guest = [turn for turn in continued["transcript"] if turn["role"] == "guest"][-1]
    assert guest["product_ids"] == [product["id"]]


def test_live_mode_does_not_fall_back_to_the_script(monkeypatch):
    demo = _ready()
    token = bind(demo)
    try:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-live-not-a-fixture")

        def boom(_prompt: str) -> str:
            raise RuntimeError("connection refused")

        def scripted(*_args, **_kwargs):
            raise AssertionError("scripted guest")

        monkeypatch.setattr("madira.domain.training.roleplay.live_complete", boom)
        monkeypatch.setattr("madira.domain.training.roleplay._scripted_guest", scripted)
        with pytest.raises(DraftFailed) as raised:
            start("skeptic")
        assert raised.value.message == "Roleplay failed (RuntimeError)."
        assert "skeptical of sommeliers" not in raised.value.message
    finally:
        reset(token)


def test_another_user_cannot_score_the_session():
    _ready()
    opened = start("skeptic")
    with TestClient(app) as client:
        client.cookies.set("madira_demo_persona", "ana")
        hidden = client.post(f"/training/roleplay/{opened['id']}/score")
        assert hidden.status_code == 404


def test_demo_model_routes_roleplay_and_team_progress():
    model = DemoChatModel(role="staff-trainer")
    started = model.invoke([HumanMessage(content="Let's roleplay a skeptical diner")])
    assert started.tool_calls[0]["name"] == "start_roleplay"
    assert started.tool_calls[0]["args"] == {"persona": "skeptic", "dish": ""}
    progress = model.invoke([HumanMessage(content="Show team progress and the weak topics")])
    assert progress.tool_calls[0]["name"] == "get_team_progress"
    session_id = "11111111-1111-4111-8111-111111111111"
    scored = model.invoke([HumanMessage(content=f"score roleplay {session_id}")])
    assert scored.tool_calls[0]["name"] == "score_roleplay"
    assert scored.tool_calls[0]["args"]["session_id"] == session_id
