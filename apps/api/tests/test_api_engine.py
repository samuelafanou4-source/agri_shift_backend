"""P4: reference routes, packs (ETag/304), online engine, golden export."""

from __future__ import annotations

import json

import pytest

from app.config import REPO_ROOT
from app.engine.rotation import recommend
from app.engine.water_balance import simulate
from app.schemas.engine import RotationPlot
from app.services.golden import build_golden
from app.services.pack_service import PackStore, etag_matches
from tests.helpers import SEED

DEMO_PLOTS = json.loads(
    (REPO_ROOT / "data" / "synthetic" / "parcelles_demo.json").read_text(encoding="utf-8")
)
API = "/api/v1"


async def test_reference_routes(client):
    zones = (await client.get(f"{API}/zones")).json()
    assert [z["zone_id"] for z in zones] == ["maritime_lome", "plateaux_kpalime", "kara_kara"]
    assert [s["season_id"] for s in zones[0]["seasons"]] == ["main", "second"]
    assert {"sowing_dekad", "sowing_source", "onset_dekad_clim"} <= set(zones[2]["seasons"][0])
    crops = (await client.get(f"{API}/crops")).json()
    assert [c["crop_id"] for c in crops] == [c.crop_id for c in SEED.crops]
    assert len((await client.get(f"{API}/scenarios")).json()) == 7
    assert len((await client.get(f"{API}/soils")).json()) == 4


async def test_health_counts_packs(client):
    assert (await client.get(f"{API}/health")).json()["packs_count"] == 3


async def test_manifest(client, packs_dir):
    man = (await client.get(f"{API}/packs/manifest")).json()
    assert {e["zone_id"] for e in man} == {"maritime_lome", "plateaux_kpalime", "kara_kara"}
    for e in man:
        assert set(e) == {"zone_id", "pack_version", "sha256", "size_bytes", "url"}
        assert e["url"] == f"{API}/packs/{e['zone_id']}"
        assert e["size_bytes"] == len((packs_dir / f"{e['zone_id']}.json").read_bytes())


async def test_pack_etag_and_304(client, packs_dir):
    raw = (packs_dir / "kara_kara.json").read_bytes()
    r = await client.get(f"{API}/packs/kara_kara")
    assert r.status_code == 200 and r.content == raw
    etag = r.headers["etag"]
    assert etag.startswith('"') and len(etag) == 66
    assert r.headers["cache-control"] == "public, max-age=3600"
    r304 = await client.get(f"{API}/packs/kara_kara", headers={"If-None-Match": etag})
    assert r304.status_code == 304 and r304.content == b"" and r304.headers["etag"] == etag
    weak = await client.get(f"{API}/packs/kara_kara", headers={"If-None-Match": f'"x", W/{etag}'})
    assert weak.status_code == 304
    stale = await client.get(f"{API}/packs/kara_kara", headers={"If-None-Match": '"old"'})
    assert stale.status_code == 200


