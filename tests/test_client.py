import json
from pathlib import Path

import httpx
import pytest
import respx

from cowastewater.client import ArcGISError, WastewaterClient
from cowastewater.config import Config

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "sample_query.json").read_text())
QUERY_URL = Config().query_url


@respx.mock
async def test_fetch_normalizes_features():
    respx.get(QUERY_URL).mock(return_value=httpx.Response(200, json=FIXTURE))
    async with WastewaterClient(Config()) as client:
        readings = await client.fetch(limit=10)
    assert len(readings) == 3
    assert {r.site for r in readings} == {"Metro Denver", "Boulder"}
    assert any(r.value == 250.0 for r in readings)


@respx.mock
async def test_arcgis_logical_error_raises():
    respx.get(QUERY_URL).mock(
        return_value=httpx.Response(200, json={"error": {"code": 400, "message": "Invalid where"}})
    )
    async with WastewaterClient(Config()) as client:
        with pytest.raises(ArcGISError):
            await client.fetch(where="bogus")


@respx.mock
async def test_latest_for_builds_filtered_where():
    route = respx.get(QUERY_URL).mock(return_value=httpx.Response(200, json=FIXTURE))
    async with WastewaterClient(Config()) as client:
        await client.latest_for(site="Metro Denver", pathogen="SARS-CoV-2", per_group=1)
    where = route.calls.last.request.url.params["where"]
    assert "Utility = 'Metro Denver'" in where
    assert "Pathogen = 'SARS-CoV-2'" in where


@respx.mock
async def test_where_clause_escapes_quotes():
    route = respx.get(QUERY_URL).mock(return_value=httpx.Response(200, json=FIXTURE))
    async with WastewaterClient(Config()) as client:
        await client.latest_for(site="O'Brien Plant")
    where = route.calls.last.request.url.params["where"]
    assert "O''Brien Plant" in where


@respx.mock
async def test_pagination_follows_exceeded_transfer_limit():
    page1 = {**FIXTURE, "exceededTransferLimit": True}
    page2 = {**FIXTURE, "exceededTransferLimit": False, "features": FIXTURE["features"][:1]}
    respx.get(QUERY_URL).mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )
    cfg = Config(page_size=3)
    async with WastewaterClient(cfg) as client:
        readings = await client.fetch(limit=100)
    # 3 from the first page + 1 from the second before the limit clears.
    assert len(readings) == 4
