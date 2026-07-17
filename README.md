# CoWastewaterBot

An easier interface to **Colorado wastewater surveillance data** — the pathogen
concentrations CDPHE measures at wastewater treatment sites across the state
(SARS-CoV-2, Influenza, RSV, EV-D68, Mpox, measles, West Nile virus).

The state publishes this as a [dashboard][dashboard] backed by an
[ArcGIS Open Data feature layer][explore]. Great for a human clicking around;
awkward for a machine to follow. This project wraps that feature layer's REST
query API in a small typed core and puts three easier surfaces on top of it:

| Surface | Status | For |
| --- | --- | --- |
| **MCP server** | ✅ implemented | LLMs (Claude Desktop, etc.) that want to query the data live |
| **RSS/Atom feed** | ✅ implemented | Anyone who wants new/notable readings in a feed reader |
| **ATProto bot** | ✅ implemented | A Bluesky/ATProto account that posts notable changes |

All three consume the same core (`cowastewater.client` + `cowastewater.analysis`),
so "notable change" means the same thing everywhere.

## Live

- **Site — "should I go out?" (GitHub Pages):** https://evelynmitchell.github.io/CoWastewaterBot/ — per-site respiratory caution level; filter to your city.
- **Risk JSON:** https://evelynmitchell.github.io/CoWastewaterBot/risk.json
- **RSS/Atom feed:** https://evelynmitchell.github.io/CoWastewaterBot/feed.xml
- **MCP server:** run locally (stdio) — see [Run the MCP server](#run-the-mcp-server).

Monitoring endpoints (secondary — for uptime/health checks, not the main content):

- **Health JSON:** https://evelynmitchell.github.io/CoWastewaterBot/health.json
- **MCP tool:** `data_health`

Updated daily by the [poll workflow](.github/workflows/poll.yml).

[dashboard]: https://cdphe.colorado.gov/dcphr/wastewater
[explore]: https://data-cdphe.opendata.arcgis.com/datasets/54a508b3c9c543559a367054fc956e6d_0/explore

## Run with Docker (no Python needed)

If you don't have Python or `uv`, the container is the easiest path — you only
need Docker.

Pull the published image (built by CI to GHCR — make the package public, or
`docker login ghcr.io` first):

```bash
docker pull ghcr.io/evelynmitchell/cowastewaterbot:latest
```

…or build it yourself from a clone:

```bash
docker build -t cowastewaterbot .
```

Run the CLI (swap the image name for the local `cowastewaterbot` if you built it):

```bash
docker run --rm ghcr.io/evelynmitchell/cowastewaterbot:latest cowastewater describe-schema
docker run --rm ghcr.io/evelynmitchell/cowastewaterbot:latest cowastewater sites
```

Point an MCP client (e.g. Claude Desktop) at the container — this is the whole
setup, no Python on your machine:

```json
{
  "mcpServers": {
    "cowastewater": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "ghcr.io/evelynmitchell/cowastewaterbot:latest"]
    }
  }
}
```

Override the schema with `-e`, e.g.
`docker run -i --rm -e COWW_FEATURESERVER_URL="https://.../FeatureServer/0" ghcr.io/evelynmitchell/cowastewaterbot:latest`.

> No Docker either? You can confirm the live schema straight from the browser:
> **Actions → "Inspect live data" → Run workflow** prints the schema, sites, and
> pathogens from a GitHub runner.

## Quick start (local dev)

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run pytest            # run the test suite (offline, uses fixtures)
```

### Run the MCP server

```bash
uv run cowastewater-mcp   # serves over stdio
```

Register it with an MCP client (e.g. Claude Desktop `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "cowastewater": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/CoWastewaterBot", "cowastewater-mcp"]
    }
  }
}
```

Tools exposed: `list_sites`, `list_pathogens`, `latest_reading`, `trend`,
`query`, `notable_changes`, `risk_assessment`, `data_health`, `describe_schema`.

### Operator CLI

```bash
uv run cowastewater describe-schema          # confirm the live column names
uv run cowastewater sites                     # list monitoring sites
uv run cowastewater latest --pathogen "SARS-CoV-2"
uv run cowastewater poll --dry-run            # detect notable changes, don't write state
```

## The FeatureServer URL and column names

**The URL resolves itself.** The service name isn't published on the portal, so
instead of guessing it the client looks the FeatureServer URL up at runtime from
the dataset's stable **item id** (`54a508b3c9c543559a367054fc956e6d`) via the
ArcGIS sharing API. Nothing to configure. To pin an exact URL and skip
resolution, set `COWW_FEATURESERVER_URL`.

**Column names** match the live layer (confirmed 2026-07):

| Meaning | Column | Notes |
| --- | --- | --- |
| Site | `utility` | |
| Pathogen / target | `pcr_target` | e.g. SARS-CoV-2, Influenza A, RSV |
| Date | `measure_date` | Esri epoch-millis |
| Concentration | `viral_conc_raw_LP1` / `_LP2` / `_LP3` | one per row by lab phase; **coalesced** to the first non-null |

The layer has no trend/county/units columns, so notable-change detection relies
on the **concentration spike**, not a reported trend. Re-confirm any time with:

```bash
docker run --rm ghcr.io/evelynmitchell/cowastewaterbot:latest cowastewater describe-schema
```

Override any mapping without touching code — every value in
[`config.py`](src/cowastewater/config.py) reads from an environment variable
(`COWW_FIELD_SITE`, `COWW_FIELD_PATHOGEN`, `COWW_FIELD_DATE`,
`COWW_FIELD_VALUE` — comma-separated for coalescing). To pin the endpoint and
skip auto-resolution, set `COWW_FEATURESERVER_URL` to a `FeatureServer/<n>` URL.

## Go-out risk ("should I go out?")

The landing page's main view answers, per site: **how cautious should I be about
going out?** For each respiratory pathogen (SARS-CoV-2, Influenza, RSV) it takes
that site's own history and reports:

- **quintile** — which fifth of the historical distribution the latest reading
  is in (1 = lowest 20%, 5 = highest 20%), and
- **trend** — rising / falling / flat over the last `COWW_TREND_WINDOW` readings.

The **verdict** (worst pathogen wins) follows a simple, configurable rule:

| Condition | Verdict |
| --- | --- |
| quintile ≤ 2 | **OK to go out** |
| quintile ≥ `COWW_CAUTION_QUINTILE` (3) and rising | **Avoid** (elevated & rising) |
| quintile ≥ 3 and not rising | **Caution** (elevated) |

```bash
uv run cowastewater risk                                  # table of all sites
uv run cowastewater risk --match "fort collins"           # just your city's sewersheds
uv run cowastewater risk --site "Fort Collins - Drake"    # full detail (JSON)
```

Exposed as the MCP `risk_assessment` tool and published for the site as
`public/risk.json`. Knobs: `COWW_RESPIRATORY` (pathogens), `COWW_TREND_WINDOW`,
`COWW_TREND_PCT`, `COWW_CAUTION_QUINTILE`, `COWW_QUINTILE_LOOKBACK_DAYS`.

> Not medical advice — a transparent heuristic over public data. The site filter
> is by city/site name today; zip-code proximity is a planned follow-up (the
> CDPHE layer carries no coordinates, so it needs a site→location mapping).

## What counts as a "notable change"

`cowastewater.analysis.find_notable` flags a reading when either:

- its reported **trend** is increasing (`COWW_NOTABLE_TRENDS`, default
  `increasing,rapidly increasing`), or
- its **concentration** rose at least `COWW_SPIKE_PCT` percent (default `50`)
  above the previous reading for the same site+pathogen.

Series are isolated per `(site, pathogen)` so spikes compare like with like, and
noise controls keep the feed from crying wolf:

| Knob | Default | Effect |
| --- | --- | --- |
| `COWW_SPIKE_PCT` | `50` | Minimum % jump to flag a spike |
| `COWW_SPIKE_MIN_BASELINE` | `0` | Ignore spikes whose baseline is below this — a jump up from near-zero is mostly detection-floor noise. Set once you know the value scale (see below). |
| `COWW_NOTABLE_MAX` | `25` | Cap items per run, ranked by severity (`0` = no cap) |

**Lab-phase guard.** The concentration lives in `viral_conc_raw_LP1/2/3` by lab
phase. Each reading's value is taken from the column matching its `lab_phase`,
and a spike is **not** flagged across a phase change (two lab methods aren't
directly comparable) — this prevents false spikes at method transitions.

### Inspecting the raw data

To see the actual `viral_conc_raw_LP*` columns and `lab_phase` for a site — e.g.
to pick a sensible `COWW_SPIKE_MIN_BASELINE`:

```bash
docker run --rm ghcr.io/evelynmitchell/cowastewaterbot:latest \
  cowastewater query --raw --limit 8 \
  --where "utility='Steamboat Springs' AND pcr_target='sars-cov-2'"
