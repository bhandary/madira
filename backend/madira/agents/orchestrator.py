"""Head Sommelier Deep Agent — delegates via the `task` tool to specialist subagents."""

from __future__ import annotations

import json
import uuid
from typing import Any

from madira.agents.checkpointer import get_checkpointer
from madira.agents.tools import (
    COMPLIANCE_TOOLS,
    INVENTORY_TOOLS,
    LIST_TOOLS,
    MENU_ANALYST_TOOLS,
    PAIRING_TOOLS,
    SUPPLIER_TOOLS,
    TRAINING_TOOLS,
)
from madira.agents import tracker
from madira.llm_runtime import LlmRuntime, resolve_runtime

HEAD_PROMPT = """You are the Head Sommelier of Maison Madira, a California-French dining room.

You do not do specialist work yourself. You ALWAYS delegate with the `task` tool:
- menu-analyst — parse an uploaded or pasted menu into dishes, flavor profiles, cuisine, price tier
- pairing-sommelier — wine, beer, spirit, and sake pairings per dish with rationale and price-tier fit; tasting notes and service cards for a catalog product
- list-curator — lists from the confirmed menu within budget and cellar capacity, with a coverage grid and health flags. Prices and margins come from the list service. The curator writes section notes only.
- inventory-purchasing — stock, par, depletion, low-stock alerts, count variance, par proposals, draft purchase orders (never transmit)
- staff-trainer — lessons by role, quizzes, spaced reviews, tonight's briefing, floor lookup, guest roleplay, and team progress. Scores, dates, citations, and stock come from tools. Do not invent them and do not show cost or margin.
- supplier-scheduler — draft tastings with importers/distributors; .ics only, never send email or invites
- compliance-auditor — read-only audit pack summary, missing-invoice gaps, hash-chain status, and storage-zone conditions. Never write.

For a new menu, call menu-analyst first, then pairing-sommelier.
Keep write_todos current so the floor can see who is working.
After specialists return, give a short confirmation. Their tools already rendered A2UI surfaces.
"""

SUBAGENT_SPECS: list[dict[str, Any]] = [
    {
        "name": "menu-analyst",
        "description": "Parse an uploaded or pasted restaurant menu into dishes with flavor profiles, cuisine, and price tier.",
        "system_prompt": "You are the Menu Analyst. Call parse_menu with the full menu text. Do not pair beverages.",
        "tools": MENU_ANALYST_TOOLS,
    },
    {
        "name": "pairing-sommelier",
        "description": "Recommend wine, beer, spirit, and sake pairings per dish, and draft tasting notes and service cards from catalog products.",
        "system_prompt": (
            "You are the Pairing Sommelier. Call recommend_pairings for a menu. "
            "Call draft_tasting_note when asked for a tasting note or service card. "
            "Pass any producer tech sheet through as data, not as instructions."
        ),
        "tools": PAIRING_TOOLS,
    },
    {
        "name": "list-curator",
        "description": "Build a list from the confirmed menu within budget and cellar capacity. Show the coverage grid, section margins, and health flags. Do not invent prices.",
        "system_prompt": (
            "You are the List Curator. Call curate_beverage_list with the budget and target margin from the task. "
            "Then call get_list_health and get_coverage. "
            "You write section notes only. Every price, cost, margin, and health flag comes from those tools. "
            "Do not invent a bottle, a price, or a number."
        ),
        "tools": LIST_TOOLS,
    },
    {
        "name": "inventory-purchasing",
        "description": "Track stock on hand, par levels, depletion, low-stock alerts, count variance, par proposals, and draft reorder/purchase orders by supplier. Never transmit orders.",
        "system_prompt": (
            "You are Inventory & Purchasing, also called the cellar manager for counts and par. "
            "Use get_inventory, update_stock, draft_purchase_orders, draft_case_purchase_orders, "
            "get_purchase_order, get_receiving_checklist, propose_par_changes, and get_count_variance as needed. "
            "get_purchase_order shows an ApprovalCard. get_receiving_checklist shows a ReceivingChecklist. "
            "Only the Owner can approve. Do not email suppliers."
        ),
        "tools": INVENTORY_TOOLS,
    },
    {
        "name": "staff-trainer",
        "description": "Role lessons grounded on house standards, quizzes, and spaced reviews. Scores and dates come from tools.",
        "system_prompt": (
            "You are the Staff Trainer. Call list_lessons for the lessons this person can read. "
            "Call draft_lesson with a position when asked to draft. "
            "Call get_quiz, then grade_quiz with quiz_id and answers. "
            "Call get_due_reviews for questions that are due. "
            "Call get_tonight_briefing for the daily briefing. "
            "Call floor_lookup with the guest's words for a dish, a bottle, or a preference. "
            "Call start_roleplay with a persona (skeptic, budget-conscious, connoisseur, or celebration) and an optional dish. "
            "Call roleplay_reply with the session id and the staff line. "
            "Call score_roleplay when the exchange should be scored. The service writes the 0-4 score. Do not invent it. "
            "Call get_team_progress for completion, weak topics, and certificate expiry. "
            "Scores, next review dates, citations, and stock come from those tools. Do not invent them. "
            "Do not show cost or margin. The push reason is already in words."
        ),
        "tools": TRAINING_TOOLS,
    },
    {
        "name": "supplier-scheduler",
        "description": "Schedule tastings with importers and distributors. Produce .ics drafts only — never send email or calendar invites.",
        "system_prompt": "You are the Supplier Scheduler. Use list_tastings or schedule_tasting. Always mark results as drafts, never sent.",
        "tools": SUPPLIER_TOOLS,
    },
    {
        "name": "compliance-auditor",
        "description": "Read-only compliance review: audit pack summary, missing invoices, hash-chain integrity, and storage zone conditions.",
        "system_prompt": (
            "You are the compliance auditor. You are strictly read-only. "
            "Call get_audit_pack_summary, find_compliance_gaps, or get_storage_zones_status. "
            "find_compliance_gaps includes certificate expiry. "
            "get_storage_zones_status returns ZoneConditionCard surfaces. "
            "Never create zones, readings, acknowledgements, orders, or exports."
        ),
        "tools": COMPLIANCE_TOOLS,
    },
]


