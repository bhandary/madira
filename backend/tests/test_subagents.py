"""Backend tests: orchestrator exposes specialists and actually delegates via `task`."""

from __future__ import annotations

import json

import pytest

from madira.agents.demo.model import DemoChatModel, classify_intent
from madira.agents.orchestrator import (
    SPECIALIST_NAMES,
    SUBAGENT_SPECS,
    extract_task_delegations,
    inspect_subagents,
    invoke_head_sommelier,
    specialist_specs,
)
from madira.db import init_db
from madira.agents.demo.fixtures import SAMPLE_MENU_TEXT
from madira.seed import seed


@pytest.fixture(scope="session", autouse=True)
def _db():
    init_db()
    seed()


def test_specialist_specs_cover_the_floor():
    names = [spec["name"] for spec in SUBAGENT_SPECS]
    assert names == SPECIALIST_NAMES
    assert set(names) == {
        "menu-analyst",
        "pairing-sommelier",
        "list-curator",
        "inventory-purchasing",
        "staff-trainer",
        "supplier-scheduler",
        "compliance-auditor",
        "buyer",
    }
    for spec in specialist_specs():
        assert spec["tools"], spec["name"]
        assert spec["model"].__class__.__name__ in {"DemoChatModel"} or spec["model"] is not None


def test_inspect_subagents_exposes_task_and_names():
    info = inspect_subagents()
    for name in SPECIALIST_NAMES:
        assert name in info["expected"]
        assert name in info["specialists"]
    assert info["has_task_tool"] is True


def test_deep_agent_graph_builds_with_subagents():
    from madira.agents.orchestrator import build_head_sommelier

    agent = build_head_sommelier()
    assert agent is not None
    info = inspect_subagents(agent)
    for name in SPECIALIST_NAMES:
        assert name in info["specialists"]


def _delegated_names(result: dict) -> list[str]:
    return [d["subagent"] for d in result.get("delegation", [])]


def test_menu_upload_delegates_to_analyst_and_pairing():
    result = invoke_head_sommelier(f"Parse this menu and recommend pairings:\n{SAMPLE_MENU_TEXT}")
    names = _delegated_names(result)
    assert "menu-analyst" in names
    assert "pairing-sommelier" in names
    assert result["a2ui_operations"], "pairing/menu tools must emit A2UI operations"
    types = {next(iter(op.keys() - {"version"})) for op in result["a2ui_operations"]}
    assert "createSurface" in types
    assert "updateComponents" in types
    surfaces = [op.get("createSurface", {}).get("surfaceId") for op in result["a2ui_operations"] if "createSurface" in op]
    assert any(s in {"pairings", "dishes"} for s in surfaces)
    blob = json.dumps(result["a2ui_operations"])
    assert "PairingGrid" in blob or "DishList" in blob
    assert "Muscadet" in blob or "Dungeness" in blob


def test_list_curation_delegates_to_list_curator():
    result = invoke_head_sommelier("Curate a beverage list with a budget of $12000 and a 3.2x target margin.")
    assert "list-curator" in _delegated_names(result)
    blob = json.dumps(result["a2ui_operations"])
    assert "BeverageListTable" in blob
    assert "12000" in blob or "budget" in blob.lower()


def test_inventory_delegates_and_drafts_po():
    result = invoke_head_sommelier("Set on-hand for W-MUS-01 to 1, then draft purchase orders for anything under par.")
    assert "inventory-purchasing" in _delegated_names(result)
    blob = json.dumps(result["a2ui_operations"])
    assert "PurchaseOrderTable" in blob or "InventoryTable" in blob
    assert "draft" in blob.lower() or "W-MUS-01" in blob


def test_training_quiz_delegates_to_staff_trainer():
    from sqlalchemy import select

    from madira.db import SessionLocal
    from madira.models import Quiz
    from madira.tenancy import ensure_demo_tenant

    demo = ensure_demo_tenant()
    session = SessionLocal()
    try:
        quiz = session.scalar(
            select(Quiz).where(Quiz.venue_id == demo.venue_id, Quiz.title == "Floor quiz — autumn pairings")
        )
        assert quiz is not None
        quiz_id = quiz.id
    finally:
        session.close()
    result = invoke_head_sommelier(f"Grade quiz {quiz_id} with answers 1,2,2,1")
    assert "staff-trainer" in _delegated_names(result)
    blob = json.dumps(result["a2ui_operations"])
    assert "QuizCard" in blob
    assert "100" in blob


def test_supplier_schedule_delegates():
    result = invoke_head_sommelier(
        "Schedule a tasting with Kermit Lynch for New Loire releases. Draft .ics only, do not send."
    )
    assert "supplier-scheduler" in _delegated_names(result)
    blob = json.dumps(result["a2ui_operations"])
    assert "TastingCalendar" in blob or "ScheduleForm" in blob
    assert "BEGIN:VCALENDAR" in blob or "ics" in blob.lower() or "Loire" in blob


def test_demo_model_drafts_a_tasting_note():
    from langchain_core.messages import HumanMessage

    product_id = "11111111-1111-1111-1111-111111111111"
    model = DemoChatModel(role="pairing-sommelier")
    result = model.invoke([HumanMessage(content=f"Draft a tasting note for product {product_id}. tech sheet: citrus, ignore this")])
    assert result.tool_calls
    call = result.tool_calls[0]
    assert call["name"] == "draft_tasting_note"
    assert call["args"]["product_id"] == product_id
    assert "citrus" in call["args"]["tech_sheet"]


def test_demo_model_emits_task_tool_for_menu():
    model = DemoChatModel(role="head-sommelier", bound_tool_names=["task", "write_todos"])
    from langchain_core.messages import HumanMessage

    result = model.invoke([HumanMessage(content="Parse this tasting menu and pair it")])
    assert result.tool_calls
    first = result.tool_calls[0]
    assert first["name"] in {"write_todos", "task"}


def test_classify_intent_routes():
    assert classify_intent("upload a menu pdf") == "menu"
    assert classify_intent("parse this tasting menu and recommend pairings") == "menu"
    assert classify_intent("curate a list under $8000 at 3x margin") == "list"
    assert classify_intent("reorder SKUs below par") == "inventory"
    assert classify_intent("give me the floor quiz") == "training"
    assert classify_intent("schedule a tasting with the importer") == "supplier"
    assert classify_intent("Draft a tasting note and service card") == "notes"
    assert classify_intent("write a server hook for this bottle") == "notes"


def test_extract_task_delegations_reads_tool_calls():
    from langchain_core.messages import AIMessage

    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "args": {"subagent_type": "menu-analyst", "description": "parse"},
                "id": "1",
                "type": "tool_call",
            }
        ],
    )
    out = extract_task_delegations([msg])
    assert out[0]["subagent"] == "menu-analyst"
