from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Response

from app.deps import get_pack_store
from app.errors import ApiError
from app.services.pack_service import PackStore, etag_matches

router = APIRouter(prefix="/packs", tags=["packs"])
CACHE_CONTROL = "public, max-age=3600"


@router.get("/manifest")
def manifest(packs: PackStore = Depends(get_pack_store)) -> list[dict]:
    return packs.manifest()


@router.get("/{zone_id}")
def get_pack(
    zone_id: str,
    packs: PackStore = Depends(get_pack_store),
    if_none_match: str | None = Header(default=None),
) -> Response:
    pf = packs.get(zone_id)
    if pf is None:
        raise ApiError(404, "unknown_zone", f"Zone inconnue ou paquet absent : {zone_id}")
    headers = {"ETag": pf.etag, "Cache-Control": CACHE_CONTROL}
    if etag_matches(if_none_match, pf.etag):
        return Response(status_code=304, headers=headers)
    return Response(content=pf.raw, media_type="application/json", headers=headers)
