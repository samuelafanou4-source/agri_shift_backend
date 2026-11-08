"""Daily reference evapotranspiration, FAO-56 Penman-Monteith (eq. 6) (§6.2).

Simplification (DECISIONS D-12): ea = RH2M_mean/100 × es (no RHmax/RHmin).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline import config

SIGMA = 4.903e-9  # MJ K-4 m-2 day-1
GSC = 0.0820  # solar constant, MJ m-2 min-1


def svp(t):
    """Saturation vapour pressure e°(T), kPa (FAO-56 eq. 11)."""
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def delta_svp(t):
    """Slope of the saturation vapour pressure curve Δ, kPa/°C (eq. 13)."""
    return 4098 * svp(t) / (t + 237.3) ** 2


def pressure(z):
    """Atmospheric pressure, kPa (eq. 7)."""
    return 101.3 * ((293 - 0.0065 * z) / 293) ** 5.26


def psychrometric(z):
    return 0.000665 * pressure(z)


def ra(lat_deg: float, doy):
    """Extraterrestrial radiation, MJ m-2 day-1 (eq. 21)."""
    phi = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    dec = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1, 1))
    return (
        (24 * 60 / np.pi)
        * GSC
        * dr
        * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
    )


def et0_pm(tmean, tmax, tmin, rh, u2, rs, lat_deg: float, z: float, doy):
    """FAO-56 Penman-Monteith ET0 (mm/day), bounded >= 0. Vectorised (numpy/pandas)."""
    es = (svp(tmax) + svp(tmin)) / 2
    ea = rh / 100 * es
    d = delta_svp(tmean)
    gamma = psychrometric(z)
    ra_ = ra(lat_deg, doy)
    rso = (0.75 + 2e-5 * z) * ra_
    rns = 0.77 * rs
    ratio = np.clip(rs / rso, 0.25, 1.0)
    rnl = (
        SIGMA
        * (((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2)
        * (0.34 - 0.14 * np.sqrt(np.maximum(ea, 0)))
        * (1.35 * ratio - 0.35)
    )
    rn = rns - rnl
    g = 0.0
    num = 0.408 * d * (rn - g) + gamma * (900 / (tmean + 273)) * u2 * (es - ea)
    den = d + gamma * (1 + 0.34 * u2)
    return np.maximum(num / den, 0.0)


def add_et0(daily: pd.DataFrame, lat_deg: float, elevation_m: float) -> pd.DataFrame:
    """daily columns from fetch_power CSV -> adds `et0_mm` (NaN where an input is missing)."""
    df = daily.copy()
    dates = pd.to_datetime(df["date"])
    df["et0_mm"] = et0_pm(
        df["t2m"], df["t2m_max"], df["t2m_min"], df["rh2m"], df["ws2m"], df["rs_mj"],
        lat_deg, elevation_m, dates.dt.day_of_year.to_numpy(),
    )  # fmt: skip
    return df


def daily_with_et0(zone_id: str) -> pd.DataFrame:
    """Load data/raw/power/{zone}.csv and compute ET0 (latitude from the seed, elevation from POWER)."""
    from pipeline.fetch_power import zones_by_id

    zone = zones_by_id()[zone_id]
    daily = pd.read_csv(config.RAW_POWER_DIR / f"{zone_id}.csv")
    elevation = float(daily["elevation_m"].dropna().iloc[0])
    return add_et0(daily, zone.latitude, elevation)