async def test_pack_gzip_and_404(client):
    r = await client.get(f"{API}/packs/kara_kara", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"
    r = await client.get(f"{API}/packs/atlantis")
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_zone"


def test_etag_matches():
    assert etag_matches('"a"', '"a"') and etag_matches("*", '"a"') and etag_matches('W/"a"', '"a"')
    assert not etag_matches(None, '"a"') and not etag_matches('"b"', '"a"')


async def test_simulate_route_equals_engine(client, packs_dir):
    body = {
        "zone_id": "kara_kara",
        "crop_id": "maize",
        "soil_id": "sandy",
        "scenario_id": "dry_minus30",
    }
    r = await client.post(f"{API}/simulate", json=body)
    assert r.status_code == 200
    pack = PackStore(packs_dir).scan().get("kara_kara").pack
    expected = json.loads(simulate(pack, "maize", "sandy", "dry_minus30").model_dump_json())
    assert r.json() == expected
    assert "disclaimer_fr" in r.json()
    for d in r.json()["dekads"]:
        assert round(d["etc_mm"], 2) == d["etc_mm"]


_SIM = {"zone_id": "kara_kara", "crop_id": "maize", "soil_id": "loam", "scenario_id": "baseline"}


@pytest.mark.parametrize(
    "patch,status,code",
    [
        ({"crop_id": "banana"}, 400, "unknown_crop"),
        ({"soil_id": "rock"}, 400, "unknown_soil"),
        ({"scenario_id": "x"}, 400, "unknown_scenario"),
        ({"sowing_dekad": 0}, 400, "invalid_sowing_dekad"),
        ({"zone_id": "mars"}, 404, "unknown_zone"),
        ({"crop_id": None}, 422, "validation_error"),
    ],
)
async def test_simulate_errors(client, patch, status, code):
    r = await client.post(f"{API}/simulate", json={**_SIM, **patch})
    assert r.status_code == status
    assert r.json()["error"]["code"] == code and r.json()["error"]["message_fr"]


@pytest.mark.parametrize("plot", DEMO_PLOTS, ids=lambda p: p["plot_id"])
async def test_recommend_demo_plots(client, packs_dir, plot):
    body = {
        "zone_id": plot["zone_id"],
        "soil_id": plot["soil_texture_demo"],
        "previous_crop_id": plot["previous_crop_id"],
        "priority": plot["farmer_priority_demo"],
        "scenario_id": "dry_minus20",
    }
    r = await client.post(f"{API}/rotation/recommend", json=body)
    assert r.status_code == 200, r.text
    res = r.json()
    assert len(res["recommendations"]) == 3 and res["n_sequences_evaluated"] == 125
    assert res["disclaimer_fr"] == "Score logiciel de comparaison, pas un rendement estimé."
    prov = {p["item"]: p["source_type"] for p in res["data_provenance"]}
    assert prov["scenario"] == "synthetic_scenario"
    pack = PackStore(packs_dir).scan().get(plot["zone_id"]).pack
    rp = RotationPlot(
        zone_id=plot["zone_id"],
        soil_id=plot["soil_texture_demo"],
        previous_crop_id=plot["previous_crop_id"],
    )
    expected = recommend(pack, rp, plot["farmer_priority_demo"], "dry_minus20")
    assert res == json.loads(expected.model_dump_json())


async def test_recommend_errors(client):
    base = {
        "zone_id": "kara_kara",
        "soil_id": "loam",
        "priority": "balanced",
        "scenario_id": "baseline",
    }
    r = await client.post(f"{API}/rotation/recommend", json={**base, "horizon": 9})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_horizon"
    r = await client.post(f"{API}/rotation/recommend", json={**base, "priority": "money"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = await client.post(f"{API}/rotation/recommend", json={**base, "previous_crop_id": "kiwi"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "unknown_crop"


async def test_compare_scenarios(client):
    body = {
        "zone_id": "kara_kara",
        "soil_id": "sandy_loam",
        "previous_crop_id": "sorghum",
        "priority": "drought_resilience",
        "scenario_ids": ["baseline", "dry_minus30", "hot_plus2"],
    }
    r = await client.post(f"{API}/rotation/compare-scenarios", json=body)
    assert r.status_code == 200
    res = r.json()
    assert [x["scenario_id"] for x in res["results"]] == body["scenario_ids"]
    assert all(len(x["recommendations"]) == 3 for x in res["results"])
    assert "pas un rendement" in res["disclaimer_fr"]
    dup = {**body, "scenario_ids": ["baseline", "baseline"]}
    assert (await client.post(f"{API}/rotation/compare-scenarios", json=dup)).status_code == 422


def _season0_rules(case: dict) -> list[str]:
    season = case["expected_output"]["recommendations"][0]["seasons"][0]
    return [h["rule_id"] for h in season["rules_applied"]]


def test_golden(packs_dir):
    store = PackStore(packs_dir).scan()
    g = build_golden(store, DEMO_PLOTS)
    ids = [c["case_id"] for c in g["cases"]]
    assert len(ids) == len(set(ids)) == 39
    assert sum(c["function"] == "simulate" for c in g["cases"]) == 30
    assert sum(c["function"] == "recommend" for c in g["cases"]) == 6
    v = {c["case_id"]: c for c in g["cases"] if c["case_id"].startswith("V")}
    assert _season0_rules(v["V001"]) == ["R001"]
    assert _season0_rules(v["V002"]) == ["R002"]
    assert _season0_rules(v["V003"]) == ["R002", "R003"]
    assert g["packs"]["kara_kara"]["sha256"] == store.get("kara_kara").sha256
    assert build_golden(store, DEMO_PLOTS)["cases"] == g["cases"]  # deterministic


def test_golden_on_disk_is_current():
    path = REPO_ROOT / "packs" / "golden_cases.json"
    if not path.is_file():
        pytest.skip("golden not exported")
    g = json.loads(path.read_text(encoding="utf-8"))
    store = PackStore(REPO_ROOT / "packs").scan()
    for z, meta in g["packs"].items():
        assert store.get(z).sha256 == meta["sha256"], "golden is stale: rerun export-golden"
    assert build_golden(store, DEMO_PLOTS)["cases"] == g["cases"]
