import json
from pathlib import Path

import httpx
import pytest
import respx
from mcp import Client

from pharma_mcp import server
from pharma_mcp.http import ApiClient
from pharma_mcp.openfda import OpenFDA
from pharma_mcp.trials import Trials

FIX = Path(__file__).parent / "fixtures"
FDA = "https://api.fda.gov"
CT = "https://clinicaltrials.gov/api/v2"


def fx(name: str) -> dict:
    return json.loads((FIX / name).read_text())


def total(n: int) -> dict:
    return {"meta": {"results": {"total": n}}, "results": [{}]}


@pytest.fixture(autouse=True)
def fresh_clients(monkeypatch):
    # new clients per test: empty cache, no throttling delay
    monkeypatch.setattr(server, "_fda", OpenFDA(ApiClient(FDA, min_interval_s=0)))
    monkeypatch.setattr(server, "_trials", Trials(ApiClient(CT, min_interval_s=0)))


async def call(name: str, args: dict) -> dict:
    async with Client(server.mcp) as c:
        res = await c.call_tool(name, args)
    assert not res.is_error, res
    return res.structured_content or json.loads(res.content[0].text)


async def test_lists_all_tools():
    async with Client(server.mcp) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert names == {
        "search_drug_labels",
        "get_adverse_events",
        "signal_check",
        "drug_recalls",
        "search_trials",
        "get_trial",
    }


@respx.mock
async def test_labels():
    route = respx.get(f"{FDA}/drug/label.json").mock(
        return_value=httpx.Response(200, json=fx("label.json"))
    )
    out = await call("search_drug_labels", {"drug": "exampleglutide"})
    lab = out["labels"][0]
    assert lab["brand_name"] == "EXAMPLEGLU" and "THYROID" in lab["boxed_warning"]
    assert lab["source"].endswith("sample-set-id-0001")
    assert 'openfda.generic_name:"exampleglutide"' in route.calls[0].request.url.params["search"]


@respx.mock
async def test_not_found_is_empty_not_error():
    respx.get(f"{FDA}/drug/label.json").mock(
        return_value=httpx.Response(
            404, json={"error": {"code": "NOT_FOUND", "message": "No matches found!"}}
        )
    )
    assert await call("search_drug_labels", {"drug": "nonexistentdrug"}) == {"labels": []}


@respx.mock
async def test_adverse_events_with_shares():
    def respond(request):
        p = request.url.params
        return httpx.Response(200, json=fx("event_counts.json") if "count" in p else total(46000))

    respx.get(f"{FDA}/drug/event.json").mock(side_effect=respond)
    out = await call("get_adverse_events", {"drug": "exampleglutide", "limit": 4})
    assert out["total_reports"] == 46000
    assert out["reactions"][0] == {"reaction": "NAUSEA", "reports": 9200, "share_of_reports": 0.2}
    assert "causation" in out["note"]


@respx.mock
async def test_signal_check_builds_table_from_four_queries():
    def respond(request):
        s = request.url.params.get("search")
        if s is None:
            return httpx.Response(200, json=total(20_000_000))
        if "AND" in s:
            return httpx.Response(200, json=total(1200))
        if "medicinalproduct" in s:
            return httpx.Response(200, json=total(46_000))
        return httpx.Response(200, json=total(60_000))

    respx.get(f"{FDA}/drug/event.json").mock(side_effect=respond)
    out = await call("signal_check", {"drug": "exampleglutide", "reaction": "pancreatitis"})
    d = out["disproportionality"]
    assert out["counts"]["drug_and_reaction"] == 1200
    assert d["a"] == 1200 and d["b"] == 44_800 and d["c"] == 58_800
    assert d["prr"] > 2 and d["is_signal"]


@respx.mock
async def test_signal_check_unknown_drug():
    respx.get(f"{FDA}/drug/event.json").mock(
        return_value=httpx.Response(404, json={"error": {"code": "NOT_FOUND"}})
    )
    out = await call("signal_check", {"drug": "zzz", "reaction": "nausea"})
    assert "no FAERS reports" in out["error"]


@respx.mock
async def test_recalls():
    respx.get(f"{FDA}/drug/enforcement.json").mock(
        return_value=httpx.Response(200, json=fx("recalls.json"))
    )
    out = await call("drug_recalls", {"drug": "exampleglutide"})
    assert out["recalls"][0]["classification"] == "Class II"


@respx.mock
async def test_search_and_get_trial():
    route = respx.get(f"{CT}/studies").mock(
        return_value=httpx.Response(200, json=fx("studies.json"))
    )
    out = await call(
        "search_trials", {"condition": "type 2 diabetes", "status": "recruiting", "phase": "phase3"}
    )
    s = out["studies"][0]
    assert s["nct_id"] == "NCT00000001" and s["phases"] == ["PHASE3"] and s["locations"] == 2
    params = route.calls[0].request.url.params
    assert params["filter.overallStatus"] == "RECRUITING"
    assert params["filter.advanced"] == "AREA[Phase]PHASE3"

    respx.get(f"{CT}/studies/NCT00000001").mock(
        return_value=httpx.Response(200, json=fx("studies.json")["studies"][0])
    )
    one = await call("get_trial", {"nct_id": "nct00000001"})
    assert one["eligibility"]["min_age"] == "18 Years"
    assert one["primary_outcomes"] == ["Change in HbA1c at week 26"]


async def test_input_validation_returns_errors():
    assert "error" in await call("get_trial", {"nct_id": "12345"})
    assert "error" in await call("search_trials", {})
    assert "error" in await call("search_trials", {"condition": "x", "status": "bogus"})


@respx.mock
async def test_retry_then_cache():
    route = respx.get(f"{FDA}/drug/enforcement.json").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=fx("recalls.json"))]
    )
    client = ApiClient(FDA, min_interval_s=0)
    fda = OpenFDA(client)
    import pharma_mcp.http as h

    async def no_sleep(_s):
        return None

    orig = h.asyncio.sleep
    h.asyncio.sleep = no_sleep
    try:
        first = await fda.recalls("x")
        second = await fda.recalls("x")
    finally:
        h.asyncio.sleep = orig
    assert first == second and route.call_count == 2  # one retry, then served from cache
    await client.aclose()
