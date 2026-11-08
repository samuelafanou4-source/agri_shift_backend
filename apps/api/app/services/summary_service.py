"""Public zone summary (§10.5): climate key figures + ANONYMOUS producer aggregates + recent posts.

Anonymity: a crop is shown only if declared on >= 3 distinct plots for that season_label;
otherwise it is merged into "autres". Seeded demo plots (synthetic_demo) are never counted.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.schemas.pack import ZonePack

ANONYMITY_THRESHOLD = 3


def climate_summary(pack: ZonePack | None) -> dict | None:
    if pack is None:
        return None
    c = pack.climate
    wettest = max(c.dekads, key=lambda d: d.p_mm)
    return {
        "source_type": c.source_type,
        "source_name": c.source_name,
        "baseline_period": c.baseline_period,
        "annual_p_mm": round(sum(d.p_mm for d in c.dekads), 2),
        "annual_et0_mm": round(sum(d.et0_mm for d in c.dekads), 2),
        "mean_tmean_c": round(sum(d.tmean_c for d in c.dekads) / 36, 2),
        "wettest_dekad": {
            "dekad": wettest.dekad,
            "label_fr": wettest.label_fr,
            "p_mm": round(wettest.p_mm, 2),
        },
        "trend": c.trend.model_dump(mode="json") if c.trend else None,
        "warnings_fr": c.warnings_fr,
        "seasons": [s.model_dump() for s in pack.zone.seasons],
    }


def _real_plot(zone_id: str):
    """Non-deleted, non-demo plots of the zone."""
    return (
        m.Plot.zone_id == zone_id,
        m.Plot.deleted.is_(False),
        m.Plot.source_type.is_(None),
    )


async def producer_aggregates(
    session: AsyncSession, zone_id: str, crop_names: dict[str, str]
) -> dict:
    n_plots = (
        await session.execute(select(func.count()).select_from(m.Plot).where(*_real_plot(zone_id)))
    ).scalar_one()
    rows = (
        await session.execute(
            select(
                m.PlotSeason.season_label,
                m.PlotSeason.crop_id,
                func.count(func.distinct(m.PlotSeason.plot_id)),
            )
            .join(m.Plot, m.Plot.id == m.PlotSeason.plot_id)
            .where(
                *_real_plot(zone_id),
                m.PlotSeason.deleted.is_(False),
                m.PlotSeason.crop_id.is_not(None),
            )
            .group_by(m.PlotSeason.season_label, m.PlotSeason.crop_id)
        )
    ).all()
    by_season: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for label, crop_id, n in rows:
        by_season[label].append((crop_id, n))

    seasons = []
    for label in sorted(by_season, reverse=True):
        shown = sorted(
            [(c, n) for c, n in by_season[label] if n >= ANONYMITY_THRESHOLD],
            key=lambda t: (-t[1], t[0]),
        )
        hidden = [(c, n) for c, n in by_season[label] if n < ANONYMITY_THRESHOLD]
        crops = [{"crop_id": c, "name_fr": crop_names.get(c, c), "n_plots": n} for c, n in shown]
        if hidden:
            # Sum of per-crop distinct plots (a plot with 2 hidden crops counts twice).
            crops.append(
                {"crop_id": "other", "name_fr": "autres", "n_plots": sum(n for _, n in hidden)}
            )
        seasons.append({"season_label": label, "crops": crops})
    return {
        "n_plots": n_plots,
        "anonymity_threshold": ANONYMITY_THRESHOLD,
        "crops_by_season": seasons,
        "note_fr": (
            "Déclarations anonymes des producteurs de la zone ; une culture n'apparaît que si "
            f"au moins {ANONYMITY_THRESHOLD} parcelles l'ont déclarée, sinon elle est comptée dans « autres ». "
            "Les parcelles de démonstration ne sont pas comptées."
        ),
    }
