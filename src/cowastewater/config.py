"""Configuration for the CDPHE wastewater feature service.

Everything an operator might need to change lives here, and every value can be
overridden with an environment variable. That matters because the exact
``FeatureServer`` layer URL and column names are properties of CDPHE's hosted
layer, not something this repo can hardcode with certainty — run
``cowastewater describe-schema`` against the live service (from a network that
can reach ``arcgis.com``) to confirm the real field names, then set the
``COWW_FIELD_*`` variables if the defaults below are wrong.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    """Read an env var, treating unset *and empty* as "use the default".

    CI often passes empty strings for unset repo variables
    (``FOO: ${{ vars.FOO }}``); those must not clobber the defaults here.
    """
    val = os.environ.get(name)
    return val if val else default

# --- Known identifiers (from the CDPHE Open Data portal) -----------------------

# ArcGIS Online organization that hosts CDPHE's public layers.
ORG_ID = "kfmqp6kwSeDnDKNY"

# The "CDPHE Colorado Wastewater Surveillance Data" item on data-cdphe.opendata.arcgis.com.
# Dashboard: https://cdphe.colorado.gov/dcphr/wastewater
# Explore:   https://data-cdphe.opendata.arcgis.com/datasets/54a508b3c9c543559a367054fc956e6d_0/explore
DATASET_ITEM_ID = "54a508b3c9c543559a367054fc956e6d"

# The service *name* is not published on the portal page; the item id resolves to
# a FeatureServer whose URL looks like the default below. If the default 404s,
# open the dataset's "I want to use this" -> "View API Resources -> GeoJSON" on
# the Open Data page and copy the FeatureServer/<n> URL here (or set COWW_FEATURESERVER_URL).
_DEFAULT_FEATURESERVER_URL = (
    "https://services3.arcgis.com/kfmqp6kwSeDnDKNY/arcgis/rest/services/"
    "CDPHE_Colorado_Wastewater_Surveillance_Data/FeatureServer/0"
)


@dataclass(frozen=True)
class FieldMap:
    """Names of the columns we rely on, so a schema change is a one-line fix.

    Defaults reflect the columns typically present in CDPHE's wastewater table.
    Confirm them with ``cowastewater describe-schema``; override via env if needed.
    """

    site: str = _env("COWW_FIELD_SITE", "Utility")
    pathogen: str = _env("COWW_FIELD_PATHOGEN", "Pathogen")
    date: str = _env("COWW_FIELD_DATE", "Date")
    value: str = _env("COWW_FIELD_VALUE", "Concentration")
    # Optional columns — used when present, tolerated when absent.
    trend: str = _env("COWW_FIELD_TREND", "Trend")
    county: str = _env("COWW_FIELD_COUNTY", "County")
    unit: str = _env("COWW_FIELD_UNIT", "Units")


@dataclass(frozen=True)
class Config:
    featureserver_url: str = _env("COWW_FEATURESERVER_URL", _DEFAULT_FEATURESERVER_URL)
    fields: FieldMap = field(default_factory=FieldMap)

    # ArcGIS caps page size (often 1000/2000). We paginate with this.
    page_size: int = int(_env("COWW_PAGE_SIZE", "1000"))
    request_timeout: float = float(_env("COWW_TIMEOUT", "30"))

    # Where the poller remembers what it has already emitted.
    state_path: str = _env("COWW_STATE_PATH", "state.json")

    # Notable-change thresholds (see cowastewater.analysis).
    # Percent increase in concentration vs. the prior reading that counts as a spike.
    spike_pct: float = float(_env("COWW_SPIKE_PCT", "50"))
    # Trend strings (case-insensitive) that count as "notable" on their own.
    notable_trends: tuple[str, ...] = tuple(
        t.strip().lower()
        for t in _env("COWW_NOTABLE_TRENDS", "increasing,rapidly increasing").split(",")
        if t.strip()
    )

    @property
    def query_url(self) -> str:
        return f"{self.featureserver_url.rstrip('/')}/query"


def load_config() -> Config:
    """Build a Config from the current environment."""
    return Config()
