"""Idempotent seeding of reference data + synthetic demo devices/plots (§11, `cli seed`)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.services.reference_data import SeedData

# Fixed timestamp so re-seeding produces identical rows (idempotence).
DEMO_TIMESTAMP = datetime(2026, 11, 1, tzinfo=UTC)
DEMO_SEASON_LABEL = "2025-main"
# Can never equal a sha256 hex digest -> demo devices cannot authenticate.
DEMO_TOKEN_HASH = "demo-device-no-token"
_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://fieldshift.tg/demo")


def demo_uuid(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"{kind}:{key}")


async def seed_reference(session: AsyncSession, seed: SeedData) -> dict[str, int]:
    for z in seed.zones:
        existing = await session.get(m.Zone, z.zone_id)
        await session.merge(
            m.Zone(
                zone_id=z.zone_id,
                name_fr=z.name_fr,
                region=z.region,
                latitude=z.latitude,
                longitude=z.longitude,
                # elevation comes from NASA POWER (pipeline); never overwritten by the seed.
                elevation_m=existing.elevation_m if existing else None,
                seasons=[s.model_dump() for s in z.seasons],
                source_type=z.source_type,
            )
        )
    for c in seed.crops:
        await session.merge(m.Crop(**c.model_dump(mode="json")))
    for s in seed.soils:
        await session.merge(
            m.Soil(
                soil_id=s.soil_id,
                label_fr=s.label_fr,
                taw_mm_per_m=s.taw_mm_per_m,
                source_type=s.source_type,
            )
        )
    for r in seed.rules:
        await session.merge(
            m.RotationRule(
                rule_id=r.rule_id,
                effect=r.effect,
                delta=r.delta,
                conditions=[c.model_dump(mode="json") for c in r.all],
                explanation_fr=r.explanation_fr,
                source_type=r.source_type,
            )
        )
    for sc in seed.scenarios:
        await session.merge(m.Scenario(**sc.model_dump()))
    return {
        "zones": len(seed.zones),
        "crops": len(seed.crops),
        "soils": len(seed.soils),
        "rules": len(seed.rules),
        "scenarios": len(seed.scenarios),
    }


async def seed_demo_plots(session: AsyncSession, demo_path: Path) -> int:
    """Create one synthetic_demo device + plot (+ previous-crop season) per demo plot."""
    with demo_path.open(encoding="utf-8") as f:
        demo = json.load(f)
    for row in demo:
        key = row["plot_id"]
        device_id = demo_uuid("device", key)
        plot_id = demo_uuid("plot", key)
        await session.merge(
            m.Device(
                device_id=device_id,
                token_hash=DEMO_TOKEN_HASH,
                display_name=f"Démo {key} (fictif)",
                zone_id=row["zone_id"],
                priority=row["farmer_priority_demo"],
                created_at=DEMO_TIMESTAMP,
                last_seen_at=None,
                source_type="synthetic_demo",
            )
        )
        await session.merge(
            m.Plot(
                id=plot_id,
                device_id=device_id,
                zone_id=row["zone_id"],
                name=f"Parcelle de démonstration {key[-3:]}",
                area_ha=row["area_ha"],
                soil_id=row["soil_texture_demo"],
                updated_at=DEMO_TIMESTAMP,
                server_updated_at=DEMO_TIMESTAMP,
                deleted=False,
                source_type="synthetic_demo",
            )
        )
        if row.get("previous_crop_id"):
            await session.merge(
                m.PlotSeason(
                    id=demo_uuid("plot_season", key),
                    plot_id=plot_id,
                    device_id=device_id,
                    season_label=DEMO_SEASON_LABEL,
                    crop_id=row["previous_crop_id"],
                    sowing_date=None,
                    yield_note=None,
                    losses_note=None,
                    updated_at=DEMO_TIMESTAMP,
                    server_updated_at=DEMO_TIMESTAMP,
                    deleted=False,
                )
            )
    return len(demo)


async def seed_all(session: AsyncSession, seed: SeedData, demo_path: Path) -> dict[str, int]:
    counts = await seed_reference(session, seed)
    await session.flush()
    counts["demo_plots"] = await seed_demo_plots(session, demo_path)
    await session.commit()
    return counts


async def seed_climate_dekad(session: AsyncSession, processed_dir: Path, packs_dir: Path) -> int:
    """Load data/processed/dekad_{zone}.csv into climate_dekad (delete + insert per zone).

    Also refreshes the zones' NASA POWER elevation and the `packs` table from packs/manifest.json.
    Silently does nothing for files that do not exist (pipeline not run yet).
    """
    import csv

    from sqlalchemy import delete

    total = 0
    for path in sorted(processed_dir.glob("dekad_*.csv")):
        zone_id = path.stem.removeprefix("dekad_")
        if await session.get(m.Zone, zone_id) is None:
            continue
        await session.execute(delete(m.ClimateDekad).where(m.ClimateDekad.zone_id == zone_id))

        def f(v: str) -> float | None:
            return None if v in ("", "nan", "NaN") else float(v)

        with path.open(encoding="utf-8") as fh:
            rows = [
                m.ClimateDekad(
                    zone_id=zone_id,
                    year=int(r["year"]),
                    dekad=int(r["dekad"]),
                    p_mm=f(r["p_mm"]),
                    et0_mm=f(r["et0_mm"]),
                    tmean_c=f(r["tmean_c"]),
                    tmax_c=f(r["tmax_c"]),
                    n_days=int(r["n_days"]),
                    n_missing=int(r["n_missing"]),
                    source_type=r["source_type"],
                )
                for r in csv.DictReader(fh)
            ]
        session.add_all(rows)
        total += len(rows)
        meta_path = processed_dir.parent / "raw" / "power" / f"{zone_id}.meta.json"
        if meta_path.is_file():
            zone = await session.get(m.Zone, zone_id)
            zone.elevation_m = json.loads(meta_path.read_text(encoding="utf-8")).get("elevation_m")

    manifest = packs_dir / "manifest.json"
    if manifest.is_file():
        for e in json.loads(manifest.read_text(encoding="utf-8")):
            if await session.get(m.Zone, e["zone_id"]) is None:
                continue
            await session.merge(
                m.Pack(
                    zone_id=e["zone_id"],
                    pack_version=e["pack_version"],
                    sha256=e["sha256"],
                    size_bytes=e["size_bytes"],
                    generated_at=datetime.fromisoformat(e["generated_at"]),
                )
            )
    await session.commit()
    return total
