"""Reference engine tests (§9.7). V005/V006 (pack provenance) live in test_pipeline.py."""

from __future__ import annotations

import ast
import inspect
import json

import pytest

import app.engine.common
import app.engine.dekad
import app.engine.explain
import app.engine.rotation
import app.engine.rules
import app.engine.water_balance
from app.engine.common import EngineError, get_crop
from app.engine.dekad import dekad_label_fr, kc_at, n_cycle_dekads, phase_at, wrap_dekad
from app.engine.explain import fmt_num
from app.engine.rotation import evaluate_sequence, recommend
from app.engine.water_balance import simulate
from app.schemas.engine import RotationPlot
from tests.helpers import SEED, constant_climate_pack, synthetic_pack

ZONES = ["maritime_lome", "plateaux_kpalime", "kara_kara"]
CROPS = [c.crop_id for c in SEED.crops]
SOILS = [s.soil_id for s in SEED.soils]
SCENARIOS = [s.scenario_id for s in SEED.scenarios]
KARA = "kara_kara"


@pytest.fixture(scope="module")
def kara():
    return synthetic_pack(KARA)


def _rules(result) -> list[str]:
    return [h.rule_id for h in result.recommendations[0].seasons[0].rules_applied]


# ---------------------------------------------------------------- dekad utilities
def test_dekad_labels_and_wrap():
    assert dekad_label_fr(1) == "janv. D1"
    assert dekad_label_fr(20) == "juil. D2"
    assert dekad_label_fr(22) == "août D1"
    assert dekad_label_fr(36) == "déc. D3"
    assert wrap_dekad(37) == 1 and wrap_dekad(42) == 6 and wrap_dekad(36) == 36
    assert [n_cycle_dekads(d) for d in (100, 110, 120, 95, 75)] == [10, 11, 12, 10, 8]


def test_phases_and_kc_maize():
    maize = get_crop(synthetic_pack(KARA), "maize")
    phases = [phase_at(i, 10, maize)[0] for i in range(10)]
    assert phases == ["initial"] * 2 + ["development"] * 3 + ["mid"] * 3 + ["late"] * 2
    assert kc_at(0, 10, maize)[1] == pytest.approx(0.30)
    assert kc_at(2, 10, maize)[1] == pytest.approx(0.30 + 0.90 * (0.05 / 0.30))
    assert kc_at(6, 10, maize)[1] == pytest.approx(1.20)
    assert kc_at(8, 10, maize)[1] == pytest.approx(1.20 - 0.60 * 0.25)


def test_harvest_dekad_wraps(kara):
    r = simulate(kara, "maize", "loam", "baseline", sowing_dekad=33)
    assert [d.dekad for d in r.dekads] == [33, 34, 35, 36, 1, 2, 3, 4, 5, 6]
    assert r.harvest_dekad == 6


# ---------------------------------------------------------------- water balance by hand
def test_water_balance_hand_computed(kara):
    pack = constant_climate_pack(kara, p_mm=0.0, et0_mm=50.0)
    r = simulate(pack, "maize", "sandy_loam", "baseline", sowing_dekad=16)
    # TAW = 110 * 1.0 ; SW0 = 55 ; threshold = 0.45 * 110 = 49.5
    s0, s1 = r.dekads[0], r.dekads[1]
    assert (s0.ks, s0.etc_mm, s0.eta_mm, s0.soil_water_mm) == pytest.approx((1.0, 15.0, 15.0, 40.0))
    ks1 = 40.0 / 49.5
    assert s1.ks == pytest.approx(ks1)
    assert s1.eta_mm == pytest.approx(ks1 * 15.0)
    assert s1.soil_water_mm == pytest.approx(40.0 - ks1 * 15.0)
    assert r.critical_periods, "no rain should produce critical periods"
    assert any("manque d'eau en" in e for e in r.explanations_fr)


