"""Reference engine outputs (§9.3, §9.5). Floats are rounded to 2 decimals at serialization only."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import R2, SourceType
from app.schemas.pack import ProvenanceItem
from app.schemas.reference import PhaseName, Priority

SIMULATION_DISCLAIMER_FR = (
    "Simulation simplifiée à but d'aide à la réflexion ; "
    "ce n'est ni une prévision ni une estimation de rendement."
)
ROTATION_DISCLAIMER_FR = "Score logiciel de comparaison, pas un rendement estimé."


class DekadStep(BaseModel):
    dekad: int
    label_fr: str
    phase: PhaseName
    kc: R2
    p_mm: R2
    etc_mm: R2
    eta_mm: R2
    soil_water_mm: R2
    ks: R2
    stress: R2


class CriticalPeriod(BaseModel):
    from_label_fr: str
    to_label_fr: str
    phase: PhaseName
    mean_stress: R2


class SimulationResult(BaseModel):
    crop_id: str
    soil_id: str
    scenario_id: str
    sowing_dekad: int
    harvest_dekad: int
    stress_index: R2
    wrsi: R2
    dekads: list[DekadStep]
    critical_periods: list[CriticalPeriod]
    explanations_fr: list[str]
    assumptions_fr: list[str]
    source_type: SourceType
    data_provenance: list[ProvenanceItem]
    disclaimer_fr: str = SIMULATION_DISCLAIMER_FR


class RuleHit(BaseModel):
    rule_id: str
    delta: R2
    explanation_fr: str


class SeasonSimulationSummary(BaseModel):
    stress_index: R2
    wrsi: R2
    critical_periods: list[CriticalPeriod]
    explanations_fr: list[str]


class SeasonScore(BaseModel):
    season_index: int
    season_id: str
    season_label_fr: str
    sowing_dekad: int
    crop_id: str
    crop_name_fr: str
    previous_crop_id: str | None
    rules_applied: list[RuleHit]
    rule_points: R2
    resilience_points: R2
    priority_points: R2
    season_score: R2
    simulation: SeasonSimulationSummary


class RotationOption(BaseModel):
    rank: int | None
    sequence: list[str]
    sequence_names_fr: list[str]
    total_score: R2
    mean_stress: R2
    seasons: list[SeasonScore]


class RotationPlot(BaseModel):
    zone_id: str
    soil_id: str
    previous_crop_id: str | None = None


class RotationResult(BaseModel):
    zone_id: str
    soil_id: str
    previous_crop_id: str | None
    priority: Priority
    scenario_id: str
    horizon: int = Field(ge=1)
    n_sequences_evaluated: int
    recommendations: list[RotationOption]
    explanations_fr: list[str]
    assumptions_fr: list[str]
    source_type: SourceType
    data_provenance: list[ProvenanceItem]
    disclaimer_fr: str = ROTATION_DISCLAIMER_FR
