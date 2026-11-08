"""Index of the zone packs on disk (PACKS_DIR), loaded once at startup. Never generated on the fly."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.schemas.pack import ZonePack

log = logging.getLogger(__name__)
NON_PACK_FILES = {"manifest.json", "zone_pack.schema.json", "golden_cases.json"}


@dataclass(frozen=True)
class PackFile:
    zone_id: str
    path: Path
    raw: bytes
    sha256: str
    pack: ZonePack

    @property
    def etag(self) -> str:
        return f'"{self.sha256}"'


class PackStore:
    def __init__(self, packs_dir: Path) -> None:
        self.packs_dir = packs_dir
        self.packs: dict[str, PackFile] = {}

    def scan(self) -> PackStore:
        self.packs = {}
        if not self.packs_dir.is_dir():
            log.warning("packs dir %s not found: no packs served", self.packs_dir)
            return self
        for path in sorted(self.packs_dir.glob("*.json")):
            if path.name in NON_PACK_FILES:
                continue
            raw = path.read_bytes()
            try:
                pack = ZonePack.model_validate_json(raw)
            except ValidationError as e:
                log.error("invalid pack %s skipped: %s", path.name, e)
                continue
            if pack.zone.zone_id != path.stem:
                log.error("pack %s declares zone %s: skipped", path.name, pack.zone.zone_id)
                continue
            self.packs[path.stem] = PackFile(
                zone_id=path.stem,
                path=path,
                raw=raw,
                sha256=hashlib.sha256(raw).hexdigest(),
                pack=pack,
            )
        return self

    def get(self, zone_id: str) -> PackFile | None:
        return self.packs.get(zone_id)

    def manifest(self) -> list[dict]:
        return [
            {
                "zone_id": p.zone_id,
                "pack_version": p.pack.pack_version,
                "sha256": p.sha256,
                "size_bytes": len(p.raw),
                "url": f"/api/v1/packs/{p.zone_id}",
            }
            for p in self.packs.values()
        ]

    def __len__(self) -> int:
        return len(self.packs)


def etag_matches(if_none_match: str | None, etag: str) -> bool:
    """RFC 7232 weak comparison on a comma-separated If-None-Match header (or '*')."""
    if not if_none_match:
        return False
    for token in if_none_match.split(","):
        t = token.strip()
        if t == "*" or t.removeprefix("W/") == etag:
            return True
    return False
