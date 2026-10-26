"""Download the public discussion record of each framework repository: issues, pull requests,
issue and pull-request comments, review comments and GitHub Discussions.

Raw API pages are cached under .cache/github/<owner>__<name>/<kind>/NNNN.json, so a rerun only
fetches what is missing (the last page of each listing is always fetched again). The token comes
from the GitHub CLI (`gh auth token`) and is never written anywhere.

  python collectors/github_threads.py            # all repositories
  python collectors/github_threads.py trl verl   # selected frameworks
  python collectors/github_threads.py --refresh  # download everything again, so old threads show their current state
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "github"
GH = r"C:\Program Files\GitHub CLI\gh.exe"

REPOS = {
    "verl": "verl-project/verl",
    "verl_recipe": "verl-project/verl-recipe",
    "trl": "huggingface/trl",
    "openrlhf": "OpenRLHF/OpenRLHF",
    "nemo-rl": "NVIDIA-NeMo/RL",
    "roll": "alibaba/ROLL",
    "slime": "THUDM/slime",
    "areal": "areal-project/AReaL",
}

# REST listings: (kind, path, params)
LISTINGS = [
    ("issues", "issues", {"state": "all", "sort": "created", "direction": "asc"}),
    ("pulls", "pulls", {"state": "all", "sort": "created", "direction": "asc"}),
    ("issue_comments", "issues/comments", {"sort": "created", "direction": "asc"}),
    ("review_comments", "pulls/comments", {"sort": "created", "direction": "asc"}),
]

# Network failures worth another try: a dropped connection, a body cut off mid-stream, a timeout.
TRANSIENT = (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError,
             requests.exceptions.Timeout)

DISCUSSIONS_Q = """
query($owner:String!, $name:String!, $after:String) {
  repository(owner:$owner, name:$name) {
    discussions(first:50, after:$after, orderBy:{field:CREATED_AT, direction:ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title body createdAt url author { login } authorAssociation
        category { name } answer { id }
        comments(first:100) {
          pageInfo { hasNextPage }
          nodes { body createdAt author { login } authorAssociation
                  replies(first:50) { nodes { body createdAt author { login } authorAssociation } } }
        }
      }
    }
  }
}"""


def token() -> str:
    """GH_TOKEN or GITHUB_TOKEN when set (as in CI), otherwise the token of the GitHub CLI."""
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    gh = shutil.which("gh") or GH
    return subprocess.run([gh, "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


class Client:
    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token()}",
                               "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"})

    def _send(self, method: str, url: str, **kwargs) -> requests.Response | None:
        """One request. A dropped connection or a timeout returns None so the caller retries."""
        try:
            return self.s.request(method, url, timeout=90, **kwargs)
        except TRANSIENT as e:
            print(f"  network error ({type(e).__name__}), retrying in 30s", flush=True)
            time.sleep(30)
            return None

    def _wait(self, r: requests.Response) -> bool:
        """Sleep through primary or secondary rate limits. Returns True if the call should be retried."""
        if r.status_code in (403, 429):
            reset = r.headers.get("X-RateLimit-Reset")
            retry = r.headers.get("Retry-After")
            if retry:
                delay = int(retry) + 1
            elif r.headers.get("X-RateLimit-Remaining") == "0" and reset:
                delay = max(5, int(reset) - int(time.time()) + 5)
            else:
                delay = 60
            print(f"  rate limited ({r.status_code}), sleeping {delay}s", flush=True)
            time.sleep(delay)
            return True
        if r.status_code >= 500:
            time.sleep(10)
            return True
        return False

    def get(self, url: str, params: dict | None = None) -> requests.Response:
        for _ in range(8):
            r = self._send("GET", url, params=params)
            if r is None or self._wait(r):
                continue
            r.raise_for_status()
            rem = r.headers.get("X-RateLimit-Remaining")
            if rem is not None and int(rem) < 50:
                delay = max(5, int(r.headers["X-RateLimit-Reset"]) - int(time.time()) + 5)
                print(f"  budget low ({rem}), sleeping {delay}s", flush=True)
                time.sleep(delay)
            return r
        raise RuntimeError(f"giving up on {url}")

    def graphql(self, query: str, variables: dict) -> dict:
        for _ in range(8):
            r = self._send("POST", "https://api.github.com/graphql", json={"query": query, "variables": variables})
            if r is None or self._wait(r):
                continue
            r.raise_for_status()
            data = r.json()
            if "errors" in data:
                print("  graphql errors:", data["errors"][:1], flush=True)
                time.sleep(10)
                continue
            return data["data"]
        raise RuntimeError("giving up on graphql")


def fetch_listing(cli: Client, repo: str, kind: str, path: str, params: dict) -> int:
    out = CACHE / repo.replace("/", "__") / kind
    out.mkdir(parents=True, exist_ok=True)
    have = sorted(out.glob("*.json"))
    # refetch the last cached page because it may have been partial
    page = max(1, len(have))
    n = 0
    while True:
        f = out / f"{page:04d}.json"
        if f.exists() and page < len(have):
            page += 1
            continue
        r = cli.get(f"https://api.github.com/repos/{repo}/{path}", {**params, "per_page": 100, "page": page})
        items = r.json()
        f.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        n += len(items)
        if len(items) < 100 or 'rel="next"' not in r.headers.get("Link", ""):
            break
        page += 1
    return page


def fetch_discussions(cli: Client, repo: str) -> int:
    owner, name = repo.split("/")
    out = CACHE / repo.replace("/", "__") / "discussions"
    out.mkdir(parents=True, exist_ok=True)
    after, page = None, 1
    while True:
        data = cli.graphql(DISCUSSIONS_Q, {"owner": owner, "name": name, "after": after})
        conn = data["repository"]["discussions"]
        (out / f"{page:04d}.json").write_text(json.dumps(conn["nodes"], ensure_ascii=False), encoding="utf-8")
        if not conn["pageInfo"]["hasNextPage"]:
            return page
        after, page = conn["pageInfo"]["endCursor"], page + 1


def main() -> None:
    refresh = "--refresh" in sys.argv
    want = [a for a in sys.argv[1:] if not a.startswith("--")] or list(REPOS)
    cli = Client()
    for fw in want:
        repo = REPOS[fw]
        if refresh:
            for kind in [k for k, _, _ in LISTINGS] + ["discussions"]:
                shutil.rmtree(CACHE / repo.replace("/", "__") / kind, ignore_errors=True)
        for kind, path, params in LISTINGS:
            t = time.time()
            pages = fetch_listing(cli, repo, kind, path, params)
            print(f"{fw:12s} {kind:16s} {pages:4d} pages  {time.time() - t:6.0f}s", flush=True)
        t = time.time()
        pages = fetch_discussions(cli, repo)
        print(f"{fw:12s} {'discussions':16s} {pages:4d} pages  {time.time() - t:6.0f}s", flush=True)
    mf = CACHE / "fetch_meta.json"
    meta = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {"repos": {}}
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    for fw in want:
        meta["repos"][fw] = {"repo": REPOS[fw], "fetched_at": stamp}
    mf.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print("done", stamp)


if __name__ == "__main__":
    main()
