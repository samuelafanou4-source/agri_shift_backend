"""Regression tests for the issues found in the code review (one test per fixed bug)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError

from app import models as m
from app.config import API_ROOT, Settings
from app.db import Base, Database, make_engine
from app.errors import ApiError
from app.main import create_app
from app.services import sync_service
from app.services.rate_limit import RateLimiter
from app.services.reference_data import load_seed
from app.services.sync_service import SyncService

API = "/api/v1"
T1 = "2026-11-10T09:00:00Z"


async def _register(client, zone_id="kara_kara") -> dict:
    r = await client.post(
        f"{API}/devices/register", json={"device_id": str(uuid.uuid4()), "zone_id": zone_id}
    )
    assert r.status_code == 201, r.text
    return {"X-Device-Token": r.json()["device_token"]}


def _plot(**kw) -> dict:
    return {"id": str(uuid.uuid4()), "zone_id": "kara_kara", "name": "Champ", "area_ha": 1.0,
            "soil_id": "loam", "updated_at": T1, "deleted": False, **kw}  # fmt: skip


async def _device(db: Database, headers: dict) -> m.Device:
    token_hash = hashlib.sha256(headers["X-Device-Token"].encode()).hexdigest()
    async with db.session_factory() as s:
        return (
            await s.execute(select(m.Device).where(m.Device.token_hash == token_hash))
        ).scalar_one()


# ---------------------------------------------------------------- sync: server timestamps
async def test_push_rows_are_stamped_right_before_commit(client, seeded_db, settings, monkeypatch):
    """Bug: rows were stamped with the clock captured when the push STARTED. A pull running
    during a long push (Postgres round trips) got a later server_time and skipped those rows
    forever. Rows must carry a timestamp taken after all rows are processed."""
    headers = await _register(client)
    device = await _device(seeded_db, headers)
    t0 = datetime(2026, 11, 10, 8, tzinfo=UTC)
    events: list[str] = []

    def provisional():  # called while each row is processed
        events.append("row")
        return t0

    stamps_given = iter(range(1, 100))

    def fake_server_now():
        events.append("stamp")
        return t0 + timedelta(minutes=next(stamps_given))

    monkeypatch.setattr(sync_service, "now_utc", provisional)
    monkeypatch.setattr(sync_service, "server_now", fake_server_now)
    rows = [_plot(), _plot()]
    async with seeded_db.session_factory() as s:
        device = await s.get(m.Device, device.device_id)
        res = await SyncService(s, load_seed(settings.seed_path), device).push(
            sync_service.PushChanges(plots=rows)
        )
    assert res.accepted == [r["id"] for r in rows]
    async with seeded_db.session_factory() as s:
        stamps = [
            sync_service.to_utc((await s.get(m.Plot, uuid.UUID(r["id"]))).server_updated_at)
            for r in rows
        ]
    # Both rows are processed first, then stamped (in push order), then server_time.
    assert events == ["row", "row", "stamp", "stamp", "stamp"]
    assert stamps == [t0 + timedelta(minutes=1), t0 + timedelta(minutes=2)]


def test_server_clock_is_strictly_increasing(monkeypatch):
    """Bug: Windows' wall clock moves in ~15 ms steps; two stamps in the same step were equal
    or 'in the future' compared with a pull's server_time."""
    from app.services import clock

    monkeypatch.setattr(clock, "_last", clock._last)  # restored after the test
    frozen = datetime(2030, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(clock, "_wall", lambda: frozen)
    values = [clock.server_now() for _ in range(5)]
    assert all(b > a for a, b in pairwise(values))
    monkeypatch.setattr(clock, "_wall", lambda: frozen - timedelta(hours=1))  # clock steps back
    assert clock.server_now() > values[-1]


async def test_push_then_pull_twice_with_a_coarse_clock(client, monkeypatch):
    """Same wall-clock tick for push and pull (Windows): the second pull must be empty, i.e.
    rows pushed before a pull are never re-sent by the next pull (was flaky)."""
    from app.services import clock

    monkeypatch.setattr(clock, "_last", clock._last)  # restored after the test
    tick = datetime(2031, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(clock, "_wall", lambda: tick)
    headers = await _register(client)
    r = await client.post(f"{API}/sync/push", headers=headers,
                          json={"changes": {"plots": [_plot(), _plot()]}})  # fmt: skip
    assert len(r.json()["accepted"]) == 2
    first = (await client.get(f"{API}/sync/pull", headers=headers)).json()
    assert len(first["changes"]["plots"]) == 2
    params = {"since": first["server_time"]}
    second = (await client.get(f"{API}/sync/pull", params=params, headers=headers)).json()
    assert second["changes"] == {"plots": [], "plot_seasons": [], "posts": []}


# ---------------------------------------------------------------- Postgres: NUL characters
async def test_nul_character_is_rejected_not_500(client):
    """Bug: PostgreSQL cannot store U+0000 in text columns (asyncpg error -> HTTP 500)."""
    headers = await _register(client)
    r = await client.post(f"{API}/sync/push", headers=headers,
                          json={"changes": {"plots": [_plot(name="Champ\u0000nord")]}})  # fmt: skip
    assert r.status_code == 200
    assert r.json()["accepted"] == [] and r.json()["rejected"][0]["reason"] == "invalid"
    r = await client.post(f"{API}/posts", headers=headers,
                          json={"zone_id": "kara_kara", "body": "a\u0000b"})  # fmt: skip
    assert r.status_code == 422
    r = await client.post(f"{API}/devices/register",
                          json={"device_id": str(uuid.uuid4()), "display_name": "A\u0000"})  # fmt: skip
    assert r.status_code == 422
    r = await client.patch(f"{API}/devices/me", headers=headers, json={"display_name": "\u0000"})
    assert r.status_code == 422


# ---------------------------------------------------------------- dates out of range
async def test_out_of_range_dates_are_validation_errors(client):
    """Bug: 0001-01-01T00:00+05:00 overflows when converted to UTC (OverflowError -> 500)."""
    headers = await _register(client)
    bad = "0001-01-01T00:00:00+05:00"
    r = await client.post(f"{API}/sync/push", headers=headers,
                          json={"changes": {"plots": [_plot(updated_at=bad)]}})  # fmt: skip
    assert r.status_code == 200 and r.json()["rejected"][0]["reason"] == "invalid"
    r = await client.get(f"{API}/sync/pull", params={"since": bad}, headers=headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = await client.get(f"{API}/posts", params={"zone_id": "kara_kara", "before": bad})
    assert r.status_code == 422
    # A normal offset is still accepted and normalised to UTC.
    r = await client.get(f"{API}/sync/pull", params={"since": "2026-11-10T10:00:00+01:00"},
                         headers=headers)  # fmt: skip
    assert r.status_code == 200


# ---------------------------------------------------------------- error format
async def test_unexpected_errors_use_the_json_error_format(settings, seeded_db):
    """Bug: an unhandled exception returned a plain-text 500, not {"error": {...}} (§10.8);
    a concurrent duplicate insert (IntegrityError) also ended as a 500."""
    app = create_app(settings, database=seeded_db)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret detail")

    @app.get("/dup")
    async def dup():
        raise IntegrityError("INSERT ...", {}, Exception("duplicate key"))

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/boom")
        assert r.status_code == 500
        assert r.json() == {
            "error": {"code": "internal_error", "message_fr": "Erreur interne du serveur."}
        }
        assert "secret" not in r.text
        r = await c.get("/dup")
        assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


# ---------------------------------------------------------------- CORS
@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://app.example.org/", ["https://app.example.org"]),
        ("https://a.org, http://localhost:3000", ["https://a.org", "http://localhost:3000"]),
        ("http://localhost:3000", ["http://localhost:3000"]),
    ],
)
def test_cors_origins_parsing(value, expected):
    """Bug: a trailing "/" in FRONTEND_ORIGIN never matched the browser's Origin header."""
    assert Settings(frontend_origin=value).cors_origins == expected


async def test_cors_preflight_with_trailing_slash_and_two_origins(settings, seeded_db):
    s = settings.model_copy(
        update={"frontend_origin": "https://app.example.org/,http://localhost:3000"}
    )
    app = create_app(s, database=seeded_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for origin in ("https://app.example.org", "http://localhost:3000"):
            r = await c.options(f"{API}/sync/push", headers={
                "Origin": origin, "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-device-token,content-type"})  # fmt: skip
            assert r.status_code == 200 and r.headers["access-control-allow-origin"] == origin
        r = await c.get(f"{API}/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in r.headers


# ---------------------------------------------------------------- database engine
async def test_sqlite_enforces_foreign_keys_like_postgres(seeded_db):
    """Test gap: SQLite ignored foreign keys, so tests could not catch rows Postgres rejects."""
    async with seeded_db.session_factory() as s:
        s.add(m.Plot(id=uuid.uuid4(), device_id=uuid.uuid4(), zone_id="atlantis", name="x",
                     updated_at=datetime.now(UTC), server_updated_at=datetime.now(UTC),
                     deleted=False))  # fmt: skip
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_postgres_engine_pings_pooled_connections():
    """Supabase's pooler closes idle connections: without pre-ping the next request fails."""
    engine = make_engine("postgresql+asyncpg://u:p@localhost:5432/db")  # no connection opened
    try:
        assert engine.sync_engine.pool._pre_ping is True
    finally:
        await engine.dispose()


# ---------------------------------------------------------------- rate limiter memory
def test_rate_limiter_forgets_idle_keys():
    """Bug: one deque per IP/device was kept forever (memory grows with every new client)."""
    now = [0.0]
    rl = RateLimiter(5, clock=lambda: now[0], max_keys=3)
    for k in ("a", "b", "c"):
        rl.check(k)
    now[0] = 61.0
    rl.check("d")  # table full + new key -> idle keys a, b, c are purged
    assert set(rl.hits) == {"d"}
    rl2 = RateLimiter(1, clock=lambda: now[0], max_keys=1)
    rl2.check("x")
    with pytest.raises(ApiError):  # the limit itself still applies
        rl2.check("x")


# ---------------------------------------------------------------- missing test: PATCH zone
async def test_patch_me_rejects_unknown_zone(client):
    headers = await _register(client)
    r = await client.patch(f"{API}/devices/me", headers=headers, json={"zone_id": "mars"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "unknown_zone"


# ---------------------------------------------------------------- migration == models
def test_alembic_migration_matches_models(tmp_path: Path):
    """Test gap: nothing checked that the migration creates exactly what the models declare."""
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext

    from alembic import command

    db = tmp_path / "drift.db"
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.cmd_opts = type("o", (), {"x": [f"db_url=sqlite+aiosqlite:///{db.as_posix()}"]})()
    command.upgrade(cfg, "head")
    eng = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        with eng.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        eng.dispose()
    assert diff == []
