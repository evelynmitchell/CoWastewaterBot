"""Small operator CLI: confirm the schema, peek at data, dry-run the poller.

    uv run cowastewater describe-schema
    uv run cowastewater sites
    uv run cowastewater latest --pathogen "SARS-CoV-2"
    uv run cowastewater poll --dry-run

The MCP server (``cowastewater-mcp``) is the LLM-facing surface; this CLI is for
humans setting things up and for the GitHub Actions poll job.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .analysis import find_notable, summarize
from .atproto_bot import post_change
from .client import WastewaterClient
from .config import load_config
from .feeds import FeedStore, item_from_change, render_atom
from .health import HealthStore, days_since_update
from .risk import assess_site
from .state import State


async def _describe_schema() -> int:
    async with WastewaterClient() as client:
        fields = await client.describe_schema()
    print(json.dumps(fields, indent=2))
    return 0


async def _sites() -> int:
    async with WastewaterClient() as client:
        for s in await client.distinct_sites():
            print(s)
    return 0


async def _pathogens() -> int:
    async with WastewaterClient() as client:
        for p in await client.distinct_pathogens():
            print(p)
    return 0


async def _latest(site: str | None, pathogen: str | None) -> int:
    async with WastewaterClient() as client:
        readings = await client.latest_for(site=site, pathogen=pathogen, per_group=1)
    print(json.dumps([r.to_dict() for r in readings], indent=2))
    return 0


async def _health() -> int:
    """Report data health: current freshness + the days-since-last-outage streak."""
    config = load_config()
    now = datetime.now(timezone.utc)
    async with WastewaterClient(config) as client:
        newest = await client.fetch(where="1=1", order_desc=True, limit=1)
    latest = newest[0].date if newest else None

    snap = HealthStore.load(config.health_path).snapshot(now)
    # Live freshness (the store only advances when `poll` runs).
    snap["current_data_date"] = latest.date().isoformat() if latest else None
    snap["current_days_since_update"] = days_since_update(latest, now)
    print(json.dumps(snap, indent=2))
    return 0


async def _build_risk(client, config, now) -> dict:
    """Assess every site (worst respiratory pathogen) into a risk payload."""
    sites = await client.distinct_sites()
    site_risks = []
    for site in sites:
        readings = await client.readings_for_site(site)
        site_risks.append(assess_site(site, readings, config, now=now).to_dict())
    site_risks.sort(key=lambda s: (-s["level"], s["site"]))
    return {"generated": now.isoformat(), "sites": site_risks}


async def _risk(site: str | None, match: str | None, as_json: bool) -> int:
    config = load_config()
    now = datetime.now(timezone.utc)
    async with WastewaterClient(config) as client:
        if site:
            readings = await client.readings_for_site(site)
            result = assess_site(site, readings, config, now=now).to_dict()
            print(json.dumps(result, indent=2))
            return 0
        payload = await _build_risk(client, config, now)

    rows = payload["sites"]
    if match:
        rows = [r for r in rows if match.lower() in r["site"].lower()]
    if as_json:
        print(json.dumps(rows, indent=2))
        return 0
    label = {0: "OK    ", 1: "CAUTION", 2: "AVOID  "}
    for r in rows:
        driver = f" ({r['driver']})" if r["driver"] else ""
        print(f"{label.get(r['level'], '?'):8} {r['site']}{driver}")
    return 0


async def _query(where: str, limit: int, raw: bool) -> int:
    """Run a raw ArcGIS where-clause. With --raw, dump every column (handy for
    inspecting the viral_conc_raw_LP* columns and lab_phase)."""
    async with WastewaterClient() as client:
        readings = await client.fetch(where=where, order_desc=True, limit=limit)
    if raw:
        print(json.dumps([r.raw for r in readings], indent=2, default=str))
    else:
        print(json.dumps([r.to_dict() for r in readings], indent=2))
    return 0


async def _poll(dry_run: bool, limit: int, feed: bool, post: bool) -> int:
    """Fetch recent readings, find new notable changes, and emit them.

    Pipeline: fetch -> detect notable -> dedup against state -> (RSS feed,
    ATProto post) -> persist state. ``--dry-run`` does the detection but writes
    nothing and posts nothing.
    """
    config = load_config()
    now = datetime.now(timezone.utc)
    state = State.load(config.state_path)
    async with WastewaterClient(config) as client:
        readings = await client.fetch(where="1=1", order_desc=True, limit=limit)
        # Per-site go-out risk needs full per-site history; build it while the
        # client is open (skipped on a dry run).
        risk_payload = None if dry_run else await _build_risk(client, config, now)

    # Data-health: advance the days-since-last-outage streak from the freshest row.
    latest_data = max((r.date for r in readings if r.date), default=None)
    health = HealthStore.load(config.health_path)
    snap = health.record(latest_data, now, config.freshness_days)
    print(
        f"health: {snap['status']}, {snap['days_since_update']} day(s) since update, "
        f"{snap['days_since_last_outage']} day(s) since last outage",
        file=sys.stderr,
    )

    # Persist the per-site go-out risk snapshot for the landing page.
    if risk_payload is not None:
        risk_path = Path(config.risk_path)
        risk_path.parent.mkdir(parents=True, exist_ok=True)
        risk_path.write_text(json.dumps(risk_payload, indent=2) + "\n")
        print(f"risk: assessed {len(risk_payload['sites'])} sites -> {config.risk_path}",
              file=sys.stderr)

    changes = find_notable(readings, config)
    fresh = [c for c in changes if state.is_new(c.reading)]

    for c in fresh:
        print(summarize(c))
    if not fresh:
        print("(no new notable changes)", file=sys.stderr)

    if dry_run:
        if post:
            for c in fresh:
                print(f"[dry-run] would post: {post_change(c, config).text}", file=sys.stderr)
        return 0

    health.save()

    # RSS/Atom feed.
    if feed:
        store = FeedStore.load(config.feed_data_path, max_items=config.feed_max_items)
        added = sum(store.add(item_from_change(c)) for c in fresh)
        store.save()
        render_atom(store, config)
        print(f"feed: +{added} item(s) -> {config.feed_path}", file=sys.stderr)

    # ATProto post (dry-run internally unless credentials are configured).
    if post:
        for c in fresh:
            result = post_change(c, config)
            if result.posted:
                print(f"posted: {result.uri}", file=sys.stderr)
            elif result.error:
                print(f"post skipped/failed: {result.error}", file=sys.stderr)
            else:
                print(f"[dry-run, no creds] would post: {result.text}", file=sys.stderr)

    for c in fresh:
        state.mark(c.reading)
    state.save()
    print(f"state saved to {config.state_path} ({len(state.seen_keys)} keys)", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cowastewater", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("describe-schema", help="Print the feature layer field definitions")
    sub.add_parser("sites", help="List monitoring sites")
    sub.add_parser("pathogens", help="List pathogens/targets")
    sub.add_parser("health", help="Report data freshness + days since last outage")

    p_latest = sub.add_parser("latest", help="Show the latest reading(s)")
    p_latest.add_argument("--site")
    p_latest.add_argument("--pathogen")

    p_risk = sub.add_parser("risk", help="Go-out caution level per site (quintile + trend)")
    p_risk.add_argument("--site", help="Assess one site in detail (exact name)")
    p_risk.add_argument("--match", help="Filter the table to sites whose name contains this")
    p_risk.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON")

    p_query = sub.add_parser("query", help="Run a raw where-clause (diagnostics)")
    p_query.add_argument("--where", default="1=1", help="ArcGIS SQL where clause")
    p_query.add_argument("--limit", type=int, default=50)
    p_query.add_argument("--raw", action="store_true", help="Dump all columns, not just mapped ones")

    p_poll = sub.add_parser("poll", help="Detect new notable changes; emit feed/posts")
    p_poll.add_argument("--dry-run", action="store_true", help="Detect only; write/post nothing")
    p_poll.add_argument("--limit", type=int, default=500)
    p_poll.add_argument("--no-feed", action="store_true", help="Skip regenerating the RSS/Atom feed")
    p_poll.add_argument(
        "--post", action="store_true", help="Post new changes to ATProto (dry-run without creds)"
    )

    args = parser.parse_args(argv)

    if args.cmd == "describe-schema":
        return asyncio.run(_describe_schema())
    if args.cmd == "sites":
        return asyncio.run(_sites())
    if args.cmd == "pathogens":
        return asyncio.run(_pathogens())
    if args.cmd == "health":
        return asyncio.run(_health())
    if args.cmd == "latest":
        return asyncio.run(_latest(args.site, args.pathogen))
    if args.cmd == "risk":
        return asyncio.run(_risk(args.site, args.match, args.as_json))
    if args.cmd == "query":
        return asyncio.run(_query(args.where, args.limit, args.raw))
    if args.cmd == "poll":
        return asyncio.run(_poll(args.dry_run, args.limit, feed=not args.no_feed, post=args.post))
    parser.error(f"unknown command {args.cmd!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
