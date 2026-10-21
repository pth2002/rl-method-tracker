"""From mention to merge: what the public record of the seven frameworks shows about inclusion.

Inputs (all under data/generated/):
  pool_adoption.jsonl, adoption.json, framework_events.jsonl   papers, labels and inclusion
  github/threads.jsonl, github/mentions.jsonl                  threads and their paper matches
  github/merged_prs.jsonl                                      who merged every pull request, and when
  github/pr_facts.jsonl                                        reviewers and changed files of selected pull requests
  process/attempts_coded.jsonl                                 coded outcome of each proposal thread
  process/attempt_replies.jsonl                                who replied in each proposal thread, and when

Writes data/generated/process/summary.json and landings.jsonl, and prints the main counts.

  python tools/process_analysis.py                  # from the files above
  python tools/process_analysis.py --build-facts    # first rebuild pr_facts and attempt_replies from the download cache
  python tools/process_analysis.py --snapshot YYYY-MM-DD  # explicit date for a weekly collection

Units
  paper         a general method from the pool
  landing       a method's first inclusion in one framework (a method-framework event)
  pull request  one distinct (repository, number); one pull request can carry several landings
  thread        one issue, pull request or discussion, coded on its own text

Definitions
  record        a link, title or bare arXiv identifier of the paper in a thread
  prior merger  someone who merged a pull request in the repository before the moment in question (UTC
                timestamps). A proxy for maintainers: it misses reviewers without merge rights and people
                before their first merge, and it keeps people who have since left.
  landing PR    the pull request named in the commit that first introduced a method in a framework
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import yaml
from process_rules import BOT, V1_SNAPSHOT, build_prior_merger, snapshot_date

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"
OUT = GEN / "process"
sys.path.insert(0, str(ROOT / "collectors"))
from github_threads import CACHE, REPOS  # noqa: E402

SNAPSHOT = V1_SNAPSHOT  # default remains the report v1 reproduction date
DEP_FILES = re.compile(r"(^|/)(requirements[^/]*\.txt|setup\.py|setup\.cfg|pyproject\.toml|environment\.ya?ml|uv\.lock)$")
FACTS = GEN / "github" / "pr_facts.jsonl"
REPLIES = OUT / "attempt_replies.jsonl"
PKG = {"verl": "verl/", "verl_recipe": None, "trl": "trl/", "openrlhf": "openrlhf/", "nemo-rl": "nemo_rl/",
       "slime": "slime/", "areal": "areal/", "roll": "roll/"}


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def days(a: str, b: str) -> int:
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


# ---------------------------------------------------------------- facts from the download cache
def _pages(repo: str, kind: str) -> list[dict]:
    rows = []
    for f in sorted((CACHE / repo.replace("/", "__") / kind).glob("*.json")):
        rows += json.loads(f.read_text(encoding="utf-8"))
    return rows


def build_facts() -> None:
    """Rebuild pr_facts.jsonl and attempt_replies.jsonl from the cache. Neither keeps any text."""
    rows = []
    for fw, repo in REPOS.items():
        d = CACHE / repo.replace("/", "__") / "pr_detail"
        for f in sorted(d.glob("*.json"), key=lambda f: int(f.stem)) if d.exists() else []:
            x = json.loads(f.read_text(encoding="utf-8"))
            p = x["pull"]
            rows.append({"framework": fw, "number": p["number"], "user": p["user"], "merged_by": p["merged_by"],
                         "state": p["state"], "created_at": p["created_at"], "closed_at": p["closed_at"],
                         "merged_at": p["merged_at"],
                         "reviews": [{"user": r["user"], "state": r["state"], "submitted_at": r.get("submitted_at")}
                                     for r in x["reviews"]],
                         "files": x["files"]})
    with FACTS.open("w", encoding="utf-8") as out:
        for r in rows:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} pull request facts")

    attempts = jl(OUT / "attempts_coded.jsonl")
    threads = {(t["framework"], t["number"]): t for t in jl(GEN / "github" / "threads.jsonl")}
    facts = {(r["framework"], r["number"]): r for r in rows}
    out_rows = []
    for fw in sorted({a["framework"] for a in attempts}):
        repo = REPOS[fw]
        want = {a["number"] for a in attempts if a["framework"] == fw}
        replies = defaultdict(list)
        for c in _pages(repo, "issue_comments"):
            n = int(c["issue_url"].rsplit("/", 1)[1])
            if n in want:
                replies[n].append(((c.get("user") or {}).get("login"), c["created_at"], "comment"))
        for c in _pages(repo, "review_comments"):
            n = int(c["pull_request_url"].rsplit("/", 1)[1])
            if n in want:
                replies[n].append(((c.get("user") or {}).get("login"), c["created_at"], "review_comment"))
        for d in _pages(repo, "discussions"):
            if d["number"] in want:
                for c in d["comments"]["nodes"]:
                    replies[d["number"]].append(((c.get("author") or {}).get("login"), c["createdAt"], "comment"))
                    for r in c["replies"]["nodes"]:
                        replies[d["number"]].append(((r.get("author") or {}).get("login"), r["createdAt"], "comment"))
        for n in want:
            f = facts.get((fw, n))
            for r in (f or {}).get("reviews", []):
                if r.get("submitted_at"):
                    replies[n].append((r["user"], r["submitted_at"], "review"))
            t = threads.get((fw, n), {})
            out_rows.append({"framework": fw, "number": n, "proposer": t.get("user"),
                             "replies": [{"user": u, "at": at, "kind": k} for u, at, k in sorted(replies[n], key=lambda x: x[1])
                                         if u and not BOT.search(u)]})
    with REPLIES.open("w", encoding="utf-8") as out:
        for r in out_rows:
            out.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote replies for {len(out_rows)} proposal threads")


_facts: dict | None = None


def pr_detail(fw: str, n: int) -> dict | None:
    """Pull request facts in the shape of the download cache, read from pr_facts.jsonl."""
    global _facts
    if _facts is None:
        _facts = {(r["framework"], r["number"]): r for r in jl(FACTS)}
    r = _facts.get((fw, int(n)))
    if r is None:
        return None
    pull = {k: r[k] for k in ("number", "user", "merged_by", "state", "created_at", "closed_at", "merged_at")}
    return {"pull": pull, "reviews": r["reviews"], "files": r["files"]}


def footprint(det: dict) -> dict:
    files = det["files"]
    lines = sum((x.get("additions") or 0) + (x.get("deletions") or 0) for x in files)
    return {"files": len(files), "lines": lines,
            "tests": any(re.search(r"(^|/)tests?/|test_", x["filename"]) for x in files),
            "docs": any(x["filename"].startswith("docs/") or x["filename"].endswith(".md") for x in files),
            "deps": any(DEP_FILES.search(x["filename"]) for x in files),
            "new_files": sum(x.get("status") == "added" for x in files)}


def core_lines(repo: str, det: dict) -> int:
    """Lines changed in the framework's own Python package, without tests, docs, examples or configs."""
    pkg, total = PKG[repo], 0
    for f in det["files"]:
        fn = f["filename"]
        if pkg and fn.startswith(pkg) and fn.endswith(".py") and "/tests/" not in fn and not fn.split("/")[-1].startswith("test_"):
            total += (f.get("additions") or 0) + (f.get("deletions") or 0)
    return total


