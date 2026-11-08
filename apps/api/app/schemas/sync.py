"""Device / sync / posts payloads (§10.3, §10.4, §10.6)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.reference import Priority

MAX_BODY = 1000
MAX_NOTE = 1000


def to_utc(dt: datetime) -> datetime:
    """Aware UTC datetime (naive values are assumed UTC; SQLite returns naive)."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def iso_z(dt: datetime | None) -> str | None:
    return None if dt is None else to_utc(dt).isoformat().replace("+00:00", "Z")


class _In(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


# ---------------------------------------------------------------- devices
class DeviceRegister(_In):
    device_id: uuid.UUID
    display_name: str | None = Field(default=None, max_length=128)
    zone_id: str | None = None
    priority: Priority | None = None


class DeviceUpdate(_In):
    display_name: str | None = Field(default=None, max_length=128)
    zone_id: str | None = None
    priority: Priority | None = None


class DeviceRegistered(BaseModel):
    device_id: uuid.UUID
    device_token: str


class DeviceProfile(BaseModel):
    device_id: uuid.UUID
    display_name: str | None
    zone_id: str | None
    priority: str | None
    created_at: str
    last_seen_at: str | None


# ---------------------------------------------------------------- synced rows (client -> server)
class _SyncRow(_In):
    id: uuid.UUID
    updated_at: datetime
    deleted: bool = False

    @field_validator("updated_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return to_utc(v)


class PlotIn(_SyncRow):
    zone_id: str
    name: str = Field(min_length=1, max_length=128)
    area_ha: float | None = Field(default=None, gt=0, le=100)
    soil_id: str | None = None


class PlotSeasonIn(_SyncRow):
    plot_id: uuid.UUID
    season_label: str = Field(min_length=1, max_length=32)
    crop_id: str | None = None
    sowing_date: date | None = None
    yield_note: str | None = Field(default=None, max_length=MAX_NOTE)
    losses_note: str | None = Field(default=None, max_length=MAX_NOTE)


class PostIn(_SyncRow):
    zone_id: str
    body: str = Field(min_length=1, max_length=MAX_BODY)


class PushChanges(BaseModel):
    """Rows are validated one by one by the service (an invalid row is rejected, not the batch)."""

    plots: list[dict] = Field(default_factory=list)
    plot_seasons: list[dict] = Field(default_factory=list)
    posts: list[dict] = Field(default_factory=list)


class PushRequest(BaseModel):
    changes: PushChanges


class Rejected(BaseModel):
    id: str | None
    entity: str
    reason: str
    message_fr: str
    server_row: dict | None = None


class PushResponse(BaseModel):
    accepted: list[str]
    rejected: list[Rejected]
    server_time: str


class PullChanges(BaseModel):
    plots: list[dict] = Field(default_factory=list)
    plot_seasons: list[dict] = Field(default_factory=list)
    posts: list[dict] = Field(default_factory=list)


class PullResponse(BaseModel):
    changes: PullChanges
    server_time: str
    next_since: str | None = None


# ---------------------------------------------------------------- posts
class PostCreate(_In):
    id: uuid.UUID | None = None
    zone_id: str
    body: str = Field(min_length=1, max_length=MAX_BODY)


class PostsPage(BaseModel):
    posts: list[dict]
    next_before: str | None
