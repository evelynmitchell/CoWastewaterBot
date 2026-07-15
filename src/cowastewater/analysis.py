"""Notable-change detection.

The channels (ATProto, RSS) should emit signal, not every row. A reading is
"notable" when either:

* its reported trend matches one of ``config.notable_trends`` (e.g. "increasing"), or
* its concentration jumped at least ``config.spike_pct`` percent above the
  previous reading for the same (site, pathogen).

:func:`find_notable` groups a flat list of readings by (site, pathogen), walks
each group oldest->newest, and flags the transitions.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .models import Reading


@dataclass(frozen=True)
class NotableChange:
    reading: Reading
    reason: str  # human-readable, e.g. "concentration up 120% vs. prior week"
    previous: Reading | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "reason": self.reason,
            "reading": self.reading.to_dict(),
            "previous": self.previous.to_dict() if self.previous else None,
        }


def _group(readings: list[Reading]) -> dict[tuple[str, str], list[Reading]]:
    groups: dict[tuple[str, str], list[Reading]] = {}
    for r in readings:
        k = (r.key[0], r.key[1])  # (site, pathogen)
        groups.setdefault(k, []).append(r)
    return groups


def find_notable(readings: list[Reading], config: Config) -> list[NotableChange]:
    """Return notable changes across a batch of readings.

    Readings may arrive in any order; each (site, pathogen) series is sorted by
    date internally so spike detection compares consecutive samples.
    """
    notable: list[NotableChange] = []
    for series in _group(readings).values():
        ordered = sorted(
            [r for r in series if r.date is not None],
            key=lambda r: r.date,  # type: ignore[arg-type,return-value]
        )
        prev: Reading | None = None
        for r in ordered:
            reason = _reason_for(r, prev, config)
            if reason:
                notable.append(NotableChange(reading=r, reason=reason, previous=prev))
            prev = r
    return notable


def _reason_for(r: Reading, prev: Reading | None, config: Config) -> str | None:
    # Trend-based signal (works even without a numeric prior).
    if r.trend and r.trend.strip().lower() in config.notable_trends:
        return f"trend reported as '{r.trend}'"

    # Spike-based signal.
    if prev and prev.value and r.value is not None and prev.value > 0:
        pct = (r.value - prev.value) / prev.value * 100
        if pct >= config.spike_pct:
            return f"concentration up {pct:.0f}% vs. prior reading"
    return None


def summarize(change: NotableChange) -> str:
    """One-line, feed-ready summary of a notable change."""
    r = change.reading
    where = r.site or "Unknown site"
    if r.county:
        where += f" ({r.county})"
    when = r.date.date().isoformat() if r.date else "unknown date"
    return f"{r.pathogen or 'Pathogen'} at {where} — {change.reason} [{when}]"
