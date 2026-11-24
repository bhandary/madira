"""Tasting note and service card surfaces.

Edit and approve stay on the REST routes. The surface only shows the draft
the pairing sommelier just wrote.
"""

from __future__ import annotations

from typing import Any

from madira.agents.presenters.ops import surface

_NOTE_FIELDS = (
    "id",
    "product_id",
    "product_name",
    "producer",
    "server_hook",
    "guest_description",
    "technical_note",
    "body",
    "acidity",
    "tannin",
    "sweetness",
    "oak",
    "intensity",
    "aroma_families",
    "source",
    "status",
    "approved_by",
    "approved_at",
    "has_tech_sheet",
    "created_at",
)

_CARD_FIELDS = (
    "id",
    "product_id",
    "product_name",
    "tasting_note_id",
    "serving_temperature",
    "glassware",
    "decanting",
    "pour_size",
    "source",
    "status",
    "approved_by",
    "approved_at",
    "created_at",
)

_SCHEMA = [
    {"id": "root", "component": "Column", "children": ["title", "note", "card"]},
    {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
    {"id": "note", "component": "TastingNoteCard", "note": {"path": "/note"}},
    {"id": "card", "component": "ServiceCard", "card": {"path": "/service_card"}},
]


def present_note(note: dict) -> dict:
    return {field: note[field] for field in _NOTE_FIELDS}


def present_notes(payload: dict) -> dict:
    return {"notes": [present_note(note) for note in payload["notes"]]}


def present_card(card: dict) -> dict:
    return {field: card[field] for field in _CARD_FIELDS}


def present_cards(payload: dict) -> dict:
    return {"service_cards": [present_card(card) for card in payload["service_cards"]]}


def with_draft(payload: dict) -> dict:
    note = present_note(payload["note"])
    card = present_card(payload["service_card"])
    title = f"Tasting note · {note['product_name']}"
    body = {"note": note, "service_card": card}
    body["a2ui_operations"] = surface(
        "tasting-note",
        _SCHEMA,
        {"title": title, "note": note, "service_card": card},
    )
    return body
