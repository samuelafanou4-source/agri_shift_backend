"""Daily -> dekad aggregation (§6.3).

CLI: python -m pipeline.dekads --zone all|<zone_id>
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from app.engine.dekad import dekad_label_fr  # noqa: F401  (re-exported: "juil. D2")
from pipeline import config

MAX_MISSING = 3
DEKAD_COLUMNS = [
    "zone_id", "year", "dekad", "p_mm", "et0_mm", "tmean_c", "tmax_c",
    "n_days", "n_missing", "source_type",
]  # fmt: skip


def dekad_of(month: int, day: int) -> int:
    """Annual dekad index 1..36: days 1-10 -> D1, 11-20 -> D2, 21-end -> D3."""
    d = 1 if day <= 10 else (2 if day <= 20 else 3)
    return (month - 1) * 3 + d


def aggregate_daily(daily: pd.DataFrame, zone_id: str, source_type: str) -> pd.DataFrame:
    """daily columns: date, precip_mm, et0_mm, t2m, t2m_max. Returns one row per (year, dekad).

    A day is missing if precip, et0 or t2m is NaN. Dekad invalid (values null) if n_missing > 3.
    """
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["dekad"] = [dekad_of(m, d) for m, d in zip(df["date"].dt.month, df["date"].dt.day)]
    df["missing"] = df[["precip_mm", "et0_mm", "t2m"]].isna().any(axis=1)
    g = df.groupby(["year", "dekad"], sort=True)
    out = pd.DataFrame(
        {
            "p_mm": g["precip_mm"].sum(min_count=1),
            "et0_mm": g["et0_mm"].sum(min_count=1),
            "tmean_c": g["t2m"].mean(),
            "tmax_c": g["t2m_max"].mean(),
            "n_days": g.size(),
            "n_missing": g["missing"].sum().astype(int),
        }
    ).reset_index()
    invalid = out["n_missing"] > MAX_MISSING
    out.loc[invalid, ["p_mm", "et0_mm", "tmean_c", "tmax_c"]] = np.nan
    out.insert(0, "zone_id", zone_id)
    out["source_type"] = source_type
    return out[DEKAD_COLUMNS]


def processed_path(zone_id: str):
    return config.PROCESSED_DIR / f"dekad_{zone_id}.csv"


def run(zone_ids: list[str]) -> None:
    from pipeline.et0 import daily_with_et0

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for zid in zone_ids:
        daily = daily_with_et0(zid)
        out = aggregate_daily(daily, zid, "nasa_power")
        out.to_csv(processed_path(zid), index=False)
        print(f"[dekads] {zid}: {len(out)} dekads -> {processed_path(zid)}")


def main(argv: list[str] | None = None) -> int:
    from pipeline.fetch_power import zone_ids_from_arg

    p = argparse.ArgumentParser(prog="python -m pipeline.dekads")
    p.add_argument("--zone", default="all")
    args = p.parse_args(argv)
    run(zone_ids_from_arg(args.zone))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
