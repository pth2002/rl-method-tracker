"""Join the labelled candidate pool with framework inclusion and count inclusion rates.

Unit: one arXiv paper. A paper is *included* when at least one catalog method sourced from it
reached the main branch of a tracked framework.

Main denominator: papers labelled rl_method with scope general from the abstract, the same
eligibility rule used to draw case-control controls. Included papers outside that rule (mostly
model reports whose component sits in the body) are listed and reported as a separate line,
never mixed into the main rate.

Writes data/generated/adoption_rate.md and data/generated/pool_adoption.jsonl.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").split(chr(10)) if l.strip()]


def paper_summary(adoption: list[dict], frame: dict) -> dict[str, dict]:
    """Per arXiv source: union of frameworks over its methods, defaults, commit-author relations."""
    out: dict[str, dict] = {}
    for r in adoption:
        a = r.get("arxiv")
        if not a or a not in frame:
            continue
        d = out.setdefault(a, {"methods": [], "fw_ever": set(), "fw_head": set(), "default": False,
                               "conditional_default": False, "relations": set()})
        d["methods"].append(r["id"])
        d["fw_ever"] |= set(r["per_framework"])
        d["fw_head"] |= set(r["frameworks_at_head"])
        d["default"] |= r["n_default_at_head"] > 0
        d["conditional_default"] |= r.get("n_conditional_default_at_head", 0) > 0
        d["relations"] |= {v["commit_author_is_paper_author"] for v in r["per_framework"].values()}
    return out


def main() -> None:
    labels = {g["arxiv"]: g for g in read_jsonl(GEN / "triage" / "labels.jsonl")}
    adoption = json.loads((GEN / "adoption.json").read_text(encoding="utf-8"))
    frame = {r["arxiv"]: r for r in read_jsonl(GEN / "arxiv_frame.jsonl")}
    by_paper = paper_summary(adoption, frame)

    rows = []
    for a, g in labels.items():
        if a not in frame:
            continue
        ad = by_paper.get(a)
        rel = ad["relations"] if ad else set()
        rows.append({
            "arxiv": a, "month": frame[a]["month"], "label": g["label"], "scope": g.get("scope"),
            "component": g.get("component"), "confidence": g["confidence"],
            "is_model_report": g.get("is_model_report", False),
            "strict_general": g["label"] == "rl_method" and g.get("scope") == "general",
            "adopted": ad is not None, "methods": ad["methods"] if ad else [],
            "n_fw_ever": len(ad["fw_ever"]) if ad else 0, "n_fw_head": len(ad["fw_head"]) if ad else 0,
            "default": bool(ad and ad["default"]), "conditional_default": bool(ad and ad["conditional_default"]),
            # at least one landing whose commit author is a named person outside the author list
            "independent": "not_author" in rel,
            "only_unknown_or_no_paper": bool(rel) and rel <= {"unknown", "no_paper"},
        })
    with (GEN / "pool_adoption.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    strict = [r for r in rows if r["strict_general"]]
    exceptions = [r for r in rows if r["adopted"] and not r["strict_general"]]

    def line(name: str, den: list[dict]) -> str:
        return (f"| {name} | {len(den)} | {sum(r['adopted'] for r in den)} | {sum(r['independent'] for r in den)} | "
                f"{sum(r['n_fw_head'] >= 3 for r in den)} | {sum(r['default'] for r in den)} | "
                f"{sum(r['conditional_default'] and not r['default'] for r in den)} |")

    out = ["# Framework inclusion rate", "",
           f"Pool: {len(rows)} labelled arXiv papers (cs.LG, cs.CL, cs.AI; ids 2501 to 2606) that mention language "
           "models and RL. A paper is included when a method sourced from it reached a tracked main branch.", "",
           "| Denominator | Papers | Included | With a named non-author commit | In ≥3 frameworks now | "
           "Unconditional default | Conditional default only |", "|---|---|---|---|---|---|---|",
           line("general methods (main)", strict),
           line("general methods plus included exceptions", strict + exceptions), "",
           "Included papers outside the general rule:", ""]
    for r in exceptions:
        out.append(f"- {r['arxiv']} ({r['label']}, scope {r['scope']}, model report {r['is_model_report']}): "
                   f"{', '.join(r['methods'])}")

    out += ["", "## By component (general methods)", "",
            "| Component | Papers | Included | In ≥3 frameworks now |", "|---|---|---|---|"]
    comp = defaultdict(list)
    for r in strict:
        comp[r["component"] or "(none)"].append(r)
    for c, rs in sorted(comp.items(), key=lambda kv: -len(kv[1])):
        out.append(f"| {c} | {len(rs)} | {sum(r['adopted'] for r in rs)} | {sum(r['n_fw_head'] >= 3 for r in rs)} |")

    out += ["", "## Per month (general methods)", "", "| Month | Papers | Included |", "|---|---|---|"]
    pm = defaultdict(lambda: [0, 0])
    for r in strict:
        pm[r["month"]][0] += 1
        pm[r["month"]][1] += r["adopted"]
    for mth in sorted(pm):
        out.append(f"| {mth} | {pm[mth][0]} | {pm[mth][1]} |")
    (GEN / "adoption_rate.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:8] + out[8:9 + len(exceptions)]))


if __name__ == "__main__":
    main()
