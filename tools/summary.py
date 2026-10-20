"""Build the per-method adoption table and the symptom index from the collected data.

Inputs:  data/generated/framework_events.jsonl, framework_head.json, papers.json,
         data/methods.yaml, data/symptoms.yaml, config/token_map.yaml
Outputs: data/generated/adoption.json, data/generated/adoption.csv, INDEX.md
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"
# conditional_default: the default value turns the method on only when another feature is enabled
TIER_RANK = {"default": 6, "conditional_default": 5, "core": 4, "option": 3, "experimental": 2, "recipe": 1}


def default_entry(defaults_map: dict, fw: str, token: str, value: str) -> tuple[str | None, str | None]:
    """Method id and condition for a default value; entries are an id or {method, condition}."""
    v = defaults_map.get(fw, {}).get(token, {}).get(value)
    if isinstance(v, dict):
        return v.get("method"), v.get("condition")
    return v, None
FRAMEWORK_LABEL = {"verl": "verl", "verl_recipe": "verl", "trl": "TRL", "openrlhf": "OpenRLHF",
                   "nemo-rl": "NeMo-RL", "roll": "ROLL", "slime": "slime", "areal": "AReaL"}


def load():
    events = [json.loads(l) for l in (GEN / "framework_events.jsonl").read_text(encoding="utf-8").split(chr(10)) if l]
    head = json.loads((GEN / "framework_head.json").read_text(encoding="utf-8"))
    papers = json.loads((GEN / "papers.json").read_text(encoding="utf-8"))["methods"]
    methods = yaml.safe_load((ROOT / "data" / "methods.yaml").read_text(encoding="utf-8"))
    symptoms = yaml.safe_load((ROOT / "data" / "symptoms.yaml").read_text(encoding="utf-8"))
    tmap = yaml.safe_load((ROOT / "config" / "token_map.yaml").read_text(encoding="utf-8"))
    return events, head, papers, methods, symptoms, tmap


# ---- commit author vs paper authors ----
def _tokens(name: str) -> set[str]:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.replace("-", "")
    return {t for t in re.split(r"[^a-z]+", name.lower()) if len(t) > 1}


def author_relation(commit_name: str, paper_authors: list[str]) -> str:
    """'author' when the commit author is one of the paper's authors, 'not_author' when the commit author
    has a full real name that matches none, 'unknown' for handles or non-Latin names.
    Commit emails are not collected, so a handle never resolves to an author."""
    if not paper_authors:
        return "no_paper"
    ct = _tokens(commit_name)
    for a in paper_authors:
        at = _tokens(a)
        if len(at) >= 2 and len(ct) >= 2 and (at <= ct or ct <= at):
            return "author"
    looks_like_name = len(ct) >= 2 and not re.search(r"\d", commit_name)
    return "not_author" if looks_like_name else "unknown"


def days_between(a: str | None, b: str | None) -> int | None:
    if not a or not b or len(a) < 10 or len(b) < 10:  # month-only dates give no day count
        return None
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def main() -> None:
    events, head, papers, methods, symptoms, tmap = load()
    mids = {m["id"] for m in methods}
    defaults_map = tmap.get("_defaults", {})

    # tokens present at HEAD -> methods, per framework
    head_methods: dict[str, dict[str, str]] = defaultdict(dict)  # method -> fw -> best tier
    surface_tier = {(e["framework"], e["surface"]): e["tier"] for e in events}
    for fw, info in head.items():
        for sid, toks in info["surfaces"].items():
            tier = surface_tier.get((fw, sid))
            if tier == "default":
                for tv in toks:
                    tok, _, val = tv.partition("=")
                    m, cond = default_entry(defaults_map, fw, tok, val)
                    if m:
                        t = "conditional_default" if cond else "default"
                        cur = head_methods[m].get(fw)
                        if cur is None or TIER_RANK[t] > TIER_RANK[cur]:
                            head_methods[m][fw] = t
                continue
            smap = tmap.get(fw, {}).get(sid, {})
            for tok in toks:
                mapped = smap.get(tok)
                if not mapped or (isinstance(mapped, str) and mapped.startswith("~")):
                    continue
                for m in (mapped if isinstance(mapped, list) else [mapped]):
                    cur = head_methods[m].get(fw)
                    if cur is None or TIER_RANK[tier] > TIER_RANK[cur]:
                        head_methods[m][fw] = tier

    # first appearance per method x framework; verl_recipe folds into verl
    first: dict[str, dict[str, dict]] = defaultdict(dict)
    default_since: dict[str, dict[str, str]] = defaultdict(dict)
    for e in sorted(events, key=lambda e: e["date"]):
        fw = "verl" if e["framework"] == "verl_recipe" else e["framework"]
        if e["event"] == "default_changed":
            m, cond = default_entry(defaults_map, e["framework"], e["token"], str(e["value"]))
            if m and fw not in default_since[m]:
                default_since[m][fw] = e["date"]
                # Becoming a default counts as landing, if the method had no earlier event here.
                if fw not in first[m]:
                    first[m][fw] = {**e, "tier": "conditional_default" if cond else "default",
                                    "left_censored": False}
            continue
        if e["event"] != "added":
            continue
        for m in e.get("methods") or []:
            if fw not in first[m]:
                first[m][fw] = e

    rows = []
    for m in methods:
        mid = m["id"]
        p = papers.get(mid, {})
        pdate = p.get("date")
        per_fw = {}
        for fw, e in first.get(mid, {}).items():
            rel = author_relation(e["author"], p.get("authors", []))
            per_fw[fw] = {
                "first_date": e["date"], "left_censored": e["left_censored"],
                "censor_reason": e.get("censor_reason"), "tier_first": e["tier"],
                "token": e["token"], "commit": e["sha"][:10], "pr": e["pr"], "subject": e["subject"],
                # git author of the commit that introduced the option (not the person who merged it)
                "commit_author": e["author"], "commit_author_is_paper_author": rel,
                "lag_days": days_between(pdate, e["date"]),
                "at_head": head_methods.get(mid, {}).get(fw),
                "default_since": default_since.get(mid, {}).get(fw),
            }
        hm = head_methods.get(mid, {})
        hm_fw: dict[str, str] = {}
        for f, t in hm.items():
            f = "verl" if f == "verl_recipe" else f
            if f not in hm_fw or TIER_RANK[t] > TIER_RANK[hm_fw[f]]:
                hm_fw[f] = t
        # The first landing across frameworks bounds the lag. If that landing is censored, the true
        # lag is at most the measured one, and it never gets replaced by a later exact landing.
        earliest = min(per_fw.values(), key=lambda v: v["first_date"], default=None)
        first_lag = earliest["lag_days"] if earliest else None
        first_lag_upper = bool(earliest and earliest["left_censored"])
        rows.append({
            "id": mid, "name": m["name"], "family": m["family"], "symptoms": m.get("symptoms", []),
            "source_status": p.get("status"), "arxiv": p.get("arxiv"), "source_title": p.get("title"),
            "source_date": pdate, "review": bool(m.get("review")),
            "frameworks_ever": sorted(per_fw), "n_frameworks_ever": len(per_fw),
            "frameworks_at_head": hm_fw, "n_frameworks_at_head": len(hm_fw),
            "n_default_at_head": sum(t == "default" for t in hm_fw.values()),
            "n_conditional_default_at_head": sum(t == "conditional_default" for t in hm_fw.values()),
            "first_adoption_date": earliest["first_date"] if earliest else None,
            "first_lag_days": first_lag,
            "first_lag_is_upper_bound": first_lag_upper,
            "n_self_contributed": sum(v["commit_author_is_paper_author"] == "author" for v in per_fw.values()),
            "per_framework": per_fw,
        })

    bad = sorted({mm for e in events for mm in (e.get("methods") or [])} - mids)
    if bad:
        raise SystemExit(f"token_map refers to unknown method ids: {bad}")

    (GEN / "adoption.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    fws = ["verl", "trl", "openrlhf", "nemo-rl", "roll", "slime", "areal"]
    with (GEN / "adoption.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "family", "source_date", "n_fw_ever", "n_fw_head", "n_default", "first_adoption",
                    "first_lag_days", "first_lag_is_upper_bound", "n_self_contributed"] + [f"{x}_first" for x in fws] + [f"{x}_head" for x in fws])
        for r in rows:
            w.writerow([r["id"], r["family"], r["source_date"], r["n_frameworks_ever"], r["n_frameworks_at_head"],
                        r["n_default_at_head"], r["first_adoption_date"], r["first_lag_days"], r["first_lag_is_upper_bound"], r["n_self_contributed"]]
                       + [(r["per_framework"].get(x) or {}).get("first_date", "") for x in fws]
                       + [r["frameworks_at_head"].get(x, "") for x in fws])
    write_index(rows, symptoms, head)
    print(f"{len(rows)} methods; in >=1 framework now: {sum(r['n_frameworks_at_head'] > 0 for r in rows)}; "
          f"default somewhere: {sum(r['n_default_at_head'] > 0 for r in rows)}")


def write_index(rows: list[dict], symptoms: list[dict], head: dict) -> None:
    lp = ROOT / "data" / "generated" / "impl_links.json"
    links = json.loads(lp.read_text(encoding="utf-8")) if lp.exists() else {}
    mark = {"default": "**default**", "conditional_default": "default when enabled", "core": "core",
            "option": "option", "experimental": "exp.", "recipe": "recipe"}
    snap = ", ".join(f"{FRAMEWORK_LABEL[f]} `{v['head_sha'][:7]}` ({v['head_date']})"
                     for f, v in head.items() if f != "verl_recipe")
    lines = [
        "# RL post-training methods by symptom",
        "",
        "Which fixes for a given training failure the major open-source frameworks include, and in what form.",
        "Inclusion means an implementation on a main branch. It does not measure how often users enable a method,",
        "and the index lists the failure each source paper says it addresses without testing whether the method helps.",
        "Each framework entry links to the file and line at the snapshot commit and names the setting that selects it.",
        "To propose a method to a framework, see `FRAMEWORKS.md` for its contribution rules and earlier proposals.",
        "To report a wrong mapping, a missed implementation or a wrong date, open an issue with the correction template.",
        "Generated by `tools/summary.py`. Do not edit by hand.",
        "",
        f"Snapshot: {snap}.",
        "",
        "Tier at HEAD: **default** (on in a default run) > default when enabled (on by default once a related feature"
        " is switched on) > core (a selectable algorithm) > option (a switch) >"
        " exp. (experimental folder) > recipe (example directory).",
        "Lag is days from the source's first public version to the first commit on a framework's main branch."
        " `≤` marks upper bounds: the option first appeared in a root commit, a bulk release or a renaming commit.",
        "",
    ]
    by_sym = defaultdict(list)
    for r in rows:
        for s in r["symptoms"] or ["(general)"]:
            by_sym[s].append(r)
    order = [s["id"] for s in symptoms] + ["(general)"]
    names = {s["id"]: s for s in symptoms}
    title = {sid: names[sid]["name"] if sid in names else "Baselines and general components" for sid in order}
    anchor = {sid: re.sub(r"[^\w\- ]", "", t.lower()).replace(" ", "-") for sid, t in title.items()}
    lines += ["Failures: " + " · ".join(f"[{title[sid]}](#{anchor[sid]})" for sid in order if sid in by_sym), ""]
    for sid in order:
        if sid not in by_sym:
            continue
        s = names.get(sid)
        lines += [f"## {s['name'] if s else 'Baselines and general components'}", ""]
        if s:
            lines += [f"*What you see:* {s['observe']}", ""]
        lines += ["| Method | Source | Frameworks shipping it now | First landed (lag) |", "|---|---|---|---|"]
        for r in sorted(by_sym[sid], key=lambda r: (-r["n_default_at_head"], -r["n_frameworks_at_head"], r["id"])):
            src = (f"[{r['arxiv']}](https://arxiv.org/abs/{r['arxiv']})" if r["arxiv"]
                   else (r["source_title"] or "unresolved"))
            if r["source_date"]:
                src += f" ({r['source_date']})"
            def shown(f: str, t: str) -> str:
                hits = links.get(r["id"], {}).get(f) or []
                hit = next((h for h in hits if h["tier"] == t), hits[0] if hits else None)
                text = f"{FRAMEWORK_LABEL[f]} {mark[t]}"
                if not hit:
                    return text
                setting = f" `{hit['setting']}`" if hit.get("setting") else ""
                return f"[{text}]({hit['url']}){setting}"
            now = ", ".join(shown(f, t) for f, t in
                            sorted(r["frameworks_at_head"].items(), key=lambda kv: -TIER_RANK[kv[1]]))
            if not now:
                was = ", ".join(f"{FRAMEWORK_LABEL[f]} {mark[v['tier_first']]}"
                                for f, v in sorted(r["per_framework"].items()))
                now = f"none (removed; was {was})" if was else "none"
            firsts = sorted(r["per_framework"].items(), key=lambda kv: kv[1]["first_date"])
            landed = ""
            if firsts:
                fw, v = firsts[0]
                lag = "" if v["lag_days"] is None else f", {'≤' if v['left_censored'] else ''}{v['lag_days']:+d} d"
                landed = f"{'≤' if v['left_censored'] else ''}{v['first_date']} {FRAMEWORK_LABEL[fw]}{lag}"
            flag = " ⚑" if r["review"] else ""
            lines.append(f"| {r['name']}{flag} | {src} | {now} | {landed} |")
        lines.append("")
    lines += ["⚑ source attribution awaiting review.", ""]
    (ROOT / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
