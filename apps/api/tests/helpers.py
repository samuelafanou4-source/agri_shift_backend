"""Test helpers: build in-memory packs without network (synthetic_demo climate)."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache

from app.config import REPO_ROOT
from app.schemas.pack import ZonePack
from app.services.reference_data import load_seed

SEED = load_seed(REPO_ROOT / "data" / "seed")
GENERATED_AT = datetime(2026, 11, 4, tzinfo=UTC)


@lru_cache
def synthetic_pack(zone_id: str) -> ZonePack:
    from pipeline.build_packs import assemble_pack
    from pipeline.synthetic_fallback import synthetic_climatology

    zone = next(z for z in SEED.zones if z.zone_id == zone_id)
    return assemble_pack(SEED, zone_id, synthetic_climatology(zone), "test-1", GENERATED_AT)


def constant_climate_pack(
    base: ZonePack, p_mm: float, et0_mm: float, source_type: str | None = None
) -> ZonePack:
    """Copy of `base` with the same (p, et0) in all 36 dekads — for hand-checked computations."""
    data = base.model_dump()
    for d in data["climate"]["dekads"]:
        d["p_mm"] = p_mm
        d["et0_mm"] = et0_mm
    if source_type:
        data["climate"]["source_type"] = source_type
    return ZonePack.model_validate(data)
