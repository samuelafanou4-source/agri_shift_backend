"""Command line: `python -m app.cli <command>` (run from apps/api).

Commands:
  seed           load data/seed/*.json + synthetic demo plots into the database (idempotent)
  init-db        create tables without Alembic (local SQLite quick start only)
  build-packs    run pipeline.build_packs (from data/processed) [--export-frontend [PATH]]
  export-golden  write packs/golden_cases.json (test contract for the TypeScript engine)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.config import REPO_ROOT, get_settings
from app.db import Database
from app.services.reference_data import load_seed
from app.services.seed_service import seed_all, seed_climate_dekad

# The pipeline package lives at the repository root (pipeline/); make it importable.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


async def _seed(database_url: str | None) -> dict[str, int]:
    settings = get_settings()
    db = Database(database_url or settings.database_url)
    try:
        seed = load_seed(settings.seed_path)
        async with db.session_factory() as session:
            counts = await seed_all(
                session, seed, settings.data_path / "synthetic" / "parcelles_demo.json"
            )
            counts["climate_dekad"] = await seed_climate_dekad(
                session, settings.data_path / "processed", settings.packs_path
            )
            return counts
    finally:
        await db.dispose()


async def _init_db(database_url: str | None) -> None:
    db = Database(database_url or get_settings().database_url)
    try:
        await db.create_all()
    finally:
        await db.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p_seed = sub.add_parser("seed", help="seed reference + demo data (idempotent)")
    p_seed.add_argument("--database-url", default=None)
    p_init = sub.add_parser("init-db", help="create tables without Alembic (SQLite quick start)")
    p_init.add_argument("--database-url", default=None)
    sub.add_parser("export-golden", help="write packs/golden_cases.json")
    p_build = sub.add_parser("build-packs", help="build packs from data/processed")
    p_build.add_argument("--export-frontend", nargs="?", const="", default=None)
    args = parser.parse_args(argv)

    if args.command == "seed":
        counts = asyncio.run(_seed(args.database_url))
        print("Seed OK:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    elif args.command == "init-db":
        asyncio.run(_init_db(args.database_url))
        print("Tables created.")
    elif args.command == "export-golden":
        from app.services.golden import export_golden

        settings = get_settings()
        out = export_golden(
            settings.packs_path, settings.data_path / "synthetic" / "parcelles_demo.json"
        )
        n = len(json.loads(out.read_text(encoding="utf-8"))["cases"])
        print(f"Golden OK: {n} cases -> {out}")
    elif args.command == "build-packs":
        from pipeline.build_packs import main as build_main

        extra = []
        if args.export_frontend is not None:
            extra = ["--export-frontend"] + ([args.export_frontend] if args.export_frontend else [])
        return build_main(extra)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
