"""Per-framework profiles: how many methods each framework includes, how fast, through whom, and
what it later removed.

Commit authors are classified for each first landing of a catalog method in a framework:
  paper_author      the git author matches the source's author list
  core_contributor  not a paper author, and among the framework's most frequent commit authors
  other_named       a named person outside both groups
  unresolved        a handle or a source without an author list
"Most frequent" means the smallest set of authors that together made half of the commits on
the framework's main branch before the landing date, a proxy for the people who maintained it at
that time. Counting only earlier commits keeps later contributions from being read back into the
landing. The snapshot-level set is kept for reporting the size of each core group.

Writes data/generated/framework_profiles.json.
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"
REPOS = ROOT / ".cache" / "repos"
sys.path.insert(0, str(ROOT / "tools"))
from summary import _tokens  # noqa: E402

FWS = ["verl", "trl", "openrlhf", "nemo-rl", "roll", "slime", "areal"]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def main_history(repo: Path) -> list[tuple[str, str]]:
    """(commit date, author name) for every main-branch commit, oldest first."""
    rows = git(repo, "log", "--first-parent", "--reverse", "--format=%cs%x09%an", "HEAD").splitlines()
    return [tuple(r.split("	", 1)) for r in rows if "	" in r]


def core_from(names: list[str], share: float = 0.5) -> tuple[set[frozenset], int, int]:
    """Name-token sets of the authors who together made `share` of the given commits."""
    counts = Counter(n.strip() for n in names if n.strip())
    total, acc, core = sum(counts.values()), 0, set()
    for name, c in counts.most_common():
        if acc >= share * total:
            break
        core.add(frozenset(_tokens(name)) or frozenset([name.lower()]))
        acc += c
    return core, len(core), len(counts)


def main() -> None:
    adoption = json.loads((GEN / "adoption.json").read_text(encoding="utf-8"))
    head = json.loads((GEN / "framework_head.json").read_text(encoding="utf-8"))
    events = [json.loads(l) for l in (GEN / "framework_events.jsonl").read_text(encoding="utf-8").split(chr(10)) if l]

    cores, hist, core_cache = {}, {}, {}
    repo_of = {}
    for fw in FWS + ["verl_recipe"]:
        hist[fw] = main_history(REPOS / fw)
        cores[fw] = core_from([a for _, a in hist[fw]])

    def core_before(repo: str, date: str) -> set[frozenset]:
        """Core set computed only from commits dated before `date`."""
        key = (repo, date)
        if key not in core_cache:
            core_cache[key] = core_from([a for d, a in hist[repo] if d < date])[0]
        return core_cache[key]
    # which repository a commit lives in (verl and its recipe repository share one label)
    for e in events:
        repo_of[e["sha"][:10]] = e["framework"]

    def classify(v: dict) -> str:
        rel = v["commit_author_is_paper_author"]
        if rel == "author":
            return "paper_author"
        if rel in ("unknown", "no_paper"):
            # a handle can still belong to a core contributor
            pass
        repo = repo_of.get(v["commit"], "verl")
        repo = repo if repo in hist else "verl"
        core = core_before(repo, v["first_date"])
        toks = frozenset(_tokens(v["commit_author"])) or frozenset([v["commit_author"].lower()])
        if toks in core:
            return "core_contributor"
        return "other_named" if rel == "not_author" else "unresolved"

    recent = [r for r in adoption if (r["source_date"] or "") >= "2025-01-01" and r["per_framework"]]
    prof = {fw: {"methods_ever": 0, "methods_now": 0, "first_anywhere": 0, "lags": [],
                 "who": Counter(), "tiers_now": Counter(), "removed": []} for fw in FWS}
    landings = []
    for r in recent:
        earliest_fw = min(r["per_framework"].items(), key=lambda kv: kv[1]["first_date"])[0]
        for fw, v in r["per_framework"].items():
            p = prof[fw]
            p["methods_ever"] += 1
            who = classify(v)
            p["who"][who] += 1
            landings.append({"method": r["id"], "framework": fw, "who": who,
                             "n_frameworks_now": r["n_frameworks_at_head"]})
            if fw == earliest_fw:
                p["first_anywhere"] += 1
            if v["lag_days"] is not None and not v["left_censored"]:
                p["lags"].append(v["lag_days"])
            tier = r["frameworks_at_head"].get(fw)
            if tier:
                p["methods_now"] += 1
                p["tiers_now"][tier] += 1
            else:
                last = [e for e in events if r["id"] in (e.get("methods") or [])
                        and ("verl" if e["framework"] == "verl_recipe" else e["framework"]) == fw
                        and e["event"] == "removed"]
                last = max(last, key=lambda e: e["date"]) if last else None
                p["removed"].append({"method": r["id"], "date": last["date"] if last else None,
                                     "subject": last["subject"] if last else None,
                                     "commit": last["sha"][:10] if last else None})

    out = {"core_definition": "smallest set of commit authors covering half of the main-branch commits made before the landing",
           "core_sizes": {fw: {"core_authors": cores[fw][1], "all_authors": cores[fw][2]} for fw in cores},
           "frameworks": {}}
    for fw, p in prof.items():
        out["frameworks"][fw] = {
            "methods_ever": p["methods_ever"], "methods_now": p["methods_now"],
            "first_anywhere": p["first_anywhere"],
            "median_lag": statistics.median(p["lags"]) if p["lags"] else None, "n_lags": len(p["lags"]),
            "who": dict(p["who"]), "tiers_now": dict(p["tiers_now"]), "removed": p["removed"]}
    # breadth of inclusion by who brought the first landing anywhere
    first_who = {}
    for r in recent:
        fw, v = min(r["per_framework"].items(), key=lambda kv: kv[1]["first_date"])
        first_who[r["id"]] = (classify(v), r["n_frameworks_at_head"])
    by = defaultdict(list)
    for who, n in first_who.values():
        by[who].append(n)
    out["breadth_by_first_route"] = {w: {"methods": len(ns), "in_3plus_now": sum(n >= 3 for n in ns),
                                         "median_frameworks_now": statistics.median(ns)} for w, ns in by.items()}
    out["landings"] = landings
    (GEN / "framework_profiles.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    for fw, p in out["frameworks"].items():
        print(f"{fw:9s} ever {p['methods_ever']:3d} now {p['methods_now']:3d} first {p['first_anywhere']:3d} "
              f"medlag {p['median_lag']} who {p['who']} removed {len(p['removed'])}")
    print("core sizes", out["core_sizes"])
    print("breadth by first route", out["breadth_by_first_route"])


if __name__ == "__main__":
    main()