```

## Feeds: RSS/Atom and ATProto

`cowastewater poll` is the pipeline that drives both channels:

```bash
uv run cowastewater poll --dry-run          # detect only, write/post nothing
uv run cowastewater poll                     # detect + (re)generate the Atom feed
uv run cowastewater poll --post              # also post new changes to ATProto
```

**RSS/Atom** — new notable changes are appended to a capped JSON store
(`public/feed.json`) and rendered to `public/feed.xml`. A run that finds nothing
new leaves the feed untouched. It's published to GitHub Pages at
**https://evelynmitchell.github.io/CoWastewaterBot/feed.xml**
([`.github/workflows/pages.yml`](.github/workflows/pages.yml) publishes
`public/`; enable **Settings → Pages → Source: GitHub Actions**).

To write the feed onto the host from the container, bind-mount `public/`. On
SELinux hosts (Fedora/RHEL) add `:Z` so the container may write to it:

```bash
docker run --rm -v "$PWD/public:/app/public:Z" \
  ghcr.io/evelynmitchell/cowastewaterbot:latest cowastewater poll
```

**ATProto (Bluesky)** — `--post` publishes each new change as a skeet. It is a
**safe dry run until you provide credentials**: set `COWW_ATPROTO_HANDLE` and
`COWW_ATPROTO_PASSWORD` (a Bluesky *app password*, not your main password) —
locally as env vars, or as repo **Actions secrets** for CI. Optional
`COWW_ATPROTO_PDS` (default `https://bsky.social`). Requires the `atproto` extra
(`uv sync --extra atproto`; already in the container image).

