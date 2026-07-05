"""FastAPI application entry point.

Run locally:   uvicorn app.main:app --reload
In production: systemd unit deploy/jobsearch-api.service
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    ai,
    applications,
    auth,
    jobs,
    preferences,
    resumes,
    telegram,
)
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    # Shared ARQ pool for enqueueing background jobs (see api/deps.py:get_arq).
    app.state.arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield
    await app.state.arq.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Job Search Platform API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,  # no public API docs in prod
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (
        auth.router,
        preferences.router,
        jobs.router,
        applications.router,
        resumes.router,
        ai.router,
        telegram.router,
    ):
        app.include_router(router)

    @app.get("/health", tags=["ops"])
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
