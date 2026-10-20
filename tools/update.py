"""One command for the whole refresh: fetch frameworks, re-trace history, verify sources,
rebuild the tables, the index and the project page data (docs/data.js), then validate.

  python tools/update.py            # use cached clones
  python tools/update.py --fetch    # pull the latest commits first (what CI runs)
  python tools/update.py --fetch --record
                                    # also refresh the public record of proposals (GitHub API, slow)

With --record, threads that propose a non-included general method and are not yet coded are listed
in data/generated/process/uncoded_threads.jsonl for a person to code.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    print("$", " ".join(args), flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main() -> int:
    fetch = ["--fetch"] if "--fetch" in sys.argv else []
    run("collectors/frameworks.py", *fetch)
    run("collectors/papers.py")
    run("tools/impl_links.py")
    run("tools/summary.py")
    if "--record" in sys.argv:
        run("tools/adoption_rate.py")
        run("collectors/code_citations.py")
        run("collectors/github_threads.py", "--refresh")
        run("collectors/github_index.py")
        run("collectors/github_mergers.py")
        run("collectors/github_prs.py")
        run("tools/process_analysis.py", "--build-facts")
        list_uncoded()
    run("tools/frameworks_doc.py")
    run("tools/framework_profiles.py")
    run("tools/site_data.py")
    return subprocess.run([sys.executable, "tools/validate.py"], cwd=ROOT).returncode


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
    with out.open("w", encoding="utf-8") as f:
        for m in new.values():
            f.write(json.dumps({k: m[k] for k in ("arxiv", "framework", "kind", "number", "date", "url")}) + "\n")
    print(f"{len(new)} uncoded proposal threads -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
