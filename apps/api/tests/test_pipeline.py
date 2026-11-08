"""Pipeline tests (§6) + V005/V006 (§9.7). Real-data tests are skipped if the NASA cache is absent."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest
from pipeline import config
from pipeline.build_packs import canonical_bytes, sha256_hex, write_packs
from pipeline.climatology import normals, onset_dekad, trend
from pipeline.dekads import aggregate_daily, dekad_of
from pipeline.et0 import delta_svp, et0_pm, ra, svp
from pipeline.fetch_power import PowerError, chunks, parse_response
from pipeline.synthetic_fallback import generate_dekad_series, synthetic_climatology

from app.config import REPO_ROOT
from app.engine.water_balance import simulate
from app.schemas.pack import ZonePack
from tests.helpers import SEED

ZONES = [z.zone_id for z in SEED.zones]
ZONE_SEEDS = {z.zone_id: z for z in SEED.zones}
HAS_NASA = all((config.RAW_POWER_DIR / f"{z}.csv").is_file() for z in ZONES)
needs_nasa = pytest.mark.skipif(
    not HAS_NASA, reason="NASA POWER cache absent (run pipeline.run_all)"
)


def _disk_pack(zone_id: str) -> ZonePack | None:
    path = REPO_ROOT / "packs" / f"{zone_id}.json"
    return ZonePack.model_validate_json(path.read_bytes()) if path.is_file() else None


# ---------------------------------------------------------------- ET0 (FAO-56)
def test_et0_intermediate_functions():
    assert svp(25.0) == pytest.approx(3.168, abs=1e-3)
    assert delta_svp(25.0) == pytest.approx(0.189, abs=1e-3)
    # FAO-56 example 8: 20°S, 3 September (doy 246) -> Ra = 32.2 MJ m-2 day-1
    assert ra(-20.0, 246) == pytest.approx(32.2, abs=0.1)


def test_et0_reasonable_and_non_negative():
    v = et0_pm(27.0, 32.0, 22.0, 70.0, 2.0, 18.0, 9.5, 400.0, 180)
    assert 3.0 < float(v) < 6.0
    cold = et0_pm(5.0, 6.0, 4.0, 100.0, 0.0, 0.5, 9.5, 400.0, 1)
    assert float(cold) >= 0.0


@needs_nasa
@pytest.mark.parametrize("zone_id", ZONES)
def test_et0_real_data_coherent(zone_id):
    from pipeline.et0 import daily_with_et0

    df = daily_with_et0(zone_id)
    inputs_ok = df[["t2m", "t2m_max", "t2m_min", "rh2m", "ws2m", "rs_mj"]].notna().all(axis=1)
    et0 = df["et0_mm"]
    assert (et0[inputs_ok] >= 0).all()
    assert et0[inputs_ok].notna().all()
    assert 3.0 <= et0.mean() <= 7.0, f"{zone_id}: mean ET0 {et0.mean():.2f} mm/day"


# ---------------------------------------------------------------- fetch_power
def test_chunks_10_years():
    c = chunks(date(1991, 1, 1), date(2025, 12, 31))
    assert c == [
        (date(1991, 1, 1), date(2000, 12, 31)),
        (date(2001, 1, 1), date(2010, 12, 31)),
        (date(2011, 1, 1), date(2020, 12, 31)),
        (date(2021, 1, 1), date(2025, 12, 31)),
    ]


def _payload(rad_units="MJ/m^2/day", t_units="C"):
    units = {
        "T2M": t_units, "T2M_MAX": "C", "T2M_MIN": "C", "PRECTOTCORR": "mm/day",
        "RH2M": "%", "WS2M": "m/s", "ALLSKY_SFC_SW_DWN": rad_units,
    }  # fmt: skip
    day = {"20200101": 1.0, "20200102": -999.0}
    return {
        "geometry": {"coordinates": [1.18, 9.55, 402.3]},
        "header": {"fill_value": -999.0, "sources": ["MERRA2"], "api": {"version": "x"}},
        "parameters": {k: {"units": u} for k, u in units.items()},
        "properties": {"parameter": {k: dict(day) for k in units}},
    }


def test_parse_response_fill_units_elevation():
    df, meta = parse_response(_payload())
    assert meta["elevation_m"] == 402.3
    assert np.isnan(df.loc["2020-01-02", "precip_mm"])
    assert df.loc["2020-01-01", "rs_mj"] == 1.0
    df2, _ = parse_response(_payload(rad_units="kW-hr/m^2/day"))
    assert df2.loc["2020-01-01", "rs_mj"] == pytest.approx(3.6)
    with pytest.raises(PowerError):
        parse_response(_payload(t_units="K"))


# ---------------------------------------------------------------- dekads
def test_dekad_index():
    assert dekad_of(1, 1) == 1 and dekad_of(1, 10) == 1 and dekad_of(1, 11) == 2
    assert dekad_of(1, 21) == 3 and dekad_of(2, 29) == 6 and dekad_of(12, 31) == 36


def test_aggregate_daily_and_invalid_dekad():
    dates = pd.date_range("2020-01-01", "2020-01-31")
    daily = pd.DataFrame(
        {"date": dates, "precip_mm": 1.0, "et0_mm": 4.0, "t2m": 25.0, "t2m_max": 31.0}
    )
    daily.loc[10:13, "precip_mm"] = np.nan  # 4 missing days in D2
    out = aggregate_daily(daily, "z", "nasa_power")
    d1, d2, d3 = out.to_dict("records")
    assert (d1["p_mm"], d1["et0_mm"], d1["n_days"], d1["n_missing"]) == (10.0, 40.0, 10, 0)
    assert d2["n_missing"] == 4 and np.isnan(d2["p_mm"]) and np.isnan(d2["tmean_c"])
    assert d3["n_days"] == 11 and d3["p_mm"] == 11.0


# ---------------------------------------------------------------- climatology
def test_onset_rule():
    rows = [{"dekad": d, "p_mm": 0.0} for d in range(1, 37)]
    assert onset_dekad(rows, 13, 19) is None
    rows[15]["p_mm"] = 30.0  # dekad 16
    rows[16]["p_mm"] = 10.0
    rows[17]["p_mm"] = 9.0
    assert onset_dekad(rows, 13, 19) is None  # next two = 19 < 20
    rows[17]["p_mm"] = 10.0
    assert onset_dekad(rows, 13, 19) == 16
    assert onset_dekad(rows, 17, 19) is None


def test_normals_and_trend_from_series():
    series = generate_dekad_series("kara_kara", years=(1991, 2025))
    rows = normals(series)
    assert [r["dekad"] for r in rows] == list(range(1, 37))
    for r in rows:
        assert r["p_p20"] <= r["p_mm"]
        if r["p_mm"] < 1:
            assert r["p_cv"] is None
    t = trend(series)
    assert t["recent_period"] == "2016-2025" and t["baseline_period"] == "1991-2020"
    assert trend(generate_dekad_series("kara_kara")) is None  # recent period not covered


# ---------------------------------------------------------------- packs (offline) + V005
@pytest.fixture
def offline_packs(tmp_path):
    clims = {zid: synthetic_climatology(ZONE_SEEDS[zid]) for zid in ZONES}
    now = datetime(2026, 11, 4, 10, 0, tzinfo=UTC)
    entries = write_packs(SEED, clims, tmp_path, now=now)
    return tmp_path, entries, clims


def test_offline_packs_valid(offline_packs):
    out, entries, _ = offline_packs
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert [e["zone_id"] for e in manifest] == sorted(ZONES)
    assert set(manifest[0]) == {"zone_id", "pack_version", "sha256", "size_bytes", "generated_at"}
    assert (out / "zone_pack.schema.json").is_file()
    for e in entries:
        raw = (out / f"{e['zone_id']}.json").read_bytes()
        assert e["sha256"] == sha256_hex(raw) and e["size_bytes"] == len(raw) < 100 * 1024
        pack = ZonePack.model_validate_json(raw)
        assert canonical_bytes(pack) == raw  # file is the canonical form
        assert [d.dekad for d in pack.climate.dekads] == list(range(1, 37))
        assert e["pack_version"] == "2026.11.04-1"
        assert pack.generated_at.isoformat().startswith("2026-11-04T10:00:00")


def test_pack_version_increments(offline_packs):
    out, _, clims = offline_packs
    again = write_packs(SEED, clims, out, now=datetime(2026, 11, 4, 12, tzinfo=UTC))
    assert {e["pack_version"] for e in again} == {"2026.11.04-2"}
    nextday = write_packs(SEED, clims, out, now=datetime(2026, 11, 5, tzinfo=UTC))
    assert {e["pack_version"] for e in nextday} == {"2026.11.05-1"}


def test_v005_offline_pack_is_synthetic(offline_packs):
    out, _, _ = offline_packs
    for zid in ZONES:
        pack = ZonePack.model_validate_json((out / f"{zid}.json").read_bytes())
        assert pack.climate.source_type == "synthetic_demo"
        assert {p.item: p.source_type for p in pack.data_provenance}["climate"] == "synthetic_demo"
        assert any("SYNTHÉTIQUES" in w for w in pack.climate.warnings_fr)
        assert pack.climate.trend is None and pack.zone.elevation_m is None
        assert simulate(pack, "maize", "loam", "baseline").source_type == "synthetic_demo"


def test_sowing_rule(offline_packs):
    _, _, clims = offline_packs
    from pipeline.build_packs import assemble_pack

    clim = dict(clims["kara_kara"], onset_by_season={"main": None})
    pack = assemble_pack(SEED, "kara_kara", clim, "v", datetime(2026, 1, 1, tzinfo=UTC))
    s = pack.zone.seasons[0]
    assert (s.sowing_dekad, s.sowing_source, s.onset_dekad_clim) == (16, "provisional_demo", None)
    clim = dict(clims["kara_kara"], onset_by_season={"main": 14})
    s = assemble_pack(SEED, "kara_kara", clim, "v", datetime(2026, 1, 1, tzinfo=UTC)).zone.seasons[
        0
    ]
    assert (s.sowing_dekad, s.sowing_source, s.onset_dekad_clim) == (14, "computed", 14)


def test_run_all_offline_cli(tmp_path, monkeypatch):
    from pipeline import run_all

    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    assert run_all.main(["--offline", "--packs-dir", str(tmp_path / "packs")]) == 0
    for zid in ZONES:
        pack = ZonePack.model_validate_json((tmp_path / "packs" / f"{zid}.json").read_bytes())
        assert pack.climate.source_type == "synthetic_demo"


# ---------------------------------------------------------------- NASA packs on disk + V006
@pytest.mark.parametrize("zone_id", ZONES)
def test_disk_packs_valid(zone_id):
    pack = _disk_pack(zone_id)
    if pack is None:
        pytest.skip("packs/ not built")
    raw = (REPO_ROOT / "packs" / f"{zone_id}.json").read_bytes()
    assert len(raw) < 100 * 1024
    manifest = {
        e["zone_id"]: e for e in json.loads((REPO_ROOT / "packs" / "manifest.json").read_bytes())
    }
    assert manifest[zone_id]["sha256"] == sha256_hex(raw)
    assert len(pack.climate.dekads) == 36


@pytest.mark.parametrize("zone_id", ZONES)
def test_v006_nasa_pack(zone_id):
    pack = _disk_pack(zone_id)
    if pack is None or pack.climate.source_type != "nasa_power":
        pytest.skip("NASA pack not built")
    assert {p.item: p.source_type for p in pack.data_provenance}["climate"] == "nasa_power"
    assert pack.climate.warnings_fr
    assert any("pas une mesure de votre champ" in w for w in pack.climate.warnings_fr)
    assert pack.climate.trend is not None and "pas une prévision" in pack.climate.trend.note_fr
    assert pack.zone.elevation_m is not None
    et0_daily = sum(d.et0_mm for d in pack.climate.dekads) / 365
    assert 3.0 <= et0_daily <= 7.0


@pytest.mark.parametrize("zone_id", ZONES)
def test_monotonicity_and_bounds_on_disk_packs(zone_id):
    pack = _disk_pack(zone_id)
    if pack is None:
        pytest.skip("packs/ not built")
    for crop in pack.crops:
        for soil in pack.soils:
            taw = soil.taw_mm_per_m * crop.root_depth_m
            for season in pack.zone.seasons:
                s = {}
                for sc in pack.scenarios:
                    r = simulate(
                        pack, crop.crop_id, soil.soil_id, sc.scenario_id, season.sowing_dekad
                    )
                    s[sc.scenario_id] = r.stress_index
                    assert 0 <= r.stress_index <= 1 and 0 <= r.wrsi <= 100
                    assert all(0 <= d.soil_water_mm <= taw for d in r.dekads)
                ctx = (zone_id, crop.crop_id, soil.soil_id, season.season_id, s)
                assert s["dry_minus30"] >= s["dry_minus10"] - 1e-12 >= s["baseline"] - 2e-12, ctx
                assert s["hot_plus2"] >= s["baseline"] - 1e-12, ctx
