"""FastAPI application factory."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from api.routes import router as api_router
from config import settings
from config.logging import logger, setup_logging
from models.database import init_db
from services.scheduler import init_scheduler, shutdown_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Booting Intelligent-Investment-Research-Multi-Agent...")
    await init_db()
    init_scheduler()
    yield
    shutdown_scheduler()
    logger.info("Shutdown complete.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Intelligent Investment Research Multi-Agent",
        version="1.0.0",
        description="基于 LangGraph 的多智能体投资研究系统 - by Qoder",
        lifespan=lifespan,
    )
    # Round-2 fix #3 (api/app.py:42, config/settings.py:45):
    # Combining `Access-Control-Allow-Origin: *` with
    # `Access-Control-Allow-Credentials: true` is rejected by every modern
    # browser per the Fetch spec. Resolve the conflict by:
    #   * Disabling credentials when the wildcard origin is in use, OR
    #   * Honouring an explicit allow-list when one is configured.
    origins = settings.cors_origins_list
    allow_credentials = "*" not in origins
    if not allow_credentials:
        logger.warning(
            "[CORS] CORS_ORIGINS=* — disabling allow_credentials to comply with "
            "the Fetch spec. Set CORS_ORIGINS to an explicit allow-list to "
            "re-enable credentialed requests."
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=allow_credentials,
    )
    app.include_router(api_router, prefix="/api/v1")

    static_dir = Path(settings.project_root) / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        async def root_index() -> HTMLResponse:
            index_file = static_dir / "index.html"
            if index_file.exists():
                return HTMLResponse(index_file.read_text(encoding="utf-8"))
            return HTMLResponse("<h1>Intelligent Investment Research</h1><p>静态面板未部署。</p>")

    @app.get("/health", include_in_schema=False)
    async def root_health():
        return {"status": "ok"}

    return app


app = create_app()
