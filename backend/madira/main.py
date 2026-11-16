from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from madira.api.agent import mount_agui, router as agent_router
from madira.api.health import fixtures_router, router as health_router, status_router
from madira.api.inventory import router as inventory_router
from madira.api.lists import router as lists_router
from madira.api.menus import router as menus_router
from madira.api.procurement import router as procurement_router
from madira.api.purchasing import router as purchasing_router
from madira.api.settings import router as settings_router
from madira.api.training import router as training_router
from madira.auth import router as auth_router
from madira.config import FRONTEND_ORIGIN, HOST, PORT
from madira.db import init_db
from madira.seed import seed

app = FastAPI(title="Madira", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:3000", "http://127.0.0.1:3000", "*"],
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
app.include_router(inventory_router)
app.include_router(purchasing_router)
app.include_router(training_router)
app.include_router(procurement_router)
app.include_router(fixtures_router)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    seed()
    mount_agui(app)


def main() -> None:
    import uvicorn

    uvicorn.run("madira.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
