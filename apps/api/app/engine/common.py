"""Lookups, errors and provenance helpers shared by the engine modules."""

from __future__ import annotations

from app.schemas.common import weakest_source
from app.schemas.pack import ProvenanceItem, ZonePack
from app.schemas.reference import Crop, Scenario, Soil


class EngineError(ValueError):
    """Invalid engine input. `code` matches the API error codes (§10.8)."""

    def __init__(self, code: str, message_fr: str) -> None:
        super().__init__(message_fr)
        self.code = code
        self.message_fr = message_fr


def get_crop(pack: ZonePack, crop_id: str) -> Crop:
    for c in pack.crops:
        if c.crop_id == crop_id:
            return c
    raise EngineError("unknown_crop", f"Culture inconnue : {crop_id}")


def get_soil(pack: ZonePack, soil_id: str) -> Soil:
    for s in pack.soils:
        if s.soil_id == soil_id:
            return s
    raise EngineError("unknown_soil", f"Sol inconnu : {soil_id}")


def get_scenario(pack: ZonePack, scenario_id: str) -> Scenario:
    for s in pack.scenarios:
        if s.scenario_id == scenario_id:
            return s
    raise EngineError("unknown_scenario", f"Scénario inconnu : {scenario_id}")


def _group_source(items: list) -> str:
    return weakest_source([i.source_type for i in items])


def provenance(
    pack: ZonePack, scenario: Scenario, crops: list[Crop], soil: Soil, with_rules: bool
) -> tuple[str, list[ProvenanceItem]]:
    """Result source_type (weakest of climate/crops/soils[/rules], DECISIONS #7) + full list.

    The scenario never enters the weakest-source computation but is always listed.
    """
    items = [
        ProvenanceItem(item="climate", source_type=pack.climate.source_type),
        ProvenanceItem(item="crops", source_type=_group_source(crops)),
        ProvenanceItem(item="soils", source_type=soil.source_type),
    ]
    if with_rules:
        items.append(ProvenanceItem(item="rules", source_type=_group_source(pack.rules)))
        items.append(ProvenanceItem(item="scoring", source_type=pack.scoring.source_type))
    weakest = weakest_source([i.source_type for i in items if i.item != "scoring"])
    items.append(ProvenanceItem(item="scenario", source_type=scenario.source_type))
    return weakest, items
