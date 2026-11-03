from __future__ import annotations

import io
import json
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from madira.agents.orchestrator import (
    SPECIALIST_NAMES,
    inspect_subagents,
    invoke_head_sommelier,
)
from madira.agents.tools import (
    curate_beverage_list,
    draft_purchase_orders,
    get_inventory,
    get_training_briefing,
    grade_quiz,
    list_tastings,
    parse_menu,
    recommend_pairings,
    schedule_tasting,
    start_roleplay,
    update_stock,
)
from madira.config import FRONTEND_ORIGIN, HOST, PORT, status_payload
from madira.db import SessionLocal, init_db
from madira.fixtures_data import SAMPLE_MENU_TEXT
from madira.models import BeverageList, Menu, PurchaseOrder, QuizAttempt, Supplier, Tasting
from madira.seed import seed

app = FastAPI(title="Madira", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    seed()
    _mount_agui()


def _mount_agui() -> None:
    try:
        from ag_ui_langgraph import add_langgraph_fastapi_endpoint
        from copilotkit import LangGraphAGUIAgent

        from madira.agents.orchestrator import build_head_sommelier

        add_langgraph_fastapi_endpoint(
            app=app,
            agent=LangGraphAGUIAgent(
                name="head_sommelier",
                description="Maison Madira Head Sommelier. Delegates to menu, pairing, list, inventory, training, and supplier specialists.",
                graph=build_head_sommelier(),
            ),
            path="/ag-ui",
        )
    except Exception as exc:  # pragma: no cover - optional bridge
        app.state.agui_error = str(exc)


class AgentRunBody(BaseModel):
    message: str
    thread_id: str | None = None


class StockBody(BaseModel):
    on_hand: int = Field(ge=0)


class QuizBody(BaseModel):
    answers: str
    staff_name: str = "Floor"


class TastingBody(BaseModel):
    supplier_name: str = "Kermit Lynch Wine Merchant"
    title: str = "New Loire releases tasting"
    starts_at: str = ""
    ends_at: str = ""
    location: str = "Maison Madira cellar"
    notes: str = "Draft hold — export .ics, do not send invites."


class ListBody(BaseModel):
    budget: float = 12000
    target_margin: float = 3.2
    name: str = "Maison Madira autumn list"


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", **status_payload()}


@app.get("/status")
def status() -> dict[str, Any]:
    payload = status_payload()
    payload["specialists"] = list(SPECIALIST_NAMES)
    payload["sample_menu"] = SAMPLE_MENU_TEXT
    try:
        payload["wiring"] = inspect_subagents()
    except Exception as exc:
        payload["wiring_error"] = str(exc)
    return payload


@app.post("/agent/run")
def agent_run(body: AgentRunBody) -> dict[str, Any]:
    return invoke_head_sommelier(body.message, thread_id=body.thread_id)


def _extract_upload_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return SAMPLE_MENU_TEXT + "\n\n[image upload in demo mode — using Maison Madira fixture]"
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return SAMPLE_MENU_TEXT


@app.post("/menus/upload")
async def upload_menu(
    file: UploadFile | None = File(default=None),
    text: str = Form(default=""),
    source_name: str = Form(default="upload"),
) -> dict[str, Any]:
    raw = text
    if file is not None:
        data = await file.read()
        extracted = _extract_upload_text(file.filename or "", data)
        raw = (raw + "\n" + extracted).strip() if raw else extracted
        source_name = file.filename or source_name
    if not raw.strip():
        raw = SAMPLE_MENU_TEXT
    return json.loads(parse_menu(raw, source_name=source_name))


@app.post("/menus/parse")
def parse_menu_route(body: dict[str, Any]) -> dict[str, Any]:
    return json.loads(parse_menu(body.get("text") or SAMPLE_MENU_TEXT, source_name=body.get("source_name") or "pasted"))


@app.get("/menus")
def list_menus() -> dict[str, Any]:
    session = SessionLocal()
    try:
        menus = session.scalars(select(Menu).order_by(Menu.id.desc())).all()
        return {
            "menus": [
                {
                    "id": m.id,
                    "name": m.name,
                    "cuisine": m.cuisine,
                    "price_tier": m.price_tier,
                    "dish_count": len(m.dishes),
                }
                for m in menus
            ]
        }
    finally:
        session.close()


@app.get("/menus/{menu_id}")
def get_menu(menu_id: int) -> dict[str, Any]:
    session = SessionLocal()
    try:
        menu = session.get(Menu, menu_id)
        if not menu:
            raise HTTPException(404, "menu not found")
        dishes = []
        for dish in menu.dishes:
            dishes.append(
                {
                    "id": dish.id,
                    "name": dish.name,
                    "course": dish.course,
                    "flavor_profile": dish.flavor_profile,
                    "price": dish.price,
                    "pairings": [
                        {
                            "category": p.category,
                            "name": p.name,
                            "producer": p.producer,
                            "region": p.region,
                            "style": p.style,
                            "rationale": p.rationale,
                            "price_tier": p.price_tier,
                            "glass_price": p.glass_price,
                            "bottle_price": p.bottle_price,
                        }
                        for p in dish.pairings
                    ],
                }
            )
        return {
            "id": menu.id,
            "name": menu.name,
            "cuisine": menu.cuisine,
            "price_tier": menu.price_tier,
            "raw_text": menu.raw_text,
            "dishes": dishes,
        }
    finally:
        session.close()


@app.post("/menus/{menu_id}/pair")
def pair_menu(menu_id: int) -> dict[str, Any]:
    return json.loads(recommend_pairings(menu_id))


@app.post("/lists/curate")
def lists_curate(body: ListBody) -> dict[str, Any]:
    return json.loads(curate_beverage_list(budget=body.budget, target_margin=body.target_margin, name=body.name))


@app.get("/lists")
def lists() -> dict[str, Any]:
    session = SessionLocal()
    try:
        rows = session.scalars(select(BeverageList).order_by(BeverageList.id.desc())).all()
        return {
            "lists": [
                {
                    "id": row.id,
                    "name": row.name,
                    "budget": row.budget,
                    "target_margin": row.target_margin,
                    "item_count": len(row.items),
                    "notes": row.notes,
                    "items": [
                        {
                            "category": i.category,
                            "name": i.name,
                            "producer": i.producer,
                            "region": i.region,
                            "style": i.style,
                            "cost": i.cost,
                            "pour_price": i.pour_price,
                            "bottle_price": i.bottle_price,
                            "margin_pct": i.margin_pct,
                        }
                        for i in row.items
                    ],
                }
                for row in rows
            ]
        }
    finally:
        session.close()


@app.get("/inventory")
def inventory() -> dict[str, Any]:
    return json.loads(get_inventory())


@app.patch("/inventory/{sku}")
def inventory_patch(sku: str, body: StockBody) -> dict[str, Any]:
    return json.loads(update_stock(sku, body.on_hand))


@app.post("/purchase-orders/draft")
def po_draft() -> dict[str, Any]:
    return json.loads(draft_purchase_orders())


@app.get("/purchase-orders")
def po_list() -> dict[str, Any]:
    session = SessionLocal()
    try:
        rows = session.scalars(select(PurchaseOrder).order_by(PurchaseOrder.id.desc())).all()
        return {
            "orders": [
                {
                    "id": po.id,
                    "status": po.status,
                    "supplier": po.supplier.name if po.supplier else "",
                    "notes": po.notes,
                    "lines": [
                        {"sku": line.sku, "name": line.name, "qty": line.qty, "unit_cost": line.unit_cost}
                        for line in po.lines
                    ],
                }
                for po in rows
            ]
        }
    finally:
        session.close()


@app.get("/training")
def training() -> dict[str, Any]:
    return json.loads(get_training_briefing())


@app.post("/training/quiz")
def training_quiz(body: QuizBody) -> dict[str, Any]:
    return json.loads(grade_quiz(body.answers, staff_name=body.staff_name))


@app.post("/training/roleplay")
def training_roleplay() -> dict[str, Any]:
    return json.loads(start_roleplay())


@app.get("/training/progress")
def training_progress() -> dict[str, Any]:
    session = SessionLocal()
    try:
        attempts = session.scalars(select(QuizAttempt).order_by(QuizAttempt.id.desc())).all()
        return {
            "attempts": [
                {"id": a.id, "staff_name": a.staff_name, "score": a.score, "answers": a.answers}
                for a in attempts
            ]
        }
    finally:
        session.close()


@app.get("/tastings")
def tastings() -> dict[str, Any]:
    return json.loads(list_tastings())


@app.post("/tastings")
def tastings_create(body: TastingBody) -> dict[str, Any]:
    return json.loads(
        schedule_tasting(
            supplier_name=body.supplier_name,
            title=body.title,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            location=body.location,
            notes=body.notes,
        )
    )


@app.get("/tastings/{tasting_id}/ics")
def tasting_ics(tasting_id: int) -> PlainTextResponse:
    session = SessionLocal()
    try:
        tasting = session.get(Tasting, tasting_id)
        if not tasting:
            raise HTTPException(404, "tasting not found")
        return PlainTextResponse(tasting.ics, media_type="text/calendar")
    finally:
        session.close()


@app.get("/suppliers")
def suppliers() -> dict[str, Any]:
    session = SessionLocal()
    try:
        rows = session.scalars(select(Supplier)).all()
        return {
            "suppliers": [
                {"id": s.id, "name": s.name, "kind": s.kind, "contact_email": s.contact_email, "notes": s.notes}
                for s in rows
            ]
        }
    finally:
        session.close()


@app.get("/fixtures/sample-menu")
def sample_menu() -> dict[str, str]:
    return {"text": SAMPLE_MENU_TEXT}


def main() -> None:
    import uvicorn

    uvicorn.run("madira.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
