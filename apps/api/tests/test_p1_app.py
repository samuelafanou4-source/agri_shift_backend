"""P1: /health, error format, idempotent seed, Alembic migration."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import func, inspect, select

from alembic import command
from app import models as m
from app.config import API_ROOT
from app.services.reference_data import load_seed
from app.services.seed_service import seed_all


async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert isinstance(body["packs_count"], int)
    assert body["version"]


async def test_error_format_404(client):
    r = await client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message_fr": "Ressource introuvable."}}


async def _counts(db) -> dict[str, int]:
    out = {}
    async with db.session_factory() as s:
        for model in (
            m.Zone,
            m.Crop,
            m.Soil,
            m.RotationRule,
            m.Scenario,
            m.Device,
            m.Plot,
            m.PlotSeason,
        ):
            out[model.__tablename__] = (
                await s.execute(select(func.count()).select_from(model))
            ).scalar_one()
    return out


async def test_seed_is_idempotent(seeded_db, settings):
    first = await _counts(seeded_db)
    assert first == {
        "zones": 3,
        "crops": 5,
        "soils": 4,
        "rotation_rules": 4,
        "scenarios": 7,
        "devices": 3,
        "plots": 3,
        "plot_seasons": 3,
    }
    async with seeded_db.session_factory() as session:
        await seed_all(
            session,
            load_seed(settings.seed_path),
            settings.data_path / "synthetic" / "parcelles_demo.json",
        )
    assert await _counts(seeded_db) == first


async def test_demo_rows_marked_synthetic(seeded_db):
    async with seeded_db.session_factory() as s:
        plots = (await s.execute(select(m.Plot))).scalars().all()
        devices = (await s.execute(select(m.Device))).scalars().all()
        rule = await s.get(m.RotationRule, "R003")
    assert {p.source_type for p in plots} == {"synthetic_demo"}
    assert {d.source_type for d in devices} == {"synthetic_demo"}
    assert rule.conditions[1] == {"field": "scenario.rainfall_change_pct", "op": "lt", "value": 0}


def test_alembic_upgrade_head(tmp_path: Path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'alembic.db').as_posix()}"
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.cmd_opts = type("o", (), {"x": [f"db_url={url}"]})()
    command.upgrade(cfg, "head")

    from sqlalchemy import create_engine

    eng = create_engine(f"sqlite:///{(tmp_path / 'alembic.db').as_posix()}")
    tables = set(inspect(eng).get_table_names())
    eng.dispose()
    assert {
        "zones",
        "crops",
        "soils",
        "rotation_rules",
        "scenarios",
        "climate_dekad",
        "packs",
        "devices",
        "plots",
        "plot_seasons",
        "posts",
        "alembic_version",
    } <= tables


async def test_seed_climate_dekad_and_packs(seeded_db, settings, tmp_path):
    from app.services.seed_service import seed_climate_dekad

    processed = tmp_path / "processed"
    processed.mkdir()
    (processed / "dekad_kara_kara.csv").write_text(
        "zone_id,year,dekad,p_mm,et0_mm,tmean_c,tmax_c,n_days,n_missing,source_type\n"
        "kara_kara,2020,1,0.5,50.1,27.0,34.0,10,0,nasa_power\n"
        "kara_kara,2020,2,,,,,10,4,nasa_power\n",
        encoding="utf-8",
    )
    packs = tmp_path / "packs"
    packs.mkdir()
    (packs / "manifest.json").write_text(
        '[{"zone_id":"kara_kara","pack_version":"2026.11.04-1","sha256":"ab","size_bytes":1,'
        '"generated_at":"2026-11-04T10:00:00Z"}]',
        encoding="utf-8",
    )
    for _ in range(2):  # idempotent
        async with seeded_db.session_factory() as s:
            assert await seed_climate_dekad(s, processed, packs) == 2
    async with seeded_db.session_factory() as s:
        rows = (await s.execute(select(m.ClimateDekad))).scalars().all()
        assert len(rows) == 2 and rows[1].p_mm is None
        assert (await s.execute(select(func.count()).select_from(m.Pack))).scalar_one() == 1
