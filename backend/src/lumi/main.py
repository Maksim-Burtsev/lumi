"""Lumi FastAPI application: API + Mini App static serving."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from lumi import __version__
from lumi.api.router import api_router
from lumi.config import get_settings
from lumi.logging import get_logger, setup_logging

log = get_logger(__name__)


def _find_static_dir() -> Path | None:
    """Mini App build: docker mount first, then local repo fallback."""
    candidates = [
        Path("/app/static/app"),
        Path(__file__).resolve().parents[3] / "frontend" / "dist",
    ]
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    if settings.auto_migrate and settings.is_local:
        import asyncio

        from alembic import command
        from alembic.config import Config

        def _migrate() -> None:
            config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
            command.upgrade(config, "head")

        await asyncio.to_thread(_migrate)
        log.info("auto-migration applied")
    log.info("lumi api started", fields={"env": settings.app_env, "version": __version__})
    yield
    from lumi.db.session import dispose_engine
    from lumi.services.realtime import close_realtime
    from lumi.worker.queue import close_queue

    await close_realtime()
    await close_queue()
    await dispose_engine()
    log.info("lumi api stopped")


settings = get_settings()
app = FastAPI(
    title="Lumi",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs" if settings.is_local else None,
    redoc_url=None,
)

# --- CORS -------------------------------------------------------------------
origins = {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000"}
if settings.app_public_url:
    origins.add(settings.app_public_url.rstrip("/"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Error shape ({"error": code}) -------------------------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "detail": str(exc.errors()[:3])},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled API error")
    return JSONResponse(status_code=500, content={"error": "internal_error"})


# --- Routes -------------------------------------------------------------------
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env,
            "version": __version__}


app.include_router(api_router)

_static_dir = _find_static_dir()
if _static_dir is not None:
    app.mount("/app", StaticFiles(directory=_static_dir, html=True), name="mini-app")
    log.info("mini app static mounted", fields={"dir": str(_static_dir)})
else:
    @app.get("/app", response_class=HTMLResponse)
    async def mini_app_placeholder() -> str:
        return (
            "<html><body style='font-family:system-ui;padding:40px;color:#333'>"
            "<h2>Lumi Mini App не собран</h2>"
            "<p>Выполни <code>make frontend-build</code> и перезапусти api.</p>"
            "</body></html>"
        )
