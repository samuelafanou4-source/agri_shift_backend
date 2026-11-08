"""ZonePack — the contract shared with the frontend (§7). SOURCE OF TRUTH for packs/{zone_id}.json.

Never remove or rename a field without incrementing `schema_version` (and telling the frontend).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import R2, R2Opt, SourceType
from app.schemas.reference import Crop, Rule, Scenario, Scoring, Soil

SCHEMA_VERSION = 1


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PackSeason(_Strict):
    season_id: str
    label_fr: str
    sowing_dekad: int = Field(ge=1, le=36)
    sowing_source: Literal["computed", "provisional_demo"]
    provisional_sowing_dekad: int = Field(ge=1, le=36)
    onset_dekad_clim: int | None = Field(default=None, ge=1, le=36)


class PackZone(_Strict):
    zone_id: str
    name_fr: str
    region: str
    latitude: float
    longitude: float
    elevation_m: float | None = None  # null when no NASA POWER elevation (offline mode)
    seasons: list[PackSeason] = Field(min_length=1)
    coordinate_note: str


class DekadClimate(_Strict):
    dekad: int = Field(ge=1, le=36)
    label_fr: str
    p_mm: R2
    p_p20: R2
    p_cv: R2Opt = None
    et0_mm: R2
    tmean_c: R2


class Trend(_Strict):
    baseline_period: str
    recent_period: str
    p_change_pct: R2Opt = None
    t_change_c: R2Opt = None
    note_fr: str = "Constat historique, pas une prévision."


class Climate(_Strict):
    source_type: SourceType
    source_name: str
    baseline_period: str
    units: dict[str, str]
    dekads: list[DekadClimate]
    trend: Trend | None = None
    warnings_fr: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _36_sorted(self) -> Climate:
        if [d.dekad for d in self.dekads] != list(range(1, 37)):
            raise ValueError("climate.dekads must contain exactly the 36 dekads, sorted 1..36")
        return self


class ProvenanceItem(_Strict):
    item: str
    source_type: SourceType


class ZonePack(_Strict):
    schema_version: Literal[1] = SCHEMA_VERSION
    pack_version: str
    generated_at: datetime
    zone: PackZone
    climate: Climate
    crops: list[Crop] = Field(min_length=1)
    soils: list[Soil] = Field(min_length=1)
    rules: list[Rule]
    scenarios: list[Scenario] = Field(min_length=1)
    scoring: Scoring
    data_provenance: list[ProvenanceItem]

    @model_validator(mode="after")
    def _unique_ids(self) -> ZonePack:
        for name, key in (
            ("crops", "crop_id"),
            ("soils", "soil_id"),
            ("rules", "rule_id"),
            ("scenarios", "scenario_id"),
        ):
            ids = [getattr(x, key) for x in getattr(self, name)]
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate {key} in {name}")
        return self
