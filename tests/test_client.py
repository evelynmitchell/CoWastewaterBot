import json
from pathlib import Path

import httpx
import pytest
import respx

from cowastewater.client import ArcGISError, WastewaterClient
from cowastewater.config import Config

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "sample_query.json").read_text())

# Pin the endpoint so tests don't hit the resolution path unless they mean to.
LAYER_URL = "https://services.example.com/arcgis/rest/services/WW/FeatureServer/0"
QUERY_URL = f"{LAYER_URL}/query"


def cfg(**kwargs) -> Config:
    return Config(featureserver_url=LAYER_URL, **kwargs)


@respx.mock
async def test_fetch_normalizes_features():
    respx.get(QUERY_URL).mock(return_value=httpx.Response(200, json=FIXTURE))
    async with WastewaterClient(cfg()) as client:
        readings = await client.fetch(limit=10)
    assert len(readings) == 3
    assert {r.site for r in readings} == {"Metro Denver", "Boulder"}
    assert any(r.value == 250.0 for r in readings)


@respx.mock
async def test_arcgis_logical_error_raises():
    respx.get(QUERY_URL).mock(
        return_value=httpx.Response(200, json={"error": {"code": 400, "message": "Invalid where"}})
    )
    async with WastewaterClient(cfg()) as client:
        with pytest.raises(ArcGISError):
            await client.fetch(where="bogus")


@respx.mock
async def test_latest_for_builds_filtered_where():
    route = respx.get(QUERY_URL).mock(return_value=httpx.Response(200, json=FIXTURE))
    async with WastewaterClient(cfg()) as client:
        await client.latest_for(site="Metro Denver", pathogen="SARS-CoV-2", per_group=1)
    where = route.calls.last.request.url.params["where"]
    assert "utility = 'Metro Denver'" in where
    assert "pcr_target = 'SARS-CoV-2'" in where


@respx.mock
async def test_where_clause_escapes_quotes():
    route = respx.get(QUERY_URL).mock(return_value=httpx.Response(200, json=FIXTURE))
    async with WastewaterClient(cfg()) as client:
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
    async with WastewaterClient(cfg(page_size=3)) as client:
        readings = await client.fetch(limit=100)
    # 3 from the first page + 1 from the second before the limit clears.
    assert len(readings) == 4


@respx.mock
async def test_resolves_featureserver_url_from_item_id():
    # With no explicit URL, the client asks the sharing API for the item's
    # service URL and appends the layer index before querying.
    item_id = "abc123"
    service_root = "https://services.example.com/arcgis/rest/services/WW/FeatureServer"
    respx.get(f"https://www.arcgis.com/sharing/rest/content/items/{item_id}").mock(
        return_value=httpx.Response(200, json={"url": service_root})
    )
    query_route = respx.get(f"{service_root}/0/query").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    config = Config(featureserver_url="", dataset_item_id=item_id)
    async with WastewaterClient(config) as client:
        readings = await client.fetch(limit=10)
        # Resolution is cached: the URL is fixed after the first lookup.
        assert await client.layer_url() == f"{service_root}/0"
    assert len(readings) == 3
    assert query_route.called
