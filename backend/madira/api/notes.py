from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from madira.agents.presenters.notes import present_card, present_cards, present_note, present_notes, with_draft
from madira.domain.catalog.notes import (
    approve_card,
    approve_note,
    draft_note,
    edit_card,
    edit_note,
    enter_note,
    get_card,
    get_note,
    list_cards,
    list_notes,
    store_tech_sheet,
)
from madira.domain.catalog.schemas import CardEdit, NoteDraft, NoteEdit
from madira.domain.errors import DraftFailed, NotFound
from madira.rbac import Capability, require
from madira.storage import StorageError, upload_max_bytes
from madira.tenancy import active_venue_id

router = APIRouter()


def _guard(call):
    try:
        return call()
    except NotFound as exc:
        raise HTTPException(404, exc.message) from exc
    except DraftFailed as exc:
        raise HTTPException(exc.status, exc.message) from exc
    except StorageError as exc:
        raise HTTPException(exc.status, exc.message) from exc


@router.get("/products/{product_id}/notes", dependencies=[require(Capability.FLOOR)])
def notes(product_id: uuid.UUID) -> dict[str, Any]:
    return _guard(lambda: present_notes(list_notes(active_venue_id(), product_id)))


@router.get("/products/{product_id}/notes/{note_id}", dependencies=[require(Capability.FLOOR)])
def note(product_id: uuid.UUID, note_id: uuid.UUID) -> dict[str, Any]:
    return _guard(lambda: present_note(get_note(active_venue_id(), product_id, note_id)))


@router.post("/products/{product_id}/notes", dependencies=[require(Capability.EDIT)])
def create_note(product_id: uuid.UUID, body: NoteDraft) -> dict[str, Any]:
    return _guard(lambda: with_draft(enter_note(active_venue_id(), product_id, body)))


@router.post("/products/{product_id}/notes/draft", dependencies=[require(Capability.EDIT)])
def create_draft(
    product_id: uuid.UUID,
    tech_sheet: str = Form(default=""),
    file: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    venue_id = active_venue_id()

    def run() -> dict[str, Any]:
        text = tech_sheet.strip()
        key = ""
        if file is not None:
            raw = file.file.read(upload_max_bytes() + 1)
            if raw or (file.filename or "").strip():
                extracted, key = store_tech_sheet(
                    venue_id,
                    filename=file.filename or "tech-sheet.txt",
                    body=raw,
                    content_type=file.content_type,
                )
                text = "\n\n".join(part for part in (extracted, text) if part)
        return with_draft(draft_note(venue_id, product_id, tech_sheet=text, tech_sheet_key=key))

    return _guard(run)


@router.patch("/products/{product_id}/notes/{note_id}", dependencies=[require(Capability.EDIT)])
def update_note(product_id: uuid.UUID, note_id: uuid.UUID, body: NoteEdit) -> dict[str, Any]:
    return _guard(lambda: present_note(edit_note(active_venue_id(), product_id, note_id, body)))


@router.post("/products/{product_id}/notes/{note_id}/approve", dependencies=[require(Capability.EDIT)])
def approve_one_note(product_id: uuid.UUID, note_id: uuid.UUID) -> dict[str, Any]:
    return _guard(lambda: present_note(approve_note(active_venue_id(), product_id, note_id)))


@router.get("/products/{product_id}/service-cards", dependencies=[require(Capability.FLOOR)])
def cards(product_id: uuid.UUID) -> dict[str, Any]:
    return _guard(lambda: present_cards(list_cards(active_venue_id(), product_id)))


@router.get("/products/{product_id}/service-cards/{card_id}", dependencies=[require(Capability.FLOOR)])
def card(product_id: uuid.UUID, card_id: uuid.UUID) -> dict[str, Any]:
    return _guard(lambda: present_card(get_card(active_venue_id(), product_id, card_id)))


@router.patch("/products/{product_id}/service-cards/{card_id}", dependencies=[require(Capability.EDIT)])
def update_card(product_id: uuid.UUID, card_id: uuid.UUID, body: CardEdit) -> dict[str, Any]:
    return _guard(lambda: present_card(edit_card(active_venue_id(), product_id, card_id, body)))


@router.post("/products/{product_id}/service-cards/{card_id}/approve", dependencies=[require(Capability.EDIT)])
def approve_one_card(product_id: uuid.UUID, card_id: uuid.UUID) -> dict[str, Any]:
    return _guard(lambda: present_card(approve_card(active_venue_id(), product_id, card_id)))
