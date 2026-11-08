"""Device identity without account (§10.3): random token, stored hashed (sha256)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.deps import get_session
from app.errors import ApiError
from app.schemas.sync import iso_z


def new_token() -> str:
    return secrets.token_urlsafe(32)  # 32 random bytes


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def now_utc() -> datetime:
    return datetime.now(UTC)


def profile(d: m.Device) -> dict:
    return {
        "device_id": d.device_id,
        "display_name": d.display_name,
        "zone_id": d.zone_id,
        "priority": d.priority,
        "created_at": iso_z(d.created_at),
        "last_seen_at": iso_z(d.last_seen_at),
    }


async def current_device(
    request: Request,
    x_device_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> m.Device:
    """Auth dependency: X-Device-Token header -> Device. Also applies the per-device rate limit."""
    if not x_device_token:
        raise ApiError(401, "unauthorized", "En-tête X-Device-Token manquant.")
    device = (
        await session.execute(
            select(m.Device).where(m.Device.token_hash == hash_token(x_device_token))
        )
    ).scalar_one_or_none()
    if device is None:
        raise ApiError(401, "invalid_token", "Jeton d'appareil invalide.")
    request.app.state.rate_limiter.check(f"device:{device.device_id}")
    device.last_seen_at = now_utc()
    return device


def client_ip(request: Request, trust_proxy_headers: bool) -> str:
    """Client IP for the per-IP rate limit.

    Behind FastAPI Cloud's proxy every request comes from the proxy's address. With
    TRUST_PROXY_HEADERS, the LAST X-Forwarded-For entry is used: the proxy appends the address it
    received the connection from, while earlier entries are whatever the client sent (spoofable).
    """
    if trust_proxy_headers:
        forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",")]
        forwarded = [p for p in forwarded if p]
        if forwarded:
            return forwarded[-1]
    return request.client.host if request.client else "unknown"


def client_key(request: Request) -> str:
    trust = request.app.state.settings.trust_proxy_headers
    return f"ip:{client_ip(request, trust)}"
