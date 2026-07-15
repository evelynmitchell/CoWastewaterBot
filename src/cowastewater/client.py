"""Async client for the CDPHE wastewater ArcGIS FeatureServer.

ArcGIS feature layers expose a documented query API. We use three properties of
it heavily:

* ``where`` — server-side filtering (by site, pathogen, date).
* ``orderByFields`` + ``resultRecordCount``/``resultOffset`` — sorting + paging.
* returning only rows past a saved date — so polling for "what's new" is cheap.

See: https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import Config, load_config
from .models import Reading


class ArcGISError(RuntimeError):
    """Raised when the feature service returns an error payload or bad status."""


class WastewaterClient:
    """Thin async wrapper over the FeatureServer ``/query`` endpoint."""

    def __init__(self, config: Config | None = None, client: httpx.AsyncClient | None = None):
        self.config = config or load_config()
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> "WastewaterClient":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.config.request_timeout)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def http(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Use WastewaterClient as an async context manager.")
        return self._client

    # -- Raw query ------------------------------------------------------------

    async def _query(self, params: dict[str, Any]) -> dict[str, Any]:
        base = {"f": "json", "outFields": "*", "returnGeometry": "false"}
        base.update(params)
        resp = await self.http.get(self.config.query_url, params=base)
        if resp.status_code != 200:
            raise ArcGISError(f"HTTP {resp.status_code} from {resp.url}")
        data = resp.json()
        # ArcGIS reports logical errors inside a 200 body.
        if isinstance(data, dict) and "error" in data:
            raise ArcGISError(str(data["error"]))
        return data

    async def describe_schema(self) -> list[dict[str, Any]]:
        """Return the layer's field definitions (name + type + alias).

        Handy for confirming the real column names against ``config.FieldMap``.
        """
        resp = await self.http.get(
            self.config.featureserver_url.rstrip("/"), params={"f": "json"}
        )
        if resp.status_code != 200:
            raise ArcGISError(f"HTTP {resp.status_code} describing layer")
        data = resp.json()
        if "error" in data:
            raise ArcGISError(str(data["error"]))
        return [
            {"name": f.get("name"), "type": f.get("type"), "alias": f.get("alias")}
            for f in data.get("fields", [])
        ]

    # -- High-level reads -----------------------------------------------------

    async def fetch(
        self,
        where: str = "1=1",
        *,
        order_desc: bool = True,
        limit: int | None = None,
    ) -> list[Reading]:
        """Fetch readings matching ``where``, paging until exhausted or ``limit``.

        Results are ordered by the date field (descending by default, i.e. newest
        first). ``limit`` caps the total number of readings returned.
        """
        fields = self.config.fields
        order = f"{fields.date} {'DESC' if order_desc else 'ASC'}"
        out: list[Reading] = []
        offset = 0
        page = self.config.page_size
        while True:
            take = page if limit is None else min(page, limit - len(out))
            if take <= 0:
                break
            data = await self._query(
                {
                    "where": where,
                    "orderByFields": order,
                    "resultOffset": offset,
                    "resultRecordCount": take,
                }
            )
            features = data.get("features", [])
            out.extend(
                Reading.from_attributes(f.get("attributes", {}), fields) for f in features
            )
            offset += len(features)
            # ArcGIS sets exceededTransferLimit when more pages remain.
            if len(features) < take or not data.get("exceededTransferLimit", False):
                break
        return out

    async def distinct_sites(self) -> list[str]:
        """List distinct monitoring sites, using server-side DISTINCT."""
        return await self._distinct(self.config.fields.site)

    async def distinct_pathogens(self) -> list[str]:
        """List distinct pathogens/targets tracked in the dataset."""
        return await self._distinct(self.config.fields.pathogen)

    async def _distinct(self, field_name: str) -> list[str]:
        data = await self._query(
            {
                "where": "1=1",
                "outFields": field_name,
                "returnDistinctValues": "true",
                "orderByFields": field_name,
            }
        )
        seen: list[str] = []
        for feat in data.get("features", []):
            val = feat.get("attributes", {}).get(field_name)
            if val is not None and str(val).strip() and str(val) not in seen:
                seen.append(str(val))
        return seen

    async def latest_for(
        self, site: str | None = None, pathogen: str | None = None, per_group: int = 1
    ) -> list[Reading]:
        """Most recent reading(s) filtered by site and/or pathogen.

        With the defaults this returns the single newest matching reading.
        """
        clauses = []
        if site:
            clauses.append(f"{self.config.fields.site} = {_sql_str(site)}")
        if pathogen:
            clauses.append(f"{self.config.fields.pathogen} = {_sql_str(pathogen)}")
        where = " AND ".join(clauses) if clauses else "1=1"
        return await self.fetch(where, order_desc=True, limit=per_group)


def _sql_str(value: str) -> str:
    """Quote a string for an ArcGIS SQL ``where`` clause (escape single quotes)."""
    return "'" + value.replace("'", "''") + "'"
