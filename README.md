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
| **RSS/Atom feed** | 🟡 planned | Anyone who wants new/notable readings in a feed reader |
| **ATProto bot** | 🟡 planned | A Bluesky/ATProto account that posts notable changes |

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

**Column names** still ship as defaults (`Utility`/`Pathogen`/`Date`/
`Concentration`). Confirm them against the live layer:

```bash
uv run cowastewater describe-schema           # or: docker run --rm <image> cowastewater describe-schema
```

If any differ, override without touching code — every value in
[`config.py`](src/cowastewater/config.py) reads from an environment variable:

```bash
export COWW_FIELD_SITE="Utility"
export COWW_FIELD_PATHOGEN="Pathogen"
export COWW_FIELD_DATE="Date"
export COWW_FIELD_VALUE="Concentration"
# optional: pin the endpoint instead of auto-resolving
export COWW_FEATURESERVER_URL="https://services3.arcgis.com/kfmqp6kwSeDnDKNY/arcgis/rest/services/<RealServiceName>/FeatureServer/0"
```

## What counts as a "notable change"

`cowastewater.analysis.find_notable` flags a reading when either:

- its reported **trend** is increasing (`COWW_NOTABLE_TRENDS`, default
  `increasing,rapidly increasing`), or
- its **concentration** rose at least `COWW_SPIKE_PCT` percent (default `50`)
  above the previous reading for the same site+pathogen.

Series are isolated per `(site, pathogen)` so spikes compare like with like.

## Scheduled polling

The feed channels are driven by a GitHub Actions cron
([`.github/workflows/poll.yml`](.github/workflows/poll.yml)) that runs the
poller, dedups against committed `state.json`, and (once the feed adapters land)
regenerates the RSS file / posts to ATProto. No server to run.

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
        ├── feeds (planned)     RSS / Atom                   🟡
        └── atproto (planned)   Bluesky poster               🟡
```

## Data source & credit

Data © Colorado Department of Public Health & Environment (CDPHE), republished
from their public [Open Data portal][explore]. This project is an unofficial
convenience wrapper and is not affiliated with or endorsed by CDPHE.

## License

MIT
