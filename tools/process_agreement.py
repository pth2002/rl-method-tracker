"""Agreement between the first coding and an independent blind recoding.

  python tools/process_agreement.py

Proposal threads: the first coding (attempts_first_coding.jsonl) against the blind recoding
(attempts_recode.jsonl), as outcome agreement and agreement on each stated reason. The analysis
itself uses the blind codes, stored in attempts_coded.jsonl.
Full-text coding: the papers in casecontrol/blind_recode_papers.jsonl, recoded blind into
casecontrol/cc_v1_blind_recode.jsonl, against the first coding of the papers added by the citation
audit (cc_v1_audit_added_first_coding.jsonl) and against cc_v1_filled.jsonl for the controls, which
measures the recoder against the original reader.
Writes data/generated/process/agreement.md.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"
REASONS = ["demand", "surface", "placement", "evidence", "completeness", "design", "covered", "priority"]
FIELDS = ["affiliation_type", "code_released", "trained_14b_or_more", "trained_30b_or_more", "moe_policy",
          "change_size", "extra_model_required", "targets_failure", "eval_scope", "reports_compute"]


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def main() -> None:
    out = ["# Agreement with the blind recoding", ""]
    first = {f"{a['framework']}#{a['number']}": a for a in jl(GEN / "process" / "attempts_first_coding.jsonl")}
    second = {a["thread_id"]: a for a in jl(GEN / "process" / "attempts_recode.jsonl")}
    # agreement is reported on the threads the analysis uses
    analysed = {f"{a['framework']}#{a['number']}" for a in jl(GEN / "process" / "attempts_coded.jsonl")}
    both = [k for k in first if k in second and k in analysed]
    out += ["## Proposal threads", "", f"Threads recoded: {len(both)}/{len(first)}", ""]
    if both:
        same = sum(first[k]["outcome"] == second[k]["outcome"] for k in both)
        out.append(f"- Outcome: {same}/{len(both)} agree")
        for r in REASONS:
            agree = sum((r in first[k]["reasons"]) == (r in second[k].get("reasons", [])) for k in both)
            n1 = sum(r in first[k]["reasons"] for k in both)
            n2 = sum(r in second[k].get("reasons", []) for k in both)
            out.append(f"- Reason {r}: {agree}/{len(both)} agree (first {n1}, recode {n2})")
        diff = [k for k in both if first[k]["outcome"] != second[k]["outcome"]]
        if diff:
            out += ["", "Outcome disagreements:"]
            out += [f"- {k}: first {first[k]['outcome']}, recode {second[k]['outcome']}" for k in diff]

    # two blind rounds: the first seven added papers with 13 controls, then two more with three controls
    rec = {g["arxiv"]: g for f in ("cc_v1_blind_recode.jsonl", "cc_v1_blind_recode2.jsonl")
           for g in jl(GEN / "casecontrol" / f)}
    keys = [json.loads(p.read_text(encoding="utf-8")) for p in
            (ROOT / "data" / "release" / "blind_recode_key.json", ROOT / "data" / "release" / "blind_recode2_key.json")
            if p.exists()]
    if keys:
        key = {"added": [a for k in keys for a in k["added"]], "controls": [a for k in keys for a in k["controls"]]}
        added = {g["arxiv"]: g for g in jl(GEN / "casecontrol" / "cc_v1_audit_added_first_coding.jsonl")}
        orig = {g["arxiv"]: g for g in jl(GEN / "casecontrol" / "cc_v1_filled.jsonl")}
        for name, ids, ref in (("Papers added by the citation audit", key["added"], added),
                               ("Controls (recoder against the original reader)", key["controls"], orig)):
            ids = [a for a in ids if a in rec and a in ref]
            out += ["", f"## {name}", "", f"Papers recoded: {len(ids)}", ""]
            for fld in FIELDS:
                agree = sum(rec[a].get(fld) == ref[a].get(fld) for a in ids)
                out.append(f"- {fld}: {agree}/{len(ids)} agree")
    (GEN / "process" / "agreement.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
