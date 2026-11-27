from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from madira.agents.checkpointer import get_checkpointer
from madira.api.agent import mount_agui, router as agent_router
from madira.api.catalog import router as catalog_router
from madira.api.compliance import router as compliance_router
from madira.api.health import fixtures_router, router as health_router, status_router
from madira.api.counts import router as counts_router
from madira.api.inventory import router as inventory_router
from madira.api.jobs import router as jobs_router
from madira.api.storage import router as storage_router
from madira.api.lists import router as lists_router
from madira.api.menus import router as menus_router
from madira.api.notes import router as notes_router
from madira.api.offers import router as offers_router
from madira.api.pos import router as pos_router
from madira.api.queries import router as queries_router
from madira.api.reminders import router as reminders_router
from madira.api.usage import router as usage_router
from madira.api.sensors import router as sensors_router
from madira.api.procurement import router as procurement_router
from madira.api.purchasing import router as purchasing_router
from madira.api.settings import router as settings_router
from madira.api.sourcing import router as sourcing_router
from madira.api.tastings import router as tastings_router
from madira.api.team import router as team_router
from madira.api.tablet import router as tablet_router
from madira.api.tonight import router as tonight_router
from madira.api.training import router as training_router
from madira.auth import router as auth_router
from madira.config import FRONTEND_ORIGIN, HOST, PORT
from madira.db import init_db
from madira.domain.errors import Unavailable
from madira.response_schema import install_response_models
from madira.seed import seed
from madira.tenancy import TenancyMiddleware

app = FastAPI(title="Madira", version="0.1.0")
# Added last so CORS wraps tenancy and 401 responses still carry the allow-origin header.
app.add_middleware(TenancyMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN.rstrip("/")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(settings_router)
app.include_router(status_router)
app.include_router(agent_router)
app.include_router(menus_router)
app.include_router(lists_router)
app.include_router(catalog_router)
app.include_router(notes_router)
app.include_router(inventory_router)
app.include_router(jobs_router)
app.include_router(storage_router)
app.include_router(counts_router)
app.include_router(compliance_router)
app.include_router(purchasing_router)
app.include_router(training_router)
app.include_router(team_router)
app.include_router(tablet_router)
app.include_router(tonight_router)
app.include_router(procurement_router)
app.include_router(tastings_router)
app.include_router(sourcing_router)
app.include_router(offers_router)
app.include_router(pos_router)
app.include_router(sensors_router)
app.include_router(reminders_router)
app.include_router(queries_router)
app.include_router(usage_router)
app.include_router(fixtures_router)

install_response_models(app)


@app.exception_handler(Unavailable)
def unavailable(_request: Request, exc: Unavailable) -> JSONResponse:
    return JSONResponse(status_code=501, content={"detail": exc.message})


@app.on_event("startup")
def _startup() -> None:
    init_db()
    seed()
    get_checkpointer()
    mount_agui(app)


def main() -> None:
    import uvicorn

    uvicorn.run("madira.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
