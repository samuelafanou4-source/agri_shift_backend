"""Offline fallback: plausible but FICTIONAL dekadal climate per zone (§6.6).

Everything produced here is `source_type = synthetic_demo`. It is NOT NASA data, NOT observed,
and is only meant to let the pipeline, packs and tests work without network (demo, CI).
Profiles: unimodal for Kara (north), bimodal for Maritime / Plateaux (south).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from pipeline import config
from pipeline.dekads import DEKAD_COLUMNS

RANDOM_SEED = 20261114
SOURCE_TYPE = "synthetic_demo"

# Mean rainfall profile = sum of gaussian bumps (amplitude mm/dekad, centre dekad, width) + floor.
_PROFILES: dict[str, dict] = {
    "maritime_lome": {
        "rain": [(60, 17, 3.5), (30, 29, 2.5)], "rain_floor": 3,
        "et0": (42, 9), "t": (27.0, 1.8),
    },
    "plateaux_kpalime": {
        "rain": [(55, 17, 4.5), (40, 28, 3.5)], "rain_floor": 5,
        "et0": (40, 9), "t": (25.5, 1.8),
    },
    "kara_kara": {
        "rain": [(75, 23, 5.5)], "rain_floor": 1,
        "et0": (48, 12), "t": (27.5, 3.0),
    },
}  # fmt: skip
_DEFAULT_PROFILE = _PROFILES["kara_kara"]


def mean_profile(zone_id: str, d: int) -> tuple[float, float, float]:
    """(rain mm/dekad, et0 mm/dekad, tmean °C) of the fictional mean climate for dekad d."""
    prof = _PROFILES.get(zone_id, _DEFAULT_PROFILE)
    rain = prof["rain_floor"] + sum(
        a * math.exp(-0.5 * ((d - c) / w) ** 2) for a, c, w in prof["rain"]
    )
    phase = 2 * math.pi * (d - 7) / 36  # warmest / most evaporative around March
    et0 = prof["et0"][0] + prof["et0"][1] * math.cos(phase)
    t = prof["t"][0] + prof["t"][1] * math.cos(phase)
    return rain, et0, t


def generate_dekad_series(
    zone_id: str, years: tuple[int, int] = config.BASELINE_PERIOD, seed: int = RANDOM_SEED
) -> pd.DataFrame:
    """Fictional (year, dekad) table with inter-annual noise; fixed seed => reproducible."""
    rng = np.random.default_rng(seed + sum(map(ord, zone_id)))
    rows = []
    for year in range(years[0], years[1] + 1):
        for d in range(1, 37):
            rain, et0, t = mean_profile(zone_id, d)
            p = rain * rng.gamma(shape=4.0, scale=0.25)  # mean factor 1, cv 0.5
            rows.append(
                {
                    "zone_id": zone_id,
                    "year": year,
                    "dekad": d,
                    "p_mm": float(p),
                    "et0_mm": float(et0 * rng.normal(1.0, 0.05)),
                    "tmean_c": float(t + rng.normal(0.0, 0.4)),
                    "tmax_c": float(t + 5.0 + rng.normal(0.0, 0.5)),
                    "n_days": 10,
                    "n_missing": 0,
                    "source_type": SOURCE_TYPE,
                }
            )
    return pd.DataFrame(rows, columns=DEKAD_COLUMNS)


def synthetic_climatology(zone_seed, seed: int = RANDOM_SEED) -> dict:
    """Processed climatology dict (same shape as the NASA path) from the fictional series.

    No `trend` (a fictional series cannot support a historical observation) and no elevation.
    """
    from pipeline.climatology import normals, onset_dekad

    series = generate_dekad_series(zone_seed.zone_id, seed=seed)
    rows = normals(series)
    return {
        "zone_id": zone_seed.zone_id,
        "source_type": SOURCE_TYPE,
        "source_name": config.SOURCES["synthetic"]["source_name"],
        "baseline_period": f"{config.BASELINE_PERIOD[0]}-{config.BASELINE_PERIOD[1]}",
        "elevation_m": None,
        "normals": rows,
        "trend": None,
        "onset_by_season": {
            s.season_id: onset_dekad(rows, s.onset_search_from, s.onset_search_to)
            for s in zone_seed.seasons
        },
        "warnings_fr": list(config.SYNTHETIC_WARNINGS_FR),
    }
