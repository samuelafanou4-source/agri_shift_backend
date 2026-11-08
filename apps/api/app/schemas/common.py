"""Shared types: provenance, rounding serializer."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import PlainSerializer

SourceType = Literal[
    "nasa_power",
    "public_historical_reanalysis",
    "provisional_demo",
    "synthetic_demo",
    "synthetic_scenario",
    "computed",
]

# Strength order used to compute the "weakest" provenance of a result (§4).
# Lower = weaker. synthetic_scenario is deliberately excluded (DECISIONS.md #7).
SOURCE_STRENGTH: dict[str, int] = {
    "synthetic_demo": 0,
    "provisional_demo": 1,
    "computed": 2,
    "nasa_power": 2,
    "public_historical_reanalysis": 2,
}


def weakest_source(sources: list[str]) -> str:
    ranked = [s for s in sources if s in SOURCE_STRENGTH]
    if not ranked:
        return "computed"
    return min(ranked, key=lambda s: (SOURCE_STRENGTH[s], s))


def _round2(v: float | None) -> float | None:
    return None if v is None else round(float(v), 2)


# Float rounded to 2 decimals at serialization time only (never during computation).
R2 = Annotated[float, PlainSerializer(_round2, return_type=float, when_used="always")]
R2Opt = Annotated[
    float | None, PlainSerializer(_round2, return_type=float | None, when_used="always")
]
