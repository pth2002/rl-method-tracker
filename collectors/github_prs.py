"""Fetch details for selected pull requests: who merged it, who reviewed it, and which files changed.

The selection is every pull request that introduced a tracked method (from the inclusion events)
plus every pull request that mentions a paper from the candidate pool (from mentions.jsonl).
Each pull request is cached as .cache/github/<owner>__<name>/pr_detail/<number>.json with the
fields `pull`, `reviews` and `files`, so a rerun only fetches what is missing.

  python collectors/github_prs.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))
from github_threads import CACHE, REPOS, Client  # noqa: E402

GEN = ROOT / "data" / "generated"


def wanted() -> set[tuple[str, int]]:
    out = set()
    for line in (GEN / "framework_events.jsonl").read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e.get("pr") and e["event"] in ("added", "removed"):
            out.add((e["framework"], int(e["pr"])))
    mp = GEN / "github" / "mentions.jsonl"
    if mp.exists():
        for line in mp.read_text(encoding="utf-8").splitlines():
            m = json.loads(line)
            if m["kind"] == "pr" and m["tier"] in ("link", "title", "bare") and m["number"]:
                out.add((m["framework"], int(m["number"])))
    return out


def fetch(cli: Client, fw: str, number: int) -> None:
    repo = REPOS[fw]
    d = CACHE / repo.replace("/", "__") / "pr_detail"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{number}.json"
    if f.exists():
        return
    base = f"https://api.github.com/repos/{repo}/pulls/{number}"
    pull = cli.get(base).json()
    reviews, files, page = [], [], 1
    while True:
        r = cli.get(f"{base}/reviews", {"per_page": 100, "page": page}).json()
        reviews += r
        if len(r) < 100:
            break
        page += 1
    page = 1
    while page <= 30:
        r = cli.get(f"{base}/files", {"per_page": 100, "page": page}).json()
        files += [{k: x.get(k) for k in ("filename", "status", "additions", "deletions", "previous_filename")} for x in r]
        if len(r) < 100:
            break
        page += 1
    keep = {k: pull.get(k) for k in ("number", "title", "state", "created_at", "closed_at", "merged_at",
                                      "merge_commit_sha", "additions", "deletions", "changed_files",
                                      "author_association", "html_url", "body")}
    keep["user"] = (pull.get("user") or {}).get("login")
    keep["merged_by"] = (pull.get("merged_by") or {}).get("login")
    keep["requested_reviewers"] = [u["login"] for u in pull.get("requested_reviewers") or []]
    rv = [{"user": (x.get("user") or {}).get("login"), "state": x.get("state"),
           "submitted_at": x.get("submitted_at"), "assoc": x.get("author_association"),
           "body": x.get("body")} for x in reviews]
    f.write_text(json.dumps({"pull": keep, "reviews": rv, "files": files}, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    cli = Client()
    todo = sorted(wanted())
    print(f"{len(todo)} pull requests", flush=True)
    for i, (fw, n) in enumerate(todo):
        try:
            fetch(cli, fw, n)
        except Exception as exc:  # a deleted or transferred pull request should not stop the run
            print(f"  {fw}#{n}: {exc}", flush=True)
        if i % 50 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
    print("done")


if __name__ == "__main__":
    main()
