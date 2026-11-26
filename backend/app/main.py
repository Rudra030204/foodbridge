"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, analytics, auth, claims, listings, misc, pickups, ws
from app.core.config import settings
from app.core.errors import install_error_handlers
from app.db.base import Base
from app.db.session import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("foodbridge")

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)  # idempotent safety net; Alembic is the source of truth
    scheduler = None
    if settings.SCHEDULER_ENABLED:
        from app.jobs.scheduler import start_scheduler

        scheduler = start_scheduler()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="FoodBridge Plus API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )
    install_error_handlers(app)
    for r in (auth.router, listings.router, claims.router, pickups.router, misc.router, analytics.router, admin.router):
        app.include_router(r, prefix=API_PREFIX)
    app.include_router(ws.router)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
