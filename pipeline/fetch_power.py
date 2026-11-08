"""Download NASA POWER daily point data per zone (§6.1).

CLI: python -m pipeline.fetch_power --zone all|<zone_id> --start 1991-01-01 --end 2025-12-31 [--force]

- 10-year chunks, timeout 120 s, 3 retries with exponential backoff, 1 s pause between requests.
- Each chunk response is cached in data/raw/power/{zone_id}/ (idempotent; --force re-downloads).
- Output: data/raw/power/{zone_id}.csv + {zone_id}.meta.json.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pandas as pd

from app.services.reference_data import load_seed
from pipeline import config

PARAM_COLUMNS = {
    "T2M": "t2m",
    "T2M_MAX": "t2m_max",
    "T2M_MIN": "t2m_min",
    "PRECTOTCORR": "precip_mm",
    "RH2M": "rh2m",
    "WS2M": "ws2m",
    "ALLSKY_SFC_SW_DWN": "rs_mj",
}
EXPECTED_UNITS = {
    "T2M": {"C"},
    "T2M_MAX": {"C"},
    "T2M_MIN": {"C"},
    "PRECTOTCORR": {"mm/day"},
    "RH2M": {"%"},
    "WS2M": {"m/s"},
    "ALLSKY_SFC_SW_DWN": {"MJ/m^2/day", "kW-hr/m^2/day"},
}
CSV_COLUMNS = [
    "date",
    "t2m",
    "t2m_max",
    "t2m_min",
    "precip_mm",
    "rh2m",
    "ws2m",
    "rs_mj",
    "elevation_m",
]


class PowerError(RuntimeError):
    pass


def zones_by_id() -> dict:
    return {z.zone_id: z for z in load_seed(config.SEED_DIR).zones}


def zone_ids_from_arg(arg: str) -> list[str]:
    zones = zones_by_id()
    if arg == "all":
        return list(zones)
    if arg not in zones:
        raise SystemExit(f"unknown zone {arg!r} (known: {', '.join(zones)})")
    return [arg]


def chunks(
    start: date, end: date, years: int = config.POWER_CHUNK_YEARS
) -> list[tuple[date, date]]:
    """[1991-01-01..2000-12-31], [2001..2010], ... aligned on `start`'s year."""
    out = []
    y = start.year
    while True:
        c_start = start if y == start.year else date(y, 1, 1)
        c_end = min(end, date(y + years - 1, 12, 31))
        out.append((c_start, c_end))
        if c_end >= end:
            return out
        y += years


def build_url_params(lat: float, lon: float, start: date, end: date) -> dict:
    return {
        "parameters": ",".join(config.POWER_PARAMETERS),
        "community": config.POWER_COMMUNITY,
        "latitude": lat,
        "longitude": lon,
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }


def _get_with_retries(client: httpx.Client, params: dict) -> dict:
    last: Exception | None = None
    for attempt in range(config.POWER_RETRIES + 1):
        try:
            r = client.get(config.POWER_URL, params=params, timeout=config.POWER_TIMEOUT_S)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            last = e
            if attempt < config.POWER_RETRIES:
                time.sleep(2**attempt)
    raise PowerError(f"NASA POWER unreachable after {config.POWER_RETRIES} retries: {last}")


