"""Record who merged every merged pull request, so that "maintainer" can be defined from merge
rights used before a given date.

Writes data/generated/github/merged_prs.jsonl with framework, number, merged date, author login
and merger login for every merged pull request.

  python collectors/github_mergers.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))
from github_threads import REPOS, Client  # noqa: E402

OUT = ROOT / "data" / "generated" / "github" / "merged_prs.jsonl"

Q = """
query($owner:String!, $name:String!, $after:String) {
  repository(owner:$owner, name:$name) {
    pullRequests(states:MERGED, first:100, after:$after, orderBy:{field:CREATED_AT, direction:ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes { number mergedAt author { login } mergedBy { login } }
    }
  }
}"""


def main() -> None:
    cli = Client()
    rows = []
    for fw, repo in REPOS.items():
        owner, name = repo.split("/")
        after, n = None, 0
        while True:
            conn = cli.graphql(Q, {"owner": owner, "name": name, "after": after})["repository"]["pullRequests"]
            for p in conn["nodes"]:
                # full UTC timestamp, so a merge earlier on the same day still counts as before an event
                rows.append({"framework": fw, "number": p["number"], "merged": p["mergedAt"] or "",
                             "author": (p.get("author") or {}).get("login"),
                             "merged_by": (p.get("mergedBy") or {}).get("login")})
                n += 1
            if not conn["pageInfo"]["hasNextPage"]:
                break
            after = conn["pageInfo"]["endCursor"]
        print(f"{fw:12s} {n:6d} merged pull requests", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
