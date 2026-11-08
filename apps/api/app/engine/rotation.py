"""Rotation recommendation (§9.5). Pure & deterministic (memoization is local to each call)."""

from __future__ import annotations

from itertools import product

from app.engine import explain
from app.engine.common import EngineError, get_crop, get_scenario, get_soil, provenance
from app.engine.rules import matching_rules
from app.engine.water_balance import simulate
from app.schemas.engine import (
    RotationOption,
    RotationPlot,
    RotationResult,
    SeasonScore,
    SeasonSimulationSummary,
    SimulationResult,
)
from app.schemas.pack import ZonePack
from app.schemas.reference import Crop, Priority, Scenario, Soil

PRIORITIES: tuple[str, ...] = ("food_security", "drought_resilience", "balanced")

SimCache = dict[tuple[str, str, str, int], SimulationResult]


def _check_common(pack: ZonePack, plot: RotationPlot, priority: str) -> Crop | None:
    if plot.zone_id != pack.zone.zone_id:
        raise EngineError(
            "zone_mismatch", f"La parcelle ({plot.zone_id}) n'est pas dans la zone du paquet."
        )
    if priority not in PRIORITIES:
        raise EngineError("invalid_priority", f"Priorité inconnue : {priority}")
    return get_crop(pack, plot.previous_crop_id) if plot.previous_crop_id else None


def _score_sequence(
    pack: ZonePack,
    sequence: tuple[Crop, ...],
    prev0: Crop | None,
    soil: Soil,
    scenario: Scenario,
    priority: Priority,
    cache: SimCache,
) -> RotationOption:
    sc = pack.scoring
    base = sc.season_resilience_base[priority]
    bonus = sc.priority_bonus[priority]
    seasons = pack.zone.seasons
    prev = prev0
    out: list[SeasonScore] = []
    total = 0.0
    stress_sum = 0.0
    for k, crop in enumerate(sequence):
        season = seasons[k % len(seasons)]
        hits = matching_rules(pack.rules, prev, crop, scenario)
        rule_pts = 0.0
        for h in hits:
            rule_pts += h.delta
        key = (crop.crop_id, soil.soil_id, scenario.scenario_id, season.sowing_dekad)
        sim = cache.get(key)
        if sim is None:
            sim = simulate(pack, *key)
            cache[key] = sim
        resilience_pts = base * (1 - sim.stress_index)
        priority_pts = bonus.food_staple * (1.0 if crop.food_staple else 0.0) + (
            bonus.drought_level_factor * sc.drought_levels[crop.drought_tolerance]
        )
        season_score = rule_pts + resilience_pts + priority_pts
        total += season_score
        stress_sum += sim.stress_index
        out.append(
            SeasonScore(
                season_index=k,
                season_id=season.season_id,
                season_label_fr=season.label_fr,
                sowing_dekad=season.sowing_dekad,
                crop_id=crop.crop_id,
                crop_name_fr=crop.name_fr,
                previous_crop_id=prev.crop_id if prev else None,
                rules_applied=hits,
                rule_points=rule_pts,
                resilience_points=resilience_pts,
                priority_points=priority_pts,
                season_score=season_score,
                simulation=SeasonSimulationSummary(
                    stress_index=sim.stress_index,
                    wrsi=sim.wrsi,
                    critical_periods=sim.critical_periods,
                    explanations_fr=sim.explanations_fr,
                ),
            )
        )
        prev = crop
    return RotationOption(
        rank=None,
        sequence=[c.crop_id for c in sequence],
        sequence_names_fr=[c.name_fr for c in sequence],
        total_score=total,
        mean_stress=stress_sum / len(sequence),
        seasons=out,
    )


def _result(
    pack: ZonePack,
    plot: RotationPlot,
    priority: Priority,
    scenario: Scenario,
    soil: Soil,
    horizon: int,
    n_eval: int,
    options: list[RotationOption],
    crops_used: list[Crop],
) -> RotationResult:
    source_type, prov = provenance(pack, scenario, crops_used, soil, with_rules=True)
    assumptions = explain.common_assumptions(pack)
    assumptions.insert(
        -1,
        "Une culture par saison ; la saison k utilise le calendrier de semis de la zone "
        "(alternance grande/petite saison si la zone en a deux).",
    )
    if any(c.crop_id == "rice" for c in crops_used):
        assumptions.append(explain.RICE_ASSUMPTION)
    return RotationResult(
        zone_id=pack.zone.zone_id,
        soil_id=soil.soil_id,
        previous_crop_id=plot.previous_crop_id,
        priority=priority,
        scenario_id=scenario.scenario_id,
        horizon=horizon,
        n_sequences_evaluated=n_eval,
        recommendations=options,
        explanations_fr=[explain.scenario_line(scenario)],
        assumptions_fr=assumptions,
        source_type=source_type,
        data_provenance=prov,
    )


def recommend(
    pack: ZonePack,
    plot: RotationPlot,
    priority: Priority,
    scenario_id: str,
    horizon: int | None = None,
) -> RotationResult:
    prev0 = _check_common(pack, plot, priority)
    soil = get_soil(pack, plot.soil_id)
    scenario = get_scenario(pack, scenario_id)
    sc = pack.scoring
    h = sc.horizon_default if horizon is None else horizon
    if not 2 <= h <= sc.horizon_max:
        raise EngineError(
            "invalid_horizon", f"Horizon invalide : {h} (entre 2 et {sc.horizon_max} saisons)"
        )

    cache: SimCache = {}
    options = [
        _score_sequence(pack, seq, prev0, soil, scenario, priority, cache)
        for seq in product(pack.crops, repeat=h)
    ]
    # total_score desc, then mean_stress asc, then sequence (crop_id list) ascending.
    options.sort(key=lambda o: (-o.total_score, o.mean_stress, o.sequence))
    top = options[: sc.top_n]
    for rank, o in enumerate(top, start=1):
        o.rank = rank
    return _result(pack, plot, priority, scenario, soil, h, len(options), top, list(pack.crops))


def evaluate_sequence(
    pack: ZonePack,
    plot: RotationPlot,
    priority: Priority,
    scenario_id: str,
    sequence: list[str],
) -> RotationResult:
    """Score one given sequence with the same logic as `recommend` (used by V001–V003)."""
    prev0 = _check_common(pack, plot, priority)
    soil = get_soil(pack, plot.soil_id)
    scenario = get_scenario(pack, scenario_id)
    if not sequence:
        raise EngineError("invalid_horizon", "La séquence de cultures est vide.")
    crops = tuple(get_crop(pack, c) for c in sequence)
    option = _score_sequence(pack, crops, prev0, soil, scenario, priority, {})
    used = list(crops) + ([prev0] if prev0 else [])
    return _result(pack, plot, priority, scenario, soil, len(crops), 1, [option], used)
