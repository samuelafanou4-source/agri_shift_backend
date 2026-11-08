from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.config import APP_VERSION
from app.db import Database
from app.deps import get_database, get_pack_store
from app.services.pack_service import PackStore

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(
    db: Database = Depends(get_database), packs: PackStore = Depends(get_pack_store)
) -> dict:
    try:
        async with db.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:  # noqa: BLE001  # pragma: no cover - depends on infra
        db_status = "error"
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "db": db_status,
        "packs_count": len(packs),
        "version": APP_VERSION,
    }
