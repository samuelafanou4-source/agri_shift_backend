"""Reference data routes (§10.1). Same content as inside the packs."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_pack_store, get_seed, get_session
from app.errors import ApiError
from app.routers.posts import recent_posts
from app.schemas.pack import PackSeason, PackZone
from app.schemas.reference import Crop, Scenario, Soil
from app.services.pack_service import PackStore
from app.services.reference_data import SeedData
from app.services.summary_service import climate_summary, producer_aggregates

router = APIRouter(tags=["reference"])


def zone_view(zone_id: str, seed: SeedData, packs: PackStore) -> PackZone | None:
    """Zone as in its pack (computed sowing dates); seed-only fallback when no pack exists."""
    pf = packs.get(zone_id)
    if pf is not None:
        return pf.pack.zone
    zs = next((z for z in seed.zones if z.zone_id == zone_id), None)
    if zs is None:
        return None
    return PackZone(
        zone_id=zs.zone_id,
        name_fr=zs.name_fr,
        region=zs.region,
        latitude=zs.latitude,
        longitude=zs.longitude,
        elevation_m=None,
        seasons=[
            PackSeason(
                season_id=s.season_id,
                label_fr=s.label_fr,
                sowing_dekad=s.provisional_sowing_dekad,
                sowing_source="provisional_demo",
                provisional_sowing_dekad=s.provisional_sowing_dekad,
                onset_dekad_clim=None,
            )
            for s in zs.seasons
        ],
        coordinate_note=zs.coordinate_note,
    )


@router.get("/zones", response_model=list[PackZone])
def list_zones(seed: SeedData = Depends(get_seed), packs: PackStore = Depends(get_pack_store)):
    return [zone_view(z.zone_id, seed, packs) for z in seed.zones]


@router.get("/crops", response_model=list[Crop])
def list_crops(seed: SeedData = Depends(get_seed)):
    return seed.crops


@router.get("/scenarios", response_model=list[Scenario])
def list_scenarios(seed: SeedData = Depends(get_seed)):
    return seed.scenarios


@router.get("/soils", response_model=list[Soil])
def list_soils(seed: SeedData = Depends(get_seed)):
    return seed.soils


@router.get("/zones/{zone_id}/summary")
async def zone_summary(
    zone_id: str,
    seed: SeedData = Depends(get_seed),
    packs: PackStore = Depends(get_pack_store),
    session: AsyncSession = Depends(get_session),
) -> dict:
    zone = zone_view(zone_id, seed, packs)
    if zone is None:
        raise ApiError(404, "unknown_zone", f"Zone inconnue : {zone_id}")
    pf = packs.get(zone_id)
    crop_names = {c.crop_id: c.name_fr for c in seed.crops}
    posts, _ = await recent_posts(session, zone_id, None, 20)
    return {
        "zone_id": zone.zone_id,
        "name_fr": zone.name_fr,
        "region": zone.region,
        "climate": climate_summary(pf.pack if pf else None),
        "producers": await producer_aggregates(session, zone_id, crop_names),
        "recent_posts": posts,
    }
