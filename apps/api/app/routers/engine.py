"""Online engine (§10.7): same reference engine as the golden file, on the zone's pack. No auth."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from app.deps import get_pack_store
from app.engine.common import EngineError
from app.engine.rotation import recommend
from app.engine.water_balance import simulate
from app.errors import ApiError
from app.schemas.engine import (
    ROTATION_DISCLAIMER_FR,
    RotationPlot,
    RotationResult,
    SimulationResult,
)
from app.schemas.pack import ZonePack
from app.schemas.reference import Priority
from app.services.pack_service import PackStore

router = APIRouter(tags=["engine"])


class SimulateRequest(BaseModel):
    zone_id: str
    crop_id: str
    soil_id: str
    scenario_id: str
    sowing_dekad: int | None = None


class RecommendRequest(BaseModel):
    zone_id: str
    soil_id: str
    previous_crop_id: str | None = None
    priority: Priority
    scenario_id: str
    horizon: int | None = None


class CompareScenariosRequest(BaseModel):
    zone_id: str
    soil_id: str
    previous_crop_id: str | None = None
    priority: Priority
    scenario_ids: list[str] = Field(min_length=1)
    horizon: int | None = None

    @field_validator("scenario_ids")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("scenario_ids must be unique")
        return v


class CompareScenariosResponse(BaseModel):
    zone_id: str
    soil_id: str
    previous_crop_id: str | None
    priority: Priority
    results: list[RotationResult]
    disclaimer_fr: str = ROTATION_DISCLAIMER_FR


def _pack(packs: PackStore, zone_id: str) -> ZonePack:
    pf = packs.get(zone_id)
    if pf is None:
        raise ApiError(404, "unknown_zone", f"Zone inconnue ou paquet absent : {zone_id}")
    return pf.pack


def _engine_error(e: EngineError) -> ApiError:
    return ApiError(400, e.code, e.message_fr)


@router.post("/simulate", response_model=SimulationResult)
def post_simulate(body: SimulateRequest, packs: PackStore = Depends(get_pack_store)):
    pack = _pack(packs, body.zone_id)
    try:
        return simulate(pack, body.crop_id, body.soil_id, body.scenario_id, body.sowing_dekad)
    except EngineError as e:
        raise _engine_error(e) from e


@router.post("/rotation/recommend", response_model=RotationResult)
def post_recommend(body: RecommendRequest, packs: PackStore = Depends(get_pack_store)):
    pack = _pack(packs, body.zone_id)
    plot = RotationPlot(
        zone_id=body.zone_id, soil_id=body.soil_id, previous_crop_id=body.previous_crop_id
    )
    try:
        return recommend(pack, plot, body.priority, body.scenario_id, body.horizon)
    except EngineError as e:
        raise _engine_error(e) from e


@router.post("/rotation/compare-scenarios", response_model=CompareScenariosResponse)
def post_compare(body: CompareScenariosRequest, packs: PackStore = Depends(get_pack_store)):
    pack = _pack(packs, body.zone_id)
    plot = RotationPlot(
        zone_id=body.zone_id, soil_id=body.soil_id, previous_crop_id=body.previous_crop_id
    )
    try:
        results = [
            recommend(pack, plot, body.priority, sid, body.horizon) for sid in body.scenario_ids
        ]
    except EngineError as e:
        raise _engine_error(e) from e
    return CompareScenariosResponse(
        zone_id=body.zone_id,
        soil_id=body.soil_id,
        previous_crop_id=body.previous_crop_id,
        priority=body.priority,
        results=results,
    )
