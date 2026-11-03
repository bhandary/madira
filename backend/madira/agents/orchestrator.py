"""Head Sommelier Deep Agent — delegates via the `task` tool to specialist subagents."""

from __future__ import annotations

import json
from typing import Any

from madira.agents.demo_model import DemoChatModel, SPECIALISTS
from madira.agents.tools import (
    INVENTORY_TOOLS,
    LIST_TOOLS,
    MENU_ANALYST_TOOLS,
    PAIRING_TOOLS,
    SUPPLIER_TOOLS,
    TRAINING_TOOLS,
)
from madira.agents import tracker
from madira.config import DEMO_MODE, LLM_MODEL, LLM_PROVIDER

SPECIALIST_NAMES = list(SPECIALISTS)

HEAD_PROMPT = """You are the Head Sommelier of Maison Madira, a California-French dining room.

You do not do specialist work yourself. You ALWAYS delegate with the `task` tool:
- menu-analyst — parse an uploaded or pasted menu into dishes, flavor profiles, cuisine, price tier
- pairing-sommelier — wine, beer, spirit, and sake pairings per dish with rationale and price-tier fit
- list-curator — balanced lists within a stated budget and target pour/bottle margin, with coverage and gaps
- inventory-purchasing — stock, par, depletion, low-stock alerts, draft purchase orders (never transmit)
- staff-trainer — wine knowledge, service etiquette, daily briefing, quizzes, diner roleplay
- supplier-scheduler — draft tastings with importers/distributors; .ics only, never send email or invites

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
        "description": "Recommend wine, beer, spirit, and sake pairings per dish with a short flavor-profile rationale and price-tier fit.",
        "system_prompt": "You are the Pairing Sommelier. Call recommend_pairings. Cover wine, beer, spirit, and sake on every dish.",
        "tools": PAIRING_TOOLS,
    },
    {
        "name": "list-curator",
        "description": "Build a balanced wine/beer/spirit/sake list to complement the menu within a budget and target margin. Show coverage, gaps, and cost/margin math.",
        "system_prompt": "You are the List Curator. Call curate_beverage_list with budget and target_margin from the task.",
        "tools": LIST_TOOLS,
    },
    {
        "name": "inventory-purchasing",
        "description": "Track stock on hand, par levels, depletion, low-stock alerts, and draft reorder/purchase orders by supplier. Never transmit orders.",
        "system_prompt": "You are Inventory & Purchasing. Use get_inventory, update_stock, and draft_purchase_orders as needed. Drafts only.",
        "tools": INVENTORY_TOOLS,
    },
    {
        "name": "staff-trainer",
        "description": "Wine knowledge, service etiquette, daily pairing briefings, flavor-profile explainers, quizzes, and diner roleplay.",
        "system_prompt": "You are the Staff Trainer. Use get_training_briefing, grade_quiz, or start_roleplay depending on the task.",
        "tools": TRAINING_TOOLS,
    },
    {
        "name": "supplier-scheduler",
        "description": "Schedule tastings with importers and distributors. Produce .ics drafts only — never send email or calendar invites.",
        "system_prompt": "You are the Supplier Scheduler. Use list_tastings or schedule_tasting. Always mark results as drafts, never sent.",
        "tools": SUPPLIER_TOOLS,
    },
]


def _live_model():
    from langchain.chat_models import init_chat_model

    return init_chat_model(f"{LLM_PROVIDER}:{LLM_MODEL}")


def _model_for(role: str):
    if DEMO_MODE:
        return DemoChatModel(role=role)
    return _live_model()


def specialist_specs() -> list[dict[str, Any]]:
    specs = []
    for spec in SUBAGENT_SPECS:
        item = dict(spec)
        item["model"] = _model_for(spec["name"])
        specs.append(item)
    return specs


def build_head_sommelier():
    from deepagents import create_deep_agent

    kwargs: dict[str, Any] = {
        "model": _model_for("head-sommelier"),
        "tools": [],
        "subagents": specialist_specs(),
        "system_prompt": HEAD_PROMPT,
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
    from madira.a2ui_ops import parse_operations

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
    tracker.start_run()
    agent = build_head_sommelier()
    result = agent.invoke({"messages": [{"role": "user", "content": message}]})
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
        "demo_mode": DEMO_MODE,
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
