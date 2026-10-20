"""Full-text reading tasks after triage: a case-control sample and a model-report check.

Case-control: every adopted paper from 2025 (enough time to be picked up) plus non-adopted
general methods from 2025, frequency-matched by quarter. One reader fills factual fields from
the full text without knowing which papers were adopted.

Model-report check: random model reports, some labelled rl_method and some not, read in full to
estimate how many general RL components abstracts hide or overstate.

  python tools/casecontrol.py make      # once: write the reading lists and the hidden key
  python tools/casecontrol.py status    # progress and format problems
  python tools/casecontrol.py analyze   # counts by group -> data/generated/casecontrol/results.md

Files under data/generated/casecontrol/:
  cc_papers.jsonl / cc_filled.jsonl          case-control reading list / one filled record per line
  report_papers.jsonl / report_filled.jsonl  model-report reading list / filled records
The key (which papers are adopted, which strata) is .cache/casecontrol_key.json.
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"
CC = GEN / "casecontrol"
KEY = ROOT / ".cache" / "casecontrol_key.json"
SEED = 20261019
N_CONTROLS = 150
N_REPORTS_NOT_METHOD, N_REPORTS_METHOD = 40, 30

AFFIL = {"industry", "academia", "mixed", "unknown"}
YNU = {"yes", "no", "unknown"}
CHANGE = {"coefficient", "term", "pipeline"}
EVAL_SCOPE = {"general", "single_domain"}
DOMAINS = {"math", "code", "general_reasoning", "agent", "multimodal", "other"}
COMPONENTS = {"advantage", "clipping", "aggregation", "sampling", "length", "offpolicy", "moe", "entropy", "kl",
              "multi_reward", "credit_assignment", "other"}


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").split(chr(10)) if l.strip()] if p.exists() else []


def quarter(month: str) -> str:
    y, m = month.split("-")
    return f"{y}Q{(int(m) - 1) // 3 + 1}"


def make() -> None:
    if KEY.exists():
        sys.exit("already made; delete .cache/casecontrol_key.json and data/generated/casecontrol to redo")
    pool = read_jsonl(GEN / "pool_adoption.jsonl")
    frame = {r["arxiv"]: r for r in read_jsonl(GEN / "arxiv_frame.jsonl")}
    rng = random.Random(SEED)

    in2025 = [r for r in pool if r["month"].startswith("2025")]
    cases = [r for r in in2025 if r["adopted"]]
    controls_pool = [r for r in in2025 if not r["adopted"] and r["label"] == "rl_method" and r["scope"] == "general"]
    by_q = defaultdict(list)
    for r in controls_pool:
        by_q[quarter(r["month"])].append(r)
    case_q = Counter(quarter(r["month"]) for r in cases)
    controls = []
    alloc = {q: round(N_CONTROLS * n / len(cases)) for q, n in case_q.items()}
    for q, n in alloc.items():
        controls += rng.sample(by_q[q], min(n, len(by_q[q])))
    cc = cases + controls
    rng.shuffle(cc)

    reports = [r for r in pool if r["is_model_report"] and not r["adopted"]]
    rep_method = [r for r in reports if r["label"] == "rl_method"]
    rep_other = [r for r in reports if r["label"] != "rl_method"]
    rep = rng.sample(rep_method, min(N_REPORTS_METHOD, len(rep_method))) + \
        rng.sample(rep_other, min(N_REPORTS_NOT_METHOD, len(rep_other)))
    rng.shuffle(rep)

    CC.mkdir(parents=True, exist_ok=True)
    for name, rows in (("cc_papers.jsonl", cc), ("report_papers.jsonl", rep)):
        with (CC / name).open("w", encoding="utf-8") as f:
            for r in rows:
                p = frame[r["arxiv"]]
                f.write(json.dumps({"arxiv": r["arxiv"], "title": p["title"],
                                    "url": f"https://arxiv.org/abs/{r['arxiv']}"}, ensure_ascii=False) + "\n")
    KEY.parent.mkdir(parents=True, exist_ok=True)
    KEY.write_text(json.dumps({
        "seed": SEED,
        "cases": [r["arxiv"] for r in cases],
        "controls": [r["arxiv"] for r in controls],
        "control_alloc": alloc,
        "reports_labelled_method": [r["arxiv"] for r in rep if r["label"] == "rl_method"],
        "reports_labelled_other": [r["arxiv"] for r in rep if r["label"] != "rl_method"],
        "n_reports_method_total": len(rep_method), "n_reports_other_total": len(rep_other),
    }, indent=1), encoding="utf-8")
    print(f"case-control: {len(cases)} adopted + {len(controls)} controls (by quarter {alloc}); "
          f"model reports: {len(rep)} ({len(rep_method)} labelled rl_method, {len(rep_other)} not, in total)")


def check_cc(g: dict) -> list[str]:
    p = []
    req = ["arxiv", "version_read", "affiliation_type", "organizations", "code_released", "code_url",
           "max_policy_params_b", "moe_policy", "new_hyperparameters", "change_size", "extra_model_required",
           "targets_failure", "failure_quote", "eval_scope", "eval_domains", "reports_compute", "notes"]
    p += [f"missing {k}" for k in req if k not in g]
    if g.get("affiliation_type") not in AFFIL:
        p.append(f"affiliation_type {g.get('affiliation_type')!r}")
    if g.get("code_released") not in YNU:
        p.append(f"code_released {g.get('code_released')!r}")
    if g.get("change_size") not in CHANGE:
        p.append(f"change_size {g.get('change_size')!r}")
    # a paper without an empirical evaluation has no evaluation scope
    if g.get("eval_scope") not in EVAL_SCOPE and not (g.get("eval_scope") is None and not g.get("eval_domains")):
        p.append(f"eval_scope {g.get('eval_scope')!r}")
    if not set(g.get("eval_domains") or []) <= DOMAINS:
        p.append(f"eval_domains {g.get('eval_domains')!r}")
    for k in ("moe_policy",):
        if g.get(k) not in (True, False, None):
            p.append(f"{k} must be true/false/null")
    for k in ("extra_model_required", "targets_failure", "reports_compute"):
        if not isinstance(g.get(k), bool):
            p.append(f"{k} must be true/false")
    if g.get("max_policy_params_b") is not None and not isinstance(g.get("max_policy_params_b"), (int, float)):
        p.append("max_policy_params_b must be a number or null")
    if g.get("new_hyperparameters") is not None and not isinstance(g.get("new_hyperparameters"), int):
        p.append("new_hyperparameters must be an integer or null")
    if g.get("targets_failure") and not g.get("failure_quote"):
        p.append("failure_quote required when targets_failure is true")
    return p


def check_report(g: dict) -> list[str]:
    p = [f"missing {k}" for k in ("arxiv", "version_read", "has_rl_component", "component_name", "component",
                                   "general", "section", "quote") if k not in g]
    if g.get("has_rl_component") not in ("yes", "no"):
        p.append(f"has_rl_component {g.get('has_rl_component')!r}")
    if g.get("has_rl_component") == "yes":
        if g.get("component") not in COMPONENTS:
            p.append(f"component {g.get('component')!r}")
        if not isinstance(g.get("general"), bool):
            p.append("general must be true/false when has_rl_component is yes")
    return p


def check_cc_v1(g: dict) -> list[str]:
    p = check_cc(g)
    if g.get("version_read") != "v1":
        p.append(f"version_read must be v1, got {g.get('version_read')!r}")
    for k in ("trained_14b_or_more", "trained_30b_or_more"):
        if g.get(k) not in (True, False, None):
            p.append(f"{k} must be true/false/null")
    return p


def check_report_scope(g: dict) -> list[str]:
    p = [f"missing {k}" for k in ("arxiv", "main_contribution") if k not in g]
    if g.get("main_contribution") not in (True, False, None):
        p.append("main_contribution must be true/false/null")
    return p


def status() -> None:
    for papers, filled, checker in (("cc_papers.jsonl", "cc_filled.jsonl", check_cc),
                                    ("report_papers.jsonl", "report_filled.jsonl", check_report),
                                    ("cc_papers.jsonl", "cc_v1_filled.jsonl", check_cc_v1),
                                    ("report_papers.jsonl", "report_scope.jsonl", check_report_scope)):
        if filled in ("cc_v1_filled.jsonl", "report_scope.jsonl") and not (CC / filled).exists():
            print(f"{filled}: not started")
            continue
        want = [r["arxiv"] for r in read_jsonl(CC / papers)]
        got = read_jsonl(CC / filled)
        ids = [g.get("arxiv") for g in got]
        problems = []
        extra = [a for a in ids if a not in want]
        dup = [a for a, n in Counter(ids).items() if n > 1]
        if extra:
            problems.append(f"ids not in the reading list: {extra[:5]}")
        if dup:
            problems.append(f"duplicate ids: {dup[:5]}")
        for g in got:
            problems += [f"{g.get('arxiv')}: {x}" for x in checker(g)]
        nxt = next((a for a in want if a not in set(ids)), None)
        print(f"{filled}: {len(set(ids) & set(want))}/{len(want)} done; next: {nxt}")
        for x in problems[:20]:
            print("  PROBLEM", x)


FEATURES = [
    ("industry_any", "Any industry author", lambda g: g["affiliation_type"] in ("industry", "mixed") if g["affiliation_type"] != "unknown" else None),
    ("industry_only", "Industry only", lambda g: g["affiliation_type"] == "industry" if g["affiliation_type"] != "unknown" else None),
    ("code", "Code released", lambda g: g["code_released"] == "yes" if g["code_released"] != "unknown" else None),
    ("big7", "Largest policy ≥ 7B", lambda g: g["max_policy_params_b"] >= 7 if g["max_policy_params_b"] is not None else None),
    ("big30", "Largest policy ≥ 30B", lambda g: g["max_policy_params_b"] >= 30 if g["max_policy_params_b"] is not None else None),
    ("moe", "Trains an MoE policy", lambda g: g["moe_policy"]),
    ("coef", "Change is a coefficient, clip, mask or weight", lambda g: g["change_size"] == "coefficient" if g["change_size"] else None),
    ("pipeline", "Change adds a training stage or model", lambda g: g["change_size"] == "pipeline" if g["change_size"] else None),
    ("hp1", "At most one new hyperparameter", lambda g: g["new_hyperparameters"] <= 1 if g["new_hyperparameters"] is not None else None),
    ("extra", "Needs an extra model", lambda g: g["extra_model_required"]),
    ("failure", "Motivated by a named training failure", lambda g: g["targets_failure"]),
    # papers with no empirical evaluation carry an empty domain list and are left out here
    ("broad", "Evaluated beyond one domain", lambda g: (g["eval_scope"] == "general") if g["eval_domains"] else None),
    ("empirical", "Has an empirical evaluation", lambda g: bool(g["eval_domains"])),
    ("compute", "Reports compute", lambda g: g["reports_compute"]),
]


def apply_overrides(records: dict[str, dict]) -> dict[str, dict]:
    """Apply documented field corrections from coding_overrides.json without touching the coded files."""
    path = CC / "coding_overrides.json"
    if path.exists():
        for a, fix in json.loads(path.read_text(encoding="utf-8")).items():
            if a in records:
                records[a] = {**records[a], **{k: v for k, v in fix.items() if k != "reason"}}
    return records


def share(rows: list[dict], fn) -> str:
    known = [r for r in rows if fn(r) is not None]
    return f"{sum(bool(fn(r)) for r in known)}/{len(known)}"


def analyze() -> None:
    key = json.loads(KEY.read_text(encoding="utf-8"))
    filled = {g["arxiv"]: g for g in read_jsonl(CC / "cc_filled.jsonl")}
    cases = [filled[a] for a in key["cases"] if a in filled]
    controls = [filled[a] for a in key["controls"] if a in filled]
    rows = [(name, fn) for _, name, fn in FEATURES]
    out = ["# Case-control comparison", "",
           f"Adopted 2025 papers read: {len(cases)}/{len(key['cases'])}. "
           f"Non-adopted 2025 general methods read: {len(controls)}/{len(key['controls'])}, matched by quarter.", "",
           "| Feature | Adopted | Not adopted |", "|---|---|---|"]
    for name, fn in rows:
        out.append(f"| {name} | {share(cases, fn)} | {share(controls, fn)} |")

    rep = {g["arxiv"]: g for g in read_jsonl(CC / "report_filled.jsonl")}
    m = [rep[a] for a in key["reports_labelled_method"] if a in rep]
    o = [rep[a] for a in key["reports_labelled_other"] if a in rep]
    def gen(rs): return sum(g["has_rl_component"] == "yes" and g.get("general") is True for g in rs)
    out += ["", "## Model reports read in full", "",
            f"- Labelled `rl_method` from the abstract: {gen(m)}/{len(m)} introduce a general RL component in the body.",
            f"- Not labelled `rl_method`: {gen(o)}/{len(o)} introduce a general RL component in the body.",
            f"- Pool totals for scaling: {key['n_reports_method_total']} labelled `rl_method`, "
            f"{key['n_reports_other_total']} not.", ""]
    (CC / "results.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    {"make": make, "status": status, "analyze": analyze}[sys.argv[1] if len(sys.argv) > 1 else "status"]()
