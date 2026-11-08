"""SQLAlchemy models (§11). Portable types only (JSON, Uuid) so tests run on SQLite."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Zone(Base):
    __tablename__ = "zones"
    zone_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name_fr: Mapped[str] = mapped_column(String(128))
    region: Mapped[str] = mapped_column(String(128))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    elevation_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    seasons: Mapped[list] = mapped_column(JSON)
    source_type: Mapped[str] = mapped_column(String(64))


class Crop(Base):
    __tablename__ = "crops"
    crop_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name_fr: Mapped[str] = mapped_column(String(128))
    family: Mapped[str] = mapped_column(String(64))
    n_fixing: Mapped[bool] = mapped_column(Boolean)
    cycle_days: Mapped[int] = mapped_column(Integer)
    water_need: Mapped[str] = mapped_column(String(32))
    drought_tolerance: Mapped[str] = mapped_column(String(32))
    food_staple: Mapped[bool] = mapped_column(Boolean)
    kc_ini: Mapped[float] = mapped_column(Float)
    kc_mid: Mapped[float] = mapped_column(Float)
    kc_end: Mapped[float] = mapped_column(Float)
    root_depth_m: Mapped[float] = mapped_column(Float)
    depletion_p: Mapped[float] = mapped_column(Float)
    phases: Mapped[dict] = mapped_column(JSON)
    source_type: Mapped[str] = mapped_column(String(64))
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Soil(Base):
    __tablename__ = "soils"
    soil_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label_fr: Mapped[str] = mapped_column(String(128))
    taw_mm_per_m: Mapped[float] = mapped_column(Float)
    source_type: Mapped[str] = mapped_column(String(64))


class RotationRule(Base):
    __tablename__ = "rotation_rules"
    rule_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    effect: Mapped[str] = mapped_column(String(16))
    delta: Mapped[float] = mapped_column(Float)
    conditions: Mapped[list] = mapped_column(JSON)
    explanation_fr: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(64))


class Scenario(Base):
    __tablename__ = "scenarios"
    scenario_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label_fr: Mapped[str] = mapped_column(String(128))
    rainfall_change_pct: Mapped[float] = mapped_column(Float)
    temperature_change_c: Mapped[float] = mapped_column(Float)
    source_type: Mapped[str] = mapped_column(String(64))
    note_fr: Mapped[str] = mapped_column(Text)


class ClimateDekad(Base):
    __tablename__ = "climate_dekad"
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.zone_id"), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    dekad: Mapped[int] = mapped_column(Integer, primary_key=True)
    p_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    et0_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    tmean_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    tmax_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_days: Mapped[int] = mapped_column(Integer)
    n_missing: Mapped[int] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String(64))


class Pack(Base):
    __tablename__ = "packs"
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.zone_id"), primary_key=True)
    pack_version: Mapped[str] = mapped_column(String(32), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Device(Base):
    __tablename__ = "devices"
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    zone_id: Mapped[str | None] = mapped_column(ForeignKey("zones.zone_id"), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Extension to §11: marks seeded demo devices as synthetic_demo (NULL for real users).
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Plot(Base):
    __tablename__ = "plots"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.device_id"), index=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.zone_id"))
    name: Mapped[str] = mapped_column(String(128))
    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    soil_id: Mapped[str | None] = mapped_column(ForeignKey("soils.soil_id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    server_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    # Extension to §11: marks seeded demo plots as synthetic_demo (NULL for real users).
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PlotSeason(Base):
    __tablename__ = "plot_seasons"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    plot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plots.id"), index=True)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.device_id"), index=True)
    season_label: Mapped[str] = mapped_column(String(32))
    crop_id: Mapped[str | None] = mapped_column(ForeignKey("crops.crop_id"), nullable=True)
    sowing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    yield_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    losses_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    server_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class Post(Base):
    __tablename__ = "posts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.device_id"), index=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.zone_id"))
    body: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    server_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (Index("ix_posts_zone_server_updated_at", "zone_id", "server_updated_at"),)


__all__ = [
    "ClimateDekad",
    "Crop",
    "Device",
    "Pack",
    "Plot",
    "PlotSeason",
    "Post",
    "RotationRule",
    "Scenario",
    "Soil",
    "Zone",
]
