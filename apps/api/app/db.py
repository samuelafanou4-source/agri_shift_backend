"""Async SQLAlchemy engine / session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> AsyncEngine:
    """Async engine with the settings each backend needs.

    - SQLite: foreign keys are OFF by default; turn them on so that local runs and tests
      reject the same rows as PostgreSQL.
    - PostgreSQL (Supabase pooler): idle connections get closed server-side; `pool_pre_ping`
      replaces a dead pooled connection instead of failing the next request.
    """
    if make_url(url).get_backend_name() == "sqlite":
        engine = create_async_engine(url)

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_fk_on(dbapi_conn, _record) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return engine
    return create_async_engine(url, pool_pre_ping=True, pool_recycle=1800)


class Database:
    """Holds one engine + session factory. Replaced in tests with a temporary SQLite DB."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.engine: AsyncEngine = make_engine(url)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as s:
            yield s

    async def create_all(self) -> None:
        """Create tables directly (tests / quick local start). Production uses Alembic."""
        from app import models  # noqa: F401  (register models on Base.metadata)

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()
