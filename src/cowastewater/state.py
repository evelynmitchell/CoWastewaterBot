"""Persistent 'what have we already emitted' cursor for the poller.

Kept deliberately simple: a JSON file holding the set of reading keys we've
already turned into feed items / posts, plus the newest date seen. The GitHub
Actions cron commits this file back to the repo so the next run picks up where
the last one left off.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import Reading


@dataclass
class State:
    path: Path
    latest_date: str | None = None
    seen_keys: set[str] = field(default_factory=set)

    @staticmethod
    def _encode_key(reading: Reading) -> str:
        return "|".join(reading.key)

    @classmethod
    def load(cls, path: str | Path) -> "State":
        p = Path(path)
        if not p.exists():
            return cls(path=p)
        data = json.loads(p.read_text())
        return cls(
            path=p,
            latest_date=data.get("latest_date"),
            seen_keys=set(data.get("seen_keys", [])),
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "latest_date": self.latest_date,
            "seen_keys": sorted(self.seen_keys),
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def is_new(self, reading: Reading) -> bool:
        return self._encode_key(reading) not in self.seen_keys

    def mark(self, reading: Reading) -> None:
        self.seen_keys.add(self._encode_key(reading))
        iso = reading.date.isoformat() if reading.date else None
        if iso and (self.latest_date is None or iso > self.latest_date):
            self.latest_date = iso

    def filter_new(self, readings: list[Reading]) -> list[Reading]:
        """Return only readings not previously seen (does not mark them)."""
        return [r for r in readings if self.is_new(r)]
