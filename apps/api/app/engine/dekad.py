"""Dekad utilities (§9.1, §9.2). Pure functions; mirrored 1:1 by the TypeScript engine."""

from __future__ import annotations

import math

from app.schemas.reference import Crop, PhaseName

N_DEKADS = 36
MONTHS_FR = [
    "janv.", "févr.", "mars", "avr.", "mai", "juin",
    "juil.", "août", "sept.", "oct.", "nov.", "déc.",
]  # fmt: skip
PHASE_ORDER: tuple[PhaseName, ...] = ("initial", "development", "mid", "late")


def wrap_dekad(d: int) -> int:
    """Dekads loop: after 36 comes 1 (and 0 -> 36)."""
    return ((d - 1) % N_DEKADS) + 1


def dekad_label_fr(d: int) -> str:
    d = wrap_dekad(d)
    return f"{MONTHS_FR[(d - 1) // 3]} D{(d - 1) % 3 + 1}"


def n_cycle_dekads(cycle_days: int) -> int:
    return math.ceil(cycle_days / 10)


def phase_bounds(crop: Crop) -> list[tuple[PhaseName, float, float]]:
    """Cumulative [start, end) per phase, summed in fixed order initial→late."""
    out: list[tuple[PhaseName, float, float]] = []
    start = 0.0
    for name in PHASE_ORDER:
        end = start + getattr(crop.phases, name)
        out.append((name, start, end))
        start = end
    return out


def phase_at(i: int, n: int, crop: Crop) -> tuple[PhaseName, float]:
    """Phase of dekad i (0-indexed) of an n-dekad cycle, and relative position within the phase.

    f = (i + 0.5) / n; first phase whose end > f (the last phase catches f >= its start).
    """
    f = (i + 0.5) / n
    bounds = phase_bounds(crop)
    for name, start, end in bounds:
        if f < end:
            return name, (f - start) / (end - start)
    name, start, end = bounds[-1]
    return name, (f - start) / (end - start)


def kc_at(i: int, n: int, crop: Crop) -> tuple[PhaseName, float]:
    """Simplified FAO Kc curve: flat ini, linear ini→mid, flat mid, linear mid→end."""
    phase, pos = phase_at(i, n, crop)
    if phase == "initial":
        kc = crop.kc_ini
    elif phase == "development":
        kc = crop.kc_ini + (crop.kc_mid - crop.kc_ini) * pos
    elif phase == "mid":
        kc = crop.kc_mid
    else:
        kc = crop.kc_mid + (crop.kc_end - crop.kc_mid) * pos
    return phase, kc
