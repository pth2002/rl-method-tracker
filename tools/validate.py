"""Consistency checks for the curated files. Exits non-zero on any problem (used as a CI gate).

Checks: unique ids, every mapped method exists, every symptom exists, no unmapped framework
tokens, every non-review method has a resolved source.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    methods = yaml.safe_load((ROOT / "data" / "methods.yaml").read_text(encoding="utf-8"))
    symptoms = yaml.safe_load((ROOT / "data" / "symptoms.yaml").read_text(encoding="utf-8"))
    tmap = yaml.safe_load((ROOT / "config" / "token_map.yaml").read_text(encoding="utf-8"))
    problems: list[str] = []

    ids = [m["id"] for m in methods]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        problems.append(f"duplicate method ids: {dup}")
    mids, sids = set(ids), {s["id"] for s in symptoms}

    for m in methods:
        for s in m.get("symptoms") or []:
            if s not in sids:
                problems.append(f"{m['id']}: unknown symptom {s}")

    def check(value, where):
        vals = value if isinstance(value, list) else [value]
        for v in vals:
            if not isinstance(v, str):
                problems.append(f"{where}: bad value {v!r}")
            elif not v.startswith("~") and v not in mids:
                problems.append(f"{where}: unknown method {v}")

    for fw, surfaces in tmap.items():
        if fw == "_defaults":
            for dfw, toks in surfaces.items():
                for tok, vals in toks.items():
                    for val, m in vals.items():
                        check(m["method"] if isinstance(m, dict) else m, f"_defaults/{dfw}/{tok}={val}")
            continue
        for sid, toks in surfaces.items():
            for tok, v in (toks or {}).items():
                check(v, f"{fw}/{sid}/{tok}")

    unmapped = ROOT / "data" / "generated" / "unmapped.json"
    if unmapped.exists():
        u = json.loads(unmapped.read_text(encoding="utf-8")).get("tokens", {})
        for fw, surfaces in u.items():
            for sid, toks in surfaces.items():
                problems.append(f"unmapped tokens in {fw}/{sid}: {toks}")

    papers = ROOT / "data" / "generated" / "papers.json"
    if papers.exists():
        resolved = json.loads(papers.read_text(encoding="utf-8"))["methods"]
        for m in methods:
            r = resolved.get(m["id"])
            if r is None:
                problems.append(f"{m['id']}: not in papers.json (run collectors/papers.py)")
            elif not m.get("review") and r["status"] not in ("ok", "ok_by_title", "non_arxiv"):
                problems.append(f"{m['id']}: source {r['status']} but not marked review")

    for p in problems:
        print("PROBLEM", p)
    print(f"{len(problems)} problems; {len(methods)} methods, {len(symptoms)} symptoms")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
