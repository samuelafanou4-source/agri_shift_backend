"""Dekadal normals, variability, historical trend, climatological season onset (§6.4)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from pipeline import config

ONSET_P_MIN = 25.0  # mm in the onset dekad
ONSET_NEXT2_MIN = 20.0  # mm over the 2 following dekads
CV_MIN_MEAN = 1.0


def _period_label(period: tuple[int, int]) -> str:
    return f"{period[0]}-{period[1]}"


def normals(dekad_df: pd.DataFrame, baseline=config.BASELINE_PERIOD) -> list[dict]:
    """36 rows: p_mm, et0_mm, tmean_c (means), p_p20 (20th percentile), p_cv (std/mean)."""
    y0, y1 = baseline
    base = dekad_df[(dekad_df["year"] >= y0) & (dekad_df["year"] <= y1)]
    rows = []
    for d in range(1, 37):
        sub = base[base["dekad"] == d]
        p = sub["p_mm"].dropna().to_numpy(dtype=float)
        if len(p) == 0:
            raise ValueError(f"no valid precipitation for dekad {d} in {y0}-{y1}")
        p_mean = float(p.mean())
        p_cv = None
        if p_mean >= CV_MIN_MEAN and len(p) > 1:
            p_cv = float(p.std(ddof=1) / p_mean)
        rows.append(
            {
                "dekad": d,
                "p_mm": p_mean,
                "p_p20": float(np.percentile(p, 20)),
                "p_cv": p_cv,
                "et0_mm": float(sub["et0_mm"].dropna().mean()),
                "tmean_c": float(sub["tmean_c"].dropna().mean()),
            }
        )
    for r in rows:
        for k in ("et0_mm", "tmean_c"):
            if math.isnan(r[k]):
                raise ValueError(f"no valid {k} for dekad {r['dekad']}")
    return rows


def _annual(dekad_df: pd.DataFrame) -> pd.DataFrame:
    """Per year: total precipitation and mean temperature, only for years with 36 valid dekads."""
    g = dekad_df.groupby("year")
    ann = pd.DataFrame(
        {
            "p_total": g["p_mm"].sum(min_count=1),
            "t_mean": g["tmean_c"].mean(),
            "n_valid": g["p_mm"].count(),
        }
    )
    return ann[ann["n_valid"] == 36]


def trend(
    dekad_df: pd.DataFrame,
    baseline=config.BASELINE_PERIOD,
    recent=config.RECENT_PERIOD,
) -> dict | None:
    """Recent period vs baseline: change in annual rainfall (%) and mean temperature (°C).

    Historical observation, never a forecast. None if the recent period is not fully covered.
    """
    ann = _annual(dekad_df)
    b = ann[(ann.index >= baseline[0]) & (ann.index <= baseline[1])]
    r = ann[(ann.index >= recent[0]) & (ann.index <= recent[1])]
    if len(r) < (recent[1] - recent[0] + 1) or len(b) < 20:
        return None
    return {
        "baseline_period": _period_label(baseline),
        "recent_period": _period_label(recent),
        "p_change_pct": float(100 * (r["p_total"].mean() / b["p_total"].mean() - 1)),
        "t_change_c": float(r["t_mean"].mean() - b["t_mean"].mean()),
        "note_fr": "Constat historique, pas une prévision.",
    }


def onset_dekad(normal_rows: list[dict], search_from: int, search_to: int) -> int | None:
    """First dekad in [from..to] (wrapping) with p >= 25 mm and p(d+1)+p(d+2) >= 20 mm."""
    p = {r["dekad"]: r["p_mm"] for r in normal_rows}

    def w(d: int) -> int:
        return ((d - 1) % 36) + 1

    length = (search_to - search_from) % 36 + 1
    for k in range(length):
        d = w(search_from + k)
        if p[d] >= ONSET_P_MIN and p[w(d + 1)] + p[w(d + 2)] >= ONSET_NEXT2_MIN:
            return d
    return None


def nasa_climatology(zone_seed) -> dict:
    """Processed climatology dict from data/processed/dekad_{zone}.csv (NASA POWER path)."""
    import json

    from pipeline.dekads import processed_path

    df = pd.read_csv(processed_path(zone_seed.zone_id))
    meta = json.loads(
        (config.RAW_POWER_DIR / f"{zone_seed.zone_id}.meta.json").read_text(encoding="utf-8")
    )
    rows = normals(df)
    return {
        "zone_id": zone_seed.zone_id,
        "source_type": "nasa_power",
        "source_name": config.SOURCES["nasa_power"]["source_name"],
        "baseline_period": _period_label(config.BASELINE_PERIOD),
        "elevation_m": meta.get("elevation_m"),
        "normals": rows,
        "trend": trend(df),
        "onset_by_season": {
            s.season_id: onset_dekad(rows, s.onset_search_from, s.onset_search_to)
            for s in zone_seed.seasons
        },
        "warnings_fr": list(config.NASA_WARNINGS_FR),
        "derived_from": {
            "raw": f"data/raw/power/{zone_seed.zone_id}.csv",
            "downloaded_at": meta.get("downloaded_at"),
            "api_version": meta.get("api_version"),
        },
    }


def write_climatology(clim: dict) -> None:
    import json

    from pipeline.build_packs import climatology_path

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    climatology_path(clim["zone_id"]).write_text(
        json.dumps(clim, ensure_ascii=False, indent=2), encoding="utf-8"
    )