def test_scenario_factors_applied(kara):
    pack = constant_climate_pack(kara, p_mm=100.0, et0_mm=50.0)
    r = simulate(pack, "maize", "loam", "dry_hot", sowing_dekad=16)
    assert r.dekads[0].p_mm == pytest.approx(80.0)
    assert r.dekads[0].etc_mm == pytest.approx(0.30 * 50.0 * 1.06)


def test_critical_periods_split_by_phase(kara):
    pack = constant_climate_pack(kara, p_mm=0.0, et0_mm=50.0)
    r = simulate(pack, "maize", "sandy", "baseline", sowing_dekad=16)
    phases = [cp.phase for cp in r.critical_periods]
    assert len(phases) == len(set(phases))  # one block per phase when stress is continuous
    for cp in r.critical_periods:
        assert cp.mean_stress > 0.2


# ---------------------------------------------------------------- rules: V001–V003
def test_v001_groundnut_then_maize(kara):
    plot = RotationPlot(zone_id=KARA, soil_id="sandy_loam", previous_crop_id="groundnut")
    res = evaluate_sequence(kara, plot, "balanced", "baseline", ["maize"])
    season = res.recommendations[0].seasons[0]
    assert _rules(res) == ["R001"]
    assert season.rule_points == 10
    assert season.rules_applied[0].explanation_fr.startswith("Une légumineuse avant une céréale")
    assert "pas un rendement" in res.disclaimer_fr


def test_v002_maize_then_sorghum(kara):
    plot = RotationPlot(zone_id=KARA, soil_id="sandy_loam", previous_crop_id="maize")
    res = evaluate_sequence(kara, plot, "balanced", "baseline", ["sorghum"])
    assert _rules(res) == ["R002"]
    assert res.recommendations[0].seasons[0].rule_points == -5


def test_v003_maize_then_rice_dry(kara):
    plot = RotationPlot(zone_id=KARA, soil_id="sandy_loam", previous_crop_id="maize")
    res = evaluate_sequence(kara, plot, "balanced", "dry_minus20", ["rice"])
    hits = res.recommendations[0].seasons[0].rules_applied
    assert [h.rule_id for h in hits] == ["R002", "R003"]
    rules = {r.rule_id: r.explanation_fr for r in SEED.rules}
    assert [h.explanation_fr for h in hits] == [rules["R002"], rules["R003"]]
    assert res.recommendations[0].seasons[0].rule_points == -15


def test_r003_fires_on_any_drier_scenario_only(kara):
    plot = RotationPlot(zone_id=KARA, soil_id="sandy_loam", previous_crop_id=None)
    for sid, expected in [
        ("baseline", []),
        ("hot_plus2", []),
        ("dry_hot", ["R003"]),
        ("dry_minus10", ["R003"]),
    ]:
        assert _rules(evaluate_sequence(kara, plot, "balanced", sid, ["rice"])) == expected, sid


def test_r004_and_no_previous_crop(kara):
    plot = RotationPlot(zone_id=KARA, soil_id="loam", previous_crop_id="sorghum")
    assert _rules(evaluate_sequence(kara, plot, "balanced", "baseline", ["cowpea"])) == ["R004"]
    no_prev = RotationPlot(zone_id=KARA, soil_id="loam", previous_crop_id=None)
    for crop in CROPS:
        res = evaluate_sequence(kara, no_prev, "balanced", "baseline", [crop])
        assert _rules(res) == [], crop  # prev.* conditions are false without history


# ---------------------------------------------------------------- V004 + provenance
def test_v004_scenario_is_hypothetical(kara):
    r = simulate(kara, "maize", "sandy_loam", "dry_minus20")
    prov = {p.item: p.source_type for p in r.data_provenance}
    assert prov["scenario"] == "synthetic_scenario"
    assert "hypothétique" in r.explanations_fr[0]
    assert r.source_type != "synthetic_scenario"
    rec = recommend(kara, RotationPlot(zone_id=KARA, soil_id="loam"), "balanced", "dry_minus20")
    assert {p.item: p.source_type for p in rec.data_provenance}["scenario"] == "synthetic_scenario"
    assert "hypothétique" in rec.explanations_fr[0]
    assert "prévision" not in " ".join(rec.explanations_fr).replace("pas une prévision", "")


