"""Notable-change detection.

The channels (ATProto, RSS) should emit signal, not every row. A reading is
"notable" when either:

* its reported trend matches one of ``config.notable_trends`` (e.g. "increasing"), or
* its concentration jumped at least ``config.spike_pct`` percent above the
  previous reading for the same (site, pathogen).

To keep the feed from crying wolf:

* spikes off a baseline below ``config.spike_min_baseline`` are ignored (a jump
  up from near-zero is mostly noise near the detection floor), and
* spikes are not flagged across a lab-phase change, since two lab methods aren't
  directly comparable (see :mod:`cowastewater.models`).

:func:`find_notable` groups a flat list of readings by (site, pathogen), walks
each group oldest->newest, flags transitions, then ranks by severity and caps
the number returned at ``config.notable_max``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import Config
from .models import Reading

# Sentinel severity for trend-based flags (no numeric magnitude): always ranks first.
_TREND_SEVERITY = math.inf


@dataclass(frozen=True)
class NotableChange:
    reading: Reading
    reason: str  # human-readable, e.g. "concentration up 120% vs. prior week"
    previous: Reading | None = None
    severity: float = _TREND_SEVERITY  # spike percent, or inf for trend flags

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
    """Return notable changes, ranked by severity and capped at ``notable_max``.

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
            change = _change_for(r, prev, config)
            if change is not None:
                notable.append(change)
            prev = r

    # Most severe first; then apply the per-run cap (0 = no cap).
    notable.sort(key=lambda c: c.severity, reverse=True)
    if config.notable_max > 0:
        notable = notable[: config.notable_max]
    return notable


def _change_for(r: Reading, prev: Reading | None, config: Config) -> NotableChange | None:
    # Trend-based signal (works even without a numeric prior).
    if r.trend and r.trend.strip().lower() in config.notable_trends:
        return NotableChange(reading=r, reason=f"trend reported as '{r.trend}'", previous=prev)

    # Spike-based signal — guarded against near-zero baselines and phase changes.
    if prev and prev.value and r.value is not None and prev.value > 0:
        if prev.value < config.spike_min_baseline:
            return None  # baseline too low to trust the ratio
        if _phase_changed(prev, r):
            return None  # different lab methods aren't directly comparable
        pct = (r.value - prev.value) / prev.value * 100
        if pct >= config.spike_pct:
            return NotableChange(
                reading=r,
                reason=f"concentration up {pct:.0f}% vs. prior reading",
                previous=prev,
                severity=pct,
            )
    return None


def _phase_changed(prev: Reading, r: Reading) -> bool:
    """True if both readings name a lab phase and they differ."""
    return bool(prev.lab_phase and r.lab_phase and prev.lab_phase != r.lab_phase)


def summarize(change: NotableChange) -> str:
    """One-line, feed-ready summary of a notable change."""
    r = change.reading
    where = r.site or "Unknown site"
    if r.county:
        where += f" ({r.county})"
    when = r.date.date().isoformat() if r.date else "unknown date"
    return f"{r.pathogen or 'Pathogen'} at {where} — {change.reason} [{when}]"
