"""Print one issue, pull request or discussion as a compact transcript for reading and coding.

  python tools/thread_dump.py trl pr 4548
  python tools/thread_dump.py verl issue 3157 --chars 400
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))
from github_threads import CACHE, REPOS  # noqa: E402


def pages(repo: str, kind: str) -> list[dict]:
    rows = []
    for f in sorted((CACHE / repo.replace("/", "__") / kind).glob("*.json")):
        rows += json.loads(f.read_text(encoding="utf-8"))
    return rows


_cache: dict = {}


def load(fw: str) -> dict:
    if fw not in _cache:
        repo = REPOS[fw]
        _cache[fw] = {
            "issues": {i["number"]: i for i in pages(repo, "issues")},
            "comments": pages(repo, "issue_comments"),
            "review_comments": pages(repo, "review_comments"),
            "discussions": {d["number"]: d for d in pages(repo, "discussions")},
        }
    return _cache[fw]


def clean(s: str | None, n: int) -> str:
    s = re.sub(r"<!--.*?-->", "", s or "", flags=re.S)
    s = re.sub(r"\n\s*\n+", "\n", s).strip()
    return s[:n] + (" [...]" if len(s) > n else "")


def dump(fw: str, kind: str, number: int, chars: int = 900) -> str:
    d = load(fw)
    out = []
    if kind == "discussion":
        t = d["discussions"].get(number)
        if not t:
            return f"{fw} discussion {number}: not found"
        out.append(f"== {fw} discussion #{number} {t['createdAt'][:10]} by {(t.get('author') or {}).get('login')} "
                   f"({t.get('authorAssociation')}) {t['url']}\nTITLE {t['title']}\n{clean(t.get('body'), chars)}")
        for c in t["comments"]["nodes"]:
            out.append(f"-- {c['createdAt'][:10]} {(c.get('author') or {}).get('login')} ({c.get('authorAssociation')}): "
                       f"{clean(c.get('body'), chars)}")
            for r in c["replies"]["nodes"]:
                out.append(f"   -- {r['createdAt'][:10]} {(r.get('author') or {}).get('login')} "
                           f"({r.get('authorAssociation')}): {clean(r.get('body'), chars)}")
        return "\n".join(out)
    t = d["issues"].get(number)
    if not t:
        return f"{fw} {kind} {number}: not found"
    pr = t.get("pull_request") or {}
    state = "merged " + pr["merged_at"][:10] if pr.get("merged_at") else f"{t['state']} {(t.get('closed_at') or '')[:10]}"
    out.append(f"== {fw} {'PR' if pr else 'issue'} #{number} opened {t['created_at'][:10]} by {t['user']['login']} "
               f"({t.get('author_association')}) -> {state} {t.get('state_reason') or ''} labels={[l['name'] for l in t.get('labels', [])]}\n"
               f"{t['html_url']}\nTITLE {t['title']}\n{clean(t.get('body'), chars)}")
    det = CACHE / REPOS[fw].replace("/", "__") / "pr_detail" / f"{number}.json"
    events = []
    for c in d["comments"]:
        if c.get("issue_url", "").endswith(f"/issues/{number}"):
            events.append((c["created_at"], f"-- {c['created_at'][:10]} {c['user']['login']} ({c.get('author_association')}): {clean(c.get('body'), chars)}"))
    for c in d["review_comments"]:
        if c.get("pull_request_url", "").endswith(f"/pulls/{number}"):
            events.append((c["created_at"], f"-- {c['created_at'][:10]} REVIEW-COMMENT {c['user']['login']} ({c.get('author_association')}) on {c.get('path')}: {clean(c.get('body'), chars // 2)}"))
    if det.exists():
        x = json.loads(det.read_text(encoding="utf-8"))
        p = x["pull"]
        out.append(f"   merged_by={p.get('merged_by')} files={p.get('changed_files')} +{p.get('additions')} -{p.get('deletions')}")
        for r in x["reviews"]:
            if r.get("body") or r.get("state") in ("APPROVED", "CHANGES_REQUESTED"):
                events.append((r.get("submitted_at") or "", f"-- {(r.get('submitted_at') or '')[:10]} REVIEW {r['state']} {r['user']} ({r.get('assoc')}): {clean(r.get('body'), chars)}"))
    out += [e for _, e in sorted(events)]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("framework")
    ap.add_argument("kind", choices=["pr", "issue", "discussion"])
    ap.add_argument("numbers", nargs="+", type=int)
    ap.add_argument("--chars", type=int, default=900)
    a = ap.parse_args()
    for n in a.numbers:
        print(dump(a.framework, a.kind, n, a.chars))
        print()


if __name__ == "__main__":
    main()
