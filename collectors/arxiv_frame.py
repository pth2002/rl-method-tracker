"""Build the denominator: arXiv papers in the window that could be RL post-training methods.

Reads the full local harvest from collectors/arxiv_oai.py (the search API misses papers whose
abstracts write names in LaTeX), strips LaTeX, and tags each paper with mechanical flags.
The flags only narrow the pool. Whether a paper proposes an objective-level change for LLM RL
is decided later by triage, not here.

  python collectors/arxiv_frame.py

Writes data/generated/arxiv_frame.jsonl: every LLM + RL paper in the window with its flags.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / ".cache" / "arxiv" / "cs_records.jsonl"
OUT = ROOT / "data" / "generated" / "arxiv_frame.jsonl"

# Acronyms that are baselines, not new proposals, when they appear in a title.
KNOWN = {"PPO", "DPO", "GRPO", "TRPO", "SPPO", "IPO", "KTO", "ORPO", "SIMPO", "CPO", "RLOO"}
LLM_RE = re.compile(r"\b(LLMs?|language models?|reasoning models?|thinking models?|LRMs?|chain[- ]of[- ]thought|"
                    r"VLMs?|MLLMs?)\b", re.I)
RL_RE = re.compile(r"\b(GRPO|PPO|RLVR|RLHF|RLAIF|policy optimi[sz]ation|policy gradients?|verifiable rewards?|"
                   r"reinforcement[- ]learning|reinforcement[- ]fine[- ]?tuning|reinforced fine[- ]?tuning)\b", re.I)
# The bare abbreviations are matched case-sensitively so that "rl" inside other words never counts.
RL_ABBR_RE = re.compile(r"\b(RL|RFT|ReFT)\b")
OBJECTIVE_RE = re.compile(r"\b(GRPO|PPO|RLVR|policy optimi[sz]ation|policy gradients?|advantage|importance (sampling|ratio)|"
                          r"clip(ping)?|trust region|on-policy|off-policy|entropy collapse|KL (penalty|divergence))\b", re.I)
PROPOSE_RE = re.compile(r"\b(we|this (paper|work|report))( also)? (propose|introduce|present|develop|design)s?\b|"
                        r"\b(propose|introduce|present)s? (a|an|the)\b", re.I)
ACRO_RE = re.compile(r"\b([A-Z][A-Za-z0-9\-]*PO)\b")


def strip_latex(text: str) -> str:
    text = re.sub(r"\$\\(?:textbf|textit|mathbf|mathrm|text|emph)\{([^}]*)\}\$", r"\1", text)
    text = re.sub(r"\\(?:textbf|textit|mathbf|mathrm|text|emph|texttt)\{([^}]*)\}", r"\1", text)
    text = text.replace("$", "")
    return re.sub(r"\s+", " ", text)


def main() -> None:
    methods = yaml.safe_load((ROOT / "data" / "methods.yaml").read_text(encoding="utf-8"))
    catalog = {m["source"]["arxiv"] for m in methods if (m.get("source") or {}).get("arxiv")}
    papers_json = ROOT / "data" / "generated" / "papers.json"
    if papers_json.exists():
        resolved = json.loads(papers_json.read_text(encoding="utf-8"))["methods"]
        catalog |= {r["arxiv"] for r in resolved.values() if r.get("arxiv")}

    seen: dict[str, dict] = {}
    for line in SRC.read_text(encoding="utf-8").split(chr(10)):
        if line.strip():
            p = json.loads(line)
            seen[p["arxiv"]] = p  # later lines are newer versions of the same record

    rows = []
    for p in seen.values():
        title, abstract = strip_latex(p["title"]), strip_latex(p["abstract"])
        text = f"{title} {abstract}"
        if not (LLM_RE.search(text) and (RL_RE.search(text) or RL_ABBR_RE.search(text))):
            continue
        acronyms = sorted({a for a in ACRO_RE.findall(title) if a.upper() not in KNOWN})
        rows.append({
            "arxiv": p["arxiv"], "title": title, "abstract": abstract, "authors": p["authors"],
            "month": "20" + p["arxiv"][:2] + "-" + p["arxiv"][2:4], "categories": p["categories"],
            "flags": {
                "objective_terms": bool(OBJECTIVE_RE.search(text)),
                "proposes": bool(PROPOSE_RE.search(abstract)),
                "title_po_acronym": acronyms,
                "in_catalog": p["arxiv"] in catalog,
            },
        })
    rows.sort(key=lambda r: r["arxiv"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    narrow = [r for r in rows if r["flags"]["objective_terms"] and r["flags"]["proposes"]]
    named = [r for r in narrow if r["flags"]["title_po_acronym"]]
    print(f"harvested {len(seen)} cs.LG/CL/AI records; LLM+RL {len(rows)}; "
          f"+objective terms and a proposal {len(narrow)}; +new *PO acronym in title {len(named)}")
    print("catalog papers found in pool:", sum(r["flags"]["in_catalog"] for r in rows), "of", len(catalog))
    missing = sorted(a for a in catalog if a not in {r["arxiv"] for r in rows} and a[:2] in ("25", "26"))
    print("catalog papers in window but outside the pool:", missing)
    print("named per month:", dict(sorted(Counter(r["month"] for r in named).items())))


if __name__ == "__main__":
    main()
