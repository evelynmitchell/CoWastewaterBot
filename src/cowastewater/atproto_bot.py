"""Post notable wastewater changes to an ATProto (Bluesky) account.

Safe by default: with no handle/app-password configured (``COWW_ATPROTO_HANDLE``
/ ``COWW_ATPROTO_PASSWORD``), :func:`post_change` composes the text but does not
publish — so the poller can run and be tested anywhere without credentials.

The ``atproto`` package is an optional dependency, imported lazily so the rest
of the tool (MCP server, RSS feed) works without it installed.
"""

from __future__ import annotations

from dataclasses import dataclass

from .analysis import NotableChange, summarize
from .config import Config

# Bluesky's post limit is 300 graphemes; stay a hair under and ellipsize.
_MAX_POST = 300


@dataclass(frozen=True)
class PostResult:
    text: str
    posted: bool
    dry_run: bool
    uri: str | None = None
    error: str | None = None


def format_post(change: NotableChange) -> str:
    """Compose the skeet text for a notable change (<= 300 chars)."""
    text = f"🚱 {summarize(change)}"
    if len(text) > _MAX_POST:
        text = text[: _MAX_POST - 1].rstrip() + "…"
    return text


def post_change(change: NotableChange, config: Config) -> PostResult:
    """Publish a notable change to Bluesky, or return a dry-run result.

    Dry-run (no publish) whenever credentials are missing; otherwise logs in with
    the app password and sends the post.
    """
    text = format_post(change)
    if not config.atproto_ready:
        return PostResult(text=text, posted=False, dry_run=True)

    try:
        from atproto import Client  # lazy: optional dependency
    except ImportError:
        return PostResult(
            text=text,
            posted=False,
            dry_run=True,
            error="atproto not installed — `uv sync --extra atproto` to enable posting.",
        )

    try:
        client = Client(base_url=config.atproto_pds)
        client.login(config.atproto_handle, config.atproto_password)
        response = client.send_post(text=text)
        return PostResult(text=text, posted=True, dry_run=False, uri=getattr(response, "uri", None))
    except Exception as exc:  # noqa: BLE001 — surface any post failure, don't crash the poll
        return PostResult(text=text, posted=False, dry_run=False, error=str(exc))
