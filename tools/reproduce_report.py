"""Rebuild every number, table and figure of the report from the frozen inputs, then compile it.

This fetches nothing. It checks the frozen inputs against data/release/inputs.sha256, restores
the sampling keys from data/release/ when the private cache is absent, and regenerates the
report's numbers, tables and figures. Use tools/update.py to refresh the tracker instead; that
command moves the framework snapshot forward and therefore changes the report's inputs.

  python tools/reproduce_report.py              # verify inputs, rebuild numbers, tables, figures
  python tools/reproduce_report.py --pdf        # also compile paper/main.pdf (needs pdflatex, bibtex)
  python tools/reproduce_report.py --freeze     # write data/release/inputs.sha256 (maintainers only)
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REL = ROOT / "data" / "release"
MANIFEST = REL / "inputs.sha256"

# Every file the report's numbers depend on. Generated outputs (adoption.json, pool_adoption.jsonl,
# numbers.tex, figures) are rebuilt from these and are not part of the frozen set.
INPUTS = [
    "config/frameworks.yaml", "config/token_map.yaml", "config/triage_rules.md",
    "data/methods.yaml", "data/symptoms.yaml",
    "data/generated/framework_events.jsonl", "data/generated/framework_head.json",
    "data/generated/unmapped.json", "data/generated/papers.json", "data/generated/harvest_meta.json",
    "data/generated/arxiv_frame.jsonl",
    "data/generated/triage/labels.jsonl", "data/generated/triage/validation.md",
    "data/generated/triage/review_sample.csv",
    "data/generated/casecontrol/cc_papers.jsonl", "data/generated/casecontrol/cc_filled.jsonl",
    "data/generated/casecontrol/cc_v1_filled.jsonl", "data/generated/casecontrol/report_papers.jsonl",
    "data/generated/casecontrol/report_filled.jsonl", "data/generated/casecontrol/report_scope.jsonl",
    "data/generated/casecontrol/coding_overrides.json",
    "data/generated/casecontrol/cc_v1_audit_added.jsonl", "data/generated/framework_profiles.json",
    "data/generated/impl_links.json",
    "data/generated/github/threads.jsonl", "data/generated/github/mentions.jsonl",
    "data/generated/github/merged_prs.jsonl", "data/generated/github/code_citations.jsonl",
    "data/generated/github/pr_facts.jsonl", "data/generated/github/fetch_meta.json",
    "data/generated/process/attempts_coded.jsonl", "data/generated/process/citation_audit.jsonl",
    "data/generated/process/attempt_replies.jsonl", "data/generated/process/attempts_first_coding.jsonl",
    "data/generated/process/landing_prs_coded.jsonl", "data/generated/process/attempts_round6_coded.jsonl",
    "data/generated/process/attempts_recode.jsonl", "data/generated/casecontrol/cc_v1_audit_added_first_coding.jsonl",
    "data/generated/casecontrol/cc_v1_blind_recode.jsonl", "data/generated/casecontrol/cc_v1_blind_recode2.jsonl",
    "data/release/triage_manifest.json", "data/release/casecontrol_key.json",
    "data/release/blind_recode_key.json", "data/release/blind_recode2_key.json",
    "config/framework_orgs.yaml", "data/generated/casecontrol/included_orgs.jsonl",
    "data/generated/process/name_audit.jsonl", "data/generated/framework_candidates.json",
    "data/generated/process/issue_failures.jsonl", "data/generated/process/issue_recall_sample.jsonl",
    "data/generated/casecontrol/model_reports.jsonl",
]


def sha256(path: Path) -> str:
    """Digest of the file with line endings normalised, so a checkout with CRLF or LF matches."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def freeze() -> None:
    lines = [f"{sha256(ROOT / p)}  {p}" for p in INPUTS]
    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {MANIFEST.relative_to(ROOT)} ({len(lines)} files)")


def verify() -> bool:
    if not MANIFEST.exists():
        print("no data/release/inputs.sha256; run with --freeze first")
        return False
    ok = True
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        digest, path = line.split("  ", 1)
        f = ROOT / path
        if not f.exists():
            print(f"MISSING  {path}")
            ok = False
        elif sha256(f) != digest:
            print(f"CHANGED  {path}")
            ok = False
    print("inputs match the frozen manifest" if ok else "inputs differ from the frozen manifest")
    return ok


def run(*args: str, cwd: Path = ROOT) -> None:
    print("$", " ".join(args), flush=True)
    subprocess.run(list(args), cwd=cwd, check=True)


def main() -> int:
    if "--freeze" in sys.argv:
        freeze()
        return 0
    if not verify():
        return 1
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    for name in ("triage_manifest.json", "casecontrol_key.json"):
        if not (cache / name).exists():
            shutil.copy(REL / name, cache / name)
    py = sys.executable
    run(py, "tools/summary.py")
    run(py, "tools/adoption_rate.py")
    run(py, "tools/process_analysis.py")
    run(py, "tools/process_agreement.py")
    run(py, "tools/paper_numbers.py")
    run(py, "tools/paper_figs.py")
    run(py, "tools/validate.py")
    if "--pdf" in sys.argv:
        paper = ROOT / "paper"
        for step in (["pdflatex", "-interaction=nonstopmode", "main.tex"], ["bibtex", "main"],
                     ["pdflatex", "-interaction=nonstopmode", "main.tex"],
                     ["pdflatex", "-interaction=nonstopmode", "main.tex"]):
            res = subprocess.run(step, cwd=paper, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode != 0 and step[0] == "bibtex":
                print("bibtex reported a problem; see paper/main.blg")
        print("compiled paper/main.pdf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
