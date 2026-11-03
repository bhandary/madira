"""Deterministic fake chat model for demo mode.

Inspects the conversation and emits the same tool-call sequence a live Head Sommelier
(or specialist) would: write_todos when available, then `task` (orchestrator) or the
specialist tools. No network, no API key.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from madira.agents.tracker import record_delegation, record_todos

SPECIALISTS = (
    "menu-analyst",
    "pairing-sommelier",
    "list-curator",
    "inventory-purchasing",
    "staff-trainer",
    "supplier-scheduler",
)

INTENT_FLOW = {
    "menu": ["menu-analyst", "pairing-sommelier"],
    "pairing": ["pairing-sommelier"],
    "list": ["list-curator"],
    "inventory": ["inventory-purchasing"],
    "training": ["staff-trainer"],
    "supplier": ["supplier-scheduler"],
}


def classify_intent(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ("quiz", "training", "lesson", "etiquette", "roleplay", "briefing", "flashcard", "waitstaff")):
        return "training"
    if any(k in t for k in ("inventory", "stock", "par level", "reorder", "purchase order", "on-hand", "on hand", "sku")):
        return "inventory"
    if any(k in t for k in ("budget", "margin", "wine list", "curate", "beverage list", "coverage")):
        return "list"
    if any(k in t for k in ("menu", "dish", "pairing", "parse", "upload", "yuzu", "ribeye", "tasting menu")):
        return "menu"
    if any(k in t for k in ("importer", "distributor", ".ics", "calendar", "supplier")) or (
        "tasting" in t and "schedule" in t
    ) or ("tasting" in t and "menu" not in t):
        return "supplier"
    return "menu"


def last_human(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""


def _tool_names_from_messages(messages: list[BaseMessage]) -> set[str]:
    names: set[str] = set()
    for msg in messages:
        if isinstance(msg, ToolMessage) and getattr(msg, "name", None):
            names.add(msg.name)
        if isinstance(msg, AIMessage):
            for call in getattr(msg, "tool_calls", None) or []:
                names.add(call.get("name") if isinstance(call, dict) else getattr(call, "name", ""))
    return names


def _task_subagents_called(messages: list[BaseMessage]) -> list[str]:
    found: list[str] = []
    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        for call in getattr(msg, "tool_calls", None) or []:
            payload = call if isinstance(call, dict) else {"name": getattr(call, "name", ""), "args": getattr(call, "args", {})}
            if payload.get("name") != "task":
                continue
            args = payload.get("args") or {}
            name = args.get("subagent_type") or args.get("name") or args.get("agent")
            if name:
                found.append(name)
    return found


def _call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "args": args, "id": f"call_{uuid.uuid4().hex[:12]}", "type": "tool_call"}


def _ai(tool_calls: list[dict[str, Any]] | None = None, content: str = "") -> AIMessage:
    if tool_calls:
        return AIMessage(content=content, tool_calls=tool_calls)
    return AIMessage(content=content)


class DemoChatModel(BaseChatModel):
    """Input-dependent fake model. `role` selects orchestrator vs specialist behavior."""

    role: str = Field(default="head-sommelier")
    bound_tool_names: list[str] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "madira-demo"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> DemoChatModel:
        names: list[str] = []
        for tool in tools:
            name = getattr(tool, "name", None)
            if name is None and isinstance(tool, dict):
                name = tool.get("name")
            if name:
                names.append(name)
        clone = self.model_copy(update={"bound_tool_names": names})
        return clone

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        msg = self._decide(messages)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def _decide(self, messages: list[BaseMessage]) -> AIMessage:
        if self.role in SPECIALISTS:
            return self._specialist(messages)
        return self._orchestrator(messages)

    def _has_tool(self, name: str, messages: list[BaseMessage]) -> bool:
        if name in self.bound_tool_names:
            return True
        # Deep Agents may inject write_todos / task without going through bind_tools on this instance.
        blob = " ".join(
            m.content if isinstance(m.content, str) else ""
            for m in messages
            if isinstance(m, SystemMessage)
        )
        return name in blob or f'"{name}"' in blob

    def _orchestrator(self, messages: list[BaseMessage]) -> AIMessage:
        text = last_human(messages)
        intent = classify_intent(text)
        flow = list(INTENT_FLOW[intent])
        done_tools = _tool_names_from_messages(messages)
        tasked = _task_subagents_called(messages)

        if "write_todos" in (self.bound_tool_names or []) or self._has_tool("write_todos", messages):
            if "write_todos" not in done_tools:
                todos = [
                    {"content": f"Delegate to {name}", "status": "pending" if i else "in_progress"}
                    for i, name in enumerate(flow)
                ]
                record_todos(todos)
                return _ai([_call("write_todos", {"todos": todos})])

        next_agent = next((name for name in flow if name not in tasked), None)
        if next_agent is not None:
            record_delegation(next_agent, f"Head Sommelier → {next_agent}", "running")
            description = self._task_description(next_agent, text)
            return _ai(
                [
                    _call(
                        "task",
                        {"subagent_type": next_agent, "description": description},
                    )
                ]
            )

        # All specialists returned. Summarize; A2UI already recorded from their tools.
        record_todos(
            [{"content": f"Delegate to {name}", "status": "completed"} for name in flow]
        )
        labels = ", ".join(flow)
        return _ai(
            content=(
                f"Head Sommelier here. I delegated to {labels} and they posted surfaces in the well. "
                "Review the cards and tables — nothing was emailed or purchased."
            )
        )

    def _task_description(self, specialist: str, text: str) -> str:
        if specialist == "menu-analyst":
            return (
                "Parse the restaurant menu into dishes with flavor profiles, cuisine, and price tier. "
                f"Menu text follows:\n{text}"
            )
        if specialist == "pairing-sommelier":
            return "Recommend wine, beer, spirit, and sake pairings for each parsed dish, with rationale and price-tier fit."
        if specialist == "list-curator":
            budget = _extract_budget(text)
            margin = _extract_margin(text)
            return f"Curate a balanced beverage list. Budget ${budget:.0f}. Target pour/bottle margin {margin}x. Complement the current menu."
        if specialist == "inventory-purchasing":
            sku_match = re.search(r"\b([WBSK]-[A-Z]{3}-\d{2})\b", text, re.I)
            qty_match = re.search(r"\b(?:to|at|=)\s*(\d+)\b", text, re.I)
            if sku_match and qty_match:
                return f"Set on-hand for {sku_match.group(1).upper()} to {qty_match.group(1)}, then draft purchase orders for anything still under par."
            if any(k in text.lower() for k in ("reorder", "purchase", "po", "draft")):
                return "Draft purchase orders for every SKU below par, grouped by supplier."
            return "Report cellar inventory, par levels, depletion, and low-stock alerts. Draft reorders if stock is short."
        if specialist == "staff-trainer":
            if "quiz" in text.lower() or "grade" in text.lower() or re.search(r"\d,\s*\d", text):
                answers = _extract_answers(text)
                return f"Grade the floor quiz with answers {answers} for staff name Floor."
            if "roleplay" in text.lower():
                return "Start diner roleplay as a skeptical guest who ordered the ribeye."
            return "Deliver today's pairing briefing, wine-knowledge lesson, and the floor quiz."
        if specialist == "supplier-scheduler":
            if any(k in text.lower() for k in ("schedule", "book", "set up", "hold")):
                return (
                    "Schedule a draft tasting with Kermit Lynch Wine Merchant titled "
                    "'New Loire releases tasting' next week at the cellar. Produce .ics only — do not send."
                )
            return "Show the supplier tasting calendar."
        return text

    def _specialist(self, messages: list[BaseMessage]) -> AIMessage:
        text = last_human(messages)
        done = _tool_names_from_messages(messages)
        role = self.role

        def finish(summary: str) -> AIMessage:
            last_tool = next((m for m in reversed(messages) if isinstance(m, ToolMessage)), None)
            extra = ""
            if last_tool and isinstance(last_tool.content, str) and last_tool.content.startswith("{"):
                extra = " Surface JSON is in the last tool result."
            return _ai(content=summary + extra)

        if role == "menu-analyst":
            if "parse_menu" not in done:
                return _ai([_call("parse_menu", {"text": text, "source_name": "agent"})])
            return finish("Menu parsed into dishes with flavor profiles, cuisine, and price tier.")

        if role == "pairing-sommelier":
            if "recommend_pairings" not in done:
                menu_id = _extract_menu_id(messages)
                return _ai([_call("recommend_pairings", {"menu_id": menu_id})])
            return finish("Pairings posted for wine, beer, spirit, and sake on each dish.")

        if role == "list-curator":
            if "curate_beverage_list" not in done:
                return _ai(
                    [
                        _call(
                            "curate_beverage_list",
                            {
                                "budget": _extract_budget(text),
                                "target_margin": _extract_margin(text),
                                "name": "Maison Madira autumn list",
                            },
                        )
                    ]
                )
            return finish("Beverage list curated with coverage, gaps, and cost/margin math.")

        if role == "inventory-purchasing":
            sku_match = re.search(r"\b([WBSK]-[A-Z]{3}-\d{2})\b", text, re.I)
            qty_match = re.search(r"\b(?:to|at|=)\s*(\d+)\b", text, re.I)
            if sku_match and qty_match and "update_stock" not in done:
                return _ai(
                    [
                        _call(
                            "update_stock",
                            {"sku": sku_match.group(1).upper(), "on_hand": int(qty_match.group(1))},
                        )
                    ]
                )
            if (
                any(k in text.lower() for k in ("reorder", "purchase", "draft", "po"))
                or "update_stock" in done
            ) and "draft_purchase_orders" not in done:
                return _ai([_call("draft_purchase_orders", {})])
            if "get_inventory" not in done and "draft_purchase_orders" not in done:
                return _ai([_call("get_inventory", {})])
            return finish("Inventory reviewed; draft purchase orders grouped by supplier where stock is under par.")

        if role == "staff-trainer":
            if ("quiz" in text.lower() or "grade" in text.lower() or re.search(r"\d,\s*\d", text)) and "grade_quiz" not in done:
                return _ai([_call("grade_quiz", {"answers": _extract_answers(text), "staff_name": "Floor"})])
            if "roleplay" in text.lower() and "start_roleplay" not in done:
                return _ai([_call("start_roleplay", {})])
            if "get_training_briefing" not in done and "grade_quiz" not in done:
                return _ai([_call("get_training_briefing", {})])
            return finish("Training surfaces ready: briefing, quiz, and roleplay opener.")

        if role == "supplier-scheduler":
            if any(k in text.lower() for k in ("schedule", "book", "set up", "hold", "new loire")) and "schedule_tasting" not in done:
                return _ai(
                    [
                        _call(
                            "schedule_tasting",
                            {
                                "supplier_name": "Kermit Lynch Wine Merchant",
                                "title": "New Loire releases tasting",
                                "location": "Maison Madira cellar",
                                "notes": "Draft hold — export .ics, do not send invites.",
                            },
                        )
                    ]
                )
            if "list_tastings" not in done and "schedule_tasting" not in done:
                return _ai([_call("list_tastings", {})])
            return finish("Supplier tasting is a draft only. .ics is attached; nothing was sent.")

        return finish("Done.")


def _extract_budget(text: str) -> float:
    match = re.search(r"\$\s*([\d,]+)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    match = re.search(r"budget\s*(?:of\s*)?([\d,]+)", text, re.I)
    if match:
        return float(match.group(1).replace(",", ""))
    return 12000.0


def _extract_margin(text: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*x", text, re.I)
    if match:
        return float(match.group(1))
    match = re.search(r"margin\s*(?:of\s*)?(\d+(?:\.\d+)?)", text, re.I)
    if match:
        val = float(match.group(1))
        return val / 100 if val > 10 else val
    return 3.2


def _extract_answers(text: str) -> str:
    match = re.search(r"(\d(?:\s*,\s*\d)+)", text)
    if match:
        return match.group(1)
    # Default correct answers for the seeded quiz: 1,2,2,1
    return "1,2,2,1"


def _extract_menu_id(messages: list[BaseMessage]) -> int:
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and isinstance(msg.content, str):
            try:
                data = json.loads(msg.content)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "menu_id" in data:
                return int(data["menu_id"])
    return 0
