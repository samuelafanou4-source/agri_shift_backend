"""P5: devices, sync (LWW, idempotence, ownership, validation, pagination), posts, zone summary."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app import models as m
from app.main import create_app
from app.services.reference_data import load_seed
from app.services.sync_service import SyncService

API = "/api/v1"
T0 = "2026-11-10T08:00:00Z"
T1 = "2026-11-10T09:00:00Z"
T2 = "2026-11-10T10:00:00Z"


async def register(client, zone_id="kara_kara", name=None) -> tuple[str, dict]:
    did = str(uuid.uuid4())
    r = await client.post(
        f"{API}/devices/register", json={"device_id": did, "zone_id": zone_id, "display_name": name}
    )
    assert r.status_code == 201, r.text
    return did, {"X-Device-Token": r.json()["device_token"]}


def plot(pid=None, ts=T1, **kw) -> dict:
    return {"id": pid or str(uuid.uuid4()), "zone_id": "kara_kara", "name": "Champ nord",
            "area_ha": 1.5, "soil_id": "sandy_loam", "updated_at": ts, "deleted": False, **kw}  # fmt: skip


async def push(client, headers, **changes):
    r = await client.post(f"{API}/sync/push", json={"changes": changes}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- devices
async def test_register_and_profile(client, seeded_db):
    did, h = await register(client, name="Ama")
    token = h["X-Device-Token"]
    assert len(token) >= 43  # 32 random bytes, urlsafe base64
    async with seeded_db.session_factory() as s:
        dev = await s.get(m.Device, uuid.UUID(did))
    assert dev.token_hash == hashlib.sha256(token.encode()).hexdigest() != token
    r = await client.post(f"{API}/devices/register", json={"device_id": did})
    assert r.status_code == 409 and r.json()["error"]["code"] == "device_exists"
    r = await client.post(
        f"{API}/devices/register", json={"device_id": str(uuid.uuid4()), "zone_id": "mars"}
    )
    assert r.status_code == 400
    r = await client.patch(
        f"{API}/devices/me", json={"display_name": "Ama K.", "priority": "balanced"}, headers=h
    )
    assert (
        r.status_code == 200
        and r.json()["display_name"] == "Ama K."
        and r.json()["zone_id"] == "kara_kara"
    )
    assert r.json()["last_seen_at"] is not None


async def test_auth_required(client):
    r = await client.post(f"{API}/sync/push", json={"changes": {}})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    r = await client.get(f"{API}/sync/pull", headers={"X-Device-Token": "nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"
    r = await client.get(f"{API}/sync/pull", headers={"X-Device-Token": "demo-device-no-token"})
    assert r.status_code == 401  # demo devices cannot authenticate


async def test_rate_limit(settings, seeded_db):
    app = create_app(settings.model_copy(update={"rate_limit_per_min": 3}), database=seeded_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        _, h = await register(c)
        codes = [(await c.get(f"{API}/sync/pull", headers=h)).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


# ---------------------------------------------------------------- push / pull
async def test_push_then_pull(client):
    _, h = await register(client)
    p = plot()
    res = await push(client, h, plots=[p])
    assert res["accepted"] == [p["id"]] and res["rejected"] == []
    pulled = (await client.get(f"{API}/sync/pull", headers=h)).json()
    assert [x["id"] for x in pulled["changes"]["plots"]] == [p["id"]]
    row = pulled["changes"]["plots"][0]
    assert row["updated_at"] == T1 and row["server_updated_at"].endswith("Z")
    again = (
        await client.get(f"{API}/sync/pull", params={"since": pulled["server_time"]}, headers=h)
    ).json()
    # Pushed less than PULL_OVERLAP ago: sent again, identical (D-62); the client upserts by id.
    assert again["changes"]["plots"] == pulled["changes"]["plots"]
    assert again["server_time"] >= pulled["server_time"]


async def test_last_write_wins(client):
    _, h = await register(client)
    pid = str(uuid.uuid4())
    await push(client, h, plots=[plot(pid, T1, name="v1")])
    res = await push(client, h, plots=[plot(pid, T2, name="v2")])
    assert res["accepted"] == [pid]
    res = await push(client, h, plots=[plot(pid, T0, name="old")])
    assert res["accepted"] == []
    rej = res["rejected"][0]
    assert rej["reason"] == "stale" and rej["server_row"]["name"] == "v2" and rej["id"] == pid
    res = await push(client, h, plots=[plot(pid, T2, name="same time, other content")])
    assert res["rejected"][0]["reason"] == "stale"


async def test_idempotent_replay(client, seeded_db):
    _, h = await register(client)
    p = plot()
    first = await push(client, h, plots=[p])
    async with seeded_db.session_factory() as s:
        ts1 = (await s.get(m.Plot, uuid.UUID(p["id"]))).server_updated_at
    second = await push(client, h, plots=[p])
    assert first["accepted"] == second["accepted"] == [p["id"]]
    async with seeded_db.session_factory() as s:
        n = (
            await s.execute(
                select(func.count()).select_from(m.Plot).where(m.Plot.id == uuid.UUID(p["id"]))
            )
        ).scalar_one()
        ts2 = (await s.get(m.Plot, uuid.UUID(p["id"]))).server_updated_at
    assert n == 1 and ts1 == ts2


async def test_ownership(client):
    _, ha = await register(client)
    _, hb = await register(client)
    p = plot()
    await push(client, ha, plots=[p])
    res = await push(client, hb, plots=[plot(p["id"], T2, name="hijack")])
    assert res["rejected"][0]["reason"] == "forbidden" and res["rejected"][0]["server_row"] is None
    season = {"id": str(uuid.uuid4()), "plot_id": p["id"], "season_label": "2026-main",
              "crop_id": "maize", "updated_at": T1}  # fmt: skip
    res = await push(client, hb, plot_seasons=[season])
    assert res["rejected"][0]["reason"] == "forbidden"


async def test_validation_per_row(client):
    _, h = await register(client)
    good = plot()
    new_plot = plot()
    season_same_batch = {"id": str(uuid.uuid4()), "plot_id": new_plot["id"], "season_label": "2026-main",
                         "crop_id": "sorghum", "sowing_date": "2026-06-05", "updated_at": T1}  # fmt: skip
    bad = [
        plot(zone_id="mars"),
        plot(soil_id="rock"),
        plot(area_ha=0),
        plot(area_ha=101),
        {"name": "no id"},
    ]
    posts = [
        {"id": str(uuid.uuid4()), "zone_id": "kara_kara", "body": "x" * 1001, "updated_at": T1},
        {
            "id": str(uuid.uuid4()),
            "zone_id": "kara_kara",
            "body": "Pluies en retard ?",
            "updated_at": T1,
        },
    ]
    seasons = [season_same_batch, {**season_same_batch, "id": str(uuid.uuid4()), "crop_id": "kiwi"},
               {**season_same_batch, "id": str(uuid.uuid4()), "plot_id": str(uuid.uuid4())}]  # fmt: skip
    res = await push(client, h, plots=[good, new_plot, *bad], plot_seasons=seasons, posts=posts)
    assert set(res["accepted"]) == {
        good["id"],
        new_plot["id"],
        season_same_batch["id"],
        posts[1]["id"],
    }
    reasons = [r["reason"] for r in res["rejected"]]
    assert reasons == ["unknown_zone", "unknown_soil", "invalid", "invalid", "invalid",
                       "unknown_crop", "unknown_plot", "invalid"]  # fmt: skip
    assert all(r["message_fr"] for r in res["rejected"])


async def test_pull_public_posts_and_tombstones(client):
    _, ha = await register(client, name="Kodjo")
    _, hb = await register(client)
    _, hc = await register(client, zone_id="maritime_lome")
    post = {
        "id": str(uuid.uuid4()),
        "zone_id": "kara_kara",
        "body": "Bonjour Kara",
        "updated_at": T1,
    }
    await push(client, ha, plots=[plot()], posts=[post])
    pb = (await client.get(f"{API}/sync/pull", headers=hb)).json()["changes"]
    assert pb["plots"] == [] and [p["id"] for p in pb["posts"]] == [post["id"]]
    assert pb["posts"][0]["is_mine"] is False and pb["posts"][0]["author_name"] == "Kodjo"
    assert "device_id" not in pb["posts"][0]
    assert (await client.get(f"{API}/sync/pull", headers=hc)).json()["changes"]["posts"] == []
    pa = (await client.get(f"{API}/sync/pull", headers=ha)).json()
    assert pa["changes"]["posts"][0]["is_mine"] is True
    await push(client, ha, posts=[{**post, "updated_at": T2, "deleted": True}])
    delta = (
        await client.get(f"{API}/sync/pull", params={"since": pa["server_time"]}, headers=hb)
    ).json()
    assert [(p["id"], p["deleted"]) for p in delta["changes"]["posts"]] == [(post["id"], True)]


async def test_pull_pagination(seeded_db, settings, client):
    _, h = await register(client)
    plots = [plot() for _ in range(5)]
    await push(client, h, plots=plots)
    seed = load_seed(settings.seed_path)
    async with seeded_db.session_factory() as s:
        token_hash = hashlib.sha256(h["X-Device-Token"].encode()).hexdigest()
        device = (
            await s.execute(select(m.Device).where(m.Device.token_hash == token_hash))
        ).scalar_one()
        seen, since = [], None
        for _ in range(5):
            page = await SyncService(s, seed, device).pull(since, limit=2)
            seen += [p["id"] for p in page.changes.plots]
            if not page.next_since:
                break
            since = datetime.fromisoformat(page.next_since)
    assert sorted(seen) == sorted(p["id"] for p in plots) and len(seen) == 5


# ---------------------------------------------------------------- posts
async def test_posts_crud_and_pagination(client):
    _, ha = await register(client, name="Afi")
    _, hb = await register(client)
    ids = []
    for i in range(3):
        r = await client.post(
            f"{API}/posts", json={"zone_id": "kara_kara", "body": f"msg {i}"}, headers=ha
        )
        assert r.status_code == 201
        ids.append(r.json()["id"])
    page1 = (await client.get(f"{API}/posts", params={"zone_id": "kara_kara", "limit": 2})).json()
    assert [p["body"] for p in page1["posts"]] == ["msg 2", "msg 1"] and page1["next_before"]
    page2 = (
        await client.get(
            f"{API}/posts",
            params={"zone_id": "kara_kara", "limit": 2, "before": page1["next_before"]},
        )
    ).json()
    assert [p["body"] for p in page2["posts"]] == ["msg 0"] and page2["next_before"] is None
    assert "device_id" not in page1["posts"][0]
    r = await client.delete(f"{API}/posts/{ids[0]}", headers=hb)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    r = await client.delete(f"{API}/posts/{ids[0]}", headers=ha)
    assert r.status_code == 200 and r.json()["deleted"] is True
    listed = (await client.get(f"{API}/posts", params={"zone_id": "kara_kara"})).json()["posts"]
    assert ids[0] not in [p["id"] for p in listed]
    assert (await client.delete(f"{API}/posts/{uuid.uuid4()}", headers=ha)).status_code == 404
    assert (
        await client.post(
            f"{API}/posts", json={"zone_id": "kara_kara", "body": "x" * 1001}, headers=ha
        )
    ).status_code == 422
    assert (
        await client.post(f"{API}/posts", json={"zone_id": "kara_kara", "body": "hi"})
    ).status_code == 401
    assert (await client.get(f"{API}/posts", params={"zone_id": "mars"})).status_code == 404
    dup = {"id": ids[1], "zone_id": "kara_kara", "body": "again"}
    assert (await client.post(f"{API}/posts", json=dup, headers=ha)).status_code == 409


# ---------------------------------------------------------------- summary (anonymity >= 3)
async def test_zone_summary_anonymity(client):
    crops = ["sorghum", "sorghum", "sorghum", "maize"]
    for crop in crops:
        _, h = await register(client)
        p = plot()
        season = {"id": str(uuid.uuid4()), "plot_id": p["id"], "season_label": "2026-main",
                  "crop_id": crop, "updated_at": T1}  # fmt: skip
        await push(client, h, plots=[p], plot_seasons=[season])
    await client.post(
        f"{API}/posts", json={"zone_id": "kara_kara", "body": "Semis faits"}, headers=h
    )
    s = (await client.get(f"{API}/zones/kara_kara/summary")).json()
    prod = s["producers"]
    assert prod["n_plots"] == 4  # the seeded demo plot of Kara is not counted
    assert prod["anonymity_threshold"] == 3
    season = prod["crops_by_season"][0]
    assert season["season_label"] == "2026-main"
    assert season["crops"] == [
        {"crop_id": "sorghum", "name_fr": "Sorgho", "n_plots": 3},
        {"crop_id": "other", "name_fr": "autres", "n_plots": 1},
    ]
    assert s["climate"]["baseline_period"] == "1991-2020" and len(s["climate"]["seasons"]) == 1
    assert [p["body"] for p in s["recent_posts"]] == ["Semis faits"]
    assert "device_id" not in s["recent_posts"][0]
    assert (await client.get(f"{API}/zones/mars/summary")).status_code == 404