def test_weakest_source(kara):
    assert simulate(kara, "maize", "loam", "baseline").source_type == "synthetic_demo"
    nasa_like = constant_climate_pack(kara, 30.0, 45.0, source_type="nasa_power")
    r = simulate(nasa_like, "maize", "loam", "baseline")
    assert r.source_type == "provisional_demo"  # crops/soils are provisional
    assert {p.item: p.source_type for p in r.data_provenance}["climate"] == "nasa_power"


def test_disclaimers_and_assumptions(kara):
    r = simulate(kara, "rice", "loam", "baseline")
    assert "ni une prévision ni une estimation de rendement" in r.disclaimer_fr
    text = " ".join(r.assumptions_fr)
    for needle in (
        "1991-2020",
        "3 % par °C",
        "Réserve utile",
        "ruissellement",
        "provisoires",
        "pluviale",
    ):
        assert needle in text, needle
    assert "DONNÉES SYNTHÉTIQUES" in text
    assert "pluviale" not in " ".join(simulate(kara, "maize", "loam", "baseline").assumptions_fr)


# ---------------------------------------------------------------- monotonicity & bounds
@pytest.mark.parametrize("zone_id", ZONES)
def test_monotonicity(zone_id):
    pack = synthetic_pack(zone_id)
    for crop in CROPS:
        for soil in SOILS:
            for season in pack.zone.seasons:
                s = {
                    sid: simulate(pack, crop, soil, sid, season.sowing_dekad).stress_index
                    for sid in ("baseline", "dry_minus10", "dry_minus30", "hot_plus2")
                }
                ctx = (zone_id, crop, soil, season.season_id, s)
                assert s["dry_minus30"] >= s["dry_minus10"] - 1e-12, ctx
                assert s["dry_minus10"] >= s["baseline"] - 1e-12, ctx
                assert s["hot_plus2"] >= s["baseline"] - 1e-12, ctx


@pytest.mark.parametrize("zone_id", ZONES)
def test_bounds(zone_id):
    pack = synthetic_pack(zone_id)
    soils = {s.soil_id: s for s in pack.soils}
    for crop_id in CROPS:
        crop = get_crop(pack, crop_id)
        for soil_id in SOILS:
            taw = soils[soil_id].taw_mm_per_m * crop.root_depth_m
            for sid in SCENARIOS:
                r = simulate(pack, crop_id, soil_id, sid)
                assert 0 <= r.stress_index <= 1
                assert 0 <= r.wrsi <= 100
                for d in r.dekads:
                    assert 0 <= d.soil_water_mm <= taw
                    assert 0 <= d.ks <= 1 and 0 <= d.stress <= 1


# ---------------------------------------------------------------- determinism & purity
def test_determinism(kara):
    a = simulate(kara, "groundnut", "clay", "dry_hot").model_dump_json()
    b = simulate(kara, "groundnut", "clay", "dry_hot").model_dump_json()
    assert a == b
    plot = RotationPlot(zone_id=KARA, soil_id="sandy_loam", previous_crop_id="sorghum")
    r1 = recommend(kara, plot, "drought_resilience", "dry_minus20", 3).model_dump_json()
    r2 = recommend(kara, plot, "drought_resilience", "dry_minus20", 3).model_dump_json()
    assert r1 == r2


_ENGINE_MODULES = [
    app.engine.common,
    app.engine.dekad,
    app.engine.explain,
    app.engine.rotation,
    app.engine.rules,
    app.engine.water_balance,
]


def test_no_eval_exec():
    forbidden = {"eval", "exec", "compile", "__import__"}
    for mod in _ENGINE_MODULES:
        tree = ast.parse(inspect.getsource(mod))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden, f"{mod.__name__}: {node.func.id}()"


