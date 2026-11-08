"""Load and validate data/seed/*.json (single entry point for CLI seed, pipeline and API)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from app.schemas.reference import Crop, Rule, Scenario, Scoring, Soil, ZoneSeed


@dataclass(frozen=True)
class SeedData:
    crops: list[Crop]
    soils: list[Soil]
    rules: list[Rule]
    scenarios: list[Scenario]
    zones: list[ZoneSeed]
    scoring: Scoring


def _read(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _unique(items: list, key: str, name: str) -> None:
    ids = [getattr(i, key) for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate {key} in {name}")


def load_seed(seed_dir: Path) -> SeedData:
    data = SeedData(
        crops=TypeAdapter(list[Crop]).validate_python(_read(seed_dir / "crops.json")),
        soils=TypeAdapter(list[Soil]).validate_python(_read(seed_dir / "soils.json")),
        rules=TypeAdapter(list[Rule]).validate_python(_read(seed_dir / "rules.json")),
        scenarios=TypeAdapter(list[Scenario]).validate_python(_read(seed_dir / "scenarios.json")),
        zones=TypeAdapter(list[ZoneSeed]).validate_python(_read(seed_dir / "zones.json")),
        scoring=Scoring.model_validate(_read(seed_dir / "scoring.json")),
    )
    _unique(data.crops, "crop_id", "crops.json")
    _unique(data.soils, "soil_id", "soils.json")
    _unique(data.rules, "rule_id", "rules.json")
    _unique(data.scenarios, "scenario_id", "scenarios.json")
    _unique(data.zones, "zone_id", "zones.json")
    return data
