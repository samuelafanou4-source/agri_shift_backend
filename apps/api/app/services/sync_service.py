"""Offline-first sync (§10.4): last-write-wins on client `updated_at`, server cursor on
`server_updated_at`, per-device ownership, per-row validation, idempotent replays."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from pydantic import BaseModel, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.schemas.sync import (
    PlotIn,
    PlotSeasonIn,
    PostIn,
    PullChanges,
    PullResponse,
    PushChanges,
    PushResponse,
    Rejected,
    iso_z,
    to_utc,
)
from app.services.device_service import now_utc
from app.services.reference_data import SeedData

PULL_PAGE_SIZE = 500
EPOCH = datetime(1970, 1, 1)


# ---------------------------------------------------------------- serialization
def plot_out(p: m.Plot) -> dict:
    return {
        "id": str(p.id),
        "zone_id": p.zone_id,
        "name": p.name,
        "area_ha": p.area_ha,
        "soil_id": p.soil_id,
        "updated_at": iso_z(p.updated_at),
        "deleted": p.deleted,
        "server_updated_at": iso_z(p.server_updated_at),
    }


def season_out(s: m.PlotSeason) -> dict:
    return {
        "id": str(s.id),
        "plot_id": str(s.plot_id),
        "season_label": s.season_label,
        "crop_id": s.crop_id,
        "sowing_date": s.sowing_date.isoformat() if s.sowing_date else None,
        "yield_note": s.yield_note,
        "losses_note": s.losses_note,
        "updated_at": iso_z(s.updated_at),
        "deleted": s.deleted,
        "server_updated_at": iso_z(s.server_updated_at),
    }


def post_out(p: m.Post, me: uuid.UUID | None, author_name: str | None) -> dict:
    """Public view of a post: never exposes the author's device_id."""
    return {
        "id": str(p.id),
        "zone_id": p.zone_id,
        "body": p.body,
        "updated_at": iso_z(p.updated_at),
        "deleted": p.deleted,
        "server_updated_at": iso_z(p.server_updated_at),
        "is_mine": me is not None and p.device_id == me,
        "author_name": author_name,
    }


# ---------------------------------------------------------------- push
_FIELDS = {
    "plots": ("zone_id", "name", "area_ha", "soil_id", "deleted"),
    "plot_seasons": (
        "plot_id", "season_label", "crop_id", "sowing_date", "yield_note", "losses_note", "deleted",
    ),
    "posts": ("zone_id", "body", "deleted"),
}  # fmt: skip
_MODELS = {
    "plots": (PlotIn, m.Plot),
    "plot_seasons": (PlotSeasonIn, m.PlotSeason),
    "posts": (PostIn, m.Post),
}

_REASONS_FR = {
    "invalid": "Ligne invalide",
    "unknown_zone": "Zone inconnue",
    "unknown_soil": "Sol inconnu",
    "unknown_crop": "Culture inconnue",
    "unknown_plot": "Parcelle inconnue",
    "forbidden": "Cette ligne appartient à un autre appareil",
    "stale": "Une version plus récente existe sur le serveur",
}


class _Reject(Exception):
    def __init__(self, reason: str, detail: str = "", server_row: dict | None = None):
        self.reason, self.detail, self.server_row = reason, detail, server_row


