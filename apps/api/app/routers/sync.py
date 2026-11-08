from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.deps import get_seed, get_session
from app.schemas.sync import PullResponse, PushRequest, PushResponse
from app.services.device_service import current_device
from app.services.reference_data import SeedData
from app.services.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/push", response_model=PushResponse)
async def push(
    body: PushRequest,
    device: m.Device = Depends(current_device),
    session: AsyncSession = Depends(get_session),
    seed: SeedData = Depends(get_seed),
):
    return await SyncService(session, seed, device).push(body.changes)


@router.get("/pull", response_model=PullResponse)
async def pull(
    since: datetime | None = Query(default=None, description="server_time of the previous pull"),
    device: m.Device = Depends(current_device),
    session: AsyncSession = Depends(get_session),
    seed: SeedData = Depends(get_seed),
):
    result = await SyncService(session, seed, device).pull(since)
    await session.commit()  # persist last_seen_at
    return result
