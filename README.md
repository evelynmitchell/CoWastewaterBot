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
`query`, `notable_changes`, `describe_schema`.

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
new leaves the feed untouched. Serve it via the raw file URL or GitHub Pages
([`.github/workflows/pages.yml`](.github/workflows/pages.yml) publishes
`public/` — enable **Settings → Pages → Source: GitHub Actions**).

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
