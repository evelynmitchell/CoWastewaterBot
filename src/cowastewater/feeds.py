"""RSS/Atom feed of notable wastewater changes.

The poller turns each new notable change into a feed *item* and keeps a capped
list of them in a small JSON store (so the feed is stable across runs — a run
that finds nothing new leaves the feed unchanged). :func:`render_atom` rebuilds
the Atom XML from that store.

The JSON store and the XML both live under ``public/`` by default so they can be
committed and served (GitHub Pages, or the raw file URL).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from dateutil import parser as dtparser
from feedgen.feed import FeedGenerator

from .analysis import NotableChange, summarize
from .config import Config

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def item_from_change(change: NotableChange) -> dict:
    """A JSON-serializable feed item derived from a notable change."""
    r = change.reading
    return {
        "id": "|".join(r.key),
        "title": summarize(change),
        "site": r.site,
        "pathogen": r.pathogen,
        "date": r.date.isoformat() if r.date else None,
        "value": r.value,
        "reason": change.reason,
    }


@dataclass
class FeedStore:
    path: Path
    max_items: int = 200
    items: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path, max_items: int = 200) -> "FeedStore":
        p = Path(path)
        items = json.loads(p.read_text()) if p.exists() else []
        return cls(path=p, max_items=max_items, items=items)

    def add(self, item: dict) -> bool:
        """Add an item unless its id is already present. Returns True if added."""
        if any(existing.get("id") == item.get("id") for existing in self.items):
            return False
        self.items.insert(0, item)
        del self.items[self.max_items :]
        return True

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.items, indent=2) + "\n")


def _parse(dt: str | None) -> datetime:
    if not dt:
        return _EPOCH
    try:
        parsed = dtparser.parse(dt)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError):
        return _EPOCH


def build_feed(items: list[dict], config: Config) -> FeedGenerator:
    """Build a FeedGenerator from feed items (newest first)."""
    fg = FeedGenerator()
    fg.id(config.feed_id)
    fg.title(config.feed_title)
    fg.author({"name": "CoWastewaterBot"})
    fg.link(href=config.feed_link, rel="alternate")
    fg.subtitle("Notable changes in Colorado (CDPHE) wastewater surveillance data.")
    fg.language("en")
    # Feed-level updated = newest item's date (falls back to epoch when empty).
    fg.updated(max((_parse(i.get("date")) for i in items), default=_EPOCH))

    # feedgen prepends entries, so add oldest-first to keep newest at the top.
    for item in reversed(items):
        when = _parse(item.get("date"))
        fe = fg.add_entry()
        fe.id(item.get("id") or config.feed_id)
        fe.title(item.get("title") or "Notable change")
        fe.content(_entry_body(item))
        fe.updated(when)
        fe.published(when)
    return fg


def _entry_body(item: dict) -> str:
    parts = [item.get("title", "")]
    if item.get("value") is not None:
        parts.append(f"Concentration: {item['value']}")
    if item.get("reason"):
        parts.append(f"Why flagged: {item['reason']}")
    return "\n".join(p for p in parts if p)


def render_atom(store: FeedStore, config: Config) -> str:
    """Write the Atom feed to ``config.feed_path`` and return the XML string."""
    fg = build_feed(store.items, config)
    out = Path(config.feed_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fg.atom_file(str(out), pretty=True)
    return fg.atom_str(pretty=True).decode("utf-8")
