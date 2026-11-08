"""French explanation templates (§9.4).

Number formatting is deterministic and easy to mirror in TypeScript:
round half up (floor(x * 10^n + 0.5) / 10^n), French decimal comma, explicit sign where asked.
"""

from __future__ import annotations

import math

from app.schemas.engine import CriticalPeriod
from app.schemas.pack import ZonePack
from app.schemas.reference import Crop, Scenario, Soil

PHASE_FR = {
    "initial": "levée",
    "development": "croissance",
    "mid": "floraison/remplissage",
    "late": "maturation",
}


def round_half_up(x: float, ndigits: int) -> float:
    k = 10**ndigits
    return math.floor(x * k + 0.5) / k


def fmt_num(x: float, ndigits: int = 2, signed: bool = False) -> str:
    """0.456 -> '0,46'; 20.0 -> '20'; signed: -20 -> '-20', 2 -> '+2', 0 -> '+0'."""
    v = round_half_up(x, ndigits)
    if v == 0:
        v = 0.0  # avoid '-0'
    s = f"{v:.{ndigits}f}".rstrip("0").rstrip(".") if ndigits > 0 else f"{v:.0f}"
    s = s.replace(".", ",")
    if signed and v >= 0:
        s = "+" + s
    return s


def scenario_line(scenario: Scenario) -> str:
    return (
        f"Scénario hypothétique : pluie {fmt_num(scenario.rainfall_change_pct, 1, signed=True)} %, "
        f"température {fmt_num(scenario.temperature_change_c, 1, signed=True)} °C."
    )


def critical_line(crop: Crop, cp: CriticalPeriod) -> str:
    return (
        f"{crop.name_fr} : manque d'eau en {PHASE_FR[cp.phase]} "
        f"({cp.from_label_fr} → {cp.to_label_fr}), stress moyen {fmt_num(cp.mean_stress, 2)}."
    )


def wrsi_line(wrsi: float) -> str:
    return f"Besoins en eau couverts à {fmt_num(wrsi, 0)} %."


NO_STRESS_LINE = "Pas de manque d'eau marqué sur le cycle dans ce scénario."


def simulation_explanations(
    crop: Crop, scenario: Scenario, critical: list[CriticalPeriod], wrsi: float
) -> list[str]:
    lines = [scenario_line(scenario)]
    if critical:
        lines.extend(critical_line(crop, cp) for cp in critical)
    else:
        lines.append(NO_STRESS_LINE)
    lines.append(wrsi_line(wrsi))
    return lines


def common_assumptions(pack: ZonePack) -> list[str]:
    out = []
    if pack.climate.source_type == "synthetic_demo":
        out.append("DONNÉES SYNTHÉTIQUES — TEST UNIQUEMENT : le climat utilisé est fictif.")
    out.append(
        f"Climat moyen {pack.climate.baseline_period} par décade "
        f"({pack.climate.source_name}), pas la météo d'une année précise."
    )
    out.append(
        "Sensibilité de l'ET0 à la température : "
        f"{fmt_num(pack.scoring.et0_temp_sensitivity_per_c * 100, 1)} % par °C."
    )
    out.append(
        "Pas de ruissellement ni de drainage modélisés : la pluie remplit la réserve du sol, "
        "le surplus au-delà de la réserve est perdu."
    )
    out.append(
        "Paramètres de cultures, de sols et de règles provisoires, à valider par un agronome."
    )
    return out


def soil_assumption(pack: ZonePack, soil: Soil, crop: Crop, taw: float) -> str:
    return (
        f"Réserve utile du sol : {fmt_num(taw, 0)} mm ({soil.label_fr}, enracinement "
        f"{fmt_num(crop.root_depth_m, 2)} m), remplie à "
        f"{fmt_num(pack.scoring.initial_soil_water_fraction * 100, 0)} % au semis."
    )


RICE_ASSUMPTION = "Riz traité en culture pluviale (ni irrigation ni submersion)."
