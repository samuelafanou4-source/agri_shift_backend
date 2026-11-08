"""Golden test cases for the TypeScript engine (§9.6): packs/golden_cases.json.

Expected outputs are computed on the packs exactly as stored on disk (what the phone sees).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.engine.rotation import evaluate_sequence, recommend
from app.engine.water_balance import simulate
from app.schemas.engine import RotationPlot
from app.services.pack_service import PackStore

GOLDEN_VERSION = 1
SIM_ZONE = "kara_kara"
SIM_SOILS = ["sandy_loam", "clay"]
SIM_SCENARIOS = ["baseline", "dry_minus20", "hot_plus2"]
REC_SCENARIOS = ["baseline", "dry_minus20"]
V_CASES = [
    ("V001", "groundnut", "maize", "baseline"),
    ("V002", "maize", "sorghum", "baseline"),
    ("V003", "maize", "rice", "dry_minus20"),
]


def _dump(model) -> dict:
    return json.loads(model.model_dump_json())


def build_golden(store: PackStore, demo_plots: list[dict]) -> dict:
    needed = {SIM_ZONE} | {p["zone_id"] for p in demo_plots}
    missing = sorted(z for z in needed if store.get(z) is None)
    if missing:
        raise FileNotFoundError(f"packs missing for {missing}: run the pipeline first")

    cases: list[dict] = []
    kara = store.get(SIM_ZONE).pack
    for crop in [c.crop_id for c in kara.crops]:
        for soil in SIM_SOILS:
            for sc in SIM_SCENARIOS:
                inp = {"zone_id": SIM_ZONE, "crop_id": crop, "soil_id": soil, "scenario_id": sc,
                       "sowing_dekad": None}  # fmt: skip
                out = simulate(kara, crop, soil, sc, None)
                cases.append({"case_id": f"SIM-{crop}-{soil}-{sc}", "function": "simulate",
                              "input": inp, "expected_output": _dump(out)})  # fmt: skip

    for plot in demo_plots:
        pack = store.get(plot["zone_id"]).pack
        rp = RotationPlot(zone_id=plot["zone_id"], soil_id=plot["soil_texture_demo"],
                          previous_crop_id=plot["previous_crop_id"])  # fmt: skip
        for sc in REC_SCENARIOS:
            inp = {**rp.model_dump(), "priority": plot["farmer_priority_demo"], "scenario_id": sc,
                   "horizon": None}  # fmt: skip
            out = recommend(pack, rp, plot["farmer_priority_demo"], sc, None)
            cases.append({"case_id": f"REC-{plot['plot_id']}-{sc}", "function": "recommend",
                          "input": inp, "expected_output": _dump(out)})  # fmt: skip

    for vid, prev, nxt, sc in V_CASES:
        rp = RotationPlot(zone_id=SIM_ZONE, soil_id="sandy_loam", previous_crop_id=prev)
        inp = {**rp.model_dump(), "priority": "balanced", "scenario_id": sc, "sequence": [nxt]}
        out = evaluate_sequence(kara, rp, "balanced", sc, [nxt])
        cases.append({"case_id": vid, "function": "evaluate_sequence", "input": inp,
                      "expected_output": _dump(out)})  # fmt: skip

    packs_used = sorted(needed)
    return {
        "golden_version": GOLDEN_VERSION,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "generator": "apps/api reference engine (python -m app.cli export-golden)",
        "comparison": {
            "numbers_abs_tolerance": 0.01,
            "strict": ["order of recommendations", "sequence", "rule_id lists", "strings", "enums"],
            "note": "Outputs are rounded to 2 decimals at serialization; compare numbers with the "
            "tolerance, everything else strictly.",
        },
        "packs": {
            z: {
                "file": f"{z}.json",
                "pack_version": store.get(z).pack.pack_version,
                "sha256": store.get(z).sha256,
                "climate_source_type": store.get(z).pack.climate.source_type,
            }
            for z in packs_used
        },
        "embedded_packs": {z: json.loads(store.get(z).raw) for z in packs_used},
        "cases": cases,
    }


def export_golden(packs_dir: Path, demo_plots_path: Path) -> Path:
    store = PackStore(packs_dir).scan()
    demo = json.loads(demo_plots_path.read_text(encoding="utf-8"))
    golden = build_golden(store, demo)
    out = packs_dir / "golden_cases.json"
    out.write_text(json.dumps(golden, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
