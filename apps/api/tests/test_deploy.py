"""FastAPI Cloud deployment: self-contained apps/api, proxy-aware rate limit."""

from __future__ import annotations

import uuid

from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.config import API_ROOT, REPO_DATA_DIR, REPO_PACKS_DIR, Settings
from app.main import create_app
from app.services.device_service import client_ip
from app.services.pack_service import PackStore

API = "/api/v1"


# ---------------------------------------------------------------- self-contained apps/api
def test_default_paths_are_inside_apps_api():
    s = Settings(_env_file=None)
    assert s.packs_path == API_ROOT / "packs"
    assert s.seed_path == API_ROOT / "data" / "seed"


def test_deploy_copies_match_sources():
    """apps/api/packs and apps/api/data/seed must be byte-identical to packs/ and data/seed/:
    rerun scripts/prepare_deploy.ps1 after rebuilding the packs or editing the seed."""
    for src_dir, dst_dir, skip in (
        (REPO_PACKS_DIR, API_ROOT / "packs", {"golden_cases.json"}),
        (REPO_DATA_DIR / "seed", API_ROOT / "data" / "seed", set()),
    ):
        src = {p.name: p.read_bytes() for p in src_dir.glob("*.json") if p.name not in skip}
        dst = {p.name: p.read_bytes() for p in dst_dir.glob("*.json")}
        assert dst == src, f"{dst_dir} is stale: run scripts/prepare_deploy.ps1"


def test_deployed_packs_are_valid():
    assert sorted(PackStore(API_ROOT / "packs").scan().packs) == [
        "kara_kara", "maritime_lome", "plateaux_kpalime",
    ]  # fmt: skip


# ---------------------------------------------------------------- proxy headers
def _request(xff: str | None, peer: str = "10.0.0.1") -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


def test_client_ip_ignores_forwarded_header_by_default():
    assert client_ip(_request("203.0.113.7"), trust_proxy_headers=False) == "10.0.0.1"


def test_client_ip_uses_the_entry_added_by_the_proxy():
    # The client can put anything in the header; the proxy appends the real address last.
    assert client_ip(_request("1.2.3.4, 203.0.113.7"), trust_proxy_headers=True) == "203.0.113.7"
    assert client_ip(_request("203.0.113.7"), trust_proxy_headers=True) == "203.0.113.7"
    assert client_ip(_request(" , "), trust_proxy_headers=True) == "10.0.0.1"
    assert client_ip(_request(None), trust_proxy_headers=True) == "10.0.0.1"


async def _register_codes(settings, seeded_db, trust: bool, xffs: list[str]) -> list[int]:
    s = settings.model_copy(update={"rate_limit_per_min": 1, "trust_proxy_headers": trust})
    app = create_app(s, database=seeded_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return [
            (
                await c.post(
                    f"{API}/devices/register",
                    json={"device_id": str(uuid.uuid4())},
                    headers={"X-Forwarded-For": xff},
                )
            ).status_code
            for xff in xffs
        ]


async def test_register_rate_limit_per_client_behind_proxy(settings, seeded_db):
    """Behind FastAPI Cloud every request has the proxy's IP: without TRUST_PROXY_HEADERS,
    two different phones share one limit; with it, each real client has its own."""
    xffs = ["198.51.100.1", "198.51.100.2"]
    assert await _register_codes(settings, seeded_db, False, xffs) == [201, 429]
    assert await _register_codes(settings, seeded_db, True, xffs) == [201, 201]
    # A client cannot escape its limit by prepending fake addresses.
    spoof = ["198.51.100.9", "6.6.6.6, 198.51.100.9"]
    assert await _register_codes(settings, seeded_db, True, spoof) == [201, 429]
