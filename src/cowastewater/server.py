"""MCP server exposing CDPHE wastewater data as tools for LLMs.

Run over stdio (the transport Claude Desktop / most MCP clients use):

    uv run cowastewater-mcp

Tools are intentionally small and composable so a model can chain them:
list what's available, then drill into a site/pathogen, then look at trend or
what's notable right now.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP

from .analysis import find_notable, summarize
from .client import WastewaterClient
from .config import load_config
from .health import HealthStore, days_since_update

mcp = FastMCP(
    "cowastewater",
    instructions=(
        "Tools for Colorado (CDPHE) wastewater surveillance data — pathogen "
        "concentrations measured at wastewater treatment sites across the state "
        "(SARS-CoV-2, Influenza, RSV, EV-D68, Mpox, measles, West Nile virus). "
        "Use list_sites / list_pathogens to discover valid filter values, then "
        "latest_reading or trend to drill in, and notable_changes for what's "
        "spiking. Dates are ISO-8601; concentrations are as reported by CDPHE."
    ),
)


@mcp.tool()
async def list_sites() -> list[str]:
    """List the distinct wastewater monitoring sites (utilities) in the dataset."""
    async with WastewaterClient() as client:
        return await client.distinct_sites()


@mcp.tool()
async def list_pathogens() -> list[str]:
    """List the distinct pathogens/targets tracked (e.g. SARS-CoV-2, Influenza, RSV)."""
    async with WastewaterClient() as client:
        return await client.distinct_pathogens()


@mcp.tool()
async def latest_reading(site: str | None = None, pathogen: str | None = None) -> dict[str, Any]:
    """Return the most recent reading, optionally filtered by site and/or pathogen.

    Args:
        site: Exact site/utility name (see list_sites). Optional.
        pathogen: Exact pathogen name (see list_pathogens). Optional.
    """
    async with WastewaterClient() as client:
        readings = await client.latest_for(site=site, pathogen=pathogen, per_group=1)
    if not readings:
        return {"found": False, "message": "No matching readings."}
    return {"found": True, "reading": readings[0].to_dict()}


@mcp.tool()
async def trend(pathogen: str, site: str | None = None, weeks: int = 12) -> dict[str, Any]:
    """Return a recent time series for a pathogen (optionally at one site).

    Args:
        pathogen: Exact pathogen name (see list_pathogens).
        site: Exact site name to restrict to a single utility. Optional.
        weeks: How many of the most recent readings per series to include (default 12).
    """
    async with WastewaterClient() as client:
        # Pull generously then trim; the service returns newest-first.
        readings = await client.latest_for(
            site=site, pathogen=pathogen, per_group=max(weeks, 1) * (1 if site else 60)
        )
    readings = [r for r in readings if r.date is not None]
    readings.sort(key=lambda r: r.date, reverse=True)  # type: ignore[arg-type,return-value]
    trimmed = readings[: weeks if site else weeks * 40]
    return {
        "pathogen": pathogen,
        "site": site,
        "count": len(trimmed),
        "series": [r.to_dict() for r in reversed(trimmed)],
    }


@mcp.tool()
async def query(where: str = "1=1", limit: int = 100) -> dict[str, Any]:
    """Run a raw ArcGIS SQL 'where' clause against the feature layer.

    Use for filters the other tools don't cover. Field names come from the
    layer schema (see describe_schema). Example: "County = 'Denver'".

    Args:
        where: ArcGIS SQL where clause. Defaults to everything.
        limit: Max readings to return (default 100).
    """
    async with WastewaterClient() as client:
        readings = await client.fetch(where=where, order_desc=True, limit=limit)
    return {"count": len(readings), "readings": [r.to_dict() for r in readings]}


@mcp.tool()
async def notable_changes(limit: int = 500) -> dict[str, Any]:
    """Surface recent notable changes — spikes and rising trends worth attention.

    Scans the most recent readings and flags where concentration jumped sharply
    or the reported trend is increasing.

    Args:
        limit: How many recent readings to scan (default 500).
    """
    config = load_config()
    async with WastewaterClient(config) as client:
        readings = await client.fetch(where="1=1", order_desc=True, limit=limit)
    changes = find_notable(readings, config)
    return {
        "scanned": len(readings),
        "notable_count": len(changes),
        "changes": [
            {"summary": summarize(c), **c.to_dict()} for c in changes
        ],
    }


@mcp.tool()
async def data_health() -> dict[str, Any]:
    """Report data-source health for monitoring.

    Returns how stale the newest measurement is (`current_days_since_update`) and
    the reliability streak (`days_since_last_outage`). `status` is "outage" when
    the source has stopped updating (newest data older than the freshness
    threshold). The streak advances only when the scheduled poller runs.
    """
    config = load_config()
    now = datetime.now(timezone.utc)
    async with WastewaterClient(config) as client:
        newest = await client.fetch(where="1=1", order_desc=True, limit=1)
    latest = newest[0].date if newest else None

    snap = HealthStore.load(config.health_path).snapshot(now)
    snap["current_data_date"] = latest.date().isoformat() if latest else None
    snap["current_days_since_update"] = days_since_update(latest, now)
    return snap


@mcp.tool()
async def describe_schema() -> list[dict[str, Any]]:
    """Return the feature layer's field definitions (name, type, alias).

    Useful for building 'query' where-clauses or confirming column names.
    """
    async with WastewaterClient() as client:
        return await client.describe_schema()


def main() -> None:
    """Console-script entry point: serve over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
