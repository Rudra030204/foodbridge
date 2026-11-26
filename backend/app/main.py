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

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Single-service deployment: if a built frontend exists (backend/static, or STATIC_DIR), serve it from this app."""
    import os
    from pathlib import Path

    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    root = Path(os.environ.get("STATIC_DIR") or Path(__file__).resolve().parents[1] / "static")
    index = root / "index.html"
    if not index.is_file():
        return
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith(("api/", "ws")) or path in ("docs", "openapi.json", "redoc"):
            return JSONResponse({"error": {"code": "not_found", "message": "Not found"}}, status_code=404)
        f = (root / path).resolve()
        if path and f.is_file() and root.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(index)  # client-side routes (/donor, /login, ...)


app = create_app()
