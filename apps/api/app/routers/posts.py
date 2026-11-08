"""Exchange platform (§10.6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import models as m
from app.deps import get_seed, get_session
from app.errors import ApiError
from app.schemas.sync import PostCreate, PostsPage, UtcDatetime, iso_z, to_utc
from app.services.clock import server_now
from app.services.device_service import current_device
from app.services.reference_data import SeedData
from app.services.sync_service import author_names, post_out

router = APIRouter(prefix="/posts", tags=["posts"])


async def recent_posts(
    session: AsyncSession, zone_id: str, before: datetime | None, limit: int
) -> tuple[list[dict], str | None]:
    q = select(m.Post).where(m.Post.zone_id == zone_id, m.Post.deleted.is_(False))
    if before is not None:
        q = q.where(m.Post.server_updated_at < to_utc(before))
    rows = (
        (await session.execute(q.order_by(m.Post.server_updated_at.desc()).limit(limit + 1)))
        .scalars()
        .all()
    )
    page = rows[:limit]
    names = await author_names(session, {p.device_id for p in page})
    posts = [post_out(p, None, names.get(p.device_id)) for p in page]
    next_before = iso_z(page[-1].server_updated_at) if len(rows) > limit else None
    for p in posts:
        p.pop("is_mine")
    return posts, next_before


@router.get("", response_model=PostsPage)
async def list_posts(
    zone_id: str,
    before: Annotated[UtcDatetime | None, Query()] = None,
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    seed: SeedData = Depends(get_seed),
):
    if zone_id not in {z.zone_id for z in seed.zones}:
        raise ApiError(404, "unknown_zone", f"Zone inconnue : {zone_id}")
    posts, next_before = await recent_posts(session, zone_id, before, limit)
    return PostsPage(posts=posts, next_before=next_before)


@router.post("", status_code=201)
async def create_post(
    body: PostCreate,
    device: m.Device = Depends(current_device),
    session: AsyncSession = Depends(get_session),
    seed: SeedData = Depends(get_seed),
) -> dict:
    if body.zone_id not in {z.zone_id for z in seed.zones}:
        raise ApiError(400, "unknown_zone", f"Zone inconnue : {body.zone_id}")
    post_id = body.id or uuid.uuid4()
    if await session.get(m.Post, post_id) is not None:
        raise ApiError(409, "post_exists", "Un message avec cet identifiant existe déjà.")
    now = server_now()
    post = m.Post(
        id=post_id,
        device_id=device.device_id,
        zone_id=body.zone_id,
        body=body.body,
        updated_at=now,
        server_updated_at=now,
        deleted=False,
    )
    session.add(post)
    await session.commit()
    return post_out(post, device.device_id, device.display_name)


@router.delete("/{post_id}")
async def delete_post(
    post_id: uuid.UUID,
    device: m.Device = Depends(current_device),
    session: AsyncSession = Depends(get_session),
) -> dict:
    post = await session.get(m.Post, post_id)
    if post is None:
        raise ApiError(404, "unknown_post", "Message introuvable.")
    if post.device_id != device.device_id:
        raise ApiError(403, "forbidden", "Seul l'auteur peut supprimer ce message.")
    now = server_now()
    post.deleted = True
    post.updated_at = now
    post.server_updated_at = now
    await session.commit()
    return post_out(post, device.device_id, device.display_name)
