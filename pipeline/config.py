"""Pipeline configuration: paths, periods, NASA POWER request, extensible source registry."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:  # make `app` (schemas, engine) importable without install
    sys.path.insert(0, str(API_ROOT))

DATA_DIR = REPO_ROOT / "data"
SEED_DIR = DATA_DIR / "seed"
RAW_POWER_DIR = DATA_DIR / "raw" / "power"
PROCESSED_DIR = DATA_DIR / "processed"
PACKS_DIR = REPO_ROOT / "packs"
FRONTEND_PACKS_DEFAULT = REPO_ROOT / "apps" / "web" / "public" / "packs"

FETCH_START = "1991-01-01"
FETCH_END = "2025-12-31"
BASELINE_PERIOD = (1991, 2020)
RECENT_PERIOD = (2016, 2025)

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
POWER_PARAMETERS = ["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "RH2M", "WS2M", "ALLSKY_SFC_SW_DWN"]
POWER_COMMUNITY = "AG"
POWER_CHUNK_YEARS = 10
POWER_TIMEOUT_S = 120
POWER_RETRIES = 3
POWER_PAUSE_S = 1.0

# Registry of climate sources. Only nasa_power + synthetic fallback are implemented in the MVP;
# GPM IMERG, SMAP, MODIS/VIIRS NDVI, Landsat are out of scope (§15) and only listed here.
SOURCES: dict[str, dict] = {
    "nasa_power": {
        "source_type": "nasa_power",
        "source_name": "NASA POWER daily point (community AG)",
        "implemented": True,
        "url": POWER_URL,
    },
    "synthetic": {
        "source_type": "synthetic_demo",
        "source_name": "Climat synthétique généré hors ligne (fictif, tests uniquement)",
        "implemented": True,
    },
    "open_meteo": {
        "source_type": "public_historical_reanalysis",
        "source_name": "Open-Meteo Historical Weather API (secours)",
        "implemented": False,
        "script": "scripts/fetch_historical_weather.py",
    },
    "gpm_imerg": {"implemented": False},
    "smap": {"implemented": False},
    "modis_viirs_ndvi": {"implemented": False},
    "landsat": {"implemented": False},
}

NASA_WARNINGS_FR = [
    "Réanalyse sur une maille de ~50 km : pas une mesure de votre champ.",
    "Source : NASA POWER (réanalyse/modèle), normales décadaires 1991-2020.",
]
SYNTHETIC_WARNINGS_FR = [
    (
        "DONNÉES SYNTHÉTIQUES — TEST UNIQUEMENT : climat fictif généré hors ligne, "
        "pas des observations ni une réanalyse."
    ),
]