def test_engine_is_pure_no_io_imports():
    for mod in _ENGINE_MODULES:
        src = inspect.getsource(mod)
        for banned in (
            "sqlalchemy",
            "httpx",
            "requests",
            "urllib",
            "open(",
            "app.models",
            "app.db",
        ):
            assert banned not in src, f"{mod.__name__} uses {banned}"


# ---------------------------------------------------------------- rotation
def test_recommend_shape_and_order(kara):
    plot = RotationPlot(zone_id=KARA, soil_id="sandy_loam", previous_crop_id="sorghum")
    res = recommend(kara, plot, "drought_resilience", "baseline")
    assert res.horizon == 3 and res.n_sequences_evaluated == 125
    assert [o.rank for o in res.recommendations] == [1, 2, 3]
    keys = [(-o.total_score, o.mean_stress, o.sequence) for o in res.recommendations]
    assert keys == sorted(keys)
    top = res.recommendations[0]
    assert top.total_score == pytest.approx(sum(s.season_score for s in top.seasons))
    for s in top.seasons:
        assert s.season_score == pytest.approx(
            s.rule_points + s.resilience_points + s.priority_points
        )
    assert "pas un rendement" in res.disclaimer_fr
    assert recommend(kara, plot, "balanced", "baseline", 4).n_sequences_evaluated == 625


def test_recommend_scoring_formula(kara):
    plot = RotationPlot(zone_id=KARA, soil_id="loam", previous_crop_id=None)
    res = evaluate_sequence(kara, plot, "drought_resilience", "baseline", ["sorghum"])
    s = res.recommendations[0].seasons[0]
    sim = simulate(kara, "sorghum", "loam", "baseline", kara.zone.seasons[0].sowing_dekad)
    assert s.resilience_points == pytest.approx(30 * (1 - sim.stress_index))
    assert s.priority_points == pytest.approx(0 + 2 * 4)  # drought_level_factor 2 × level(high)=4


def test_bimodal_season_alternation():
    pack = synthetic_pack("maritime_lome")
    res = recommend(
        pack, RotationPlot(zone_id="maritime_lome", soil_id="loam"), "balanced", "baseline", 4
    )
    assert [s.season_id for s in res.recommendations[0].seasons] == [
        "main",
        "second",
        "main",
        "second",
    ]


def test_engine_errors(kara):
    with pytest.raises(EngineError) as e:
        simulate(kara, "banana", "loam", "baseline")
    assert e.value.code == "unknown_crop"
    with pytest.raises(EngineError) as e:
        simulate(kara, "maize", "loam", "baseline", sowing_dekad=40)
    assert e.value.code == "invalid_sowing_dekad"
    plot = RotationPlot(zone_id=KARA, soil_id="loam")
    with pytest.raises(EngineError) as e:
        recommend(kara, plot, "balanced", "baseline", horizon=5)
    assert e.value.code == "invalid_horizon"
    with pytest.raises(EngineError) as e:
        recommend(
            kara, RotationPlot(zone_id="maritime_lome", soil_id="loam"), "balanced", "baseline"
        )
    assert e.value.code == "zone_mismatch"
    with pytest.raises(EngineError) as e:
        recommend(kara, plot, "balanced", "nope")
    assert e.value.code == "unknown_scenario"


# ---------------------------------------------------------------- serialization
def test_rounding_only_at_serialization(kara):
    r = simulate(kara, "maize", "sandy", "dry_minus30")
    raw = r.dekads[3].etc_mm
    dumped = json.loads(r.model_dump_json())["dekads"][3]["etc_mm"]
    assert dumped == round(raw, 2)
    assert r.dekads[3].etc_mm == raw  # in-memory value untouched


def test_fmt_num():
    assert fmt_num(0.456) == "0,46"
    assert fmt_num(20.0, 0) == "20"
    assert fmt_num(-20, 1, signed=True) == "-20"
    assert fmt_num(2, 1, signed=True) == "+2"
    assert fmt_num(0, 1, signed=True) == "+0"
    assert fmt_num(0.125) == "0,13"
