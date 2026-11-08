"""Dekadal soil water balance (§9.3). Pure & deterministic: no DB, no network, no globals."""

from __future__ import annotations

from dataclasses import dataclass

from app.engine import explain
from app.engine.common import EngineError, get_crop, get_scenario, get_soil, provenance
from app.engine.dekad import dekad_label_fr, kc_at, n_cycle_dekads, wrap_dekad
from app.schemas.engine import CriticalPeriod, DekadStep, SimulationResult
from app.schemas.pack import ZonePack
from app.schemas.reference import Crop, PhaseName, Scenario, Soil

CRITICAL_STRESS_THRESHOLD = 0.2


@dataclass(frozen=True)
class _Step:
    dekad: int
    phase: PhaseName
    kc: float
    p: float
    etc: float
    eta: float
    sw: float
    ks: float
    stress: float


def default_sowing_dekad(pack: ZonePack) -> int:
    return pack.zone.seasons[0].sowing_dekad


def _run(pack: ZonePack, crop: Crop, soil: Soil, scenario: Scenario, sowing: int) -> list[_Step]:
    sc = pack.scoring
    climate = {d.dekad: d for d in pack.climate.dekads}
    taw = soil.taw_mm_per_m * crop.root_depth_m
    sw = sc.initial_soil_water_fraction * taw
    threshold = (1 - crop.depletion_p) * taw
    rain_factor = 1 + scenario.rainfall_change_pct / 100
    et0_factor = 1 + sc.et0_temp_sensitivity_per_c * scenario.temperature_change_c
    n = n_cycle_dekads(crop.cycle_days)

    steps: list[_Step] = []
    for i in range(n):
        d = wrap_dekad(sowing + i)
        phase, kc = kc_at(i, n, crop)
        p = climate[d].p_mm * rain_factor
        etc = kc * climate[d].et0_mm * et0_factor
        # Ks from soil water at the START of the dekad, before rain (DECISIONS #3).
        ks = 1.0 if sw >= threshold else min(1.0, max(0.0, sw / threshold))
        eta = ks * etc
        sw = min(taw, max(0.0, sw + p - eta))
        steps.append(_Step(d, phase, kc, p, etc, eta, sw, ks, 1 - ks))
    return steps


def _critical_periods(steps: list[_Step]) -> list[CriticalPeriod]:
    """Runs of consecutive cycle dekads with stress > 0.2, split when the phase changes."""
    out: list[CriticalPeriod] = []
    run: list[_Step] = []

    def flush() -> None:
        if run:
            out.append(
                CriticalPeriod(
                    from_label_fr=dekad_label_fr(run[0].dekad),
                    to_label_fr=dekad_label_fr(run[-1].dekad),
                    phase=run[0].phase,
                    mean_stress=sum(s.stress for s in run) / len(run),
                )
            )

    for s in steps:
        if s.stress > CRITICAL_STRESS_THRESHOLD:
            if run and run[-1].phase != s.phase:
                flush()
                run = []
            run.append(s)
        else:
            flush()
            run = []
    flush()
    return out


def simulate(
    pack: ZonePack,
    crop_id: str,
    soil_id: str,
    scenario_id: str,
    sowing_dekad: int | None = None,
) -> SimulationResult:
    crop = get_crop(pack, crop_id)
    soil = get_soil(pack, soil_id)
    scenario = get_scenario(pack, scenario_id)
    sowing = default_sowing_dekad(pack) if sowing_dekad is None else sowing_dekad
    if not 1 <= sowing <= 36:
        raise EngineError("invalid_sowing_dekad", f"Décade de semis invalide : {sowing} (1 à 36)")

    steps = _run(pack, crop, soil, scenario, sowing)
    weights = pack.scoring.phase_weights
    w_sum = sum(weights[s.phase] for s in steps)
    stress_index = sum(weights[s.phase] * s.stress for s in steps) / w_sum
    etc_sum = sum(s.etc for s in steps)
    wrsi = 100.0 if etc_sum <= 0 else 100 * sum(s.eta for s in steps) / etc_sum
    wrsi = min(100.0, max(0.0, wrsi))  # float noise can give 100.00000000000001
    critical = _critical_periods(steps)
    taw = soil.taw_mm_per_m * crop.root_depth_m

    assumptions = explain.common_assumptions(pack)
    assumptions.insert(-1, explain.soil_assumption(pack, soil, crop, taw))
    if crop.crop_id == "rice":
        assumptions.append(explain.RICE_ASSUMPTION)
    source_type, prov = provenance(pack, scenario, [crop], soil, with_rules=False)

    return SimulationResult(
        crop_id=crop.crop_id,
        soil_id=soil.soil_id,
        scenario_id=scenario.scenario_id,
        sowing_dekad=sowing,
        harvest_dekad=steps[-1].dekad,
        stress_index=stress_index,
        wrsi=wrsi,
        dekads=[
            DekadStep(
                dekad=s.dekad,
                label_fr=dekad_label_fr(s.dekad),
                phase=s.phase,
                kc=s.kc,
                p_mm=s.p,
                etc_mm=s.etc,
                eta_mm=s.eta,
                soil_water_mm=s.sw,
                ks=s.ks,
                stress=s.stress,
            )
            for s in steps
        ],
        critical_periods=critical,
        explanations_fr=explain.simulation_explanations(crop, scenario, critical, wrsi),
        assumptions_fr=assumptions,
        source_type=source_type,
        data_provenance=prov,
    )
