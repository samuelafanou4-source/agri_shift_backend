"""Build packs/{zone_id}.json + manifest.json + zone_pack.schema.json (§6.5, §7).

CLI: python -m pipeline.build_packs [--zone all|<zone_id>] [--export-frontend [PATH]]

Reads data/seed/*.json and data/processed/climatology_{zone_id}.json (written by
pipeline.climatology or by the offline fallback).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.engine.dekad import dekad_label_fr
from app.schemas.common import weakest_source
from app.schemas.pack import ZonePack
from app.services.reference_data import SeedData, load_seed
from pipeline import config

MAX_PACK_BYTES = 100 * 1024
UNITS = {"p_mm": "mm/décade", "et0_mm": "mm/décade", "tmean_c": "°C"}


def climatology_path(zone_id: str) -> Path:
    return config.PROCESSED_DIR / f"climatology_{zone_id}.json"


def assemble_pack(
    seed: SeedData, zone_id: str, clim: dict, pack_version: str, generated_at: datetime
) -> ZonePack:
    """Pure assembly of a ZonePack from the seed and a processed climatology dict."""
    zs = next((z for z in seed.zones if z.zone_id == zone_id), None)
    if zs is None:
        raise ValueError(f"unknown zone {zone_id}")
    onsets: dict[str, int | None] = clim.get("onset_by_season", {})
    seasons = []
    for s in zs.seasons:
        onset = onsets.get(s.season_id)
        seasons.append(
            {
                "season_id": s.season_id,
                "label_fr": s.label_fr,
                "sowing_dekad": onset if onset is not None else s.provisional_sowing_dekad,
                "sowing_source": "computed" if onset is not None else "provisional_demo",
                "provisional_sowing_dekad": s.provisional_sowing_dekad,
                "onset_dekad_clim": onset,
            }
        )
    climate_source = clim["source_type"]
    pack = {
        "schema_version": 1,
        "pack_version": pack_version,
        "generated_at": generated_at,
        "zone": {
            "zone_id": zs.zone_id,
            "name_fr": zs.name_fr,
            "region": zs.region,
            "latitude": zs.latitude,
            "longitude": zs.longitude,
            "elevation_m": clim.get("elevation_m"),
            "seasons": seasons,
            "coordinate_note": zs.coordinate_note,
        },
        "climate": {
            "source_type": climate_source,
            "source_name": clim["source_name"],
            "baseline_period": clim["baseline_period"],
            "units": UNITS,
            "dekads": [{**r, "label_fr": dekad_label_fr(r["dekad"])} for r in clim["normals"]],
            "trend": clim.get("trend"),
            "warnings_fr": clim.get("warnings_fr", []),
        },
        "crops": [c.model_dump() for c in seed.crops],
        "soils": [s.model_dump() for s in seed.soils],
        "rules": [r.model_dump() for r in seed.rules],
        "scenarios": [s.model_dump() for s in seed.scenarios],
        "scoring": seed.scoring.model_dump(),
        "data_provenance": [
            {"item": "climate", "source_type": climate_source},
            {"item": "crops", "source_type": weakest_source([c.source_type for c in seed.crops])},
            {"item": "soils", "source_type": weakest_source([s.source_type for s in seed.soils])},
            {"item": "rules", "source_type": weakest_source([r.source_type for r in seed.rules])},
            {"item": "scoring", "source_type": seed.scoring.source_type},
            {"item": "sowing_calendar", "source_type": _calendar_source(seasons)},
            {"item": "scenarios", "source_type": "synthetic_scenario"},
        ],
    }
    return ZonePack.model_validate(pack)


def _calendar_source(seasons: list[dict]) -> str:
    """Sowing dates: 'computed' only if every season's onset was derived from the climate."""
    return (
        "computed" if all(s["sowing_source"] == "computed" for s in seasons) else "provisional_demo"
    )


def canonical_bytes(pack: ZonePack) -> bytes:
    """Canonical JSON (sorted keys, compact separators, UTF-8). Floats rounded by the schema."""
    return json.dumps(
        pack.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def next_pack_version(packs_dir: Path, now: datetime) -> str:
    day = now.strftime("%Y.%m.%d")
    n = 0
    manifest = packs_dir / "manifest.json"
    if manifest.is_file():
        for entry in json.loads(manifest.read_text(encoding="utf-8")):
            v = str(entry.get("pack_version", ""))
            if v.startswith(day + "-"):
                n = max(n, int(v.rsplit("-", 1)[1]))
    return f"{day}-{n + 1}"


def write_schema(packs_dir: Path) -> Path:
    path = packs_dir / "zone_pack.schema.json"
    schema = ZonePack.model_json_schema(mode="serialization")
    path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_packs(
    seed: SeedData,
    climatologies: dict[str, dict],
    packs_dir: Path = config.PACKS_DIR,
    now: datetime | None = None,
) -> list[dict]:
    """Write one pack per zone + manifest + JSON Schema. Returns the manifest entries."""
    packs_dir.mkdir(parents=True, exist_ok=True)
    now = (now or datetime.now(UTC)).replace(microsecond=0)
    version = next_pack_version(packs_dir, now)
    manifest_path = packs_dir / "manifest.json"
    existing = []
    if manifest_path.is_file():
        existing = [
            e
            for e in json.loads(manifest_path.read_text(encoding="utf-8"))
            if e["zone_id"] not in climatologies
        ]
    entries = []
    for zone_id, clim in climatologies.items():
        pack = assemble_pack(seed, zone_id, clim, version, now)
        raw = canonical_bytes(pack)
        if len(raw) >= MAX_PACK_BYTES:
            raise ValueError(f"pack {zone_id} is {len(raw)} bytes (limit {MAX_PACK_BYTES})")
        (packs_dir / f"{zone_id}.json").write_bytes(raw)
        entries.append(
            {
                "zone_id": zone_id,
                "pack_version": version,
                "sha256": sha256_hex(raw),
                "size_bytes": len(raw),
                "generated_at": now.isoformat().replace("+00:00", "Z"),
            }
        )
    manifest = sorted(existing + entries, key=lambda e: e["zone_id"])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_schema(packs_dir)
    return entries


def export_frontend(packs_dir: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for f in packs_dir.glob("*.json"):
        shutil.copy2(f, target / f.name)
    print(f"[build_packs] copied packs to {target}")


def load_climatologies(zone_ids: list[str]) -> dict[str, dict]:
    out = {}
    for zid in zone_ids:
        path = climatology_path(zid)
        if not path.is_file():
            raise FileNotFoundError(f"{path} missing: run the pipeline (or --offline) first")
        out[zid] = json.loads(path.read_text(encoding="utf-8"))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m pipeline.build_packs")
    p.add_argument("--zone", default="all")
    p.add_argument(
        "--export-frontend",
        nargs="?",
        const=str(config.FRONTEND_PACKS_DEFAULT),
        default=None,
        help="also copy packs/ to this folder (default apps/web/public/packs)",
    )
    args = p.parse_args(argv)
    seed = load_seed(config.SEED_DIR)
    zone_ids = [z.zone_id for z in seed.zones] if args.zone == "all" else [args.zone]
    entries = write_packs(seed, load_climatologies(zone_ids))
    for e in entries:
        src = json.loads((config.PACKS_DIR / f"{e['zone_id']}.json").read_bytes())
        print(
            f"[build_packs] {e['zone_id']}: {e['size_bytes']} bytes, "
            f"{src['climate']['source_type']}, v{e['pack_version']}"
        )
    if args.export_frontend:
        export_frontend(config.PACKS_DIR, Path(args.export_frontend))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
