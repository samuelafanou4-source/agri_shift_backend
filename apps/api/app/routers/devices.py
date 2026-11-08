from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.deps import get_seed, get_session
from app.errors import ApiError
from app.schemas.sync import DeviceProfile, DeviceRegister, DeviceRegistered, DeviceUpdate
from app.services.device_service import (
    client_key,
    current_device,
    hash_token,
    new_token,
    now_utc,
    profile,
)
from app.services.reference_data import SeedData

router = APIRouter(prefix="/devices", tags=["devices"])


def _check_zone(zone_id: str | None, seed: SeedData) -> None:
    if zone_id is not None and zone_id not in {z.zone_id for z in seed.zones}:
        raise ApiError(400, "unknown_zone", f"Zone inconnue : {zone_id}")


@router.post("/register", response_model=DeviceRegistered, status_code=201)
async def register(
    body: DeviceRegister,
    request: Request,
    session: AsyncSession = Depends(get_session),
    seed: SeedData = Depends(get_seed),
):
    request.app.state.rate_limiter.check(client_key(request))
    _check_zone(body.zone_id, seed)
    if await session.get(m.Device, body.device_id) is not None:
        raise ApiError(409, "device_exists", "Cet appareil est déjà enregistré.")
    token = new_token()
    session.add(
        m.Device(
            device_id=body.device_id,
            token_hash=hash_token(token),
            display_name=body.display_name,
            zone_id=body.zone_id,
            priority=body.priority,
            created_at=now_utc(),
            last_seen_at=None,
        )
    )
    await session.commit()
    return DeviceRegistered(device_id=body.device_id, device_token=token)


@router.patch("/me", response_model=DeviceProfile)
async def update_me(
    body: DeviceUpdate,
    device: m.Device = Depends(current_device),
    session: AsyncSession = Depends(get_session),
    seed: SeedData = Depends(get_seed),
):
    changes = body.model_dump(exclude_unset=True)
    _check_zone(changes.get("zone_id"), seed)
    for k, v in changes.items():
        setattr(device, k, v)
    await session.commit()
    return profile(device)
