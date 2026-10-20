"""Every number the report cites, computed from data/generated and written as LaTeX macros.

  python tools/paper_numbers.py  ->  paper/numbers.tex (and a readable dump on stdout)

The text uses only these macros for data-derived numbers, so a data refresh updates the text.
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").split(chr(10)) if l.strip()]


def fmt(v) -> str:
    return f"{v:,}" if isinstance(v, int) else str(v)


def main() -> None:
    pool = read_jsonl(GEN / "pool_adoption.jsonl")
    adoption = json.loads((GEN / "adoption.json").read_text(encoding="utf-8"))
    head = json.loads((GEN / "framework_head.json").read_text(encoding="utf-8"))
    events = read_jsonl(GEN / "framework_events.jsonl")
    methods = yaml.safe_load((ROOT / "data" / "methods.yaml").read_text(encoding="utf-8"))
    oai = json.loads((GEN / "harvest_meta.json").read_text())

    meth = [r for r in pool if r["label"] == "rl_method"]
    # Main denominator: general methods by the abstract rule (the rule used to draw controls).
    gen = [r for r in pool if r["strict_general"]]
    exc = [r for r in pool if r["adopted"] and not r["strict_general"]]
    early = [r for r in gen if r["month"] <= "2025-12"]
    late = [r for r in gen if r["month"] > "2025-12"]

    def comp(cs):
        rs = [r for r in gen if r["component"] in cs]
        return len(rs), sum(r["adopted"] for r in rs), sum(r["n_fw_head"] >= 3 for r in rs)

    core_n, core_k, core_3 = comp({"clipping", "offpolicy", "aggregation"})
    crowd_n, crowd_k, crowd_3 = comp({"sampling", "credit_assignment"})

    # Component level: catalog methods with a dated source from 2025 on. A lag is exact when the
    # earliest landing across frameworks is not censored, and an upper bound otherwise.
    recent = [r for r in adoption if (r["source_date"] or "") >= "2025-01-01" and r["per_framework"]]
    exact = [r["first_lag_days"] for r in recent if r["first_lag_days"] is not None and not r["first_lag_is_upper_bound"]]
    upper = [r for r in recent if r["first_lag_days"] is not None and r["first_lag_is_upper_bound"]]
    # Paper level: one lag per arXiv source, from the earliest landing of any of its methods.
    by_src: dict[str, list[dict]] = {}
    for r in recent:
        if r.get("arxiv") and r["first_lag_days"] is not None:
            by_src.setdefault(r["arxiv"], []).append(r)
    paper_exact = []
    for rs in by_src.values():
        e = min(rs, key=lambda r: r["first_adoption_date"])
        if not e["first_lag_is_upper_bound"]:
            paper_exact.append(e["first_lag_days"])

    rel_of = lambda v: v["commit_author_is_paper_author"]
    single = [r for r in recent if r["n_frameworks_ever"] == 1]
    single_self = sum(rel_of(next(iter(r["per_framework"].values()))) == "author" for r in single)
    wide = [r for r in recent if r["n_frameworks_at_head"] >= 3]
    wide_land = [v for r in wide for v in r["per_framework"].values()]
    wl = Counter(rel_of(v) for v in wide_land)

    gspo = next(r for r in adoption if r["id"] == "gspo")
    gsrc = date.fromisoformat(gspo["source_date"])
    days = {fw: (date.fromisoformat(v["first_date"]) - gsrc).days for fw, v in gspo["per_framework"].items()}
    july = [r for r in gen if r["month"] == "2025-07"]
    july_gspo = [r for r in july if "gspo" in r["methods"]]

    cispo = next(r for r in adoption if r["id"] == "cispo")
    tri = (GEN / "triage" / "validation.md").read_text(encoding="utf-8")
    vals = {
        "NFrameworks": len([f for f in head if f != "verl_recipe"]),
        "NEvents": len(events),
        "NCatalog": len(methods),
        "NCatalogRecent": len(recent),
        "NHarvest": oai["records_kept"],
        "NPool": len(pool),
        "NMethod": len(meth),
        "NGeneral": len(gen),
        "NAdopted": sum(r["adopted"] for r in gen),
        "NIndependent": sum(r["independent"] for r in gen),
        "NOnlyUnknown": sum(r["adopted"] and r["only_unknown_or_no_paper"] for r in gen),
        "NThree": sum(r["n_fw_head"] >= 3 for r in gen),
        "NDefault": sum(r["default"] for r in gen),
        "NExceptions": len(exc),
        "NGeneralPlus": len(gen) + len(exc),
        "NAdoptedPlus": sum(r["adopted"] for r in gen) + len(exc),
        "NThreePlus": sum(r["n_fw_head"] >= 3 for r in gen + exc),
        "NEarly": len(early), "NEarlyAdopted": sum(r["adopted"] for r in early),
        "NEarlyThree": sum(r["n_fw_head"] >= 3 for r in early),
        "NLate": len(late), "NLateAdopted": sum(r["adopted"] for r in late),
        "NCoreComp": core_n, "NCoreCompAdopted": core_k, "NCoreCompThree": core_3,
        "NCrowdComp": crowd_n, "NCrowdCompAdopted": crowd_k, "NCrowdCompThree": crowd_3,
        "LagMedian": int(statistics.median(exact)), "NLags": len(exact), "NLagsUpper": len(upper),
        "NRecentIncluded": len(recent), "NLagsNoDate": sum(r["first_lag_days"] is None for r in recent),
        "NLagNegative": sum(x < 0 for x in exact),
        "PaperLagMedian": statistics.median(paper_exact), "NPaperLags": len(paper_exact),
        "NSingle": len(single), "NSingleSelf": single_self, "NWideRecent": len(wide),
        "NWideLandings": len(wide_land), "NWideAuthor": wl["author"], "NWideNotAuthor": wl["not_author"],
        "NWideUnknown": wl["unknown"], "NWideNoPaper": wl["no_paper"],
        "GSPOtrl": days["trl"], "GSPOverl": days["verl"], "GSPOlastFw": max(days.values()),
        "NJulyGeneral": len(july), "NJulyAdopted": sum(r["adopted"] for r in july),
        "NJulyOthers": len(july) - len(july_gspo),
        "NJulyOthersAdopted": sum(r["adopted"] for r in july) - len(july_gspo),
        "NModelReports": sum(r["is_model_report"] for r in pool),
        "NMethodMonthlyMin": min(Counter(r["month"] for r in meth if r["month"] >= "2026").values()),
        "CISPOLag": cispo["first_lag_days"],
    }
    papers_json = json.loads((GEN / "papers.json").read_text(encoding="utf-8"))["methods"]
    in_window = {r["arxiv"] for r in papers_json.values() if r.get("arxiv") and "2501" <= r["arxiv"][:4] <= "2606"}
    pool_ids = {r["arxiv"] for r in pool}
    vals["NCatalogInWindow"] = len(in_window)
    vals["NCatalogInPool"] = len(in_window & pool_ids)

    vals.update(casecontrol_numbers(pool))
    vals.update(org_numbers(gen, adoption))
    vals.update(candidate_numbers(gen))
    vals.update(report_numbers(pool))
    vals.update(extra_numbers(pool, adoption, head, gen))
    vals.update(profile_tables(adoption, head))
    vals.update(process_numbers(pool))
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "tools"))
    from demand_tables import issue_numbers, report_numbers as report_table_numbers  # noqa: E402
    vals.update(issue_numbers())
    vals.update(report_table_numbers())

    # validation numbers are parsed from validation.md so the text and the record agree
    import re
    m = re.search(r"labelled `rl_method`: (\d+)/(\d+)", tri)
    vals["RecallHit"], vals["RecallAll"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"named as examples in the v1 rules: (\d+)/(\d+)", tri)
    vals["RecallCleanHit"], vals["RecallCleanAll"] = int(m.group(1)), int(m.group(2))
    m = re.findall(r"Repeated papers with the same label both times: (\d+)/(\d+)", tri)[-1]
    vals["RepeatAgree"], vals["RepeatAll"] = int(m[0]), int(m[1])
    m = re.search(r"general vs everything else\): (\d+)/(\d+) agree", tri)
    vals["ReviewAgree"], vals["ReviewAll"] = int(m.group(1)), int(m.group(2))

    lines = ["% Generated by tools/paper_numbers.py. Do not edit by hand."]
    for k, v in vals.items():
        lines.append(f"\\newcommand{{\\{k}}}{{{fmt(v)}}}")
    out = ROOT / "paper" / "numbers.tex"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for k, v in vals.items():
        print(f"{k:24s} {fmt(v)}")
    write_tables(adoption, head)


def process_numbers(pool: list[dict]) -> dict:
    """Counts from the public record of the frameworks (tools/process_analysis.py) and the citation audit."""
    nl, row_end = chr(10), r" \\"
    pr = GEN / "process"
    sm = json.loads((pr / "summary.json").read_text(encoding="utf-8"))
    att = read_jsonl(pr / "attempts_coded.jsonl")
    audit = read_jsonl(pr / "citation_audit.jsonl")
    f, po, ro = sm["funnel"], sm["pr_outcomes"], sm["request_outcomes"]
    not_inc = sm["n_strict"] - f["included"]
    out = {
        "NThreads": sm["n_threads"], "NNotIncluded": not_inc, "NNoRecord": f["no_record"],
        "NNoRecordPct": round(100 * f["no_record"] / not_inc), "NWithRecord": not_inc - f["no_record"],
        # recall audit of the record by method name
        "NNameSearch": sm["name_audit"]["searchable"], "NNameCand": sm["name_audit"]["candidates"],
        "NNameRefers": sm["name_audit"]["refers"], "NNameCited": sm["name_audit"]["cited"],
        "NNameProposal": sm["name_audit"]["proposal_pr"] + sm["name_audit"]["request"],
        "NNameProposalPR": sm["name_audit"]["proposal_pr"], "NNameRequest": sm["name_audit"]["request"],
        "NNoRecordAfter": sm["name_audit"]["no_record_after"],
        "NNoRecordAfterPct": round(100 * sm["name_audit"]["no_record_after"] / not_inc),
        "NNoRecordExtrapPct": round(100 * sm["name_audit"]["no_record_extrapolated"] / not_inc),
        "NImplPapers": f["implementation_pr"], "NRequestPapers": f["request_only"], "NCitedOnly": f["cited_only"],
        "NAttemptThreads": sm["attempt_threads"], "NAttemptPapers": sm["attempt_papers"],
        # papers whose proposal a maintainer declined or redirected in public
        "NRefusedPapers": len({a["arxiv"] for a in att if a["outcome"] in ("declined", "redirected")}),
        "NAttemptPRs": sm["attempt_prs"], "NAttemptRequests": sm["attempt_requests"],
        "NPROpen": po.get("open_no_reply", 0) + po.get("open_engaged", 0), "NPROpenNoReply": po.get("open_no_reply", 0),
        "NPROpenEngaged": po.get("open_engaged", 0), "NPRDeclined": po.get("declined", 0),
        "NPRRedirected": po.get("redirected", 0), "NPRInactive": po.get("closed_inactive", 0),
        "NPRNoComment": po.get("closed_no_comment", 0), "NPRWithdrawn": po.get("withdrawn", 0),
        "NReqStale": ro.get("stale_cleanup", 0), "NReqDeclined": ro.get("declined", 0),
        "NReqRedirected": ro.get("redirected", 0), "NReqWithdrawn": ro.get("withdrawn", 0),
        "NReqOpen": ro.get("open_no_reply", 0) + ro.get("open_engaged", 0),
        "NNoMergerReply": sm["no_merger_reply"], "NNoMergerReplyHuman": sm["no_merger_reply_any_human"],
        "NNoMergerReplyNone": sm["no_merger_reply"] - sm["no_merger_reply_any_human"],
        "OpenPRMedianAge": int(sm["open_attempt_median_age"]), "OpenPROverHalfYear": sm["open_attempt_over_180"],
        "NLandingExact": sm["landings_exact"], "NLandingEvents": sm["landing_events_with_pr"],
        "NLandingPRs": sm["landing_prs"], "NLandingPriorRequest": sm["landing_prior_request"],
        "NLandingAuthor": sm["landing_author_paper"],
        "NPRPriorMerger": sm["pr_author_prior_merger"], "NPRSelfMerged": sm["pr_self_merged"],
        "PRDaysOpen": f"{sm['pr_median_days_open']:g}", "NPRTests": sm["pr_tests"],
        "NPRCore": sm["pr_core_n"], "PRCoreLines": int(sm["pr_median_core_lines"]),
        "NAttemptCore": sm["attempt_core_n"], "AttemptCoreLines": int(sm["attempt_median_core_lines"]),
    }
    for k, name in (("coefficient", "Coef"), ("term", "Term"), ("pipeline", "Pipe")):
        v = sm["core_lines_by_form"].get(k, {"n": 0, "median": 0})
        out[f"CoreLines{name}"], out[f"NCoreLines{name}"] = int(v["median"]), v["n"]
    out["NClosedWithReason"] = sm["closed_with_reason"]
    rc = sm["reasons_closed"]
    for k, name in (("demand", "Demand"), ("surface", "Surface"), ("placement", "Placement"), ("evidence", "Evidence"),
                    ("completeness", "Completeness"), ("design", "Design"), ("covered", "Covered")):
        out[f"Reason{name}"] = rc.get(k, 0)
    ac = Counter(r["category"] for r in audit)
    out.update({"NAuditCited": len(audit), "NAuditBefore": ac["included_before_audit"],
                "NAuditAdded": ac["implementation"], "NAuditList": ac["project_list_or_news"],
                "NAuditUnmatched": len(audit) - ac["included_before_audit"],
                "NAuditReport": ac["report_reference"],
                "NAuditOther": ac["configuration_note"] + ac["background_reference"] + ac["bug_fix"]})

    # agreement between the first coding and the blind recoding, from the frozen comparison
    agr = (pr / "agreement.md").read_text(encoding="utf-8") if (pr / "agreement.md").exists() else ""
    import re as _re
    m = _re.search(r"Threads recoded: (\d+)/(\d+)", agr)
    m2 = _re.search(r"- Outcome: (\d+)/(\d+) agree", agr)
    if m and m2:
        out["AgreeThreads"], out["AgreeOutcome"] = int(m.group(1)), int(m2.group(1))

    # review threads coded with the same fields: merged landing pull requests against proposals
    rv = sm.get("review") or {}
    if rv:
        g = {"M": rv["merged"], "U": rv["unmerged_pr"], "R": rv["request"]}
        for k, v in g.items():
            out[f"Rev{k}N"] = v["n"]
            out[f"Rev{k}Human"] = v["human_discussion"]
            out[f"Rev{k}Silent"] = v["n"] - v["human_discussion"]
            out[f"Rev{k}Any"] = v["any_concern"]
            out[f"Rev{k}Open"] = v["open_concern"]
            out[f"Rev{k}DS"] = v["demand_or_surface"]
            out[f"Rev{k}DC"] = v["design_or_completeness"]
            out[f"Rev{k}Results"] = v["results_shown"]
            out[f"Rev{k}Req"] = v["results_requested"]
            out[f"Rev{k}Prior"] = v["concern_by_prior_merger"]
            out[f"Rev{k}Fixed"] = v["driver"].get("proposer", 0) + v["driver"].get("both", 0)
        out["RevOtherAny"] = g["U"]["any_concern"] + g["R"]["any_concern"]
        out["RevOtherPrior"] = g["U"]["concern_by_prior_merger"] + g["R"]["concern_by_prior_merger"]
        fwv = rv["by_framework"]
        out["RevTRLMN"], out["RevTRLMDS"] = fwv["trl"]["merged"]["n"], fwv["trl"]["merged"]["demand_or_surface"]
        out["RevTRLUN"], out["RevTRLUDS"] = fwv["trl"]["unmerged_pr"]["n"], fwv["trl"]["unmerged_pr"]["demand_or_surface"]
        # the text says every unmerged pull request with a demand or surface concern is from TRL
        if out["RevTRLUDS"] != out["RevUDS"]:
            print("WARNING: not all demand or surface concerns in unmerged pull requests are from TRL; revise Section 7")
        out["RevNeMoMN"], out["RevNeMoMReq"] = fwv["nemo-rl"]["merged"]["n"], fwv["nemo-rl"]["merged"]["results_requested"]
        out["RevverlUN"], out["RevverlUHuman"] = fwv["verl"]["unmerged_pr"]["n"], fwv["verl"]["unmerged_pr"]["human_discussion"]
        names = [("Reply from someone other than the proposer", "human_discussion", None),
                 ("Concern raised in the thread", "any_concern", None),
                 (r"\quad design or interface", "raised", "design"),
                 (r"\quad tests or documentation", "raised", "completeness"),
                 (r"\quad evidence", "raised", "evidence"),
                 (r"\quad placement", "raised", "placement"),
                 (r"\quad maintenance burden", "raised", "surface"),
                 (r"\quad thin demand", "raised", "demand"),
                 (r"\quad already covered", "raised", "covered"),
                 ("Concern still open at the end", "open_concern", None),
                 ("Training results shown", "results_shown", None),
                 ("Results requested", "results_requested", None),
                 ("Demand stated in the thread", "demand_signal", None)]
        trows = []
        for label_, key, sub in names:
            cells = [str(g[k][key][sub] if sub else g[k][key]) for k in ("M", "U", "R")]
            trows.append(label_ + " & " + " & ".join(cells) + row_end)
        thead = [r"\begin{tabular}{lrrr}", r"\toprule",
                 r" & Merged & Unmerged & \\",
                 r"Thread record & pull requests & pull requests & Requests \\",
                 r"\midrule",
                 r"Threads & " + " & ".join(str(g[k]["n"]) for k in ("M", "U", "R")) + row_end,
                 r"\addlinespace"]
        (ROOT / "paper" / "table_review.tex").write_text(
            nl.join(thead + trows + [r"\bottomrule", r"\end{tabular}"]) + nl, encoding="utf-8", newline=nl)

    # appendix table of proposals for non-included methods
    label = {"open_no_reply": "open, no prior-merger reply", "open_engaged": "open, under discussion",
             "declined": "declined", "redirected": "redirected", "closed_inactive": "closed as inactive",
             "closed_no_comment": "closed without comment", "withdrawn": "withdrawn by proposer",
             "stale_cleanup": "closed in stale cleanup", "resolved_otherwise": "closed by another change"}
    rname = {"demand": "demand", "surface": "maintenance burden", "placement": "placement", "evidence": "evidence",
             "completeness": "tests and docs", "design": "design", "covered": "already covered", "priority": "priority"}
    short = dict(FW_SHORT, verl_recipe="verl recipes")
    rows = []
    for a in sorted(att, key=lambda a: (a["arxiv"], a["framework"], a["number"])):
        thread = ("PR" if a["type"] == "pr" else "issue") + r" \#" + str(a["number"])
        rows.append(f"{tex(a['method'])} & {a['arxiv']} & {short[a['framework']]} & {thread} & "
                    f"{label[a['outcome']]} & {', '.join(rname[r] for r in a['reasons']) or '--'}" + row_end)
    head = [r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{2.2cm} l l l >{\raggedright\arraybackslash}p{2.5cm} >{\raggedright\arraybackslash}p{2.6cm}@{}}",
            r"\caption{\textbf{Proposals to include general methods that no framework included.} Unit: issue, pull request or discussion that proposes or requests the method, coded blind from its own text. The arXiv identifier tells apart methods with the same name. Reasons are those a maintainer stated in the thread.}\label{tab:attempts}\\",
            r"\toprule", r"Method & arXiv & Framework & Thread & Outcome & Stated reasons \\", r"\midrule", r"\endfirsthead",
            r"\toprule", r"Method & arXiv & Framework & Thread & Outcome & Stated reasons \\", r"\midrule", r"\endhead"]
    (ROOT / "paper" / "table_attempts.tex").write_text(
        nl.join(head + rows + [r"\bottomrule", r"\end{longtable}"]) + nl, encoding="utf-8", newline=nl)
    return out


CC_NAMES = {"industry_any": "IndustryAny", "industry_only": "IndustryOnly", "code": "Code", "big7": "BigSeven",
            "big30": "BigThirty", "moe": "Moe", "coef": "Coef", "pipeline": "Pipeline", "hp1": "HpOne",
            "extra": "Extra", "failure": "Failure", "broad": "Broad", "empirical": "Empirical", "compute": "Compute"}


FW_ORGS = {fw: re.compile(v["pattern"], re.I) for fw, v in
           yaml.safe_load((ROOT / "config" / "framework_orgs.yaml").read_text(encoding="utf-8")).items()
           if v["pattern"]}


def framework_orgs_of(g: dict) -> set[str]:
    """Frameworks maintained by a company among the paper's first-page affiliations."""
    s = " | ".join(g.get("organizations") or [])
    return {fw for fw, rx in FW_ORGS.items() if rx.search(s)}


