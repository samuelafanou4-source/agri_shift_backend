#!/usr/bin/env python3
"""
Validation de l'ET0 FAO-56 Penman-Monteith (NASA POWER) contre la référence Open-Meteo.

Comparaison de deux réanalyses — pas une mesure de terrain.
  - Notre ET0 : calculée par pipeline/et0.py à partir des données NASA POWER.
  - Référence  : et0_fao_evapotranspiration fournie par Open-Meteo Historical API
                 (source sous-jacente : ERA5-Land / Best Match).

Sorties :
  docs/VALIDATION_ET0.md        — rapport en français
  docs/figures/et0_<zone>.png   — graphique journalier par zone (si matplotlib disponible)

Usage :
  python scripts/validation_et0.py [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--force]

Options :
  --start   Date de début (défaut : 2016-01-01)
  --end     Date de fin   (défaut : 2025-12-31)
  --force   Re-télécharge même si le cache existe déjà
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

RAW_POWER_DIR = REPO_ROOT / "data" / "raw" / "power"
RAW_OPENMETEO_DIR = REPO_ROOT / "data" / "raw" / "openmeteo"
DOCS_DIR = REPO_ROOT / "docs"
FIGURES_DIR = DOCS_DIR / "figures"
ZONES_JSON = REPO_ROOT / "data" / "zones.json"

OPENMETEO_BASE = "https://archive-api.open-meteo.com/v1/archive"
SOURCE_POWER = "nasa_power"
SOURCE_OPENMETEO = "public_historical_reanalysis"

# ---------------------------------------------------------------------------
# Chargement des zones
# ---------------------------------------------------------------------------

def load_zones() -> list[dict]:
    """Lit data/zones.json et renvoie la liste des zones du projet."""
    return json.loads(ZONES_JSON.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Notre ET0 (NASA POWER → pipeline/et0.py)
# ---------------------------------------------------------------------------

def load_power_et0(zone_id: str, start: date, end: date) -> pd.Series:
    """
    Charge les données brutes NASA POWER et recalcule l'ET0 FAO-56.
    Renvoie une Series journalière (index DatetimeIndex, valeur mm/jour).
    Lève FileNotFoundError si le cache NASA est absent.
    """
    csv_path = RAW_POWER_DIR / f"{zone_id}.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"Cache NASA POWER absent : {csv_path}\n"
            "Lancez d'abord : python -m pipeline.run_all"
        )

    from pipeline.et0 import add_et0
    from pipeline.fetch_power import zones_by_id

    zone_seed = zones_by_id()[zone_id]
    daily = pd.read_csv(csv_path, parse_dates=["date"])
    elevation = float(daily["elevation_m"].dropna().iloc[0])
    daily = add_et0(daily, zone_seed.latitude, elevation)

    daily = daily.set_index("date").sort_index()
    mask = (daily.index.date >= start) & (daily.index.date <= end)
    series = daily.loc[mask, "et0_mm"].rename(f"et0_power_{zone_id}")
    return series


# ---------------------------------------------------------------------------
# ET0 Open-Meteo (téléchargement + cache)
# ---------------------------------------------------------------------------

def _openmeteo_cache_path(zone_id: str, start: date, end: date) -> Path:
    fname = f"{zone_id}_{start.strftime('%Y%m%d')}_{end.strftime('%Y%m%d')}.json"
    return RAW_OPENMETEO_DIR / fname


def fetch_openmeteo_et0(
    zone_id: str,
    lat: float,
    lon: float,
    start: date,
    end: date,
    force: bool = False,
) -> pd.Series:
    """
    Télécharge (ou lit depuis le cache) l'ET0 Open-Meteo pour une zone.
    Cache brut : data/raw/openmeteo/{zone_id}_{start}_{end}.json
    Renvoie une Series journalière (index DatetimeIndex, valeur mm/jour).
    """
    RAW_OPENMETEO_DIR.mkdir(parents=True, exist_ok=True)
    cache = _openmeteo_cache_path(zone_id, start, end)

    if cache.is_file() and not force:
        print(f"  [openmeteo] {zone_id}: cache utilisé ({cache.name})")
        payload = json.loads(cache.read_text(encoding="utf-8"))
    else:
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "et0_fao_evapotranspiration",
            "timezone": "auto",
        }
        url = OPENMETEO_BASE + "?" + urllib.parse.urlencode(params)
        print(f"  [openmeteo] {zone_id}: téléchargement {start} → {end}…")
        req = urllib.request.Request(url, headers={"User-Agent": "field-shift-togo-validation/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
        except Exception as exc:
            raise RuntimeError(f"Open-Meteo injoignable pour {zone_id}: {exc}") from exc
        payload = json.loads(raw)
        cache.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        print(f"  [openmeteo] {zone_id}: {len(payload.get('daily', {}).get('time', []))} jours enregistrés → {cache.name}")

    # Vérification d'unité
    daily_units: dict = payload.get("daily_units", {})
    et0_unit = daily_units.get("et0_fao_evapotranspiration", "")
    if et0_unit not in ("mm", "mm/day", ""):
        raise ValueError(
            f"[openmeteo] Unité inattendue pour et0_fao_evapotranspiration : {et0_unit!r}. "
            "Attendu : 'mm' (mm/jour). Vérifiez la réponse API."
        )

    daily = payload.get("daily", {})
    times = daily.get("time", [])
    values = daily.get("et0_fao_evapotranspiration", [])
    if not times:
        raise ValueError(f"[openmeteo] Réponse vide pour {zone_id}")

    series = pd.Series(
        data=[float(v) if v is not None else float("nan") for v in values],
        index=pd.to_datetime(times),
        name=f"et0_openmeteo_{zone_id}",
        dtype=float,
    )
    series.index.name = "date"

    # Restreindre à la fenêtre demandée
    mask = (series.index.date >= start) & (series.index.date <= end)
    return series.loc[mask]


# ---------------------------------------------------------------------------
# Métriques
# ---------------------------------------------------------------------------

def pearson_r(a: np.ndarray, b: np.ndarray) -> float:
    """Corrélation de Pearson sur les paires sans NaN."""
    if len(a) < 2:
        return float("nan")
    a_c = a - a.mean()
    b_c = b - b.mean()
    denom = np.sqrt((a_c**2).sum() * (b_c**2).sum())
    if denom == 0:
        return float("nan")
    return float((a_c * b_c).sum() / denom)


def compute_metrics(power: pd.Series, om: pd.Series, zone_id: str) -> dict[str, Any]:
    """
    Calcule les métriques globales et mensuelles pour une zone.
    Les deux séries sont alignées sur leurs dates communes.
    """
    df = pd.DataFrame({"power": power, "openmeteo": om}).dropna(how="all")
    df.index = pd.to_datetime(df.index)

    n_missing_power = int(power.isna().sum())
    n_missing_om = int(om.isna().sum())

    # Paires valides uniquement
    both = df.dropna()
    n_common = len(both)

    if n_common == 0:
        return {
            "zone_id": zone_id,
            "n_common_days": 0,
            "n_missing_power": n_missing_power,
            "n_missing_openmeteo": n_missing_om,
            "error": "Aucun jour commun valide",
        }

    p = both["power"].to_numpy(dtype=float)
    o = both["openmeteo"].to_numpy(dtype=float)

    mean_power_annual = float(p.mean() * 365.25)
    mean_om_annual = float(o.mean() * 365.25)
    bias_mm_day = float(p.mean() - o.mean())
    rel_diff_pct = float((p.mean() - o.mean()) / o.mean() * 100) if o.mean() != 0 else float("nan")
    r = pearson_r(p, o)

    # Par mois
    monthly: list[dict] = []
    both["month"] = both.index.month
    for m in range(1, 13):
        sub = both[both["month"] == m].dropna()
        if len(sub) < 5:
            monthly.append({"month": m, "n_days": len(sub), "bias": None, "r": None})
            continue
        pm = sub["power"].to_numpy(dtype=float)
        om_m = sub["openmeteo"].to_numpy(dtype=float)
        monthly.append({
            "month": m,
            "n_days": len(sub),
            "mean_power_mm_day": round(float(pm.mean()), 3),
            "mean_om_mm_day": round(float(om_m.mean()), 3),
            "bias_mm_day": round(float(pm.mean() - om_m.mean()), 3),
            "rel_diff_pct": round(float((pm.mean() - om_m.mean()) / om_m.mean() * 100) if om_m.mean() != 0 else float("nan"), 1),
            "r": round(pearson_r(pm, om_m), 4),
        })

    return {
        "zone_id": zone_id,
        "n_common_days": n_common,
        "n_missing_power": n_missing_power,
        "n_missing_openmeteo": n_missing_om,
        "mean_power_mm_day": round(float(p.mean()), 3),
        "mean_om_mm_day": round(float(o.mean()), 3),
        "mean_power_annual_mm": round(mean_power_annual, 1),
        "mean_om_annual_mm": round(mean_om_annual, 1),
        "bias_mm_day": round(bias_mm_day, 3),
        "rel_diff_pct": round(rel_diff_pct, 2),
        "pearson_r": round(r, 4),
        "monthly": monthly,
    }


# ---------------------------------------------------------------------------
# Graphiques
# ---------------------------------------------------------------------------

def plot_zone(power: pd.Series, om: pd.Series, zone_id: str, figures_dir: Path) -> str | None:
    """
    Génère un graphique PNG de l'ET0 journalière des deux sources.
    Renvoie le chemin du fichier créé, ou None si matplotlib absent.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")  # pas d'affichage
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print(f"  [figures] matplotlib absent → pas de graphique pour {zone_id}")
        return None

    figures_dir.mkdir(parents=True, exist_ok=True)

    # Rééchantillonner en hebdomadaire pour la lisibilité
    df = pd.DataFrame({"NASA POWER (notre ET0)": power, "Open-Meteo (ERA5-Land)": om})
    df_w = df.resample("W").mean()

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(df_w.index, df_w["NASA POWER (notre ET0)"], lw=0.9, label="NASA POWER (Penman-Monteith FAO-56)", color="#1976D2")
    ax.plot(df_w.index, df_w["Open-Meteo (ERA5-Land)"], lw=0.9, linestyle="--", label="Open-Meteo (ERA5-Land, référence)", color="#E53935", alpha=0.85)
    ax.set_title(f"ET0 journalière — zone {zone_id}\n(moyennes hebdomadaires, 2016–2025)", fontsize=11)
    ax.set_ylabel("ET0 (mm/jour)")
    ax.set_xlabel("Date")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    out = figures_dir / f"et0_{zone_id}.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"  [figures] {out.name} créé")
    return str(out)


