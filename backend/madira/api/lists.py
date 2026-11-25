from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from madira.agents.presenters.lists import with_list
from madira.domain.errors import DraftFailed, NotFound
from madira.domain.lists.versions import ListVersionError
from madira.domain.lists import versions as list_versions
from madira.domain.lists.csv_import import ImportRejected, import_csv
from madira.domain.lists.service import (
    add_item,
    coverage_for,
    curate,
    health_for,
    list_lists,
    pricing_rules,
    remove_item,
    save_pricing_rules,
    save_sections,
    update_item,
)
from madira.rbac import Capability, require
from madira.storage import StorageError, upload_max_bytes
from madira.tenancy import STAFF, active_venue_id, current_request

router = APIRouter()

_HIDDEN = (
    "cost",
    "margin_pct",
    "beverage_cost_pct",
    "line_cost",
    "rule_bottle_price",
    "rule_glass_price",
    "spend",
)


class ListBody(BaseModel):
    budget: float = 12000
    target_margin: float = 3.2
    target_beverage_cost_pct: float | None = None
    concept: str = ""
    price_tier: str = ""
    name: str = "Maison Madira autumn list"
    menu_id: uuid.UUID | None = None


class PricingRuleBody(BaseModel):
    category: str
    cost_min_cents: int
    cost_max_cents: int | None = None
    bottle_multiple: float
    glass_pours_per_bottle: int = 5
    glass_multiple: float = 1.2
    round_to_cents: int = 100


class PricingRulesBody(BaseModel):
    rules: list[PricingRuleBody]


class ItemBody(BaseModel):
    sku_id: uuid.UUID
    section: str = ""


class ItemPatch(BaseModel):
    reprice: bool = False
    pour_price: int | None = None
    bottle_price: int | None = None
    position: int | None = None
    section: str | None = None


class SectionBody(BaseModel):
    name: str
    position: int = 0
    budget_share_pct: float | None = None


class SectionsBody(BaseModel):
    sections: list[SectionBody] = Field(min_length=1)


class DecisionBody(BaseModel):
    comment: str | None = None


def _fail(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, exc.message)
    if isinstance(exc, ListVersionError):
        return HTTPException(exc.status, exc.message)
    if isinstance(exc, DraftFailed):
        return HTTPException(exc.status, exc.message)
    raise exc


def _strip_cost(payload: dict) -> dict:
    """Staff can read the list. Cost and margin stay off that response."""

    ctx = current_request()
    if ctx is None or ctx.role != STAFF:
        return payload
    for row in payload.get("lists", []):
        for item in row.get("items", []):
            for key in _HIDDEN:
                item.pop(key, None)
        for section in row.get("sections", []):
            for key in _HIDDEN:
                section.pop(key, None)
        for candidate in row.get("candidates", []):
            candidate.pop("cost", None)
    return payload


@router.get("/lists/pricing-rules", dependencies=[require(Capability.EDIT)])
def get_pricing_rules() -> dict[str, Any]:
    try:
        return pricing_rules(active_venue_id())
    except NotFound as exc:
        raise _fail(exc) from exc


@router.put("/lists/pricing-rules", dependencies=[require(Capability.EDIT)])
def put_pricing_rules(body: PricingRulesBody) -> dict[str, Any]:
    try:
        return save_pricing_rules(active_venue_id(), [rule.model_dump() for rule in body.rules])
    except (NotFound, DraftFailed) as exc:
        raise _fail(exc) from exc


@router.post("/lists/curate", dependencies=[require(Capability.EDIT)])
def lists_curate(body: ListBody) -> dict[str, Any]:
    try:
        payload = curate(
            active_venue_id(),
            budget=body.budget,
            target_margin=body.target_margin,
            name=body.name,
            target_beverage_cost_pct=body.target_beverage_cost_pct,
            concept=body.concept,
            price_tier=body.price_tier,
            menu_id=body.menu_id,
        )
    except (NotFound, DraftFailed) as exc:
        raise _fail(exc) from exc
    return with_list(payload)


@router.get("/lists", dependencies=[require(Capability.FLOOR)])
def lists() -> dict[str, Any]:
    return _strip_cost(list_lists(active_venue_id()))


@router.get("/lists/{list_id}/coverage", dependencies=[require(Capability.RECORDS)])
def list_coverage(list_id: uuid.UUID) -> dict[str, Any]:
    try:
        return coverage_for(active_venue_id(), list_id)
    except NotFound as exc:
        raise _fail(exc) from exc


@router.get("/lists/{list_id}/health", dependencies=[require(Capability.RECORDS)])
def list_health_route(list_id: uuid.UUID) -> dict[str, Any]:
    try:
        return health_for(active_venue_id(), list_id)
    except NotFound as exc:
        raise _fail(exc) from exc


@router.post("/lists/{list_id}/items", dependencies=[require(Capability.EDIT)])
def post_item(list_id: uuid.UUID, body: ItemBody) -> dict[str, Any]:
    try:
        payload = add_item(active_venue_id(), list_id, body.sku_id, body.section)
    except (NotFound, DraftFailed) as exc:
        raise _fail(exc) from exc
    return with_list(payload)


