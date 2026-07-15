"""Typed representations of wastewater readings, normalized from ArcGIS rows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from dateutil import parser as dtparser

from .config import FieldMap


@dataclass(frozen=True)
class Reading:
    """A single normalized wastewater measurement.

    ``raw`` keeps the untouched attributes from ArcGIS so nothing is lost when we
    map onto our known columns; the typed fields are the ones the channels use.
    """

    site: str | None
    pathogen: str | None
    date: datetime | None
    value: float | None
    trend: str | None = None
    county: str | None = None
    unit: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def key(self) -> tuple[str, str, str]:
        """Stable identity for dedup: (site, pathogen, iso-date)."""
        return (
            (self.site or "").strip().lower(),
            (self.pathogen or "").strip().lower(),
            self.date.date().isoformat() if self.date else "",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "site": self.site,
            "pathogen": self.pathogen,
            "date": self.date.isoformat() if self.date else None,
            "value": self.value,
            "trend": self.trend,
            "county": self.county,
            "unit": self.unit,
        }

    @classmethod
    def from_attributes(cls, attrs: dict[str, Any], fields: FieldMap) -> "Reading":
        return cls(
            site=_as_str(attrs.get(fields.site)),
            pathogen=_as_str(attrs.get(fields.pathogen)),
            date=_parse_date(attrs.get(fields.date)),
            value=_as_float(attrs.get(fields.value)),
            trend=_as_str(attrs.get(fields.trend)),
            county=_as_str(attrs.get(fields.county)),
            unit=_as_str(attrs.get(fields.unit)),
            raw=attrs,
        )


def _as_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _as_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_date(v: Any) -> datetime | None:
    """Parse either an Esri epoch-millis integer or an ISO/text date string."""
    if v is None or v == "":
        return None
    # ArcGIS date fields commonly serialize as epoch milliseconds.
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        try:
            return datetime.fromtimestamp(v / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        dt = dtparser.parse(str(v))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError):
        return None
