"""Find arXiv identifiers that the frameworks cite in their own files.

Walks the main-branch history of each framework (first parent, as for the inclusion events) and
records every added line that contains an arXiv identifier from the candidate pool, with the
commit, date, author and file path. A citation counts as "linked" when the identifier sits in an
arXiv, Hugging Face papers or alphaXiv URL or follows "arXiv:", and as "bare" otherwise.

Writes data/generated/github/code_citations.jsonl (one row per identifier, framework and file,
with the first commit that added it there) and prints a per-framework summary. Keeping every file
lets a later implementation be seen next to an earlier background mention.
"""
from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOS = ROOT / ".cache" / "repos"
OUT = ROOT / "data" / "generated" / "github"
FWS = ["verl", "verl_recipe", "trl", "openrlhf", "nemo-rl", "roll", "slime", "areal"]

ID_RE = re.compile(r"(?<![\d.])(\d{4}\.\d{4,5})(?:v\d+)?(?![\d])")
LINK_RE = re.compile(r"(arxiv\.org/(?:abs|pdf|html)/|arxiv:\s*|huggingface\.co/papers/|alphaxiv\.org/(?:abs|overview)/)$",
                     re.I)


def pool_ids() -> set[str]:
    rows = (ROOT / "data" / "generated" / "pool_adoption.jsonl").read_text(encoding="utf-8").splitlines()
    ids = {json.loads(r)["arxiv"] for r in rows if r}
    papers = json.loads((ROOT / "data" / "generated" / "papers.json").read_text(encoding="utf-8"))["papers"]
    return ids | set(papers)


def scan(fw: str, ids: set[str]) -> list[dict]:
    repo = REPOS / fw
    cmd = ["git", "-C", str(repo), "log", "--first-parent", "--diff-merges=first-parent", "--reverse",
           "-p", "--unified=0", "--no-color", "--no-ext-diff", "--format=@@COMMIT%x09%H%x09%cs%x09%an%x09%s", "HEAD"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, encoding="utf-8", errors="replace")
    first: dict[tuple[str, str], dict] = {}
    sha = date = author = subject = path = None
    for line in proc.stdout:
        if line.startswith("@@COMMIT\t"):
            _, sha, date, author, subject = (line.rstrip("\n").split("\t", 4) + [""])[:5]
            continue
        if line.startswith("+++ "):
            path = line[6:].strip() if line.startswith("+++ b/") else None
            continue
        if not line.startswith("+") or line.startswith("+++"):
            continue
        for m in ID_RE.finditer(line):
            aid = m.group(1)
            if aid not in ids:
                continue
            linked = bool(LINK_RE.search(line[max(0, m.start() - 40):m.start()]))
            key = (aid, path)
            row = first.get(key)
            if row is None or (linked and not row["linked"]):
                # keep the first commit per file, upgraded to the first linked mention in that file
                first[key] = {"arxiv": aid, "framework": fw, "sha": sha, "date": date, "author": author,
                              "subject": subject[:160], "path": path, "linked": linked,
                              "line": line[1:].strip()[:240]}
    proc.wait()
    return list(first.values())


def main() -> None:
    ids = pool_ids()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for fw in FWS:
        found = scan(fw, ids)
        rows += found
        print(f"{fw:12s} {len({r['arxiv'] for r in found}):4d} identifiers in {len(found)} files", flush=True)
    rows.sort(key=lambda r: (r["arxiv"], r["framework"], r["date"], r["path"] or ""))
    with (OUT / "code_citations.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    by = defaultdict(set)
    for r in rows:
        by[r["arxiv"]].add(r["framework"])
    print(f"{len(by)} distinct pool papers cited in framework files")


if __name__ == "__main__":
    main()