def inclusion_frameworks() -> dict[str, set[str]]:
    """arXiv id -> frameworks that include a method from that source (verl-recipe counts as verl)."""
    adoption = json.loads((GEN / "adoption.json").read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for r in adoption:
        if r.get("arxiv"):
            out.setdefault(r["arxiv"], set()).update(r["per_framework"])
    return out


def org_numbers(gen: list[dict], adoption: list[dict]) -> dict:
    """Organisation of every included general paper against the frameworks that include it.

    Affiliations come from the full-text coding, and from included_orgs.jsonl for included papers
    outside the 2025 comparison. A landing is independent when its commit author is a named person
    outside the author list; it is also outside the paper's company when that company does not
    maintain the framework."""
    orgs = {}
    for f in ("cc_v1_filled.jsonl", "cc_v1_audit_added.jsonl", "included_orgs.jsonl"):
        for g in read_jsonl(GEN / "casecontrol" / f):
            orgs.setdefault(g["arxiv"], g)
    inc = [r["arxiv"] for r in gen if r["adopted"]]
    missing = [a for a in inc if a not in orgs]
    if missing:
        raise SystemExit(f"included papers without affiliations: {missing}")
    rel: dict[str, dict[str, str]] = {}
    for r in adoption:
        if r.get("arxiv"):
            for fw, v in r["per_framework"].items():
                rel.setdefault(r["arxiv"], {})[fw] = v["commit_author_is_paper_author"]
    from_fw = [a for a in inc if framework_orgs_of(orgs[a])]
    own = [a for a in inc if framework_orgs_of(orgs[a]) & set(rel.get(a, {}))]
    indep = [a for a in inc if "not_author" in rel.get(a, {}).values()]
    indep_out = [a for a in indep if any(v == "not_author" and fw not in framework_orgs_of(orgs[a])
                                         for fw, v in rel[a].items())]
    author_only = [a for a in inc if a not in indep and "author" in rel.get(a, {}).values()]
    if len(indep_out) != len(indep):
        print(f"WARNING: {len(indep) - len(indep_out)} papers with an outside committer only landed in their "
              "own company's framework; revise the company paragraph of Section 5")
    return {"NOrgIncluded": len(from_fw), "NOwnIncluded": len(own), "NIndependentOutside": len(indep_out),
            "NAuthorOnly": len(author_only)}


def candidate_numbers(gen: list[dict]) -> dict:
    """Other frameworks against the selection criteria, and the methods the qualifying ones add."""
    d = json.loads((GEN / "framework_candidates.json").read_text(encoding="utf-8"))
    rows = d["candidates"]
    extra = [r for r in rows if r["meets_criteria"] and not r["tracked"]]
    new = sorted({a for r in extra for a in r["general_new_implemented"]})
    adopted = sum(r["adopted"] for r in gen)
    head = json.loads((GEN / "framework_head.json").read_text(encoding="utf-8"))
    fw_of = {"volcengine/verl": "verl", "huggingface/trl": "trl", "OpenRLHF/OpenRLHF": "openrlhf",
             "NVIDIA-NeMo/RL": "nemo-rl", "alibaba/ROLL": "roll", "THUDM/slime": "slime", "inclusionAI/AReaL": "areal"}
    lines = [r"\begin{tabularx}{\linewidth}{@{}l r l >{\raggedright\arraybackslash}X@{}}", r"\toprule",
             r"Repository & Stars & Commit & Status \\", r"\midrule"]
    # the table lists repositories above the star threshold; smaller ones stay in the json
    shown = [r for r in rows if r["stars"] >= d["min_stars"]]
    for r in sorted(shown, key=lambda r: (not r["tracked"], not r["meets_criteria"], -r["stars"])):
        commit = ""
        if r["tracked"]:
            h = head[fw_of[r["repo"]]]
            commit = rf"\texttt{{{h['head_sha'][:10]}}} {h['head_date']}"
            status = "tracked"
        elif r["meets_criteria"]:
            commit = rf"\texttt{{{r['commit'][:10]}}} {r['date']}"
            k = len(r["general_new_implemented"])
            status = "meets the criteria; adds " + ("no general method" if k == 0 else
                                                    f"{k} general method{'s' if k != 1 else ''}")
        else:
            status = r["reason_outside"]
        lines.append(rf"\texttt{{{tex(r['current_name'])}}} & {r['stars']:,} & {commit} & {tex(status)} \\")
    lines += [r"\bottomrule", r"\end{tabularx}"]
    rec = head["verl_recipe"]
    extra_note = {"VerlRecipeCommit": rf"\texttt{{{rec['head_sha'][:10]}}}", "VerlRecipeDate": rec["head_date"]}
    (ROOT / "paper" / "table_candidates.tex").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return {**extra_note, "MinStars": f"{d['min_stars']:,}", "NFwQualify": sum(r["meets_criteria"] for r in rows),
            "NFwExtra": len(extra), "NFwExtraNew": len(new),
            "NFwExtraDate": min(r["date"] for r in extra) if extra else "--",
            "RateWithExtra": f"{100 * (adopted + len(new)) / len(gen):.1f}"}


def casecontrol_numbers(pool: list[dict]) -> dict:
    """Counts for every case-control feature, the robustness cuts used in the text, and bounds.

    Features come from the v1 re-reading when it is complete, so that experiments added after a
    method entered a framework do not count. Main cases are included papers that meet the same
    general-method rule as the controls; the remaining included papers form a sensitivity row.
    """
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from casecontrol import FEATURES  # noqa: E402

    key = json.loads((ROOT / ".cache" / "casecontrol_key.json").read_text(encoding="utf-8"))
    v1_path = GEN / "casecontrol" / "cc_v1_filled.jsonl"
    v1 = {g["arxiv"]: g for g in read_jsonl(v1_path)} if v1_path.exists() else {}
    # included papers found later by the citation audit, coded separately from v1
    v1.update({g["arxiv"]: g for g in read_jsonl(GEN / "casecontrol" / "cc_v1_audit_added.jsonl")})
    added = key.get("cases_added_by_audit", [])
    # v1 is used once every case and all but a few controls have a v1 record; a paper whose v1
    # was withdrawn has no v1 record and leaves the comparison rather than borrowing a later version
    missing_v1 = [a for a in key["cases"] + key["controls"] if a not in v1]
    use_v1 = bool(v1) and all(a in v1 for a in key["cases"]) and len(missing_v1) <= 3
    cc = v1 if use_v1 else {g["arxiv"]: g for g in read_jsonl(GEN / "casecontrol" / "cc_filled.jsonl")}
    from casecontrol import apply_overrides  # noqa: E402
    cc = apply_overrides(dict(cc))
    by_id = {r["arxiv"]: r for r in pool}
    all_cases = [cc[a] for a in key["cases"] + added if a in cc]
    cases = [g for g in all_cases if by_id[g["arxiv"]]["strict_general"]]
    orig_cases = [g for g in cases if g["arxiv"] not in added]
    ctrls = [cc[a] for a in key["controls"] if a in cc]

    def count(rows, fn):
        known = [g for g in rows if fn(g) is not None]
        return sum(bool(fn(g)) for g in known), len(known)

    feats = {fid: fn for fid, _, fn in FEATURES}
    # threshold fields from the v1 reading give a size lower bound even when the maximum is unknown
    if use_v1:
        feats["big30"] = lambda g: g.get("trained_30b_or_more")
        feats["big14"] = lambda g: g.get("trained_14b_or_more")
    else:
        feats["big14"] = lambda g: g["max_policy_params_b"] >= 14 if g["max_policy_params_b"] is not None else None

    out = {"CCCases": len(cases), "CCCasesAll": len(all_cases), "CCControls": len(ctrls),
           "CCCasesOrig": len(orig_cases), "CCCasesAdded": len(cases) - len(orig_cases),
           "CCVersionRule": "v1" if use_v1 else "latest",
           "CCNoVOne": len(missing_v1) if use_v1 else 0}
    names = {**CC_NAMES, "big14": "BigFourteen"}
    for fid, fn in feats.items():
        n = names[fid]
        out[f"CC{n}Case"], out[f"CC{n}CaseN"] = count(cases, fn)
        out[f"CC{n}Ctrl"], out[f"CC{n}CtrlN"] = count(ctrls, fn)
        # missing values pushed against the observed gap: cases as false, controls as true
        k1, n1 = count(cases, fn)
        k0, n0 = count(ctrls, fn)
        out[f"CC{n}CaseWorst"] = k1
        out[f"CC{n}CtrlWorst"] = k0 + (len(ctrls) - n0)
        out[f"CC{n}CaseMissing"] = len(cases) - n1
        out[f"CC{n}CtrlMissing"] = len(ctrls) - n0
    nr = lambda rows: [g for g in rows if not by_id[g["arxiv"]]["is_model_report"]]
    ia = lambda rows: [g for g in rows if g["affiliation_type"] in ("industry", "mixed")]
    for fid in ("big30", "coef"):
        n = names[fid]
        out[f"CCNoRep{n}Case"], out[f"CCNoRep{n}CaseN"] = count(nr(cases), feats[fid])
        out[f"CCNoRep{n}Ctrl"], out[f"CCNoRep{n}CtrlN"] = count(nr(ctrls), feats[fid])
        out[f"CCInd{n}Case"], out[f"CCInd{n}CaseN"] = count(ia(cases), feats[fid])
        out[f"CCInd{n}Ctrl"], out[f"CCInd{n}CtrlN"] = count(ia(ctrls), feats[fid])
        out[f"CCAll{n}Case"], out[f"CCAll{n}CaseN"] = count(all_cases, feats[fid])
        out[f"CCOrig{n}Case"], out[f"CCOrig{n}CaseN"] = count(orig_cases, feats[fid])
    # the included papers added by the citation audit, by how they were coded
    added_strict = [g for g in cases if g["arxiv"] in added]
    out["CCCasesAddedBlind"] = sum(g.get("coder") == "blind_recode" for g in added_strict)
    out["CCCasesAddedOpen"] = len(added_strict) - out["CCCasesAddedBlind"]
    # controls recoded blind by a second reader, substituted for the original coding
    rec = {g["arxiv"]: g for f in ("cc_v1_blind_recode.jsonl", "cc_v1_blind_recode2.jsonl")
           for g in read_jsonl(GEN / "casecontrol" / f)}
    ctrls_rec = [rec.get(g["arxiv"], g) for g in ctrls]
    out["CCRecodedCtrls"] = sum(g["arxiv"] in rec for g in ctrls)
    for fid in ("big30", "coef"):
        n = names[fid]
        out[f"CCRec{n}Ctrl"], out[f"CCRec{n}CtrlN"] = count(ctrls_rec, feats[fid])
    for n in ("BigThirty", "Coef", "Pipeline", "Code", "IndustryAny", "Failure", "Compute", "Broad"):
        out[f"CC{n}CasePct"] = round(100 * out[f"CC{n}Case"] / out[f"CC{n}CaseN"])
        out[f"CC{n}CtrlPct"] = round(100 * out[f"CC{n}Ctrl"] / out[f"CC{n}CtrlN"])
    # papers from a company that maintains one of the frameworks, and cases included by that framework
    org_fw = framework_orgs_of
    included_by = inclusion_frameworks()
    from_fw = lambda rows: [g for g in rows if org_fw(g)]
    not_fw = lambda rows: [g for g in rows if not org_fw(g)]
    own = [g for g in cases if org_fw(g) & included_by.get(g["arxiv"], set())]
    out["CCOrgCase"], out["CCOrgCtrl"] = len(from_fw(cases)), len(from_fw(ctrls))
    out["CCOwnCase"] = len(own)
    for fid in ("big30", "coef"):
        n = names[fid]
        out[f"CCNoOrg{n}Case"], out[f"CCNoOrg{n}CaseN"] = count(not_fw(cases), feats[fid])
        out[f"CCNoOrg{n}Ctrl"], out[f"CCNoOrg{n}CtrlN"] = count(not_fw(ctrls), feats[fid])
        out[f"CCNoOwn{n}Case"], out[f"CCNoOwn{n}CaseN"] = count([g for g in cases if g not in own], feats[fid])
    for n in ("NoOrgBigThirty", "NoOrgCoef"):
        out[f"CC{n}CasePct"] = round(100 * out[f"CC{n}Case"] / out[f"CC{n}CaseN"])
        out[f"CC{n}CtrlPct"] = round(100 * out[f"CC{n}Ctrl"] / out[f"CC{n}CtrlN"])
    out["CCOrgCasePct"] = round(100 * out["CCOrgCase"] / len(cases))
    out["CCOrgCtrlPct"] = round(100 * out["CCOrgCtrl"] / len(ctrls))
    out["CCAcademiaCases"] = sum(g["affiliation_type"] == "academia" for g in cases)
    out["CCAcademiaCtrls"] = sum(g["affiliation_type"] == "academia" for g in ctrls)
    q = lambda a: (int(by_id[a]["month"][5:7]) - 1) // 3 + 1
    for i, word in zip(range(1, 5), ("One", "Two", "Three", "Four")):
        out[f"CCQ{word}Case"] = sum(q(g["arxiv"]) == i for g in cases)
        out[f"CCQ{word}CaseAll"] = sum(q(g["arxiv"]) == i for g in all_cases)
        out[f"CCQ{word}Ctrl"] = sum(q(g["arxiv"]) == i for g in ctrls)
    # two-sided Fisher exact test for each row of the sensitivity table
    for n in ("BigThirty", "Coef"):
        rows = {"Main": (f"CC{n}Case", f"CC{n}CaseN", f"CC{n}Ctrl", f"CC{n}CtrlN"),
                "All": (f"CCAll{n}Case", f"CCAll{n}CaseN", f"CC{n}Ctrl", f"CC{n}CtrlN"),
                "NoRep": (f"CCNoRep{n}Case", f"CCNoRep{n}CaseN", f"CCNoRep{n}Ctrl", f"CCNoRep{n}CtrlN"),
                "Ind": (f"CCInd{n}Case", f"CCInd{n}CaseN", f"CCInd{n}Ctrl", f"CCInd{n}CtrlN"),
                "Worst": (f"CC{n}CaseWorst", "CCCases", f"CC{n}CtrlWorst", "CCControls"),
                "Orig": (f"CCOrig{n}Case", f"CCOrig{n}CaseN", f"CC{n}Ctrl", f"CC{n}CtrlN"),
                "NoOwn": (f"CCNoOwn{n}Case", f"CCNoOwn{n}CaseN", f"CC{n}Ctrl", f"CC{n}CtrlN"),
                "NoOrg": (f"CCNoOrg{n}Case", f"CCNoOrg{n}CaseN", f"CCNoOrg{n}Ctrl", f"CCNoOrg{n}CtrlN")}
        if n == "BigThirty":
            rows["Fourteen"] = ("CCBigFourteenCase", "CCBigFourteenCaseN", "CCBigFourteenCtrl", "CCBigFourteenCtrlN")
        for row, (k1, n1, k0, n0) in rows.items():
            k1, n1, k0, n0 = (out[x] for x in (k1, n1, k0, n0))
            out[f"CCP{row}{n}"] = fmt_p(fisher_p(k1, n1 - k1, k0, n0 - k0))
    return out


def fisher_p(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact test for the table [[a, b], [c, d]]: the probability of tables with the
    same margins that are no more likely than the observed one."""
    from math import comb
    r1, r2, c1 = a + b, c + d, a + c
    total = comb(r1 + r2, c1)
    pmf = lambda x: comb(r1, x) * comb(r2, c1 - x) / total
    p_obs = pmf(a)
    return min(1.0, sum(p for x in range(max(0, c1 - r2), min(r1, c1) + 1)
                        if (p := pmf(x)) <= p_obs * (1 + 1e-7)))


def fmt_p(p: float) -> str:
    return "$<$0.001" if p < 0.001 else f"{p:.3f}"


def extra_numbers(pool: list[dict], adoption: list[dict], head: dict, gen: list[dict]) -> dict:
    """Observation window, equal follow-up, stratified review estimate, wide report bound."""
    import csv
    out = {}
    heads = sorted(v["head_date"] for v in head.values())
    out["SnapshotLatest"] = date.fromisoformat(heads[-1]).strftime("%-d %B %Y") if False else \
        f"{int(heads[-1][8:])} {date.fromisoformat(heads[-1]).strftime('%B %Y')}"

    # equal follow-up: included within 180 days of the source, among papers with 180 days of exposure
    first_landing: dict[str, str] = {}
    for r in adoption:
        if r.get("arxiv") and r["first_adoption_date"]:
            a = r["arxiv"]
            first_landing[a] = min(first_landing.get(a, "9999"), r["first_adoption_date"])
    src_date = {r["arxiv"]: r["source_date"] for r in adoption if r.get("arxiv")}
    cutoff = date.fromisoformat(heads[-1])
    pool_dates = {}
    papers = json.loads((GEN / "papers.json").read_text(encoding="utf-8"))["papers"]
    frame = {r["arxiv"]: r for r in read_jsonl(GEN / "arxiv_frame.jsonl")}
    def pub(a):
        """First-version date when known; otherwise the last day of the identifier's month, so that a
        paper counts as eligible only if 180 days have passed whatever its day of publication."""
        if a in papers:
            return date.fromisoformat(papers[a]["published"])
        y, m = 2000 + int(a[:2]), int(a[2:4])
        return (date(y + (m == 12), m % 12 + 1, 1) - date.resolution)
    eligible = [r for r in gen if (cutoff - pub(r["arxiv"])).days >= 180]
    within = [r for r in eligible if r["arxiv"] in first_landing
              and (date.fromisoformat(first_landing[r["arxiv"]]) - pub(r["arxiv"])).days <= 180]
    out["NFollowEligible"], out["NFollowIncluded"] = len(eligible), len(within)

    # supply and inclusion by quarter of the first version, for quarters whose every paper has
    # 180 days of exposure; a paper counts as included when a framework took it in within 180 days
    def quarter(d: date) -> str:
        return f"{d.year}Q{(d.month - 1) // 3 + 1}"
    within_ids = {r["arxiv"] for r in within}
    by_q: dict[str, list[dict]] = {}
    for r in gen:
        by_q.setdefault(quarter(pub(r["arxiv"])), []).append(r)
    full = []
    for qname in sorted(by_q):
        y, qn = int(qname[:4]), int(qname[-1])
        q_end = date(y + (qn == 4), (qn % 4) * 3 + 1, 1) - date.resolution
        if (cutoff - q_end).days >= 180:
            full.append(qname)
    series = [{"quarter": qname, "general": len(by_q[qname]),
               "included_180": sum(r["arxiv"] in within_ids for r in by_q[qname])} for qname in full]
    # the same quarters counted by the date of the landing: first landings of general papers
    landed_q = Counter(quarter(date.fromisoformat(first_landing[r["arxiv"]]))
                       for r in gen if r["adopted"] and r["arxiv"] in first_landing)
    for sr in series:
        sr["landed"] = landed_q.get(sr["quarter"], 0)
    out["LandFirst"] = series[0]["landed"]
    out["LandLast"] = series[-1]["landed"]
    peak = max(series, key=lambda sr: sr["landed"])
    out["LandPeak"], out["LandPeakQuarter"] = peak["landed"], peak["quarter"]
    out["QRateFirst"] = f"{100 * series[0]['included_180'] / series[0]['general']:.1f}"
    out["QRateLast"] = f"{100 * series[-1]['included_180'] / series[-1]['general']:.1f}"
    (GEN / "quarterly.json").write_text(json.dumps(series, indent=1) + "\n", encoding="utf-8", newline="\n")
    out["NQuarters"] = len(series)
    out["QFirst"], out["QLast"] = series[0]["quarter"], series[-1]["quarter"]
    out["QSupplyFirst"], out["QSupplyLast"] = series[0]["general"], series[-1]["general"]
    out["QSupplyRatio"] = f"{series[-1]['general'] / series[0]['general']:.1f}"
    out["QIncMin"] = min(s["included_180"] for s in series)
    out["QIncMax"] = max(s["included_180"] for s in series)
    out["QIncTotal"] = sum(s["included_180"] for s in series)
    out["QSupplyTotal"] = sum(s["general"] for s in series)
    partial = [qname for qname in sorted(by_q) if qname not in full]
    out["QPartialGeneral"] = sum(len(by_q[qname]) for qname in partial)

    # manual review reweighted by the three label strata of the sample
    labels = {json.loads(l)["arxiv"]: json.loads(l) for l in
              (GEN / "triage" / "labels.jsonl").read_text(encoding="utf-8").split(chr(10)) if l.strip()}
    with (GEN / "triage" / "review_sample.csv").open(encoding="utf-8-sig") as f:
        hs = list(csv.DictReader(f))
    def stratum(g):
        return g.get("scope") if g["label"] == "rl_method" else "other"
    rates = {}
    for s_ in ("general", "embedded", "other"):
        rows = [r for r in hs if r["arxiv"] in labels and stratum(labels[r["arxiv"]]) == s_]
        rates[s_] = (sum(r["review_label"] == "general" for r in rows), len(rows))
    sizes = Counter(stratum(g) for a, g in labels.items() if a in frame)
    est = sum(sizes[s_] * k / n for s_, (k, n) in rates.items() if n)
    for s_, nm in (("general", "Gen"), ("embedded", "Emb"), ("other", "Oth")):
        out[f"Review{nm}Hit"], out[f"Review{nm}N"] = rates[s_]
    out["ReviewEstimate"] = int(round(est, -1))
    return out


def report_numbers(pool: list[dict]) -> dict:
    """Model reports read in full: how many hide or overstate a general RL component.

    With main-contribution judgments available, the scaled change to the general denominator
    uses the same rule as the denominator. Without them, only the raw counts are returned.
    """
    key = json.loads((ROOT / ".cache" / "casecontrol_key.json").read_text(encoding="utf-8"))
    rep = {g["arxiv"]: g for g in read_jsonl(GEN / "casecontrol" / "report_filled.jsonl")}
    sp = GEN / "casecontrol" / "report_scope.jsonl"
    scope = {g["arxiv"]: g.get("main_contribution") for g in read_jsonl(sp)} if sp.exists() else {}
    by_id = {r["arxiv"]: r for r in pool}
    rm, ro = key["reports_labelled_method"], key["reports_labelled_other"]
    comp = lambda a: rep[a]["has_rl_component"] == "yes" and rep[a].get("general") is True
    out = {"NReportsRead": len(rm) + len(ro), "NReportsMethod": len(rm), "NReportsOther": len(ro),
           "NReportsMethodGen": sum(comp(a) for a in rm if a in rep),
           "NReportsOtherGen": sum(comp(a) for a in ro if a in rep)}
    # wide bound: every report with a transferable component counts as a general method
    reports_all = [r for r in pool if r["is_model_report"] and not r["adopted"]]
    pop_m = sum(r["label"] == "rl_method" for r in reports_all)
    pop_o = len(reports_all) - pop_m
    pop_mg = sum(r["strict_general"] for r in reports_all)
    wide = pop_m * out["NReportsMethodGen"] / len(rm) + pop_o * out["NReportsOtherGen"] / len(ro) - pop_mg
    out["NReportAdjWide"] = int(round(wide))
    gen_n = sum(r["strict_general"] for r in pool)
    inc_n = sum(r["strict_general"] and r["adopted"] for r in pool)
    out["NReportAdjWidePct"] = int(round(100 * wide / gen_n))
    out["RateWide"] = f"{100 * inc_n / (gen_n + wide):.1f}"
    out["RateMain"] = f"{100 * inc_n / gen_n:.1f}"
    if scope and all(a in scope for a in rm + ro):
        # general under the denominator rule: transferable component that is the main contribution
        main = lambda a: comp(a) and scope.get(a) is True
        reports = [r for r in pool if r["is_model_report"] and not r["adopted"]]
        pop_other = sum(r["label"] != "rl_method" for r in reports)
        pop_method_general = sum(r["strict_general"] for r in reports)
        sampled_method_general = [a for a in rm if by_id[a]["strict_general"]]
        add = pop_other * sum(main(a) for a in ro) / len(ro)
        drop = (pop_method_general * sum(not main(a) for a in sampled_method_general) / len(sampled_method_general)
                if sampled_method_general else 0.0)
        out.update({"NReportsOtherMain": sum(main(a) for a in ro), "NReportsPopOther": pop_other,
                    "NReportsPopMethodGeneral": pop_method_general,
                    "NReportsSampledMethodGeneral": len(sampled_method_general),
                    "NReportsSampledMethodGeneralMain": sum(main(a) for a in sampled_method_general),
                    "NReportAdj": int(round(add - drop)),
                    "NReportAdjPctMain": f"{100 * (add - drop) / max(1, sum(r['strict_general'] for r in pool)):.1f}"})
    return out


SYMPTOM_SHORT = {"critic_cost": "value-model cost", "high_variance": "gradient variance",
                 "entropy_collapse": "entropy collapse", "length_bias": "length bias",
                 "zero_gradient_groups": "groups without signal", "truncation_noise": "truncation noise",
                 "train_infer_mismatch": "rollout-training mismatch", "moe_instability": "MoE instability",
                 "ratio_outliers": "extreme ratios", "stale_policy": "stale data",
                 "multi_reward_collapse": "multi-reward collapse", "diversity_loss": "diversity loss",
                 "sparse_reward": "sparse reward"}
FW = {"verl": "verl", "trl": "TRL", "openrlhf": "OpenRLHF", "nemo-rl": "NeMo-RL", "roll": "ROLL",
      "slime": "slime", "areal": "AReaL"}


TABLE_NAME = {"tis": "Truncated importance sampling (TIS)", "mis": "Masked importance sampling (MIS)",
              "dapo_overlong": "Overlong filtering and penalty"}


def tex(s: str) -> str:
    return s.replace("&", r"\&").replace("_", r"\_").replace("%", r"\%")


def write_tables(adoption: list[dict], head: dict) -> None:
    keys = json.loads((GEN / "papers.json").read_text(encoding="utf-8"))["methods"]
    bib = {r["arxiv"]: "arxiv" + r["arxiv"].replace(".", "") for r in keys.values() if r.get("arxiv")}
    rows = [r for r in adoption if (r["source_date"] or "") >= "2025-01-01" and r["n_frameworks_at_head"] >= 3]
    rows.sort(key=lambda r: (-r["n_frameworks_at_head"], r["source_date"]))
    nl, row_end = chr(10), r" \\"
    lines = []
    notes = []
    for r in rows:
        key = bib.get(r.get("arxiv")) or "yao2025tis"
        src = r"\citep{" + key + "}"
        if r["first_lag_days"] is None:
            lag = "--"
        else:
            lag = (r"$\le$" if r["first_lag_is_upper_bound"] else "") + str(r["first_lag_days"])
        sym = ", ".join(SYMPTOM_SHORT[s] for s in r["symptoms"]) or "--"
        name = TABLE_NAME.get(r["id"], r["name"].split(" (")[0])
        d_un = [FW[f] for f, t in r["frameworks_at_head"].items() if t == "default"]
        d_co = [FW[f] for f, t in r["frameworks_at_head"].items() if t == "conditional_default"]
        if d_un:
            notes.append(f"{name[0].lower() + name[1:]} is a default in " + ", ".join(d_un))
        elif d_co:
            notes.append(f"{name[0].lower() + name[1:]} is a conditional default in " + ", ".join(d_co))
        lines.append(f"{tex(name)} & {src} & {r['source_date']} & {r['n_frameworks_at_head']} & {lag} & {sym}" + row_end)
    head_wide = [
        r"\begin{tabularx}{\linewidth}{>{\raggedright\arraybackslash}p{3.7cm} l l "
        r">{\raggedright\arraybackslash}p{1.7cm} r >{\raggedright\arraybackslash}X}",
        r"\toprule",
        r"Method & Source & First public & Frameworks & Days & Failure it addresses \\",
        r"\midrule",
    ]
    tail = [r"\bottomrule"]
    out = nl.join(head_wide + lines + tail + [r"\end{tabularx}"]) + nl
    (ROOT / "paper" / "table_wide.tex").write_text(out, encoding="utf-8", newline=nl)
    # the defaults go into the caption through a macro, so the Frameworks column stays a count
    note = ("Of these, " + " and ".join(notes) + ".") if notes else ""
    (ROOT / "paper" / "table_wide_note.tex").write_text(
        r"\newcommand{\WideDefaultsNote}{" + tex(note) + "}" + nl, encoding="utf-8", newline=nl)

    snap = []
    for f, v in head.items():
        label = "verl recipes" if f == "verl_recipe" else FW[f]
        url = v["url"].replace("https://", "")
        snap.append(f"{label} & " + r"\url{" + url + "} & " + r"\texttt{" + v["head_sha"][:10] + "} & "
                    + v["head_date"] + row_end)
    head_snap = [r"\begin{tabular}{llll}", r"\toprule", r"Framework & Repository & Commit & Date \\", r"\midrule"]
    out = nl.join(head_snap + snap + tail + [r"\end{tabular}"]) + nl
    (ROOT / "paper" / "table_snapshot.tex").write_text(out, encoding="utf-8", newline=nl)

    # included papers that do not meet the general-method rule, listed with their methods
    pool = read_jsonl(GEN / "pool_adoption.jsonl")
    names = {r["id"]: TABLE_NAME.get(r["id"], r["name"].split(" (")[0]) for r in adoption}
    exc = []
    for r in sorted((r for r in pool if r["adopted"] and not r["strict_general"]), key=lambda r: r["arxiv"]):
        lab = r["label"].replace("rl_", "RL ").replace("_", " ")
        lab = lab[0].upper() + lab[1:]
        if r["label"] == "rl_method":
            lab += f" ({r['scope']})"
        rep = "yes" if r["is_model_report"] else "no"
        meths = ", ".join(tex(names[m]) for m in r["methods"])
        exc.append(r"\citet{arxiv" + r["arxiv"].replace(".", "") + "} & " + lab + " & " + rep + " & " + meths + row_end)
    head_exc = [r"\begin{tabularx}{\linewidth}{l l l >{\raggedright\arraybackslash}X}", r"\toprule",
                r"Source & Abstract label & Model report & Included methods \\", r"\midrule"]
    out = nl.join(head_exc + exc + tail + [r"\end{tabularx}"]) + nl
    (ROOT / "paper" / "table_exceptions.tex").write_text(out, encoding="utf-8", newline=nl)


FW_SHORT = {"verl": "verl", "trl": "TRL", "openrlhf": "OpenRLHF", "nemo-rl": "NeMo-RL", "roll": "ROLL",
            "slime": "slime", "areal": "AReaL"}
NON_ARXIV_CITE = {"tis": r"\citet{yao2025tis}", "kl_k3": r"\citet{schulman2020kl}"}


def profile_tables(adoption: list[dict], head: dict) -> dict:
    """Framework profile table, option names of widely included methods, and the full catalog."""
    nl, row_end = chr(10), r" \\"
    prof = json.loads((GEN / "framework_profiles.json").read_text(encoding="utf-8"))
    tmap = yaml.safe_load((ROOT / "config" / "token_map.yaml").read_text(encoding="utf-8"))
    papers = json.loads((GEN / "papers.json").read_text(encoding="utf-8"))["methods"]
    out = {}

    # ---- framework profiles: methods, speed, and the pull requests that brought methods in
    proc = json.loads((GEN / "process" / "summary.json").read_text(encoding="utf-8"))["by_framework"]
    order = ["verl", "trl", "areal", "nemo-rl", "roll", "slime", "openrlhf"]
    rows = []
    for fw in order:
        p = prof["frameworks"][fw]
        q = proc.get(fw, {})
        lag = "--" if p["median_lag"] is None else f"{p['median_lag']:g}"
        n_pr = q.get("landing_prs", 0)
        maint = f"{q['author_prior_merger']} of {n_pr}" if n_pr else "--"
        dopen = "--" if q.get("median_days_open") is None else f"{q['median_days_open']:g}"
        att = q.get("attempts", 0)
        turned = q.get("attempts_declined", 0) + q.get("attempts_redirected", 0)
        rows.append(f"{FW_SHORT[fw]} & {p['methods_ever']} & {p['first_anywhere']} & {lag} & {maint} & {dopen} & "
                    f"{att} & {q.get('attempts_open', 0)} & {turned} & "
                    f"{q.get('attempts_stale', 0)}" + row_end)
        key = FW_SHORT[fw].replace("-", "")
        out[f"Prof{key}Methods"] = p["methods_ever"]
        out[f"Prof{key}First"] = p["first_anywhere"]
        out[f"Prof{key}Lag"] = lag
        out[f"Pr{key}Land"] = n_pr
        out[f"Pr{key}Maint"] = q.get("author_prior_merger", 0)
        out[f"Pr{key}Att"] = att
        out[f"Pr{key}AttOpen"] = q.get("attempts_open", 0)
        out[f"Pr{key}AttDeclined"] = turned
        out[f"Pr{key}AttStale"] = q.get("attempts_stale", 0)
    head_rows = [r"\begin{tabular}{lrrrrrrrrr}", r"\toprule",
                 r" & & First & Median & \multicolumn{2}{c}{Landing pull requests} & \multicolumn{4}{c}{Proposals for other methods} \\",
                 r"\cmidrule(lr){5-6} \cmidrule(lr){7-10}",
                 r"Framework & Methods & anywhere & days & By a prior merger & Days open & All & Open & Declined & Lapsed \\",
                 r"\midrule"]
    (ROOT / "paper" / "table_frameworks.tex").write_text(
        nl.join(head_rows + rows + [r"\bottomrule", r"\end{tabular}"]) + nl, encoding="utf-8", newline=nl)
    out["NRecentLandings"] = sum(p["methods_ever"] for p in prof["frameworks"].values())
    removed = [(fw, r) for fw, p in prof["frameworks"].items() for r in p["removed"]]
    out["NRemoved"] = len(removed)

    # ---- option names of widely included methods
    wide = [r for r in adoption if (r["source_date"] or "") >= "2025-01-01" and r["n_frameworks_at_head"] >= 3]
    wide.sort(key=lambda r: (-r["n_frameworks_at_head"], r["source_date"]))
    names_by = {r["id"]: defaultdict(list) for r in wide}
    for fw, info in head.items():
        label = "verl" if fw == "verl_recipe" else fw
        for sid, toks in info["surfaces"].items():
            smap = tmap.get(fw, {}).get(sid, {})
            for tok in toks:
                tok0 = tok.split("=")[0]
                m = smap.get(tok0)
                ms = m if isinstance(m, list) else [m]
                for mid in ms:
                    if mid in names_by:
                        shown = ("recipe/" + tok0) if sid == "recipe" else tok0
                        if shown not in names_by[mid][label]:
                            names_by[mid][label].append(shown)
    crow = []
    for r in wide:
        parts = []
        for fw in ["verl", "trl", "openrlhf", "nemo-rl", "roll", "slime", "areal"]:
            toks = names_by[r["id"]].get(fw)
            if toks:
                parts.append(FW_SHORT[fw] + ": " + ", ".join(r"\texttt{" + tex(t) + "}" for t in sorted(toks)))
        name = TABLE_NAME.get(r["id"], r["name"].split(" (")[0])
        crow.append(tex(name) + " & " + "; ".join(parts) + row_end + r" \addlinespace[3pt]")
    head_c = [r"\begin{tabularx}{\linewidth}{>{\raggedright\arraybackslash}p{3.2cm} >{\raggedright\arraybackslash}X}",
              r"\toprule", r"Method & Option names at the snapshot \\", r"\midrule"]
    (ROOT / "paper" / "table_configs.tex").write_text(
        nl.join(head_c + crow + [r"\bottomrule", r"\end{tabularx}"]) + nl, encoding="utf-8", newline=nl)

    # ---- full catalog (longtable)
    keys = {r["arxiv"]: "arxiv" + r["arxiv"].replace(".", "") for r in papers.values() if r.get("arxiv")}
    cat = []
    for r in sorted(adoption, key=lambda r: (r["source_date"] or "9999", r["id"])):
        if r.get("arxiv"):
            src = r"\citet{" + keys[r["arxiv"]] + "}"
        else:
            src = NON_ARXIV_CITE.get(r["id"], "framework" if r["source_status"] == "non_arxiv" else "--")
        fws = ", ".join(FW_SHORT[f] for f in ["verl", "trl", "openrlhf", "nemo-rl", "roll", "slime", "areal"]
                        if f in r["frameworks_at_head"]) or "removed"
        first = r["first_adoption_date"] or "--"
        if r["first_lag_is_upper_bound"]:
            first = r"$\le$" + first
        name = TABLE_NAME.get(r["id"], r["name"])
        cat.append(f"{tex(name)} & {src} & {r['source_date'] or '--'} & {first} & {fws}" + row_end)
    head_l = [r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{3.5cm} >{\raggedright\arraybackslash}p{2.3cm} l l "
              r">{\raggedright\arraybackslash}p{2.9cm}@{}}",
              r"\caption{\textbf{Method catalog.} Unit: catalog method. First landing is the earliest main-branch "
              r"commit in any framework, with $\le$ for upper bounds. Frameworks list where the method is offered at "
              r"the snapshot.}\label{tab:catalog} \\",
              r"\toprule", r"Method & Source & First public & First landing & Frameworks now \\", r"\midrule",
              r"\endfirsthead", r"\toprule", r"Method & Source & First public & First landing & Frameworks now \\",
              r"\midrule", r"\endhead", r"\bottomrule", r"\endfoot"]
    (ROOT / "paper" / "table_catalog.tex").write_text(
        nl.join(head_l + cat + [r"\end{longtable}"]) + nl, encoding="utf-8", newline=nl)
    out["NCatalogMethods"] = len(adoption)
    return out


if __name__ == "__main__":
    main()