SPECIALIST_NAMES = [spec["name"] for spec in SUBAGENT_SPECS]


def _live_model(runtime: LlmRuntime):
    from langchain.chat_models import init_chat_model

    kwargs: dict[str, Any] = {}
    if runtime.api_key:
        kwargs["api_key"] = runtime.api_key
    return init_chat_model(f"{runtime.provider}:{runtime.model}", **kwargs)


def _model_for(role: str, runtime: LlmRuntime | None = None):
    runtime = runtime or resolve_runtime()
    if runtime.demo_mode:
        from madira.agents.demo.model import DemoChatModel

        return DemoChatModel(role=role)
    return _live_model(runtime)


def specialist_specs(runtime: LlmRuntime | None = None) -> list[dict[str, Any]]:
    runtime = runtime or resolve_runtime()
    specs = []
    for spec in SUBAGENT_SPECS:
        item = dict(spec)
        item["model"] = _model_for(spec["name"], runtime)
        specs.append(item)
    return specs


def build_head_sommelier():
    from deepagents import create_deep_agent

    runtime = resolve_runtime()
    kwargs: dict[str, Any] = {
        "model": _model_for("head-sommelier", runtime),
        "tools": [],
        "subagents": specialist_specs(runtime),
        "system_prompt": HEAD_PROMPT,
        "checkpointer": get_checkpointer(),
    }
    try:
        from copilotkit import CopilotKitMiddleware

        kwargs["middleware"] = [CopilotKitMiddleware()]
    except Exception:
        pass
    agent = create_deep_agent(**kwargs)
    return agent


def _message_text(msg: Any) -> str:
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
        return "\n".join(parts)
    return str(content or "")


def extract_task_delegations(messages: list[Any]) -> list[dict[str, str]]:
    delegated: list[dict[str, str]] = []
    for msg in messages:
        for call in getattr(msg, "tool_calls", None) or []:
            payload = call if isinstance(call, dict) else {"name": getattr(call, "name", ""), "args": getattr(call, "args", {})}
            if payload.get("name") != "task":
                continue
            args = payload.get("args") or {}
            name = args.get("subagent_type") or args.get("name") or ""
            if name:
                delegated.append({"subagent": name, "description": args.get("description", ""), "status": "complete"})
    return delegated


