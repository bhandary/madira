from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from madira.agents.presenters.lists import with_list
from madira.domain.lists.service import curate, list_lists
from madira.rbac import Capability, require
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
