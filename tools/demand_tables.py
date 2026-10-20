"""Two complements to the inclusion record: the training failures that users report in the frameworks'
issues, and the methods that technical reports of large open-weight models state they used.

Both read coded files under data/generated and are called from tools/paper_numbers.py, which writes
their counts as LaTeX macros and their tables as paper/table_demand.tex and paper/table_reports.tex.

  data/generated/process/issue_failures.jsonl      threads screened by keyword and coded by a reader
  data/generated/process/issue_recall_sample.jsonl  random unscreened threads read the same way
  data/generated/casecontrol/model_reports.jsonl   RL sections of model reports, one row per report
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"

# codes a reader can assign to a screened thread; the first group are failures of the catalog's
# symptom list, the second are failures the catalog does not name, the rest are not failure reports
SYMPTOM_CODES = ["train_infer_mismatch", "length_bias", "stale_policy", "moe_instability",
                 "zero_gradient_groups", "entropy_collapse", "sparse_reward", "diversity_loss",
                 "high_variance", "critic_cost", "multi_reward_collapse", "truncation_noise", "ratio_outliers"]
OTHER_FAILURE_CODES = {"instability": "Collapse or divergence, cause not named", "kl_drift": "KL penalty grows"}
NON_FAILURE = {"bug", "question", "other", "request"}

SYMPTOM_NAME = {"critic_cost": "Value-model cost", "high_variance": "Gradient variance",
                "entropy_collapse": "Entropy collapse", "length_bias": "Response-length drift",
                "zero_gradient_groups": "Groups without signal", "truncation_noise": "Truncation noise",
                "train_infer_mismatch": "Rollout-training mismatch", "moe_instability": "MoE instability",
                "ratio_outliers": "Extreme importance ratios", "stale_policy": "Stale rollout data",
                "multi_reward_collapse": "Multi-reward collapse", "diversity_loss": "Loss of diversity",
                "sparse_reward": "Sparse reward"}

# how a request note names the method it asks for, and the display name it maps to
REQUEST_GROUPS = [("dynamic sampling", "dynamic sampling"), ("DAPO", "dynamic sampling"),
                  ("routing replay", "rollout routing replay"), ("R3", "rollout routing replay"),
                  ("TIS", "TIS or MIS"), ("MIS", "TIS or MIS"), ("IcePop", "TIS or MIS"),
                  ("off-policy correction", "TIS or MIS"), ("rejection sampling", "TIS or MIS")]


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").split(chr(10)) if l.strip()]


def tex(s: str) -> str:
    return s.replace("&", r"\&").replace("_", r"\_").replace("%", r"\%")


def issue_numbers() -> dict:
    """Counts of failure reports and method requests in the frameworks' issues and discussions."""
    coded = read_jsonl(GEN / "process" / "issue_failures.jsonl")
    recall = read_jsonl(GEN / "process" / "issue_recall_sample.jsonl")
    if not coded:
        return {}
    threads = read_jsonl(GEN / "github" / "threads.jsonl")
    universe = [t for t in threads if t["kind"] in ("issue", "discussion") and t["created"] >= "2025-01-01"]
    pool = read_jsonl(GEN / "pool_adoption.jsonl")
    labels = {r["arxiv"]: r for r in read_jsonl(GEN / "triage" / "labels.jsonl")}
    methods = yaml.safe_load((ROOT / "data" / "methods.yaml").read_text(encoding="utf-8"))
    adoption = {r["id"]: r for r in json.loads((GEN / "adoption.json").read_text(encoding="utf-8"))}

    codes = Counter(r["code"] for r in coded)
    failures = [r for r in coded if r["code"] not in NON_FAILURE]
    requests = [r for r in coded if r["code"] == "request"]
    out = {"NIssueUniverse": len(universe), "NIssueScreened": len(coded), "NIssueFailure": len(failures),
           "NIssueRequest": len(requests), "NIssueBug": codes["bug"], "NIssueQuestion": codes["question"],
           "NIssueOther": codes["other"], "NIssueRecall": len(recall),
           "NIssueRecallHit": sum(r["code"] not in ("none", "borderline", "no_progress") for r in recall),
           "NIssueRecallBorder": sum(r["code"] == "borderline" for r in recall),
           "NIssueRecallNoProgress": sum(r["code"] == "no_progress" for r in recall)}
    fw = Counter(r["framework"].replace("verl_recipe", "verl") for r in failures)
    out["NIssueFailureVerl"] = fw["verl"]
    out["NIssueFailureTRL"] = fw["trl"]
    out["NIssueFailureNeMo"] = fw["nemo-rl"]
    out["NIssueFrameworksWithFailure"] = len(fw)
    for code in list(SYMPTOM_CODES) + list(OTHER_FAILURE_CODES):
        key = "".join(w.capitalize() for w in code.split("_"))
        out[f"NIssue{key}"] = codes[code]

    # what the requests ask for
    req_groups = Counter()
    for r in requests:
        note = r.get("note") or ""
        for needle, group in REQUEST_GROUPS:
            if needle in note:
                req_groups[group] += 1
                break
    out["NReqDynamicSampling"] = req_groups["dynamic sampling"]
    out["NReqRoutingReplay"] = req_groups["rollout routing replay"]
    out["NReqMismatch"] = req_groups["TIS or MIS"]
    out["NReqNamed"] = sum(1 for r in requests if "method request" in (r.get("note") or "")
                           or "request:" in (r.get("note") or ""))

    # supply side: general methods whose abstract names the same failure, and the catalog methods
    gen = [r for r in pool if r["strict_general"]]
    supply = Counter()
    supply_inc = Counter()
    for r in gen:
        for s in labels.get(r["arxiv"], {}).get("symptoms") or []:
            supply[s] += 1
            supply_inc[s] += int(r["adopted"])
    catalog = Counter()
    for m in methods:
        a = adoption.get(m["id"])
        if a and a["n_frameworks_at_head"] >= 1:
            for s in m.get("symptoms") or []:
                catalog[s] += 1
    out["NSupplyLabelled"] = sum(1 for r in gen if labels.get(r["arxiv"], {}).get("symptoms"))
    for s in SYMPTOM_CODES:
        key = "".join(w.capitalize() for w in s.split("_"))
        out[f"NSupply{key}"], out[f"NSupplyInc{key}"], out[f"NCatalog{key}"] = supply[s], supply_inc[s], catalog[s]

    # table: one row per failure, issues against supply
    rows = []
    for s in SYMPTOM_CODES:
        rows.append((SYMPTOM_NAME[s], codes[s], str(supply[s]), str(supply_inc[s]), str(catalog[s])))
    for code, name in OTHER_FAILURE_CODES.items():
        rows.append((name, codes[code], "--", "--", "--"))
    rows.sort(key=lambda r: (-r[1], -(int(r[2]) if r[2].isdigit() else -1)))
    nl, row_end = chr(10), r" \\"
    lines = [r"\begin{tabular}{lrrrr}", r"\toprule",
             r" & Issue threads & \multicolumn{2}{c}{General methods} & Catalog methods \\",
             r"\cmidrule(lr){3-4}",
             r"Failure & naming it & naming it & included & in a framework \\", r"\midrule"]
    for name, k, a, b, c in rows:
        lines.append(f"{tex(name)} & {k} & {a} & {b} & {c}" + row_end)
    lines += [r"\bottomrule", r"\end{tabular}"]
    (ROOT / "paper" / "table_demand.tex").write_text(nl.join(lines) + nl, encoding="utf-8", newline=nl)
    return out


