"""Write docs/data.js, the data behind the project page in docs/.

  python tools/site_data.py   ->  docs/data.js

The page reads one script so it works from GitHub Pages and from a local file alike. Everything
comes from data/generated and data/*.yaml; tools/update.py calls this after each refresh, so the
weekly pull request carries the page's data with the rest of the tracker.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"
REPO = "https://github.com/pth2002/rl-method-tracker"

FRAMEWORKS = [("verl", "verl"), ("trl", "TRL"), ("openrlhf", "OpenRLHF"), ("nemo-rl", "NeMo-RL"),
              ("roll", "ROLL"), ("slime", "slime"), ("areal", "AReaL")]
TIER_RANK = {"default": 6, "conditional_default": 5, "core": 4, "option": 3, "experimental": 2, "recipe": 1}


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


PAGE = "https://pth2002.github.io/rl-method-tracker/"
README_START, README_END = "<!-- failures:start -->", "<!-- failures:end -->"


def write_readme_table(groups: list[dict], methods: dict) -> None:
    """Rewrite the README table of training failures between its two markers."""
    rows = ["| Training failure | Methods | Most widely included |", "|---|--:|---|"]
    for g in groups:
        # the row already names the failure, so a name that repeats it drops that part
        top = [methods[m]["name"].split(" (")[0].removesuffix(" for rollout-training mismatch")
               for m in g["methods"][:3]]
        rows.append(f"| [{g['name']}]({PAGE}#failure-{g['id']}) | {len(g['methods'])} | {', '.join(top)} |")
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    if README_START not in text or README_END not in text:
        return
    head, rest = text.split(README_START, 1)
    tail = rest.split(README_END, 1)[1]
    new = head + README_START + "\n" + "\n".join(rows) + "\n" + README_END + tail
    if new != text:
        readme.write_text(new, encoding="utf-8", newline="\n")


def main() -> None:
    pool = jl(GEN / "pool_adoption.jsonl")
    titles = {r["arxiv"]: " ".join(r["title"].split()) for r in jl(GEN / "arxiv_frame.jsonl")}
    adoption = json.loads((GEN / "adoption.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in adoption}
    links = json.loads((GEN / "impl_links.json").read_text(encoding="utf-8"))
    head = json.loads((GEN / "framework_head.json").read_text(encoding="utf-8"))
    profiles = json.loads((GEN / "framework_profiles.json").read_text(encoding="utf-8"))["frameworks"]
    process = json.loads((GEN / "process" / "summary.json").read_text(encoding="utf-8"))["by_framework"]
    symptoms = yaml.safe_load((ROOT / "data" / "symptoms.yaml").read_text(encoding="utf-8"))
    quarterly = json.loads((GEN / "quarterly.json").read_text(encoding="utf-8"))
    label = dict(FRAMEWORKS)

    # every general method paper, in order of its arXiv identifier: [arxiv, month, title, included,
    # frameworks at the snapshot, method names, [framework, date] of removals from frameworks it left]
    order = [k for k, _ in FRAMEWORKS]
    gone = {}
    for fw, prof in profiles.items():
        for x in prof["removed"]:
            gone.setdefault(x["method"], []).append((fw, x["date"]))
    gen = sorted((r for r in pool if r["strict_general"]), key=lambda r: r["arxiv"])
    papers = []
    for r in gen:
        ms = [m for m in r["methods"] if m in by_id]
        now = sorted({f for m in ms for f in by_id[m]["frameworks_at_head"]}, key=order.index)
        left = sorted({(f, d) for m in ms for f, d in gone.get(m, []) if f not in now}, key=lambda x: order.index(x[0]))
        names = [by_id[m]["name"].split(" (")[0] for m in ms]
        papers.append([r["arxiv"], r["month"], titles.get(r["arxiv"], ""), int(bool(r["adopted"])),
                       [label[f] for f in now], names, [[label[f], d] for f, d in left]])

    # methods with the setting that selects them in each framework, and removals
    removed = {(x["method"], fw): x["date"] for fw, p in profiles.items() for x in p["removed"]}
    methods = {}
    for r in adoption:
        cells = {}
        for fw, _ in FRAMEWORKS:
            tier = r["frameworks_at_head"].get(fw)
            if tier:
                imp = sorted(links.get(r["id"], {}).get(fw, []), key=lambda x: -TIER_RANK.get(x["tier"], 0))
                first = imp[0] if imp else {}
                cells[fw] = {"tier": tier, "setting": first.get("setting") or first.get("token"),
                             "url": first.get("url")}
            elif (r["id"], fw) in removed:
                cells[fw] = {"tier": "removed", "date": removed[(r["id"], fw)]}
        if not cells:
            continue
        src = f"https://arxiv.org/abs/{r['arxiv']}" if r.get("arxiv") else None
        methods[r["id"]] = {"name": r["name"], "arxiv": r.get("arxiv"), "src": src,
                            "date": r["source_date"], "n": r["n_frameworks_at_head"], "cells": cells}

    groups = []
    for s in symptoms:
        ids = [m for m in methods if s["id"] in (by_id[m]["symptoms"] or [])]
        ids.sort(key=lambda m: (-methods[m]["n"], methods[m]["date"] or ""))
        if ids:
            groups.append({"id": s["id"], "name": s["name"], "observe": s["observe"], "methods": ids})
    rest = [m for m in methods if not by_id[m]["symptoms"]]
    rest.sort(key=lambda m: (-methods[m]["n"], methods[m]["date"] or ""))
    groups.append({"id": "baselines", "name": "Baselines and general components",
                   "observe": "Algorithms and components that are not tied to one failure, such as GRPO and PPO.",
                   "methods": rest})

    # the most recent landings, newest first
    # adoption.json files verl-recipe landings under verl, so their commits are matched to the recipe history
    recipe = {e["sha"][:10] for e in jl(GEN / "framework_events.jsonl") if e["framework"] == "verl_recipe"}
    landings = []
    for r in adoption:
        for fw, v in r["per_framework"].items():
            if v["left_censored"]:
                continue
            in_recipe = fw == "verl" and (v.get("commit") or "")[:10] in recipe
            repo = head["verl_recipe" if in_recipe else fw]["url"]
            url = f"{repo}/pull/{v['pr']}" if v.get("pr") else f"{repo}/commit/{v['commit']}"
            landings.append({"date": v["first_date"], "method": r["name"].split(" (")[0],
                             "fw": "verl recipes" if in_recipe else label[fw], "days": v["lag_days"], "url": url})
    landings.sort(key=lambda x: x["date"], reverse=True)

    ledger = []
    for fw, name in FRAMEWORKS:
        p, q = profiles[fw], process.get(fw, {})
        ledger.append({"fw": name, "anchor": name.lower().replace(" ", "-"), "url": head[fw]["url"],
                       "methods": p["methods_ever"], "first": p["first_anywhere"],
                       "median": None if p["median_lag"] is None else round(p["median_lag"]),
                       "prs": q.get("landing_prs", 0), "by_merger": q.get("author_prior_merger", 0),
                       "days_open": q.get("median_days_open"),
                       "proposals": q.get("attempts", 0), "open": q.get("attempts_open", 0),
                       "declined": q.get("attempts_declined", 0) + q.get("attempts_redirected", 0),
                       "lapsed": q.get("attempts_stale", 0)})
    ledger.sort(key=lambda x: (-x["methods"], -x["first"]))

    snaps = [(label[f], head[f]["head_sha"][:7], head[f]["head_date"]) for f, _ in FRAMEWORKS]
    snaps.insert(1, ("verl recipes", head["verl_recipe"]["head_sha"][:7], head["verl_recipe"]["head_date"]))
    data = {
        "repo": REPO,
        "snapshot": max(d for _, _, d in snaps),
        "snapshots": snaps,
        "frameworks": [name for _, name in FRAMEWORKS],
        "frameworkKeys": [k for k, _ in FRAMEWORKS],
        "counts": {"pool": len(pool), "general": len(gen), "included": sum(p[3] for p in papers),
                   "removed": sum(1 for p in papers if p[3] and not p[4]), "months": len({p[1] for p in papers})},
        "papers": papers,
        "methods": methods,
        "groups": groups,
        "landings": landings[:10],
        "ledger": ledger,
        "quarterly": quarterly,
    }
    write_readme_table(groups, methods)
    out = ROOT / "docs" / "data.js"
    out.parent.mkdir(exist_ok=True)
    out.write_text("window.TRACKER = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
                   encoding="utf-8", newline="\n")
    print(f"wrote {out.relative_to(ROOT)}: {len(papers)} papers, {len(methods)} methods, "
          f"{len(groups)} failure groups, {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
