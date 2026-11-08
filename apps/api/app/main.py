"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import APP_VERSION, Settings, get_settings
from app.db import Database
from app.errors import install_error_handlers
from app.routers import devices, engine, health, packs, posts, sync, zones
from app.services.pack_service import PackStore
from app.services.rate_limit import RateLimiter
from app.services.reference_data import load_seed

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None, database: Database | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if database is None:
            await app.state.db.dispose()

    app = FastAPI(title="Field Shift Togo API", version=APP_VERSION, lifespan=lifespan)
    app.state.settings = settings
    app.state.db = database or Database(settings.database_url)
    app.state.packs = PackStore(settings.packs_path).scan()
    app.state.seed = load_seed(settings.seed_path)
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_min)

    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["ETag"],
    )
    install_error_handlers(app)

    for r in (
        health.router, zones.router, packs.router, engine.router,
        devices.router, sync.router, posts.router,
    ):  # fmt: skip
        app.include_router(r, prefix=API_PREFIX)
    return app


app = create_app()