## Data health: "days since last data outage"

The source updates roughly weekly, so a stretch of silence means the pipeline
behind CDPHE has stalled. `poll` tracks this each run and persists it to
`public/health.json`:

- **outage** = the newest measurement is older than `COWW_FRESHNESS_DAYS`
  (default `10`).
- **days since last outage** = the reliability streak (0 while in an outage),
  the headline number.

Check it live (freshness now + the streak):

```bash
uv run cowastewater health
# {"status": "ok", "current_days_since_update": 2, "days_since_last_outage": 37, ...}
```

### Monitoring endpoint

The same data is published as a machine-readable **monitoring endpoint** for
uptime/health checks — [`health.json`](https://evelynmitchell.github.io/CoWastewaterBot/health.json):

```json
{ "status": "ok", "days_since_update": 8, "days_since_last_outage": null, "outage_events": 0, ... }
```

Point an uptime monitor at it and alert on `status == "outage"` (or on
`days_since_update` exceeding your own threshold). It's also exposed as the MCP
`data_health` tool for an LLM to poll. On the landing page it's intentionally
just a small footer line — monitoring, not the main content. The streak advances
only when the scheduled `poll` runs, so keep the cron enabled for an accurate count.

## Scheduled polling

The whole thing is driven by a GitHub Actions cron
([`.github/workflows/poll.yml`](.github/workflows/poll.yml)): it polls, dedups
against committed `data/state.json`, regenerates the feed, posts to ATProto (if
secrets are set), and commits `data/` + `public/` back. No server to run.

## Architecture

```
FeatureServer (CDPHE ArcGIS)
        │  REST /query
        ▼
  client.py ── models.py        data core: fetch + normalize
        │
        ├── analysis.py         notable-change detection
        ├── health.py           freshness + days-since-last-outage
        ├── state.py            last-seen cursor (dedup)
        │
        ├── server.py           MCP server  (LLMs)          ✅
        ├── feeds.py            RSS / Atom                   ✅
        └── atproto_bot.py      Bluesky poster               ✅
```

## Data source & credit

Data © Colorado Department of Public Health & Environment (CDPHE), republished
from their public [Open Data portal][explore]. This project is an unofficial
convenience wrapper and is not affiliated with or endorsed by CDPHE.

## License

MIT