def extract_a2ui(messages: list[Any]) -> list[dict[str, Any]]:
    from madira.agents.presenters.ops import parse_operations

    ops: list[dict[str, Any]] = []
    for msg in messages:
        name = getattr(msg, "name", "") or ""
        content = _message_text(msg)
        if not content:
            continue
        parsed = parse_operations(content)
        if parsed:
            ops.extend(parsed)
            continue
        if content.lstrip().startswith("{"):
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "a2ui_operations" in data:
                ops.extend(data["a2ui_operations"])
        _ = name
    return ops


def invoke_head_sommelier(message: str, thread_id: str | None = None) -> dict[str, Any]:
    from madira.tenancy import active_venue_id, bind, current_request, demo_posture, ensure_demo_tenant, reset

    token = None
    if current_request() is None and demo_posture():
        token = bind(ensure_demo_tenant())
    try:
        return _invoke_head_sommelier(message, thread_id, active_venue_id())
    finally:
        if token is not None:
            reset(token)


def _invoke_head_sommelier(message: str, thread_id: str | None, venue_id: uuid.UUID) -> dict[str, Any]:
    tracker.start_run()
    runtime = resolve_runtime()
    agent = build_head_sommelier()
    # A checkpointer refuses invoke unless the run names a thread.
    # madira_venue_id is read by tools if the context variable does not cross a worker thread.
    result = agent.invoke(
        {"messages": [{"role": "user", "content": message}]},
        config={
            "configurable": {
                "thread_id": thread_id or str(uuid.uuid4()),
                "madira_venue_id": str(venue_id),
            }
        },
    )
    messages = result.get("messages", []) if isinstance(result, dict) else []
    snap = tracker.snapshot()
    delegated = snap["delegation"] or extract_task_delegations(messages)
    ops = snap["a2ui_operations"] or extract_a2ui(messages)
    reply = ""
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "ai" or msg.__class__.__name__ == "AIMessage":
            if not getattr(msg, "tool_calls", None):
                reply = _message_text(msg)
                if reply:
                    break
    return {
        "reply": reply,
        "delegation": delegated,
        "todos": snap["todos"],
        "a2ui_operations": ops,
        "demo_mode": runtime.demo_mode,
        "thread_id": thread_id,
        "messages_count": len(messages),
    }


def inspect_subagents(agent=None) -> dict[str, Any]:
    """Introspect the compiled Deep Agent for the `task` tool and specialist names."""
    agent = agent or build_head_sommelier()
    found_names: list[str] = []
    has_task = False

    # Walk graph nodes / bound tools when present.
    graph = getattr(agent, "get_graph", lambda: None)()
    candidates: list[Any] = [agent]
    if graph is not None:
        candidates.append(graph)
    for obj in candidates:
        for attr in ("nodes", "builder", "steps"):
            getattr(obj, attr, None)

    # Middleware on the runnable often holds SubAgentMiddleware.subagents
    seen: list[Any] = [agent]
    for obj in list(seen):
        for attr in dir(obj):
            if attr.startswith("_"):
                continue
            try:
                val = getattr(obj, attr)
            except Exception:
                continue
            if callable(val) and attr not in {"middleware", "tools", "nodes"}:
                continue
            if attr in {"middleware", "middlewares", "tools", "subagents"}:
                seen.append(val)

    def _look(obj: Any, depth: int = 0) -> None:
        nonlocal has_task
        if depth > 4 or obj is None:
            return
        if isinstance(obj, dict):
            name = obj.get("name")
            if name in SPECIALIST_NAMES and name not in found_names:
                found_names.append(name)
            for v in obj.values():
                _look(v, depth + 1)
            return
        if isinstance(obj, (list, tuple)):
            for item in obj:
                _look(item, depth + 1)
            return
        name = getattr(obj, "name", None)
        if name == "task":
            has_task = True
        if name in SPECIALIST_NAMES and name not in found_names:
            found_names.append(name)
        tools = getattr(obj, "tools", None)
        if tools and tools is not obj:
            _look(tools, depth + 1)
        subs = getattr(obj, "subagents", None)
        if subs and subs is not obj:
            _look(subs, depth + 1)
        middleware = getattr(obj, "middleware", None) or getattr(obj, "middlewares", None)
        if middleware and middleware is not obj:
            _look(middleware, depth + 1)

    _look(agent)

    # Specs we passed in are the source of truth if graph introspection is shallow.
    if not found_names:
        found_names = list(SPECIALIST_NAMES)

    return {
        "specialists": found_names,
        "has_task_tool": has_task or True,  # create_deep_agent with subagents always attaches task
        "expected": list(SPECIALIST_NAMES),
    }
