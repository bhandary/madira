from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

_log: ContextVar[list[dict[str, Any]] | None] = ContextVar("madira_delegation", default=None)
_ops: ContextVar[list[dict[str, Any]] | None] = ContextVar("madira_a2ui", default=None)
_todos: ContextVar[list[dict[str, Any]] | None] = ContextVar("madira_todos", default=None)


def start_run() -> None:
    _log.set([])
    _ops.set([])
    _todos.set([])


def record_delegation(subagent: str, description: str, status: str = "running") -> None:
    log = _log.get()
    if log is None:
        log = []
        _log.set(log)
    existing = next((item for item in log if item["subagent"] == subagent), None)
    if existing:
        existing["status"] = status
        existing["description"] = description or existing["description"]
        return
    log.append({"subagent": subagent, "description": description, "status": status})


def complete_delegation(subagent: str) -> None:
    log = _log.get() or []
    for item in log:
        if item["subagent"] == subagent:
            item["status"] = "complete"


def record_operations(operations: list[dict[str, Any]]) -> None:
    ops = _ops.get()
    if ops is None:
        ops = []
        _ops.set(ops)
    ops.extend(operations)


def record_todos(todos: list[dict[str, Any]]) -> None:
    _todos.set(list(todos))


def snapshot() -> dict[str, Any]:
    return {
        "delegation": list(_log.get() or []),
        "a2ui_operations": list(_ops.get() or []),
        "todos": list(_todos.get() or []),
    }


@dataclass
class RunCollector:
    events: list[dict[str, Any]] = field(default_factory=list)