# the widely included methods of Table 1, in its order, with the column heads of the report table
WIDE = [("dapo_clip_higher", "Clip-higher"), ("gspo", "GSPO"), ("dapo_dynamic_sampling", "Dyn. sampling"),
        ("dr_grpo", "Dr. GRPO"), ("cispo", "CISPO"), ("tis", "TIS"), ("mis", "MIS"), ("reinforce_pp", "R++"),
        ("dapo_token_loss", "Token loss"), ("dapo_overlong", "Overlong"), ("r3_rollout_routing_replay", "R3"),
        ("sapo", "SAPO"), ("gdpo", "GDPO")]
MARK = {"yes": r"\checkmark", "own": "S", "tried": "T", "variant": "V"}
FRAMEWORK_WORDS = ["verl", "TRL", "OpenRLHF", "NeMo-RL", "ROLL", "slime", "AReaL"]


def report_numbers() -> dict:
    """Which widely included methods the RL sections of large open-weight model reports state."""
    reps = read_jsonl(GEN / "casecontrol" / "model_reports.jsonl")
    if not reps:
        return {}
    reps.sort(key=lambda r: r["date"])
    adoption = {r["id"]: r for r in json.loads((GEN / "adoption.json").read_text(encoding="utf-8"))}

    def mark_of(v: str) -> str:
        v = (v or "").lower()
        for k, m in MARK.items():
            if v.startswith(k):
                return m
        return ""

    nl, row_end = chr(10), r" \\"
    heads = " & ".join(rf"\rotatebox{{90}}{{{h}}}" for _, h in WIDE)
    lines = [r"\setlength{\tabcolsep}{2.5pt}",
             r"\begin{tabular}{@{}l l l " + "c" * len(WIDE) + "@{}}", r"\toprule",
             r"Report & Size & Framework stated & " + heads + r" \\", r"\midrule"]
    used_any = 0
    per_method = Counter()
    named_fw = 0
    no_detail = 0
    n_source = n_variant = n_none = n_no_kl = 0
    for r in reps:
        marks = []
        any_used = False
        for mid, _ in WIDE:
            m = mark_of(r["methods"].get(mid, ""))
            marks.append(m)
            if m == r"\checkmark":
                any_used = True
                per_method[mid] += 1
        used_any += any_used
        n_source += "S" in marks
        n_variant += "V" in marks
        n_none += not any(marks)
        n_no_kl += mark_of(r["methods"].get("dapo_no_kl", "")) == r"\checkmark"
        fw = r.get("framework_stated") or ""
        if any(w.lower() in fw.lower() for w in FRAMEWORK_WORDS):
            named_fw += 1
        if r.get("algorithm", "").startswith("not described"):
            no_detail += 1
        cite = r"~\citep{arxiv" + r["arxiv"].replace(".", "") + "}"
        lines.append(f"{tex(r['short'])}{cite} & {tex(r['params'])} & {tex(fw)} & " + " & ".join(marks) + row_end)
    lines += [r"\bottomrule", r"\end{tabular}"]
    (ROOT / "paper" / "table_reports.tex").write_text(nl.join(lines) + nl, encoding="utf-8", newline=nl)
    out = {"NReports": len(reps), "NReportsUseAny": used_any, "NReportsNamedFramework": named_fw,
           "NReportsNoDetail": no_detail, "NReportsSource": n_source, "NReportsVariant": n_variant,
           "NReportsNone": n_none, "NReportsNoKL": n_no_kl,
           "ReportFirst": reps[0]["short"], "ReportLast": reps[-1]["short"],
           "NReportsMethodsUsed": sum(1 for mid, _ in WIDE if per_method[mid] > 0),
           "NWideMethods": len(WIDE)}
    for mid, _ in WIDE:
        # LaTeX macro names take letters only, so the digit in r3 becomes a word
        key = "".join(w.capitalize() for w in mid.split("_")).replace("3", "Three")
        out[f"NRep{key}"] = per_method[mid]
    # methods with the most reports, for the text
    top = per_method.most_common(3)
    out["RepTopMethod"] = adoption[top[0][0]]["name"].split(" (")[0] if top else "--"
    out["RepTopCount"] = top[0][1] if top else 0
    return out


if __name__ == "__main__":
    for k, v in {**issue_numbers(), **report_numbers()}.items():
        print(f"{k:28s} {v}")
