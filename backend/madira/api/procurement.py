from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from madira.domain.procurement.service import list_suppliers
from madira.rbac import Capability, require
from madira.tenancy import active_venue_id

router = APIRouter()


@router.get("/suppliers", dependencies=[require(Capability.RECORDS)])
def suppliers() -> dict[str, Any]:
    return list_suppliers(active_venue_id())
