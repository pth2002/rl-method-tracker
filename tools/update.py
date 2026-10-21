"""One command for the whole refresh: fetch frameworks, re-trace history, verify sources,
rebuild the tables, the index, the project page data and the README header, then validate.

  python tools/update.py            # use cached clones
  python tools/update.py --fetch    # pull the latest commits first (what CI runs)
  python tools/update.py --fetch --record --snapshot YYYY-MM-DD
                                    # also refresh the public record of proposals (GitHub API, slow)

With --record, threads that propose a non-included general method and are not yet coded are listed
in data/generated/process/uncoded_threads.jsonl for a person to code.
Without --snapshot the analysis retains the report v1 date; weekly runs pass their UTC collection date.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from process_rules import V1_SNAPSHOT, snapshot_date

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    print("$", " ".join(args), flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--snapshot", type=snapshot_date, default=V1_SNAPSHOT)
    args = parser.parse_args()
    fetch = ["--fetch"] if args.fetch else []
    run("collectors/frameworks.py", *fetch)
    run("collectors/papers.py")
    rebuild_adoption()
    if args.record:
        run("collectors/code_citations.py")
        run("collectors/github_threads.py", "--refresh")
        run("collectors/github_index.py")
        run("collectors/github_mergers.py")
        run("collectors/github_prs.py")
        rebuild_process(args.snapshot)
    rebuild_pages()
    # 3 means the refresh finished and validation found problems; a crash exits with 1
    return 3 if subprocess.run([sys.executable, "tools/validate.py"], cwd=ROOT).returncode else 0


def rebuild_adoption() -> None:
    """Shared by a refresh and by draft mappings, before selecting proposal threads."""
    run("tools/impl_links.py")
    run("tools/summary.py")
    run("tools/adoption_rate.py")


def rebuild_process(snapshot: str) -> None:
    run("tools/process_analysis.py", "--build-facts", "--snapshot", snapshot)
    list_uncoded()


def rebuild_pages() -> None:
    for script in ("frameworks_doc", "framework_profiles", "site_data", "site_hero"):
        run(f"tools/{script}.py")


def list_uncoded() -> None:
    """Threads that open with a citation of a non-included general method and have no code yet."""
    import json
    gen = ROOT / "data" / "generated"
    jl = lambda p: [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []
    open_set = {r["arxiv"] for r in jl(gen / "pool_adoption.jsonl") if r["strict_general"] and not r["adopted"]}
    known = {(a["framework"], a["number"]) for a in jl(gen / "process" / "attempts_coded.jsonl")}
    known |= {(r["framework"], r["number"]) for r in jl(gen / "process" / "threads_reference_only.jsonl")}
    new = {}
    for m in jl(gen / "github" / "mentions.jsonl"):
        if (m["arxiv"] in open_set and m["tier"] in ("link", "title", "bare") and m["place"] == "opening"
                and (m["framework"], m["number"]) not in known):
            new[(m["framework"], m["number"])] = m
    out = gen / "process" / "uncoded_threads.jsonl"
    blocked = {(u["framework"], u["number"]): u["draft_blocked"] for u in jl(out) if u.get("draft_blocked")}
    with out.open("w", encoding="utf-8") as f:
        for m in new.values():
            row = {k: m[k] for k in ("arxiv", "framework", "kind", "number", "date", "url")}
            if (m["framework"], m["number"]) in blocked:
                row["draft_blocked"] = blocked[(m["framework"], m["number"])]
            f.write(json.dumps(row) + "\n")
    print(f"{len(new)} uncoded proposal threads -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
