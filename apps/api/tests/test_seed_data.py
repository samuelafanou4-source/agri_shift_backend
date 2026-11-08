"""data/seed/*.json: valid, consistent with the original pack (§8)."""

from __future__ import annotations

import json

from app.config import REPO_ROOT
from app.services.reference_data import load_seed

DATA = REPO_ROOT / "data"
SEED = load_seed(DATA / "seed")


def _pack(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_original_pack_files_untouched():
    for name in [
        "cultures.json",
        "cultures.csv",
        "regles_rotation.json",
        "zones.json",
        "synthetic/climat_synthetique.json",
        "synthetic/parcelles_demo.json",
        "synthetic/scenarios.json",
    ]:
        assert (DATA / name).is_file(), name
    assert [r["rule_id"] for r in _pack("regles_rotation.json")] == ["R001", "R002", "R003"]


def test_crops_match_pack():
    pack = {c["crop_id"]: c for c in _pack("cultures.json")}
    crops = {c.crop_id: c for c in SEED.crops}
    assert set(crops) == set(pack) == {"maize", "sorghum", "rice", "groundnut", "cowpea"}
    for cid, c in crops.items():
        p = pack[cid]
        assert c.name_fr == p["name_fr"]
        assert c.family == p["family"]
        assert c.n_fixing == p["nitrogen_fixing"]
        assert c.cycle_days == p["cycle_days_demo"]
        assert c.water_need == p["water_need_class_demo"]
        assert c.drought_tolerance == p["drought_tolerance_demo"]
        assert c.source_type == "provisional_demo"
        assert c.source_note
        assert c.phases.mid == 0.30


def test_crop_water_parameters_table():
    expected = {
        "maize": (0.30, 1.20, 0.60, 1.0, 0.55, True),
        "sorghum": (0.30, 1.05, 0.55, 1.0, 0.55, True),
        "rice": (1.05, 1.20, 0.75, 0.5, 0.20, True),
        "groundnut": (0.40, 1.15, 0.60, 0.5, 0.50, False),
        "cowpea": (0.40, 1.05, 0.60, 0.6, 0.45, True),
    }
    for c in SEED.crops:
        assert (c.kc_ini, c.kc_mid, c.kc_end, c.root_depth_m, c.depletion_p, c.food_staple) == (
            expected[c.crop_id]
        )


def test_zones_match_pack():
    pack = {z["zone_id"]: z for z in _pack("zones.json")}
    for z in SEED.zones:
        assert z.latitude == pack[z.zone_id]["latitude"]
        assert z.longitude == pack[z.zone_id]["longitude"]
        assert z.name_long_fr == pack[z.zone_id]["zone_name"]
    seasons = {
        z.zone_id: [(s.season_id, s.provisional_sowing_dekad) for s in z.seasons]
        for z in SEED.zones
    }
    assert seasons == {
        "maritime_lome": [("main", 10), ("second", 25)],
        "plateaux_kpalime": [("main", 11), ("second", 25)],
        "kara_kara": [("main", 16)],
    }


def test_rules_structured():
    rules = {r.rule_id: r for r in SEED.rules}
    assert list(rules) == ["R001", "R002", "R003", "R004"]
    assert [r.delta for r in SEED.rules] == [10, -5, -10, 5]
    r3 = rules["R003"]
    assert {(c.field, c.op, c.value) for c in r3.all} == {
        ("next.water_need", "eq", "high"),
        ("scenario.rainfall_change_pct", "lt", 0),
    }


def test_scenarios_extend_pack():
    pack = {s["scenario_id"]: s for s in _pack("synthetic/scenarios.json")}
    sc = {s.scenario_id: s for s in SEED.scenarios}
    assert set(pack) <= set(sc)
    assert set(sc) - set(pack) == {"dry_minus10", "dry_minus30", "hot_plus1"}
    for sid, p in pack.items():
        assert sc[sid].rainfall_change_pct == p["rainfall_change_pct"]
        assert sc[sid].temperature_change_c == p["temperature_change_c"]
    assert all(s.source_type == "synthetic_scenario" for s in SEED.scenarios)
    assert all("pas une prévision" in s.note_fr for s in SEED.scenarios)


def test_soils_and_scoring():
    assert {s.soil_id: s.taw_mm_per_m for s in SEED.soils} == {
        "sandy": 70,
        "sandy_loam": 110,
        "loam": 140,
        "clay": 170,
    }
    assert SEED.scoring.horizon_default == 3 and SEED.scoring.top_n == 3
    # demo plots reference known soils/crops/zones
    for p in _pack("synthetic/parcelles_demo.json"):
        assert p["soil_texture_demo"] in {s.soil_id for s in SEED.soils}
        assert p["previous_crop_id"] in {c.crop_id for c in SEED.crops}
        assert p["zone_id"] in {z.zone_id for z in SEED.zones}
