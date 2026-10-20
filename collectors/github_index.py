"""Index the downloaded GitHub record and find every mention of a candidate paper.

Reads the raw pages written by collectors/github_threads.py and writes, under
data/generated/github/:

  threads.jsonl   one row per issue, pull request or discussion (metadata only, no text)
  mentions.jsonl  one row per (paper, thread, place) where a paper is mentioned
  xrefs.jsonl     issue numbers that a pull request says it fixes, closes or resolves

A paper can be mentioned in four ways, kept apart because their precision differs:
  link   its arXiv identifier inside an arXiv, Hugging Face papers or alphaXiv URL, or after "arXiv:"
  bare   its arXiv identifier without such context
  title  its full title (normalised, at least five words)
  name   the method name from its abstract label, as a whole word with its capitalisation
The first three identify the paper. A name match only says the name occurs and is checked by hand.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "github"
OUT = ROOT / "data" / "generated" / "github"
GEN = ROOT / "data" / "generated"

REPOS = {
    "verl": "verl-project/verl",
    "verl_recipe": "verl-project/verl-recipe",
    "trl": "huggingface/trl",
    "openrlhf": "OpenRLHF/OpenRLHF",
    "nemo-rl": "NVIDIA-NeMo/RL",
    "roll": "alibaba/ROLL",
    "slime": "THUDM/slime",
    "areal": "areal-project/AReaL",
}

ID_RE = re.compile(r"(?<![\d.])(\d{4}\.\d{4,5})(?:v\d+)?(?![\d])")
LINK_RE = re.compile(r"(arxiv\.org/(?:abs|pdf|html)/|arxiv:\s*|huggingface\.co/papers/|alphaxiv\.org/(?:abs|overview)/)$", re.I)
XREF_RE = re.compile(r"\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s*:?\s+(?:[\w.-]+/[\w.-]+)?#(\d+)", re.I)
# method names that are ordinary words or framework terms and would match everywhere
NAME_STOP = {"ECHO", "GRPO", "PPO", "RLOO", "DPO", "KL", "RL", "LLM", "SFT", "REINFORCE", "TRL", "ROLL", "AReaL",
             "slime", "verl", "VERL", "TROLL", "REFT", "TLDR"}
# all-capital method names that are also English words or common proper names
NAME_STOP |= set("""ALIVE ARIA ARISE BARD BASIS BOOST BOTS BREAD BRIDGE CAMEL CANON CARL CAST CHORD CLEANER COBALT
COVER CRAFT CURE DARLING DARTS DASH DEFT DIET DISCO DITTO DIVER DUEL DUET DUMP EASE ENIGMA ESSA FEST GASP GIFT
GLANCE GLIDER GOLF GRAB GRADE GRAIL GRAPE GRIP GROW HAMMER HAWKEYE HEAL HELIX HIPPO HIVE IMAGINE IMAX IRIS LACONIC
LADDER LANG LEAD LEAF LEMON LESS LOOP MAESTRO MAGE MAGIC MARS MARSHAL MASH MEDS MENTOR METIS MICA MONA MOTIF
MURPHY OASES OPERA ORBIT PASS PIVOT PODS POETS POLARIS PURE RADAR RAPID RARE RECAP REFINE RENT RESTRAIN RISE
RIVAL ROMA ROSE ROVER RULES SABER SALT SAVE SAVOIR SCALER SCAR SCOPE SCORE SEELE SEGA SENTINEL SIGHT SIREN SIRI
SLATE SLIM SMART SOAR SOPHIA SPARK SPEAR SPECTRA SPEED SPELL SPINE SPIRAL STACK START STARE STEER STITCH SWAP
TANDEM TEMPO TIPS TRUST TRUSTEE VIGIL VIGOR VISOR""".split())
# capitalised ordinary words are dropped unless they are coined names
NAME_KEEP_TITLE = {"Delethink", "Entrocraft", "Intuitor", "Lopti", "Pixelis", "Seirenes"}


def pages(repo: str, kind: str) -> list[dict]:
    d = CACHE / repo.replace("/", "__") / kind
    rows = []
    for f in sorted(d.glob("*.json")):
        rows += json.loads(f.read_text(encoding="utf-8"))
    return rows


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " " + " ".join(s.split()) + " "


def load_papers() -> tuple[set[str], dict[str, list[tuple[str, str]]], dict[str, str]]:
    pool = [json.loads(l) for l in (GEN / "pool_adoption.jsonl").read_text(encoding="utf-8").splitlines() if l]
    frame = {json.loads(l)["arxiv"]: json.loads(l) for l in (GEN / "arxiv_frame.jsonl").read_text(encoding="utf-8").splitlines() if l}
    labels = {json.loads(l)["arxiv"]: json.loads(l) for l in (GEN / "triage" / "labels.jsonl").read_text(encoding="utf-8").splitlines() if l}
    ids = {p["arxiv"] for p in pool}
    papers = json.loads((GEN / "papers.json").read_text(encoding="utf-8"))["papers"]
    ids |= set(papers)
    # titles of rl_method papers, indexed by their first three words
    by_head: dict[str, list[tuple[str, str]]] = defaultdict(list)
    name_papers: dict[str, set[str]] = defaultdict(set)
    for p in pool:
        if labels.get(p["arxiv"], {}).get("label") != "rl_method":
            continue
        t = norm(frame.get(p["arxiv"], {}).get("title", ""))
        words = t.split()
        if len(words) >= 5:
            by_head[" ".join(words[:3])].append((t, p["arxiv"]))
        nm = (labels[p["arxiv"]].get("method_name") or "").strip()
        if re.fullmatch(r"[A-Z][a-z]+", nm) and nm not in NAME_KEEP_TITLE:
            continue
        if len(nm) >= 4 and nm not in NAME_STOP and re.search(r"[A-Z]", nm) and re.fullmatch(r"[\w\-+.]+", nm):
            name_papers[nm].add(p["arxiv"])
    # a name shared by two papers cannot identify either
    names = {k: next(iter(v)) for k, v in name_papers.items() if len(v) == 1}
    return ids, by_head, names


class Matcher:
    def __init__(self) -> None:
        self.ids, self.by_head, names = load_papers()
        self.names = names
        self.name_re = re.compile(r"(?<![\w\-])(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)) + r")(?![\w\-])")

    def find(self, text: str) -> list[tuple[str, str]]:
        if not text:
            return []
        hits: dict[str, str] = {}
        rank = {"link": 0, "title": 1, "bare": 2, "name": 3}
        for m in ID_RE.finditer(text):
            aid = m.group(1)
            if aid in self.ids:
                tier = "link" if LINK_RE.search(text[max(0, m.start() - 40):m.start()]) else "bare"
                if aid not in hits or rank[tier] < rank[hits[aid]]:
                    hits[aid] = tier
        t = norm(text)
        words = t.split()
        for i in range(len(words) - 2):
            for title, aid in self.by_head.get(" ".join(words[i:i + 3]), ()):
                if title in t and (aid not in hits or rank["title"] < rank[hits[aid]]):
                    hits[aid] = "title"
        for m in self.name_re.finditer(text):
            aid = self.names[m.group(1)]
            if aid not in hits:
                hits[aid] = "name"
        return list(hits.items())


def num_from(url: str) -> int | None:
    m = re.search(r"/(?:issues|pulls)/(\d+)$", url or "")
    return int(m.group(1)) if m else None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mt = Matcher()
    threads, mentions, xrefs = [], [], []

    def add_mentions(fw, kind, number, place, text, date, user, assoc, url):
        for aid, tier in mt.find(text):
            mentions.append({"arxiv": aid, "framework": fw, "kind": kind, "number": number, "place": place,
                             "tier": tier, "date": (date or "")[:10], "user": user, "assoc": assoc, "url": url})

    for fw, repo in REPOS.items():
        if not (CACHE / repo.replace("/", "__") / "issues").exists():
            print(f"{fw}: not downloaded yet")
            continue
        pulls = {p["number"]: p for p in pages(repo, "pulls")}
        issues = pages(repo, "issues")
        kind_of = {}
        for it in issues:
            n = it["number"]
            is_pr = "pull_request" in it
            kind = "pr" if is_pr else "issue"
            kind_of[n] = kind
            pr = pulls.get(n, {})
            threads.append({
                "framework": fw, "kind": kind, "number": n, "title": it["title"],
                "user": (it.get("user") or {}).get("login"), "assoc": it.get("author_association"),
                "created": it["created_at"][:10], "closed": (it.get("closed_at") or "")[:10] or None,
                "state": it["state"], "state_reason": it.get("state_reason"),
                "merged": (pr.get("merged_at") or (it.get("pull_request") or {}).get("merged_at") or "")[:10] or None,
                "merge_commit_sha": pr.get("merge_commit_sha") if pr.get("merged_at") else None,
                "base": (pr.get("base") or {}).get("ref"), "labels": [l["name"] for l in it.get("labels", [])],
                "n_comments": it.get("comments", 0), "url": it["html_url"]})
            text = (it["title"] or "") + "\n" + (it.get("body") or "")
            add_mentions(fw, kind, n, "opening", text, it["created_at"], (it.get("user") or {}).get("login"),
                         it.get("author_association"), it["html_url"])
            if is_pr:
                for m in XREF_RE.finditer(it.get("body") or ""):
                    xrefs.append({"framework": fw, "pr": n, "issue": int(m.group(1))})
        for c in pages(repo, "issue_comments"):
            n = num_from(c.get("issue_url"))
            add_mentions(fw, kind_of.get(n, "issue"), n, "comment", c.get("body"), c["created_at"],
                         (c.get("user") or {}).get("login"), c.get("author_association"), c["html_url"])
        for c in pages(repo, "review_comments"):
            n = num_from(c.get("pull_request_url"))
            add_mentions(fw, "pr", n, "review_comment", c.get("body"), c["created_at"],
                         (c.get("user") or {}).get("login"), c.get("author_association"), c["html_url"])
        for d in pages(repo, "discussions"):
            n = d["number"]
            threads.append({"framework": fw, "kind": "discussion", "number": n, "title": d["title"],
                            "user": (d.get("author") or {}).get("login"), "assoc": d.get("authorAssociation"),
                            "created": d["createdAt"][:10], "closed": None, "state": None, "state_reason": None,
                            "merged": None, "merge_commit_sha": None, "base": None, "labels": [],
                            "n_comments": len(d["comments"]["nodes"]), "url": d["url"]})
            add_mentions(fw, "discussion", n, "opening", (d["title"] or "") + "\n" + (d.get("body") or ""),
                         d["createdAt"], (d.get("author") or {}).get("login"), d.get("authorAssociation"), d["url"])
            for c in d["comments"]["nodes"]:
                add_mentions(fw, "discussion", n, "comment", c.get("body"), c["createdAt"],
                             (c.get("author") or {}).get("login"), c.get("authorAssociation"), d["url"])
                for r in c["replies"]["nodes"]:
                    add_mentions(fw, "discussion", n, "comment", r.get("body"), r["createdAt"],
                                 (r.get("author") or {}).get("login"), r.get("authorAssociation"), d["url"])
        print(f"{fw:12s} threads {sum(t['framework'] == fw for t in threads):6d}  "
              f"mentions {sum(m['framework'] == fw for m in mentions):5d}", flush=True)

    for name, rows in (("threads", threads), ("mentions", mentions), ("xrefs", xrefs)):
        with (OUT / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tiers = defaultdict(set)
    for m in mentions:
        tiers[m["tier"]].add(m["arxiv"])
    print("distinct papers by best tier:", {k: len(v) for k, v in tiers.items()})


if __name__ == "__main__":
    main()
