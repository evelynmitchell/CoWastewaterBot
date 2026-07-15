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
            site=_lookup_str(attrs, fields.site),
            pathogen=_lookup_str(attrs, fields.pathogen),
            date=_parse_date(attrs.get(fields.date)) if fields.date else None,
            value=_first_float(attrs, fields.value_fields),
            trend=_lookup_str(attrs, fields.trend),
            county=_lookup_str(attrs, fields.county),
            unit=_lookup_str(attrs, fields.unit),
            raw=attrs,
        )


def _lookup_str(attrs: dict[str, Any], name: str) -> str | None:
    """Look up ``name`` in ``attrs`` as a string; empty name means 'column absent'."""
    return _as_str(attrs.get(name)) if name else None


def _first_float(attrs: dict[str, Any], names: tuple[str, ...]) -> float | None:
    """First non-null float among ``names`` (coalesces the lab-phase columns)."""
    for name in names:
        v = _as_float(attrs.get(name))
        if v is not None:
            return v
    return None


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