# ---------------------------------------------------------------- review threads, merged against not merged
REVIEW_FIELDS = ["design", "completeness", "evidence", "placement", "surface", "demand", "covered", "priority"]


def review_comparison(attempts: list[dict], snapshot: str = SNAPSHOT) -> dict:
    """Same-field coding of merged landing pull requests and of proposals for non-included methods.

    A concern is an explicit objection raised by someone other than the proposer at any point in the
    thread; an open concern was still unaddressed when the thread ended. Counts are threads."""
    merged = jl(OUT / "landing_prs_coded.jsonl")
    others = jl(OUT / "attempts_round6_coded.jsonl")
    if not merged or not others:
        return {}
    kind = {f"{a['framework']}#{a['number']}": a["type"] for a in attempts}
    # a reason a maintainer stated is a concern someone raised, so the two codings must nest
    raised = {r["thread_id"]: set(r["concerns_raised"]) for r in others}
    for a in attempts:
        if f"{a['framework']}#{a['number']}" not in raised:
            continue  # new weekly records are outside the fixed paired-review sample
        extra = set(a["reasons"]) - raised.get(f"{a['framework']}#{a['number']}", set())
        if extra:
            raise SystemExit(f"{a['framework']}#{a['number']}: stated reasons {sorted(extra)} missing from concerns_raised")
    groups = {"merged": merged,
              "unmerged_pr": [r for r in others if kind.get(r["thread_id"]) == "pr"],
              "request": [r for r in others if kind.get(r["thread_id"]) == "request"]}
    facts = {(r["framework"], r["number"]): r for r in jl(FACTS)}
    threads = {(t["framework"], t["number"]): t for t in jl(GEN / "github" / "threads.jsonl")}
    prior_merger = build_prior_merger(jl(GEN / "github" / "merged_prs.jsonl"))

    def thread_end(fw: str, n: int) -> str:
        f = facts.get((fw, n))
        if f:
            return f.get("merged_at") or f.get("closed_at") or snapshot + "T23:59:59Z"
        closed = threads.get((fw, n), {}).get("closed") or snapshot
        return closed if "T" in closed else closed + "T23:59:59Z"

    def stats(rows: list[dict]) -> dict:
        out = {"n": len(rows),
               "human_discussion": sum(r["human_discussion"] for r in rows),
               "any_concern": sum(bool(r["concerns_raised"]) for r in rows),
               "open_concern": sum(bool(r["concerns_open_at_end"]) for r in rows),
               "demand_or_surface": sum(bool({"demand", "surface"} & set(r["concerns_raised"])) for r in rows),
               "design_or_completeness": sum(bool({"design", "completeness"} & set(r["concerns_raised"])) for r in rows),
               "results_shown": sum(r["results_shown"] for r in rows),
               "results_requested": sum(r["results_requested"] for r in rows),
               "demand_signal": sum(r["demand_signal"] for r in rows),
               "placement_change": sum(r["placement_change"] for r in rows),
               "driver": dict(sorted(Counter(r["driver"] for r in rows).items())),
               "raised": {k: sum(k in r["concerns_raised"] for r in rows) for k in REVIEW_FIELDS},
               "open": {k: sum(k in r["concerns_open_at_end"] for r in rows) for k in REVIEW_FIELDS}}
        with_c = [r for r in rows if r["concerns_raised"]]
        pm = 0
        for r in with_c:
            fw, n = r["thread_id"].split("#")
            end = thread_end(fw, int(n))
            pm += any(prior_merger(fw, u, end) for u in r["raised_by"])
        out["concern_by_prior_merger"] = pm
        return out

    res = {g: stats(rows) for g, rows in groups.items()}
    res["by_framework"] = {}
    for fw in ["trl", "verl", "nemo-rl", "areal", "slime", "openrlhf"]:
        sel = (fw, "verl_recipe") if fw == "verl" else (fw,)
        res["by_framework"][fw] = {g: stats([r for r in rows if r["thread_id"].split("#")[0] in sel])
                                   for g, rows in groups.items() if g != "request"}
    return res


