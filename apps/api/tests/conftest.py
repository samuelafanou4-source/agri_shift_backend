from __future__ import annotations

import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
for p in (str(API_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.config import Settings
from app.db import Database
from app.main import create_app
from app.services.reference_data import load_seed
from app.services.seed_service import seed_all


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture(scope="session")
def packs_dir(tmp_path_factory) -> Path:
    """Offline (synthetic_demo) packs in a temp folder: API tests never depend on the network."""
    from datetime import UTC, datetime

    from pipeline.build_packs import write_packs
    from pipeline.synthetic_fallback import synthetic_climatology

    seed = load_seed(REPO_ROOT / "data" / "seed")
    out = tmp_path_factory.mktemp("packs")
    clims = {z.zone_id: synthetic_climatology(z) for z in seed.zones}
    write_packs(seed, clims, out, now=datetime(2026, 11, 4, 10, tzinfo=UTC))
    return out


@pytest.fixture
def settings(sqlite_url: str, packs_dir: Path) -> Settings:
    return Settings(
        database_url=sqlite_url,
        packs_dir=str(packs_dir),
        data_dir=str(REPO_ROOT / "data"),
        rate_limit_per_min=10_000,
    )


@pytest.fixture
async def db(settings: Settings):
    database = Database(settings.database_url)
    await database.create_all()
    yield database
    await database.dispose()


@pytest.fixture
async def seeded_db(db: Database, settings: Settings):
    async with db.session_factory() as session:
        await seed_all(
            session,
            load_seed(settings.seed_path),
            settings.data_path / "synthetic" / "parcelles_demo.json",
        )
    return db


@pytest.fixture
async def client(settings: Settings, seeded_db: Database):
    app = create_app(settings, database=seeded_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
