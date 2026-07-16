"""Typed representations of wastewater readings, normalized from ArcGIS rows."""

from __future__ import annotations

import re
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
    lab_phase: str | None = None
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
            "lab_phase": self.lab_phase,
            "trend": self.trend,
            "county": self.county,
            "unit": self.unit,
        }

    @classmethod
    def from_attributes(cls, attrs: dict[str, Any], fields: FieldMap) -> "Reading":
        lab_phase = _lookup_str(attrs, fields.lab_phase)
        return cls(
            site=_lookup_str(attrs, fields.site),
            pathogen=_lookup_str(attrs, fields.pathogen),
            date=_parse_date(attrs.get(fields.date)) if fields.date else None,
            value=_select_value(attrs, fields.value_fields, lab_phase),
            lab_phase=lab_phase,
            trend=_lookup_str(attrs, fields.trend),
            county=_lookup_str(attrs, fields.county),
            unit=_lookup_str(attrs, fields.unit),
            raw=attrs,
        )


def _lookup_str(attrs: dict[str, Any], name: str) -> str | None:
    """Look up ``name`` in ``attrs`` as a string; empty name means 'column absent'."""
    return _as_str(attrs.get(name)) if name else None


def _select_value(
    attrs: dict[str, Any], names: tuple[str, ...], lab_phase: str | None
) -> float | None:
    """Pick the concentration value.

    Prefer the column matching this row's lab phase (so we never read a different
    phase's column); otherwise coalesce to the first non-null candidate.
    """
    phase_col = _phase_column(lab_phase, names)
    if phase_col is not None:
        v = _as_float(attrs.get(phase_col))
        if v is not None:
            return v
    return _first_float(attrs, names)


def _phase_column(lab_phase: str | None, names: tuple[str, ...]) -> str | None:
    """The candidate column matching a lab-phase label, e.g. 'LP2'/'2' -> ...LP2."""
    if not lab_phase:
        return None
    m = re.search(r"(\d+)", lab_phase)
    if not m:
        return None
    digit = m.group(1)
    for name in names:
        if name.endswith(f"LP{digit}") or name.endswith(digit):
            return name
    return None


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
