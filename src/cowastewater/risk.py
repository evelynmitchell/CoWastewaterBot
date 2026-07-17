"""Go-out risk assessment.

Answers "how cautious should I be about going out?" for a site, from two signals
over that site's own history:

* **Quintile** — which fifth of the historical distribution the latest reading
  sits in (1 = lowest 20%, 5 = highest 20%).
* **Trend** — whether the last ``trend_window`` readings are rising or falling.

The verdict follows a simple rule (all thresholds configurable):

* quintile <= ``caution_quintile`` - 1  -> **OK** (level 0)
* quintile >= ``caution_quintile`` and rising -> **AVOID** (level 2)
* quintile >= ``caution_quintile`` and not rising -> **CAUTION** (level 1)

For a site, each respiratory pathogen is assessed and the **worst** case wins,
so an elevated-and-rising flu signal still says "avoid" even if COVID is low.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from .config import Config
from .models import Reading

_LEVEL_TEXT = {0: "OK to go out", 1: "Caution — elevated", 2: "Avoid — elevated & rising"}


@dataclass(frozen=True)
class PathogenRisk:
    pathogen: str
    latest_value: float | None
    latest_date: str | None
    n_history: int
    quintile: int | None  # 1-5
    percentile: float | None  # 0-1
    trend: str  # rising | falling | flat | unknown
    trend_pct: float | None
    level: int  # 0 OK, 1 caution, 2 avoid
    verdict: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SiteRisk:
    site: str
    level: int
    verdict: str
    driver: str | None  # pathogen driving the (worst) level
    pathogens: list[PathogenRisk]

    def to_dict(self) -> dict:
        return {
            "site": self.site,
            "level": self.level,
            "verdict": self.verdict,
            "driver": self.driver,
            "pathogens": [p.to_dict() for p in self.pathogens],
        }


def _quintile(values: list[float], latest: float) -> tuple[int, float]:
    n = len(values)
    at_or_below = sum(1 for v in values if v <= latest)
    percentile = at_or_below / n
    quintile = min(5, max(1, math.ceil(percentile * 5)))
    return quintile, percentile


def _trend(window: list[Reading], config: Config) -> tuple[str, float | None]:
    if len(window) < 2:
        return "unknown", None
    first, last = window[0].value, window[-1].value
    if first is None or last is None:
        return "unknown", None
    if first <= 0:
        # Can't take a ratio off a zero baseline; fall back to direction only.
        return ("rising" if last > first else "falling" if last < first else "flat"), None
    pct = (last - first) / first * 100
    if pct >= config.trend_pct:
        return "rising", pct
    if pct <= -config.trend_pct:
        return "falling", pct
    return "flat", pct


def _level(quintile: int, trend: str, config: Config) -> int:
    if quintile <= config.caution_quintile - 1:
        return 0
    return 2 if trend == "rising" else 1


def assess_pathogen(pathogen: str, readings: list[Reading], config: Config) -> PathogenRisk:
    """Assess one (site, pathogen) series. ``readings`` may be unsorted."""
    pts = sorted(
        [r for r in readings if r.value is not None and r.date is not None],
        key=lambda r: r.date,  # type: ignore[arg-type,return-value]
    )
    if not pts:
        return PathogenRisk(pathogen, None, None, 0, None, None, "unknown", None, 0, "no data")

    values = [r.value for r in pts]  # type: ignore[misc]
    latest = pts[-1]
    quintile, percentile = _quintile(values, latest.value)  # type: ignore[arg-type]
    trend, trend_pct = _trend(pts[-config.trend_window :], config)
    level = _level(quintile, trend, config)
    return PathogenRisk(
        pathogen=pathogen,
        latest_value=latest.value,
        latest_date=latest.date.date().isoformat() if latest.date else None,
        n_history=len(values),
        quintile=quintile,
        percentile=round(percentile, 3),
        trend=trend,
        trend_pct=round(trend_pct, 1) if trend_pct is not None else None,
        level=level,
        verdict=_LEVEL_TEXT[level],
    )


def _matches_respiratory(pathogen: str, config: Config) -> bool:
    p = pathogen.lower()
    return any(sub in p for sub in config.respiratory_pathogens)


def _within_lookback(readings: list[Reading], now: datetime, config: Config) -> list[Reading]:
    if config.quintile_lookback_days <= 0:
        return readings
    cutoff = now - timedelta(days=config.quintile_lookback_days)
    return [r for r in readings if r.date is not None and r.date >= cutoff]


def assess_site(
    site: str, readings: list[Reading], config: Config, now: datetime | None = None
) -> SiteRisk:
    """Assess a site across its respiratory pathogens; worst case wins."""
    now = now or datetime.now(timezone.utc)
    scoped = _within_lookback(readings, now, config)

    by_pathogen: dict[str, list[Reading]] = {}
    for r in scoped:
        if r.pathogen and _matches_respiratory(r.pathogen, config):
            by_pathogen.setdefault(r.pathogen, []).append(r)

    risks = [assess_pathogen(p, rs, config) for p, rs in sorted(by_pathogen.items())]
    # Worst level wins; break ties by higher quintile then rising trend.
    scored = [r for r in risks if r.n_history > 0]
    if scored:
        worst = max(scored, key=lambda r: (r.level, r.quintile or 0, r.trend == "rising"))
        return SiteRisk(site, worst.level, worst.verdict, worst.pathogen, risks)
    return SiteRisk(site, 0, "no data", None, risks)