# ---------------------------------------------------------------------------
# Rapport Markdown
# ---------------------------------------------------------------------------

MONTH_FR = ["", "Jan", "Fév", "Mar", "Avr", "Mai", "Jun",
            "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"]

ZONE_NAMES_FR = {
    "maritime_lome": "Maritime – Lomé",
    "plateaux_kpalime": "Plateaux – Kpalimé",
    "kara_kara": "Kara – Kara",
}


def _fmt(v: float | None, decimals: int = 2, suffix: str = "") -> str:
    if v is None or (isinstance(v, float) and (v != v)):  # None ou NaN
        return "—"
    return f"{v:.{decimals}f}{suffix}"


def write_report(
    all_metrics: list[dict],
    start: date,
    end: date,
    figures_created: list[str],
    errors: list[str],
    out_path: Path,
) -> None:
    """Écrit docs/VALIDATION_ET0.md."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    lines = [
        "# Validation ET0 — NASA POWER vs Open-Meteo",
        "",
        f"> **Date de génération** : {today}  ",
        f"> **Période analysée** : {start} → {end}  ",
        f"> **Source NASA POWER** : `source_type: nasa_power` — réanalyse NASA, ET0 recalculée par Penman-Monteith FAO-56 (notre pipeline `pipeline/et0.py`)  ",
        f"> **Source Open-Meteo** : `source_type: public_historical_reanalysis` — ET0 FAO fournie par l'API Open-Meteo Historical (ERA5-Land/Best Match)  ",
        "> **Avertissement** : cette comparaison porte sur deux modèles de réanalyse à des mailles différentes. Ce n'est **pas** une mesure de terrain.",
        "",
        "---",
        "",
        "## Métriques globales par zone",
        "",
        "| Zone | ET0 POWER (mm/an) | ET0 Open-Meteo (mm/an) | Biais (mm/j) | Écart rel. (%) | Corrélation r | Jours communs |",
        "|---|---|---|---|---|---|---|",
    ]

    for m in all_metrics:
        if "error" in m:
            lines.append(f"| {ZONE_NAMES_FR.get(m['zone_id'], m['zone_id'])} | — | — | — | — | — | {m.get('n_common_days', 0)} |")
            continue
        lines.append(
            f"| {ZONE_NAMES_FR.get(m['zone_id'], m['zone_id'])} "
            f"| {_fmt(m.get('mean_power_annual_mm'), 0)} "
            f"| {_fmt(m.get('mean_om_annual_mm'), 0)} "
            f"| {_fmt(m.get('bias_mm_day'), 3)} "
            f"| {_fmt(m.get('rel_diff_pct'), 1)} "
            f"| {_fmt(m.get('pearson_r'), 4)} "
            f"| {m.get('n_common_days', 0)} |"
        )

    lines += ["", "## Jours manquants", "", "| Zone | Manquants POWER | Manquants Open-Meteo |", "|---|---|---|"]
    for m in all_metrics:
        lines.append(
            f"| {ZONE_NAMES_FR.get(m['zone_id'], m['zone_id'])} "
            f"| {m.get('n_missing_power', '—')} "
            f"| {m.get('n_missing_openmeteo', '—')} |"
        )

    lines += ["", "## Métriques mensuelles (biais moyen mm/jour)"]
    for m in all_metrics:
        if "error" in m or "monthly" not in m:
            continue
        zone_name = ZONE_NAMES_FR.get(m["zone_id"], m["zone_id"])
        lines += ["", f"### {zone_name}", "",
                  "| Mois | ET0 POWER (mm/j) | ET0 Open-Meteo (mm/j) | Biais (mm/j) | Écart rel. (%) | r | N jours |",
                  "|---|---|---|---|---|---|---|"]
        max_bias = None
        max_month = None
        for row in m["monthly"]:
            bias_val = row.get("bias_mm_day")
            if bias_val is not None:
                if max_bias is None or abs(bias_val) > abs(max_bias):
                    max_bias = bias_val
                    max_month = row["month"]
            lines.append(
                f"| {MONTH_FR[row['month']]} "
                f"| {_fmt(row.get('mean_power_mm_day'), 2)} "
                f"| {_fmt(row.get('mean_om_mm_day'), 2)} "
                f"| {_fmt(row.get('bias_mm_day'), 3)} "
                f"| {_fmt(row.get('rel_diff_pct'), 1)} "
                f"| {_fmt(row.get('r'), 4)} "
                f"| {row.get('n_days', '—')} |"
            )
        if max_month is not None:
            lines.append(f"\n> **Plus grand biais** : {_fmt(max_bias, 3)} mm/j en {MONTH_FR[max_month]}.")

    # Figures
    lines += ["", "## Graphiques", ""]
    if figures_created:
        for fig_path in figures_created:
            fname = Path(fig_path).name
            zone_id = fname.replace("et0_", "").replace(".png", "")
            zone_name = ZONE_NAMES_FR.get(zone_id, zone_id)
            lines.append(f"![ET0 {zone_name}](figures/{fname})")
            lines.append("")
    else:
        lines.append("*Graphiques non générés (matplotlib absent ou erreur réseau).*")

    # Interprétation
    lines += [
        "",
        "## Interprétation",
        "",
        "### Origine des écarts",
        "",
        "Les deux sources produisent une ET0 de référence FAO-56, mais à partir de données et de mailles différentes :",
        "",
        "| Critère | NASA POWER | Open-Meteo (ERA5-Land) |",
        "|---|---|---|",
        "| Modèle climatique | GEOS-5 (NASA GMAO) | ERA5-Land (ECMWF) |",
        "| Résolution spatiale | ~50 km | ~9 km (ERA5-Land rétropolé) |",
        "| Méthode ET0 | Penman-Monteith FAO-56 **recalculée** par notre pipeline | Penman-Monteith FAO-56 **calculée** par Open-Meteo |",
        "| Variables d'entrée | T2M, RH2M, WS2M, ALLSKY_SFC_SW_DWN, altitude POWER | Températures, humidité, vent, rayonnement ERA5 |",
        "| Rayonnement solaire | ALLSKY_SFC_SW_DWN (toutes conditions de ciel) | Rayonnement ERA5-Land |",
        "",
        "Les différences de biais entre zones reflètent probablement :",
        "- des écarts de représentation du rayonnement solaire (principale source de variabilité de l'ET0 en Afrique de l'Ouest) ;",
        "- des différences d'humidité relative et de vent entre les deux réanalyses ;",
        "- la résolution : NASA POWER à 50 km lisse les gradients locaux (orographie des Plateaux, brise de mer à Lomé).",
        "",
        "### Limites",
        "",
        "- Notre simplification FAO-56 utilise RH2M (moyenne journalière) au lieu de RHmax/RHmin (D-12 dans `DECISIONS.md`), ce qui peut sous-estimer légèrement la demande évaporative.",
        "- Open-Meteo arrondit certaines valeurs à la journée ; NASA POWER est une intégration journalière.",
        "- Cette comparaison ne valide pas le moteur de bilan hydrique, qui utilise nos normales décadaires 1991-2020, pas les valeurs journalières.",
        "",
        "**Ce résultat est une comparaison de deux réanalyses, pas une validation sur données de terrain.**",
        "Les deux sources portent `source_type: nasa_power` et `public_historical_reanalysis` respectivement.",
    ]

    # Erreurs éventuelles
    if errors:
        lines += ["", "## Problèmes rencontrés", ""]
        for e in errors:
            lines.append(f"- {e}")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[rapport] {out_path} créé.")


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def run(start: date, end: date, force: bool = False) -> dict:
    """
    Lance la comparaison pour les 3 zones.
    Renvoie un dict {"metrics": [...], "errors": [...], "figures": [...]}.
    """
    zones = load_zones()
    all_metrics: list[dict] = []
    figures: list[str] = []
    errors: list[str] = []

    for zone in zones:
        zid = zone["zone_id"]
        lat = zone["latitude"]
        lon = zone["longitude"]
        print(f"\n── Zone : {zid} ──")

        # Notre ET0 (NASA POWER)
        try:
            power_et0 = load_power_et0(zid, start, end)
            print(f"  [power]    {len(power_et0)} jours chargés")
        except FileNotFoundError as exc:
            msg = str(exc)
            print(f"  [power] ERREUR : {msg}")
            errors.append(f"{zid} — cache NASA absent : {msg}")
            continue

        # ET0 Open-Meteo
        try:
            om_et0 = fetch_openmeteo_et0(zid, lat, lon, start, end, force=force)
            print(f"  [openmeteo] {len(om_et0)} jours chargés")
        except Exception as exc:
            msg = str(exc)
            print(f"  [openmeteo] ERREUR : {msg}")
            errors.append(f"{zid} — Open-Meteo : {msg}")
            # On calcule quand même les métriques sans OM
            all_metrics.append({"zone_id": zid, "error": msg,
                                 "n_common_days": 0,
                                 "n_missing_power": int(power_et0.isna().sum()),
                                 "n_missing_openmeteo": "?"})
            continue

        # Vérification des unités (mm/jour des deux côtés)
        # NASA POWER : rs_mj converti en MJ, ET0 en mm/j par la formule FAO-56
        # Open-Meteo : et0_fao_evapotranspiration en mm/jour (confirmé dans daily_units)
        # Les deux sont en mm/jour → comparaison directe valide.

        metrics = compute_metrics(power_et0, om_et0, zid)
        all_metrics.append(metrics)

        fig_path = plot_zone(power_et0, om_et0, zid, FIGURES_DIR)
        if fig_path:
            figures.append(fig_path)

    return {"metrics": all_metrics, "errors": errors, "figures": figures}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", default="2016-01-01")
    p.add_argument("--end", default="2025-12-31")
    p.add_argument("--force", action="store_true", help="Re-télécharge même si le cache existe")
    args = p.parse_args(argv)

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    print(f"=== Validation ET0 : {start} → {end} ===")
    result = run(start, end, force=args.force)

    report_path = DOCS_DIR / "VALIDATION_ET0.md"
    write_report(
        all_metrics=result["metrics"],
        start=start,
        end=end,
        figures_created=result["figures"],
        errors=result["errors"],
        out_path=report_path,
    )

    # Résumé console
    print("\n=== RÉSUMÉ ===")
    for m in result["metrics"]:
        if "error" in m:
            print(f"  {m['zone_id']}: ERREUR — {m['error']}")
        else:
            print(
                f"  {m['zone_id']}: "
                f"POWER={m['mean_power_annual_mm']:.0f}mm/an  "
                f"OM={m['mean_om_annual_mm']:.0f}mm/an  "
                f"biais={m['bias_mm_day']:+.3f}mm/j  "
                f"r={m['pearson_r']:.4f}"
            )
    if result["errors"]:
        print("\n⚠  Problèmes rencontrés :")
        for e in result["errors"]:
            print(f"  - {e}")

    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

