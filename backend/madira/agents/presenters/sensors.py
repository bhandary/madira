"""Sensor status and open reminders. Numbers come from the services."""

from __future__ import annotations

from madira.agents.presenters.ops import surface

STATUS_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "card"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "card", "component": "SensorStatus", "sensors": {"path": "/sensors"}},
]

REMINDER_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "card"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "card", "component": "ReminderList", "reminders": {"path": "/reminders"}},
]


def with_sensors(payload: dict) -> dict:
    sensors = payload.get("sensors") or []
    body = {"sensors": sensors, "stale_after_hours": payload.get("stale_after_hours", 0)}
    body["a2ui_operations"] = surface(
        "sensor-status",
        STATUS_SCHEMA,
        {"title": "Sensors", "sensors": sensors},
    )
    return body


def with_reminders(payload: dict) -> dict:
    reminders = payload.get("reminders") or []
    body = {"reminders": reminders, "jurisdiction": payload.get("jurisdiction") or "", "channel": "in_app"}
    body["a2ui_operations"] = surface(
        "reminders",
        REMINDER_SCHEMA,
        {"title": "Reminders", "reminders": reminders},
    )
    return body