# ---------------------------------------------------------------- analysis
def main(snapshot: str = SNAPSHOT) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pool = {r["arxiv"]: r for r in jl(GEN / "pool_adoption.jsonl")}
    strict = {a for a, r in pool.items() if r["strict_general"]}
    included = {a for a in strict if pool[a]["adopted"]}
    adoption = json.loads((GEN / "adoption.json").read_text(encoding="utf-8"))
    threads = {(t["framework"], t["kind"], t["number"]): t for t in jl(GEN / "github" / "threads.jsonl")}
    mentions = [m for m in jl(GEN / "github" / "mentions.jsonl") if m["tier"] in ("link", "title", "bare")]
    attempts = jl(OUT / "attempts_coded.jsonl")
    replies = {(r["framework"], r["number"]): r for r in jl(REPLIES)}

    prior_merger = build_prior_merger(jl(GEN / "github" / "merged_prs.jsonl"))

    # ---- funnel over the strict general denominator
    rec = defaultdict(list)
    for m in mentions:
        if m["arxiv"] in strict:
            rec[m["arxiv"]].append(m)
    att_by = defaultdict(list)
    for a in attempts:
        att_by[a["arxiv"]].append(a)
    stage = {}
    for a in strict:
        if a in included:
            stage[a] = "included"
        elif any(x["type"] == "pr" for x in att_by.get(a, [])):
            stage[a] = "implementation_pr"
        elif att_by.get(a):
            stage[a] = "request_only"
        elif rec.get(a):
            stage[a] = "cited_only"
        else:
            stage[a] = "no_record"
    funnel = Counter(stage.values())

    # ---- recall of the record: method-name matches of papers without a link, id or title match,
    # each judged by reading the thread (name_audit.jsonl); names shared or generic are not searchable
    from github_index import load_papers  # noqa: E402
    searchable = set(load_papers()[2].values())
    no_rec = {a for a, s in stage.items() if s == "no_record"}
    name_hits = {m["arxiv"] for m in jl(GEN / "github" / "mentions.jsonl") if m["tier"] == "name"} & no_rec
    judged = {r["arxiv"]: r for r in jl(OUT / "name_audit.jsonl")}
    if name_hits - set(judged):
        print(f"WARNING: {len(name_hits - set(judged))} name-only matches not yet judged in name_audit.jsonl: "
              f"{sorted(name_hits - set(judged))}")
    found = [judged[a] for a in sorted(name_hits & set(judged)) if judged[a]["refers"]]
    n_search = len(no_rec & searchable)
    name_audit = {"no_record": len(no_rec), "searchable": n_search, "candidates": len(name_hits),
                  "refers": len(found), "proposal_pr": sum(r["role"] == "pr" for r in found),
                  "request": sum(r["role"] == "request" for r in found),
                  "cited": sum(r["role"] == "cited" for r in found),
                  "no_record_after": len(no_rec) - len(found),
                  # the same rate applied to papers whose names cannot be searched
                  "no_record_extrapolated": round(len(no_rec) - len(found) * len(no_rec) / n_search) if n_search else None}

    # ---- proposal threads: outcomes, stated reasons, and who replied
    for a in attempts:
        r = replies.get((a["framework"], a["number"]), {"proposer": None, "replies": []})
        others = [x for x in r["replies"] if x["user"] != r["proposer"] and x["at"][:10] <= snapshot]
        a["any_human_reply"] = bool(others)
        a["prior_merger_reply"] = any(prior_merger(a["framework"], x["user"], x["at"]) for x in others)
    pr_outcomes = Counter(x["outcome"] for x in attempts if x["type"] == "pr")
    req_outcomes = Counter(x["outcome"] for x in attempts if x["type"] == "request")
    closed_reason = [x for x in attempts if x["reasons"] and not x["outcome"].startswith("open")]
    no_merger_reply = [x for x in attempts if x["outcome"] == "open_no_reply"]

    # ---- landings of recent methods and the pull requests behind them
    repo_of = {e["sha"][:10]: e["framework"] for e in jl(GEN / "framework_events.jsonl")}
    methods_src = {m["id"]: m["source"]["arxiv"]
                   for m in yaml.safe_load((ROOT / "data" / "methods.yaml").read_text(encoding="utf-8"))
                   if m.get("source", {}).get("arxiv")}
    cc = {}
    for f in ("cc_v1_filled.jsonl", "cc_v1_audit_added.jsonl"):
        for g in jl(GEN / "casecontrol" / f):
            cc[g["arxiv"]] = g
    landings = []
    for r in adoption:
        if not r["per_framework"] or (r["source_date"] or "") < "2025-01-01":
            continue
        first_fw = min(r["per_framework"].items(), key=lambda kv: kv[1]["first_date"])[0]
        src = methods_src.get(r["id"])
        for fw, v in r["per_framework"].items():
            if v["left_censored"]:
                continue
            repo_fw = repo_of.get(v["commit"], fw)
            n = v.get("pr")
            det = pr_detail(repo_fw, int(n)) if n else None
            row = {"method": r["id"], "framework": fw, "repo": repo_fw, "first_in_any": fw == first_fw,
                   "date": v["first_date"], "pr": n, "commit_author_relation": v["commit_author_is_paper_author"],
                   "tier": v["tier_first"], "n_frameworks_now": r["n_frameworks_at_head"],
                   "form": (cc.get(src) or {}).get("change_size")}
            prior = [m for m in mentions if src and m["arxiv"] == src and m["framework"] == repo_fw
                     and m["kind"] in ("issue", "discussion") and m["place"] == "opening" and m["date"] < v["first_date"]]
            row["prior_request"] = bool(prior)
            if det:
                p = det["pull"]
                revs = [x for x in det["reviews"] if x["user"] and not BOT.search(x["user"]) and x["user"] != p["user"]]
                row.update({
                    "pr_author": p["user"], "merged_by": p["merged_by"],
                    "author_prior_merger": prior_merger(repo_fw, p["user"], p["created_at"]),
                    "self_merged": p["merged_by"] == p["user"],
                    "human_reviewers": len({x["user"] for x in revs}),
                    "days_open": days(p["created_at"], p["merged_at"]) if p.get("merged_at") else None,
                    "core_lines": core_lines(repo_fw, det) if v["tier_first"] != "recipe" else None,
                    **footprint(det)})
            landings.append(row)
    with (OUT / "landings.jsonl").open("w", encoding="utf-8") as f:
        for r in landings:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    events = [r for r in landings if "pr_author" in r]
    prs: dict[tuple[str, int], dict] = {}
    for r in events:
        k = (r["repo"], int(r["pr"]))
        if k not in prs:
            prs[k] = {**r, "forms": set(), "methods": []}
        prs[k]["methods"].append(r["method"])
        if r["form"]:
            prs[k]["forms"].add(r["form"])
    pr_rows = list(prs.values())
    # code size by the form coded from the paper: one count per pull request and form
    by_form = defaultdict(list)
    for p in pr_rows:
        if p.get("core_lines") is not None:
            for form in p["forms"]:
                by_form[form].append(p["core_lines"])

    # unmerged implementation proposals
    att_fp = []
    for x in attempts:
        if x["type"] != "pr":
            continue
        det = pr_detail(x["framework"], x["number"])
        if det:
            p = det["pull"]
            end = (p.get("closed_at") or snapshot)[:10]
            att_fp.append({**x, **footprint(det), "core_lines": core_lines(x["framework"], det),
                           "age_days": days(p["created_at"], end), "is_open": p.get("state") == "open"})

    summary = {
        "n_strict": len(strict), "funnel": dict(sorted(funnel.items())), "name_audit": name_audit,
        "n_threads": len(threads),
        "attempt_threads": len(attempts), "attempt_papers": len(att_by),
        "attempt_prs": sum(x["type"] == "pr" for x in attempts),
        "attempt_requests": sum(x["type"] == "request" for x in attempts),
        "pr_outcomes": dict(sorted(pr_outcomes.items())), "request_outcomes": dict(sorted(req_outcomes.items())),
        "closed_with_reason": len(closed_reason),
        "reasons_closed": dict(sorted(Counter(r for x in closed_reason for r in x["reasons"]).items())),
        "reasons_all": dict(sorted(Counter(r for x in attempts for r in x["reasons"]).items())),
        "no_merger_reply": len(no_merger_reply),
        "no_merger_reply_any_human": sum(x["any_human_reply"] for x in no_merger_reply),
        "attempts_any_human_reply": sum(x["any_human_reply"] for x in attempts),
        # landings are method-framework events; pull request statistics count each pull request once
        "landings_exact": len(landings), "landing_events_with_pr": len(events),
        "landing_prior_request": sum(r["prior_request"] for r in events),
        "landing_author_paper": sum(r["commit_author_relation"] == "author" for r in events),
        "landing_prs": len(pr_rows),
        "pr_author_prior_merger": sum(p["author_prior_merger"] for p in pr_rows),
        "pr_self_merged": sum(p["self_merged"] for p in pr_rows),
        "pr_no_human_review": sum(p["human_reviewers"] == 0 for p in pr_rows),
        "pr_median_days_open": med([p["days_open"] for p in pr_rows]),
        "pr_tests": sum(p["tests"] for p in pr_rows),
        "pr_core_n": len([p for p in pr_rows if p.get("core_lines") is not None]),
        "pr_median_core_lines": med([p.get("core_lines") for p in pr_rows]),
        "core_lines_by_form": {k: {"n": len(v), "median": med(v)} for k, v in sorted(by_form.items())},
        "attempt_prs_with_detail": len(att_fp),
        "attempt_core_n": len([r for r in att_fp if r["framework"] != "verl_recipe"]),
        "attempt_median_core_lines": med([r["core_lines"] for r in att_fp if r["framework"] != "verl_recipe"]),
        "open_attempt_prs": sum(r["is_open"] for r in att_fp),
        "open_attempt_median_age": med([r["age_days"] for r in att_fp if r["is_open"]]),
        "open_attempt_over_180": sum(r["is_open"] and r["age_days"] > 180 for r in att_fp),
        "by_framework": {},
    }
    for fw in REPOS:
        if fw == "verl_recipe":
            continue
        ps = [p for p in pr_rows if p["framework"] == fw]
        xs = [x for x in attempts if x["framework"] in ((fw, "verl_recipe") if fw == "verl" else (fw,))]
        summary["by_framework"][fw] = {
            "landing_prs": len(ps),
            "author_prior_merger": sum(p["author_prior_merger"] for p in ps),
            "self_merged": sum(p["self_merged"] for p in ps),
            "median_days_open": med([p["days_open"] for p in ps]),
            "attempts": len(xs),
            "attempts_open": sum(x["outcome"].startswith("open") for x in xs),
            "attempts_declined": sum(x["outcome"] == "declined" for x in xs),
            "attempts_redirected": sum(x["outcome"] == "redirected" for x in xs),
            "attempts_stale": sum(x["outcome"] in ("stale_cleanup", "closed_inactive") for x in xs),
            "attempts_withdrawn": sum(x["outcome"] in ("withdrawn", "closed_no_comment") for x in xs),
        }
    summary["review"] = review_comparison(attempts, snapshot)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "by_framework"}, indent=1, ensure_ascii=False))
    for fw, v in summary["by_framework"].items():
        print(fw, v)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-facts", action="store_true")
    parser.add_argument("--snapshot", type=snapshot_date, default=SNAPSHOT,
                        help="analysis date; defaults to report v1, weekly runs must pass their collection date")
    args = parser.parse_args()
    if args.build_facts:
        build_facts()
    main(args.snapshot)
