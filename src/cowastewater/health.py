"""Data-health / outage tracking.

A "data outage" here means the *source* stopped publishing: the newest
measurement in the layer is older than ``config.freshness_days`` (the data
normally updates ~weekly). We persist a little state so we can report:

* **days since update** — how stale the freshest reading is right now, and
* **days since last outage** — an uptime streak, the headline reliability number.

The poller calls :meth:`HealthStore.record` each run to advance the streak;
read-only views (MCP tool, CLI, landing page) call :meth:`HealthStore.snapshot`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


def days_since_update(latest_data_date: datetime | None, now: datetime) -> int | None:
    """Whole days between the newest measurement and ``now`` (None if unknown)."""
    if latest_data_date is None:
        return None
    return (now.date() - latest_data_date.date()).days


@dataclass
class HealthStore:
    path: Path
    last_checked: str | None = None  # ISO datetime of the last record()
    last_data_date: str | None = None  # ISO date of the newest measurement seen
    in_outage: bool = False
    last_outage_date: str | None = None  # ISO date most recently observed stale
    outage_events: int = 0  # count of distinct outage episodes

    def __post_init__(self) -> None:
        self.path = Path(self.path)

    @classmethod
    def load(cls, path: str | Path) -> "HealthStore":
        p = Path(path)
        if not p.exists():
            return cls(path=p)
        data = json.loads(p.read_text())
        return cls(
            path=p,
            last_checked=data.get("last_checked"),
            last_data_date=data.get("last_data_date"),
            in_outage=bool(data.get("in_outage", False)),
            last_outage_date=data.get("last_outage_date"),
            outage_events=int(data.get("outage_events", 0)),
        )

    def record(
        self, latest_data_date: datetime | None, now: datetime, freshness_days: int
    ) -> dict:
        """Update the streak from a fresh observation and return a snapshot."""
        stale_days = days_since_update(latest_data_date, now)
        is_stale = stale_days is not None and stale_days > freshness_days

        if is_stale:
            if not self.in_outage:
                self.outage_events += 1  # a new episode started
            self.in_outage = True
            self.last_outage_date = now.date().isoformat()
        else:
            self.in_outage = False

        if latest_data_date is not None:
            self.last_data_date = latest_data_date.date().isoformat()
        self.last_checked = now.isoformat()
        return self.snapshot(now)

    def snapshot(self, now: datetime) -> dict:
        """Read-only health view as of ``now`` (does not mutate)."""
        stale_days = None
        if self.last_data_date:
            stale_days = (now.date() - date.fromisoformat(self.last_data_date)).days

        since_outage = None
        if self.last_outage_date:
            since_outage = (now.date() - date.fromisoformat(self.last_outage_date)).days

        return {
            "status": "outage" if self.in_outage else "ok",
            "days_since_update": stale_days,
            "days_since_last_outage": since_outage,
            "outage_events": self.outage_events,
            "last_data_date": self.last_data_date,
            "last_outage_date": self.last_outage_date,
            "last_checked": self.last_checked,
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_checked": self.last_checked,
            "last_data_date": self.last_data_date,
            "in_outage": self.in_outage,
            "last_outage_date": self.last_outage_date,
            "outage_events": self.outage_events,
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n")
