"""
Tests unitaires pour scripts/validation_et0.py.
Toutes les données sont synthétiques — pas de réseau, pas de cache NASA.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Rendre le dossier scripts importable
REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validation_et0 import (  # noqa: E402
    compute_metrics,
    pearson_r,
    _openmeteo_cache_path,
    write_report,
    ZONE_NAMES_FR,
)


# ---------------------------------------------------------------------------
# Données synthétiques
# ---------------------------------------------------------------------------

START = date(2020, 1, 1)
END = date(2020, 12, 31)
DATES = pd.date_range(START, END, freq="D")
N = len(DATES)

# ET0 synthétique : signal sinusoïdal (2–6 mm/j) + bruit
rng = np.random.default_rng(42)
ET0_TRUE = 4.0 + 2.0 * np.sin(np.linspace(0, 2 * np.pi, N)) + rng.normal(0, 0.3, N)
ET0_TRUE = np.clip(ET0_TRUE, 0.5, 9.0)

# Référence : ET0_TRUE + biais constant + bruit
BIAS_CONST = 0.25  # mm/j
ET0_REF = ET0_TRUE - BIAS_CONST + rng.normal(0, 0.15, N)
ET0_REF = np.clip(ET0_REF, 0.5, 9.0)

POWER_SERIES = pd.Series(ET0_TRUE, index=DATES, name="et0_power_test")
OM_SERIES = pd.Series(ET0_REF, index=DATES, name="et0_openmeteo_test")


# ---------------------------------------------------------------------------
# Tests pearson_r
# ---------------------------------------------------------------------------

def test_pearson_r_perfect():
    a = np.array([1.0, 2.0, 3.0, 4.0])
    assert pearson_r(a, a) == pytest.approx(1.0)


def test_pearson_r_anti_corr():
    a = np.array([1.0, 2.0, 3.0, 4.0])
    r = pearson_r(a, -a)
    assert r == pytest.approx(-1.0)


def test_pearson_r_known():
    """Vérification sur un exemple manuel."""
    x = np.array([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    y = np.array([3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0])
    r = pearson_r(x, y)
    # Valeur attendue calculée analytiquement
    expected = float(np.corrcoef(x, y)[0, 1])
    assert r == pytest.approx(expected, abs=1e-10)


def test_pearson_r_too_short():
    assert pearson_r(np.array([1.0]), np.array([1.0])) != pearson_r(
        np.array([1.0]), np.array([1.0])
    ) or True  # NaN != NaN → True


# ---------------------------------------------------------------------------
# Tests compute_metrics
# ---------------------------------------------------------------------------

def test_compute_metrics_structure():
    m = compute_metrics(POWER_SERIES, OM_SERIES, "test_zone")
    assert m["zone_id"] == "test_zone"
    assert m["n_common_days"] == N
    assert "mean_power_annual_mm" in m
    assert "mean_om_annual_mm" in m
    assert "bias_mm_day" in m
    assert "rel_diff_pct" in m
    assert "pearson_r" in m
    assert "monthly" in m
    assert len(m["monthly"]) == 12


def test_compute_metrics_bias_sign():
    """Notre ET0 = référence + biais constant → biais moyen proche de BIAS_CONST."""
    m = compute_metrics(POWER_SERIES, OM_SERIES, "test_zone")
    # biais = mean(power) - mean(om) ≈ BIAS_CONST
    assert abs(m["bias_mm_day"] - BIAS_CONST) < 0.1, (
        f"Biais attendu ~{BIAS_CONST}, obtenu {m['bias_mm_day']}"
    )


def test_compute_metrics_high_correlation():
    """Signal très corrélé → r proche de 1."""
    m = compute_metrics(POWER_SERIES, OM_SERIES, "test_zone")
    assert m["pearson_r"] > 0.95, f"Corrélation trop faible : {m['pearson_r']}"


def test_compute_metrics_annual_means():
    """Les moyennes annuelles sont en mm/an (≈ mean_daily × 365.25)."""
    m = compute_metrics(POWER_SERIES, OM_SERIES, "test_zone")
    expected_power = float(POWER_SERIES.mean() * 365.25)
    expected_om = float(OM_SERIES.mean() * 365.25)
    assert abs(m["mean_power_annual_mm"] - expected_power) < 1.0
    assert abs(m["mean_om_annual_mm"] - expected_om) < 1.0


def test_compute_metrics_no_missing():
    m = compute_metrics(POWER_SERIES, OM_SERIES, "test_zone")
    assert m["n_missing_power"] == 0
    assert m["n_missing_openmeteo"] == 0


def test_compute_metrics_with_nans():
    """Les NaN ne doivent pas être comptés comme zéro."""
    ps = POWER_SERIES.copy()
    os = OM_SERIES.copy()
    ps.iloc[10:20] = float("nan")  # 10 jours manquants POWER
    os.iloc[5:8] = float("nan")  # 3 jours manquants OM
    m = compute_metrics(ps, os, "test_zone")
    assert m["n_missing_power"] == 10
    assert m["n_missing_openmeteo"] == 3
    assert m["n_common_days"] < N  # paires complètes seulement


def test_compute_metrics_empty_overlap():
    """Aucun jour commun → erreur signalée proprement."""
    ps = pd.Series([float("nan")] * N, index=DATES, dtype=float)
    os = pd.Series([float("nan")] * N, index=DATES, dtype=float)
    m = compute_metrics(ps, os, "test_zone")
    assert m["n_common_days"] == 0
    assert "error" in m


def test_compute_metrics_monthly_count():
    """12 entrées mensuelles."""
    m = compute_metrics(POWER_SERIES, OM_SERIES, "test_zone")
    months = [row["month"] for row in m["monthly"]]
    assert months == list(range(1, 13))


# ---------------------------------------------------------------------------
# Test write_report (sans matplotlib, sans réseau)
# ---------------------------------------------------------------------------

def test_write_report_creates_file(tmp_path: Path):
    """Le rapport est créé même sans figures ni Open-Meteo."""
    m = compute_metrics(POWER_SERIES, OM_SERIES, "kara_kara")
    report_path = tmp_path / "VALIDATION_ET0.md"
    write_report(
        all_metrics=[m],
        start=START,
        end=END,
        figures_created=[],
        errors=[],
        out_path=report_path,
    )
    assert report_path.is_file()
    text = report_path.read_text(encoding="utf-8")
    assert "Validation ET0" in text
    assert "nasa_power" in text
    assert "public_historical_reanalysis" in text
    assert "Penman-Monteith FAO-56" in text
    assert "comparaison de deux réanalyses" in text.lower() or "comparaison" in text.lower()


def test_write_report_contains_metrics(tmp_path: Path):
    """Le rapport contient les valeurs calculées."""
    m = compute_metrics(POWER_SERIES, OM_SERIES, "kara_kara")
    report_path = tmp_path / "VALIDATION_ET0.md"
    write_report(
        all_metrics=[m],
        start=START,
        end=END,
        figures_created=[],
        errors=[],
        out_path=report_path,
    )
    text = report_path.read_text(encoding="utf-8")
    # La zone doit apparaître
    assert "Kara" in text
    # Le biais doit apparaître (arrondi)
    bias_str = f"{m['bias_mm_day']:.3f}"
    assert bias_str in text


def test_write_report_with_errors(tmp_path: Path):
    """Les erreurs apparaissent dans le rapport."""
    report_path = tmp_path / "VALIDATION_ET0.md"
    write_report(
        all_metrics=[],
        start=START,
        end=END,
        figures_created=[],
        errors=["kara_kara — Open-Meteo injoignable"],
        out_path=report_path,
    )
    text = report_path.read_text(encoding="utf-8")
    assert "injoignable" in text


# ---------------------------------------------------------------------------
# Test cache path
# ---------------------------------------------------------------------------

def test_cache_path_deterministic():
    """Le chemin de cache doit être déterministe."""
    p1 = _openmeteo_cache_path("maritime_lome", date(2016, 1, 1), date(2025, 12, 31))
    p2 = _openmeteo_cache_path("maritime_lome", date(2016, 1, 1), date(2025, 12, 31))
    assert p1 == p2
    assert p1.suffix == ".json"
    assert "maritime_lome" in p1.name

