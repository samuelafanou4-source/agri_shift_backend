#!/usr/bin/env python3
"""
Télécharge des données historiques publiques Open-Meteo pour les 3 points de référence.
Les résultats sont des données de réanalyse, pas des mesures de parcelle.
Usage:
  python scripts/fetch_historical_weather.py --start 2023-01-01 --end 2023-12-31
Dépendances: Python 3.9+ (bibliothèque standard uniquement).
"""
import argparse, csv, json, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZONES = [
    {"zone_id":"maritime_lome","latitude":6.1725,"longitude":1.2314},
    {"zone_id":"plateaux_kpalime","latitude":6.9000,"longitude":0.6333},
    {"zone_id":"kara_kara","latitude":9.5511,"longitude":1.1861},
]
BASE = "https://archive-api.open-meteo.com/v1/archive"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2023-01-01")
    p.add_argument("--end", default="2023-12-31")
    args = p.parse_args()
    outdir = ROOT / "data" / "historical"
    outdir.mkdir(parents=True, exist_ok=True)
    rows = []
    raw = []
    for z in ZONES:
        params = {
            "latitude": z["latitude"], "longitude": z["longitude"],
            "start_date": args.start, "end_date": args.end,
            "daily": "temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum,et0_fao_evapotranspiration",
            "timezone": "Africa/Lome", "temperature_unit": "celsius",
            "precipitation_unit": "mm"
        }
        url = BASE + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent":"AGRI-SHIFT-demo/1.0"})
        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        daily = data.get("daily", {})
        times = daily.get("time", [])
        for i, day in enumerate(times):
            rows.append({
                "zone_id": z["zone_id"], "date": day,
                "temperature_mean_c": daily["temperature_2m_mean"][i],
                "temperature_max_c": daily["temperature_2m_max"][i],
                "temperature_min_c": daily["temperature_2m_min"][i],
                "precipitation_mm": daily["precipitation_sum"][i],
                "et0_mm_day": daily["et0_fao_evapotranspiration"][i],
                "source_type": "public_historical_reanalysis",
                "source_name": "Open-Meteo Historical Weather API (ERA5/ERA5-Land/Best Match)",
                "source_url": url,
                "latitude_requested": z["latitude"], "longitude_requested": z["longitude"],
                "timezone": "Africa/Lome",
                "quality_note": "Reanalysis/model estimate; grid cell may differ from requested point; not parcel measurement."
            })
        raw.append({"zone": z, "request_url": url, "api_response_metadata": {
            "latitude_returned": data.get("latitude"), "longitude_returned": data.get("longitude"),
            "elevation": data.get("elevation"), "timezone": data.get("timezone"),
            "daily_units": data.get("daily_units")
        }})
    csv_path = outdir / "climat_historique_open_meteo.csv"
    json_path = outdir / "climat_historique_open_meteo.json"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["zone_id","date"])
        w.writeheader(); w.writerows(rows)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    (outdir / "metadata_requetes.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {len(rows)} lignes téléchargées")
    print(csv_path)
    print(json_path)

if __name__ == "__main__":
    main()