class SyncService:
    def __init__(self, session: AsyncSession, seed: SeedData, device: m.Device) -> None:
        self.s = session
        self.device = device
        self.zones = {z.zone_id for z in seed.zones}
        self.soils = {x.soil_id for x in seed.soils}
        self.crops = {c.crop_id for c in seed.crops}
        self._clock = now_utc()
        self._tick = 0

    def _server_ts(self) -> datetime:
        """Strictly increasing server timestamps inside one push (stable pull pagination)."""
        self._tick += 1
        return self._clock + timedelta(microseconds=self._tick)

    def _check_refs(self, entity: str, row: BaseModel) -> None:
        zone = getattr(row, "zone_id", None)
        if zone is not None and zone not in self.zones:
            raise _Reject("unknown_zone", zone)
        soil = getattr(row, "soil_id", None)
        if soil is not None and soil not in self.soils:
            raise _Reject("unknown_soil", soil)
        crop = getattr(row, "crop_id", None)
        if crop is not None and crop not in self.crops:
            raise _Reject("unknown_crop", crop)

    async def _check_plot_owner(self, row: PlotSeasonIn) -> None:
        plot = await self.s.get(m.Plot, row.plot_id)
        if plot is None:
            raise _Reject("unknown_plot", str(row.plot_id))
        if plot.device_id != self.device.device_id:
            raise _Reject("forbidden")

    def _out(self, entity: str, obj) -> dict:
        if entity == "plots":
            return plot_out(obj)
        if entity == "plot_seasons":
            return season_out(obj)
        return post_out(obj, self.device.device_id, self.device.display_name)

    async def _apply(self, entity: str, raw: dict) -> str:
        schema, model = _MODELS[entity]
        try:
            row = schema.model_validate(raw)
        except ValidationError as e:
            first = e.errors()[0]
            raise _Reject("invalid", f"{'.'.join(map(str, first['loc']))}: {first['msg']}") from e
        self._check_refs(entity, row)
        if entity == "plot_seasons":
            await self._check_plot_owner(row)

        existing = await self.s.get(model, row.id)
        values = {f: getattr(row, f) for f in _FIELDS[entity]}
        if existing is not None:
            if existing.device_id != self.device.device_id:
                raise _Reject("forbidden")
            existing_ts = to_utc(existing.updated_at)
            if row.updated_at <= existing_ts:
                same = row.updated_at == existing_ts and all(
                    getattr(existing, k) == v for k, v in values.items()
                )
                if same:  # replay of an already applied change: idempotent no-op
                    return str(row.id)
                raise _Reject("stale", "", self._out(entity, existing))
            for k, v in values.items():
                setattr(existing, k, v)
            existing.updated_at = row.updated_at
            existing.server_updated_at = self._server_ts()
        else:
            self.s.add(
                model(
                    id=row.id,
                    device_id=self.device.device_id,
                    updated_at=row.updated_at,
                    server_updated_at=self._server_ts(),
                    **values,
                )
            )
        await self.s.flush()
        return str(row.id)

    async def push(self, changes: PushChanges) -> PushResponse:
        accepted: list[str] = []
        rejected: list[Rejected] = []
        # Plots first so that seasons pushed in the same batch can reference them.
        for entity in ("plots", "plot_seasons", "posts"):
            for raw in getattr(changes, entity):
                try:
                    accepted.append(await self._apply(entity, raw))
                except _Reject as r:
                    rid = raw.get("id") if isinstance(raw, dict) else None
                    msg = _REASONS_FR[r.reason] + (f" : {r.detail}" if r.detail else "")
                    rejected.append(
                        Rejected(
                            id=str(rid) if rid is not None else None,
                            entity=entity,
                            reason=r.reason,
                            message_fr=msg,
                            server_row=r.server_row,
                        )
                    )
        await self.s.commit()
        return PushResponse(accepted=accepted, rejected=rejected, server_time=iso_z(now_utc()))

    # ------------------------------------------------------------ pull
    async def pull(self, since: datetime | None, limit: int = PULL_PAGE_SIZE) -> PullResponse:
        server_time = now_utc()  # captured before querying: later writes are seen next time
        since = to_utc(since) if since else to_utc(EPOCH)
        me = self.device.device_id
        n = limit + 1
        plots = (
            (
                await self.s.execute(
                    select(m.Plot)
                    .where(m.Plot.device_id == me, m.Plot.server_updated_at > since)
                    .order_by(m.Plot.server_updated_at)
                    .limit(n)
                )
            )
            .scalars()
            .all()
        )
        seasons = (
            (
                await self.s.execute(
                    select(m.PlotSeason)
                    .where(m.PlotSeason.device_id == me, m.PlotSeason.server_updated_at > since)
                    .order_by(m.PlotSeason.server_updated_at)
                    .limit(n)
                )
            )
            .scalars()
            .all()
        )
        own_or_zone = m.Post.device_id == me
        if self.device.zone_id:
            own_or_zone = or_(own_or_zone, m.Post.zone_id == self.device.zone_id)
        posts = (
            (
                await self.s.execute(
                    select(m.Post)
                    .where(own_or_zone, m.Post.server_updated_at > since)
                    .order_by(m.Post.server_updated_at)
                    .limit(n)
                )
            )
            .scalars()
            .all()
        )

        merged = sorted(
            [(to_utc(x.server_updated_at), "plots", x) for x in plots]
            + [(to_utc(x.server_updated_at), "plot_seasons", x) for x in seasons]
            + [(to_utc(x.server_updated_at), "posts", x) for x in posts],
            key=lambda t: (t[0], t[1], str(t[2].id)),
        )
        page = merged[:limit]
        names = await author_names(self.s, {x.device_id for _, e, x in page if e == "posts"})
        out = PullChanges()
        for _, entity, obj in page:
            if entity == "posts":
                out.posts.append(post_out(obj, me, names.get(obj.device_id)))
            else:
                getattr(out, entity).append(self._out(entity, obj))
        if len(merged) > limit:
            cursor = iso_z(page[-1][0])
            return PullResponse(changes=out, server_time=cursor, next_since=cursor)
        return PullResponse(changes=out, server_time=iso_z(server_time))


async def author_names(session: AsyncSession, device_ids: set) -> dict:
    if not device_ids:
        return {}
    rows = await session.execute(
        select(m.Device.device_id, m.Device.display_name).where(m.Device.device_id.in_(device_ids))
    )
    return dict(rows.all())