def parse_response(payload: dict) -> tuple[pd.DataFrame, dict]:
    """Daily DataFrame (fill_value -> NaN, radiation in MJ/m²/day) + metadata."""
    fill = payload.get("header", {}).get("fill_value", -999.0)
    units = {k: v.get("units") for k, v in payload.get("parameters", {}).items()}
    for p in config.POWER_PARAMETERS:
        if units.get(p) not in EXPECTED_UNITS[p]:
            raise PowerError(f"unexpected unit for {p}: {units.get(p)!r}")
    params = payload["properties"]["parameter"]
    df = pd.DataFrame(
        {PARAM_COLUMNS[p]: pd.Series(params[p], dtype=float) for p in config.POWER_PARAMETERS}
    )
    df = df.mask(df == fill)
    if units["ALLSKY_SFC_SW_DWN"] == "kW-hr/m^2/day":
        df["rs_mj"] = df["rs_mj"] * 3.6
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "date"
    coords = payload.get("geometry", {}).get("coordinates", [None, None, None])
    meta = {
        "units": units,
        "fill_value": fill,
        "elevation_m": coords[2] if len(coords) > 2 else None,
        "sources": payload.get("header", {}).get("sources"),
        "api_version": payload.get("header", {}).get("api", {}).get("version"),
    }
    return df, meta


def fetch_zone(
    zone, start: date, end: date, force: bool = False, client: httpx.Client | None = None
) -> Path:
    zone_dir = config.RAW_POWER_DIR / zone.zone_id
    zone_dir.mkdir(parents=True, exist_ok=True)
    own = client is None
    client = client or httpx.Client(headers={"User-Agent": "field-shift-togo-pipeline/0.1"})
    urls, frames, metas = [], [], []
    try:
        for c_start, c_end in chunks(start, end):
            cache = zone_dir / f"chunk_{c_start:%Y%m%d}_{c_end:%Y%m%d}.json"
            params = build_url_params(zone.latitude, zone.longitude, c_start, c_end)
            urls.append(str(httpx.URL(config.POWER_URL, params=params)))
            if cache.is_file() and not force:
                payload = json.loads(cache.read_text(encoding="utf-8"))
                print(f"[fetch_power] {zone.zone_id} {c_start}..{c_end}: cached")
            else:
                print(f"[fetch_power] {zone.zone_id} {c_start}..{c_end}: downloading")
                payload = _get_with_retries(client, params)
                cache.write_text(json.dumps(payload), encoding="utf-8")
                time.sleep(config.POWER_PAUSE_S)
            df, meta = parse_response(payload)
            frames.append(df)
            metas.append(meta)
    finally:
        if own:
            client.close()

    daily = pd.concat(frames).sort_index()
    daily = daily[~daily.index.duplicated()]
    elevation = next((m["elevation_m"] for m in metas if m["elevation_m"] is not None), None)
    daily["elevation_m"] = elevation
    out = config.RAW_POWER_DIR / f"{zone.zone_id}.csv"
    daily.reset_index().assign(date=lambda d: d["date"].dt.strftime("%Y-%m-%d"))[
        CSV_COLUMNS
    ].to_csv(out, index=False)
    meta = {
        "zone_id": zone.zone_id,
        "latitude": zone.latitude,
        "longitude": zone.longitude,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "urls": urls,
        "downloaded_at": datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "units": metas[0]["units"],
        "radiation_units_used": "MJ/m^2/day",
        "fill_value": metas[0]["fill_value"],
        "elevation_m": elevation,
        "sources": metas[0]["sources"],
        "api_version": metas[0]["api_version"],
        "n_days": len(daily),
        "n_missing_precip": int(daily["precip_mm"].isna().sum()),
        "source_type": "nasa_power",
    }
    (config.RAW_POWER_DIR / f"{zone.zone_id}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[fetch_power] {zone.zone_id}: {len(daily)} days, elevation {elevation} m -> {out}")
    return out


def run(zone_ids: list[str], start: str, end: str, force: bool = False) -> None:
    zones = zones_by_id()
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    with httpx.Client(headers={"User-Agent": "field-shift-togo-pipeline/0.1"}) as client:
        for zid in zone_ids:
            fetch_zone(zones[zid], s, e, force=force, client=client)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m pipeline.fetch_power")
    p.add_argument("--zone", default="all")
    p.add_argument("--start", default=config.FETCH_START)
    p.add_argument("--end", default=config.FETCH_END)
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)
    run(zone_ids_from_arg(args.zone), args.start, args.end, args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
