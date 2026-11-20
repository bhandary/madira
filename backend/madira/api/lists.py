from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from madira.agents.presenters.lists import with_list
from madira.domain.errors import NotFound
from madira.domain.lists.csv_import import ImportRejected, import_csv
from madira.domain.lists.service import curate, list_lists
from madira.rbac import Capability, require
from madira.storage import StorageError, upload_max_bytes
from madira.tenancy import active_venue_id

router = APIRouter()


class ListBody(BaseModel):
    budget: float = 12000
    target_margin: float = 3.2
    name: str = "Maison Madira autumn list"


@router.post("/lists/curate", dependencies=[require(Capability.EDIT)])
def lists_curate(body: ListBody) -> dict[str, Any]:
    payload = curate(active_venue_id(), budget=body.budget, target_margin=body.target_margin, name=body.name)
    return with_list(payload)


@router.get("/lists", dependencies=[require(Capability.FLOOR)])
def lists() -> dict[str, Any]:
    return list_lists(active_venue_id())


@router.post("/lists/import", dependencies=[require(Capability.EDIT)])
def import_list(
    file: UploadFile = File(),
    confirm: str = Form(default="false"),
    name: str = Form(default=""),
) -> dict[str, Any]:
    # Sync, like the other list routes, so the role dependency's venue binding is visible.
    body = file.file.read(upload_max_bytes() + 1)
    writing = confirm.strip().lower() in {"1", "true", "yes", "on"}
    try:
        return import_csv(
            active_venue_id(),
            filename=file.filename or "",
            body=body,
            content_type=file.content_type,
            confirm=writing,
            name=name,
        )
    except StorageError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    except ImportRejected as exc:
        raise HTTPException(exc.status, exc.message) from exc
    except NotFound as exc:
        raise HTTPException(404, exc.message) from exc
