"""Harvest arXiv metadata for computer science through OAI-PMH, the complete bulk interface.

The search API misses papers whose abstracts spell names in LaTeX (DAPO writes
`$\\textbf{D}$ecouple ...`), so the candidate pool is built from a full local copy instead.
Keeps records whose categories include cs.LG, cs.CL or cs.AI and whose id falls in the window.

  python collectors/arxiv_oai.py --from 2025-01-01 --ids 2501-2606

Output: .cache/arxiv/cs_records.jsonl (append-only, resumable through .cache/arxiv/state.json).
"""
from __future__ import annotations

import argparse
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / ".cache" / "arxiv"
OUT = DIR / "cs_records.jsonl"
STATE = DIR / "state.json"
BASE = "https://oaipmh.arxiv.org/oai"
NS = {"o": "http://www.openarchives.org/OAI/2.0/", "a": "http://arxiv.org/OAI/arXiv/"}
KEEP = {"cs.LG", "cs.CL", "cs.AI"}


def in_window(arxiv_id: str, lo: int, hi: int) -> bool:
    m = re.match(r"(\d{4})\.\d{4,5}$", arxiv_id)
    return bool(m) and lo <= int(m.group(1)) <= hi


def request(params: dict) -> str:
    for attempt in range(8):
        try:
            r = requests.get(BASE, params=params, timeout=180,
                             headers={"User-Agent": "rl-adoption-tracker (research)"})
            if r.status_code == 503:
                wait = int(r.headers.get("Retry-After", "30"))
                time.sleep(min(wait, 300))
                continue
            r.raise_for_status()
            return r.text
        except requests.RequestException:
            time.sleep(20 * (attempt + 1))
    raise RuntimeError("OAI-PMH request kept failing")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="since", default="2025-01-01")
    ap.add_argument("--ids", default="2501-2606", help="yymm range of arXiv ids to keep")
    args = ap.parse_args()
    lo, hi = map(int, args.ids.split("-"))
    DIR.mkdir(parents=True, exist_ok=True)

    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    token = state.get("token")
    pages, kept = state.get("pages", 0), state.get("kept", 0)
    if state.get("done"):
        print("harvest already complete; delete .cache/arxiv/state.json to redo")
        return

    with OUT.open("a", encoding="utf-8") as f:
        while True:
            params = ({"verb": "ListRecords", "resumptionToken": token} if token else
                      {"verb": "ListRecords", "metadataPrefix": "arXiv", "set": "cs", "from": args.since})
            root = ET.fromstring(request(params))
            for rec in root.iter(f"{{{NS['o']}}}record"):
                md = rec.find("o:metadata/a:arXiv", NS)
                if md is None:
                    continue
                aid = md.findtext("a:id", default="", namespaces=NS)
                cats = md.findtext("a:categories", default="", namespaces=NS).split()
                if not in_window(aid, lo, hi) or not KEEP & set(cats):
                    continue
                authors = []
                for a in md.findall("a:authors/a:author", NS):
                    name = " ".join(x for x in [a.findtext("a:forenames", default="", namespaces=NS),
                                                a.findtext("a:keyname", default="", namespaces=NS)] if x)
                    authors.append(name)
                f.write(json.dumps({
                    "arxiv": aid,
                    "title": " ".join(md.findtext("a:title", default="", namespaces=NS).split()),
                    "abstract": " ".join(md.findtext("a:abstract", default="", namespaces=NS).split()),
                    "authors": authors,
                    "created": md.findtext("a:created", default="", namespaces=NS),
                    "categories": cats,
                }, ensure_ascii=False) + "\n")
                kept += 1
            tok_el = root.find(".//o:resumptionToken", NS)
            token = tok_el.text if tok_el is not None and tok_el.text else None
            pages += 1
            f.flush()
            STATE.write_text(json.dumps({"token": token, "pages": pages, "kept": kept,
                                         "cursor": tok_el.get("cursor") if tok_el is not None else None,
                                         "size": tok_el.get("completeListSize") if tok_el is not None else None,
                                         "done": token is None}))
            if pages % 20 == 0:
                print(f"page {pages}, kept {kept}, cursor {tok_el.get('cursor') if tok_el is not None else '-'}"
                      f" / {tok_el.get('completeListSize') if tok_el is not None else '-'}", flush=True)
            if token is None:
                break
            time.sleep(3)
    print(f"done: {pages} pages, {kept} records kept")


if __name__ == "__main__":
    main()
