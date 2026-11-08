"""Reference data models (data/seed/*.json). Reused inside the ZonePack contract."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import SourceType

WaterLevel = Literal["low", "low_medium", "medium", "medium_high", "high"]
PhaseName = Literal["initial", "development", "mid", "late"]
Priority = Literal["food_security", "drought_resilience", "balanced"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Phases(_Strict):
    initial: float = Field(gt=0)
    development: float = Field(gt=0)
    mid: float = Field(gt=0)
    late: float = Field(gt=0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> Phases:
        total = self.initial + self.development + self.mid + self.late
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"phases must sum to 1 (got {total})")
        return self


class Crop(_Strict):
    crop_id: str
    name_fr: str
    family: str
    n_fixing: bool
    cycle_days: int = Field(gt=0)
    water_need: WaterLevel
    drought_tolerance: WaterLevel
    food_staple: bool
    kc_ini: float = Field(gt=0)
    kc_mid: float = Field(gt=0)
    kc_end: float = Field(gt=0)
    root_depth_m: float = Field(gt=0)
    depletion_p: float = Field(gt=0, lt=1)
    phases: Phases
    source_type: SourceType
    source_note: str | None = None


class Soil(_Strict):
    soil_id: str
    label_fr: str
    taw_mm_per_m: float = Field(gt=0)
    source_type: SourceType
    source_note: str | None = None


ConditionOp = Literal["eq", "neq", "lt", "lte", "gt", "gte", "in", "eq_field"]


class RuleCondition(_Strict):
    field: str = Field(pattern=r"^(prev|next|scenario)\.[a-z_]+$")
    op: ConditionOp
    value: Any

    @model_validator(mode="after")
    def _check_eq_field(self) -> RuleCondition:
        roots = {"prev", "next", "scenario"}
        if self.op == "eq_field" and (
            not isinstance(self.value, str) or self.value.split(".")[0] not in roots
        ):
            raise ValueError("eq_field value must be a field path like 'next.family'")
        if self.op == "in" and not isinstance(self.value, list):
            raise ValueError("'in' value must be a list")
        return self


class Rule(_Strict):
    rule_id: str
    effect: Literal["bonus", "penalty"]
    delta: float
    all: list[RuleCondition] = Field(min_length=1)
    explanation_fr: str
    source_type: SourceType
    source_note: str | None = None


class Scenario(_Strict):
    scenario_id: str
    label_fr: str
    rainfall_change_pct: float
    temperature_change_c: float
    source_type: SourceType
    note_fr: str


class PriorityBonus(_Strict):
    food_staple: float
    drought_level_factor: float


class Scoring(_Strict):
    season_resilience_base: dict[Priority, float]
    priority_bonus: dict[Priority, PriorityBonus]
    drought_levels: dict[WaterLevel, float]
    phase_weights: dict[PhaseName, float]
    et0_temp_sensitivity_per_c: float
    initial_soil_water_fraction: float = Field(ge=0, le=1)
    horizon_default: int = Field(ge=2)
    horizon_max: int = Field(ge=2)
    top_n: int = Field(ge=1)
    source_type: SourceType


class SeasonSeed(_Strict):
    season_id: str
    label_fr: str
    provisional_sowing_dekad: int = Field(ge=1, le=36)
    onset_search_from: int = Field(ge=1, le=36)
    onset_search_to: int = Field(ge=1, le=36)


class ZoneSeed(_Strict):
    zone_id: str
    name_fr: str
    name_long_fr: str | None = None
    region: str
    latitude: float
    longitude: float
    coordinate_note: str
    seasons: list[SeasonSeed] = Field(min_length=1)
    source_type: SourceType
    source_note: str | None = None
