"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Database
from app.services.pack_service import PackStore
from app.services.reference_data import SeedData


def get_database(request: Request) -> Database:
    return request.app.state.db


def get_pack_store(request: Request) -> PackStore:
    return request.app.state.packs


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    db: Database = request.app.state.db
    async with db.session_factory() as session:
        yield session


def get_seed(request: Request) -> SeedData:
    return request.app.state.seed
