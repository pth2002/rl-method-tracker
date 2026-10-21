"""Time and participant rules shared by analysis and language-model drafting."""
from __future__ import annotations

import argparse
import re
from datetime import date, datetime, timezone

V1_SNAPSHOT = "2026-10-18"
BOT = re.compile(r"\[bot\]$|^(copilot|gemini-code-assist|coderabbitai|CLAassistant|HuggingFaceDocBuilderDev|"
                 r"github-actions|copy-pr-bot|cursor)", re.I)


def snapshot_date(value: str) -> str:
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError as exc:
        raise argparse.ArgumentTypeError("snapshot must be YYYY-MM-DD") from exc
    return value


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("participant timestamps must include a timezone")
    return result.astimezone(timezone.utc)


def build_prior_merger(merged: list[dict]):
    """Return the shared predicate: a human merged a PR strictly before this event."""
    first = {}
    for row in merged:
        login, when = row.get("merged_by"), row.get("merged")
        if login and when and not BOT.search(login):
            key, at = (row["framework"], login), timestamp(when)
            first[key] = min(first.get(key, at), at)

    def prior_merger(framework: str, login: str | None, when: str) -> bool:
        at = first.get((framework, login))
        return at is not None and at < timestamp(when)

    return prior_merger
