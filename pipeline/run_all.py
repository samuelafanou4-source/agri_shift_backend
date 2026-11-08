"""Full pipeline: fetch -> ET0 -> dekads -> climatology -> build_packs (§6.7).

CLI: python -m pipeline.run_all [--offline] [--zone all|<zone_id>] [--force] [--export-frontend [PATH]]

--offline : no network; fictional climate from synthetic_fallback (source_type synthetic_demo).
Without --offline, a NASA POWER failure stops the pipeline with an error: it NEVER silently
falls back to synthetic data (rerun explicitly with --offline).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.services.reference_data import load_seed
from pipeline import config
from pipeline import dekads as dekads_step
from pipeline.build_packs import export_frontend, write_packs
from pipeline.climatology import nasa_climatology, write_climatology
from pipeline.fetch_power import run as fetch_run
from pipeline.fetch_power import zone_ids_from_arg, zones_by_id
from pipeline.synthetic_fallback import synthetic_climatology


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m pipeline.run_all")
    p.add_argument("--offline", action="store_true", help="synthetic fallback (no network)")
    p.add_argument("--zone", default="all")
    p.add_argument("--force", action="store_true", help="re-download NASA POWER chunks")
    p.add_argument("--start", default=config.FETCH_START)
    p.add_argument("--end", default=config.FETCH_END)
    p.add_argument("--packs-dir", default=str(config.PACKS_DIR), help="output folder for packs")
    p.add_argument(
        "--export-frontend", nargs="?", const=str(config.FRONTEND_PACKS_DEFAULT), default=None
    )
    args = p.parse_args(argv)

    zone_ids = zone_ids_from_arg(args.zone)
    zones = zones_by_id()
    climatologies: dict[str, dict] = {}
    if args.offline:
        print("[run_all] OFFLINE: synthetic_demo climate (fictional, tests/demo only)")
        for zid in zone_ids:
            climatologies[zid] = synthetic_climatology(zones[zid])
    else:
        fetch_run(zone_ids, args.start, args.end, args.force)
        dekads_step.run(zone_ids)
        for zid in zone_ids:
            climatologies[zid] = nasa_climatology(zones[zid])
    for clim in climatologies.values():
        write_climatology(clim)
        print(
            f"[run_all] {clim['zone_id']}: {clim['source_type']}, "
            f"P={sum(r['p_mm'] for r in clim['normals']):.0f} mm/an, "
            f"ET0={sum(r['et0_mm'] for r in clim['normals']) / 365:.2f} mm/j, "
            f"onset={clim['onset_by_season']}, trend={clim['trend']}"
        )

    entries = write_packs(load_seed(config.SEED_DIR), climatologies, Path(args.packs_dir))
    for e in entries:
        print(f"[run_all] pack {e['zone_id']}: {e['size_bytes']} bytes, v{e['pack_version']}")
    if args.export_frontend:
        export_frontend(Path(args.packs_dir), Path(args.export_frontend))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