@router.patch("/lists/{list_id}/items/{item_id}", dependencies=[require(Capability.EDIT)])
def patch_item(list_id: uuid.UUID, item_id: uuid.UUID, body: ItemPatch) -> dict[str, Any]:
    try:
        payload = update_item(active_venue_id(), list_id, item_id, body.model_dump(exclude_unset=True))
    except (NotFound, DraftFailed) as exc:
        raise _fail(exc) from exc
    return with_list(payload)


@router.delete("/lists/{list_id}/items/{item_id}", dependencies=[require(Capability.EDIT)])
def delete_item(list_id: uuid.UUID, item_id: uuid.UUID) -> dict[str, Any]:
    try:
        payload = remove_item(active_venue_id(), list_id, item_id)
    except (NotFound, DraftFailed) as exc:
        raise _fail(exc) from exc
    return with_list(payload)


@router.put("/lists/{list_id}/sections", dependencies=[require(Capability.EDIT)])
def put_sections(list_id: uuid.UUID, body: SectionsBody) -> dict[str, Any]:
    try:
        payload = save_sections(active_venue_id(), list_id, [section.model_dump() for section in body.sections])
    except (NotFound, DraftFailed) as exc:
        raise _fail(exc) from exc
    return with_list(payload)


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


@router.post("/lists/{list_id}/versions", dependencies=[require(Capability.EDIT)])
def post_list_version(list_id: uuid.UUID) -> dict[str, Any]:
    try:
        return list_versions.snapshot_draft(active_venue_id(), list_id, current_request())
    except (NotFound, ListVersionError) as exc:
        raise _fail(exc) from exc


@router.get("/lists/{list_id}/versions", dependencies=[require(Capability.RECORDS)])
def get_list_versions(list_id: uuid.UUID) -> dict[str, Any]:
    try:
        return list_versions.list_versions(active_venue_id(), list_id, current_request())
    except NotFound as exc:
        raise _fail(exc) from exc


@router.get("/lists/versions/{version_id}", dependencies=[require(Capability.RECORDS)])
def get_list_version(version_id: uuid.UUID) -> dict[str, Any]:
    try:
        return list_versions.get_version(active_venue_id(), version_id, current_request())
    except NotFound as exc:
        raise _fail(exc) from exc


@router.get("/lists/versions/{version_id}/diff", dependencies=[require(Capability.RECORDS)])
def get_list_version_diff(version_id: uuid.UUID) -> dict[str, Any]:
    try:
        return list_versions.diff_version(active_venue_id(), version_id)
    except NotFound as exc:
        raise _fail(exc) from exc


@router.post("/lists/versions/{version_id}/submit", dependencies=[require(Capability.LIST_PUBLISH_SUBMIT)])
def post_list_version_submit(version_id: uuid.UUID) -> dict[str, Any]:
    try:
        return list_versions.submit_version(active_venue_id(), version_id, current_request())
    except (NotFound, ListVersionError) as exc:
        raise _fail(exc) from exc


@router.post("/lists/versions/{version_id}/approve", dependencies=[require(Capability.LIST_PUBLISH_DECIDE)])
def post_list_version_approve(version_id: uuid.UUID, body: DecisionBody | None = None) -> dict[str, Any]:
    comment = None if body is None else body.comment
    try:
        return list_versions.approve(active_venue_id(), version_id, current_request(), comment)
    except (NotFound, ListVersionError) as exc:
        raise _fail(exc) from exc


@router.post("/lists/versions/{version_id}/reject", dependencies=[require(Capability.LIST_PUBLISH_DECIDE)])
def post_list_version_reject(version_id: uuid.UUID, body: DecisionBody | None = None) -> dict[str, Any]:
    comment = None if body is None else body.comment
    try:
        return list_versions.reject(active_venue_id(), version_id, current_request(), comment)
    except (NotFound, ListVersionError) as exc:
        raise _fail(exc) from exc


@router.get("/lists/versions/{version_id}/pdf", dependencies=[require(Capability.RECORDS)])
def get_list_version_pdf(version_id: uuid.UUID) -> Response:
    try:
        filename, payload = list_versions.version_pdf(active_venue_id(), version_id)
    except NotFound as exc:
        raise _fail(exc) from exc
    quoted = filename.replace('"', "")
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{quoted}"'},
    )


@router.get("/lists/versions/{version_id}/qr.png", dependencies=[require(Capability.EDIT)])
def get_list_version_qr(version_id: uuid.UUID) -> Response:
    try:
        payload = list_versions.version_qr(active_venue_id(), version_id)
    except NotFound as exc:
        raise _fail(exc) from exc
    return Response(content=payload, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/lists/versions/{version_id}/revoke-public", dependencies=[require(Capability.EDIT)])
def post_list_version_revoke(version_id: uuid.UUID) -> dict[str, Any]:
    try:
        return list_versions.revoke_public(active_venue_id(), version_id, current_request())
    except (NotFound, ListVersionError) as exc:
        raise _fail(exc) from exc


@router.get("/public/lists/{token}")
def get_public_list(token: str) -> dict[str, Any]:
    try:
        return list_versions.public_list(token)
    except NotFound as exc:
        raise HTTPException(404, "Not found.") from exc
