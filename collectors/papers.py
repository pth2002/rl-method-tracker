"""Resolve and verify the source paper of every method in data/methods.yaml.

For entries with an arXiv id: fetch title, authors and first-version date, and check that
the id is not a typo by comparing against `title` when one is given.
For entries with only a title: search arXiv by title and accept the hit only when the
normalised titles match exactly. Everything else is reported for a human to resolve.

Writes data/generated/papers.json. Respects arXiv's request spacing (3 s).
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "generated" / "papers.json"
API = "http://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom"}
HEADERS = {"User-Agent": "rl-adoption-tracker (research; contact via GitHub)"}


def norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def parse_entries(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    out = []
    for e in root.findall("a:entry", NS):
        eid = e.findtext("a:id", default="", namespaces=NS)
        m = re.search(r"abs/(\d{4}\.\d{4,5})(v\d+)?$", eid)
        if not m:
            continue
        out.append({
            "arxiv": m.group(1),
            "title": " ".join(e.findtext("a:title", default="", namespaces=NS).split()),
            "authors": [a.findtext("a:name", default="", namespaces=NS) for a in e.findall("a:author", NS)],
            "published": e.findtext("a:published", default="", namespaces=NS)[:10],
            "primary_category": (e.find("{http://arxiv.org/schemas/atom}primary_category").get("term")
                                 if e.find("{http://arxiv.org/schemas/atom}primary_category") is not None else None),
        })
    return out


def fetch(params: dict) -> list[dict]:
    r = requests.get(API, params=params, headers=HEADERS, timeout=60)
    r.raise_for_status()
    time.sleep(3)
    return parse_entries(r.text)


def main() -> None:
    methods = yaml.safe_load((ROOT / "data" / "methods.yaml").read_text(encoding="utf-8"))
    cache = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"papers": {}, "methods": {}}
    papers = cache["papers"]

    ids = sorted({m["source"]["arxiv"] for m in methods if m.get("source", {}).get("arxiv")} - set(papers))
    for i in range(0, len(ids), 40):
        for p in fetch({"id_list": ",".join(ids[i:i + 40]), "max_results": 40}):
            papers[p["arxiv"]] = p
    print(f"fetched {len(ids)} ids; {len(papers)} papers cached")

    resolved = {}
    for m in methods:
        src = m.get("source") or {}
        rec = {"status": "unresolved", "date": None, "arxiv": None, "title": None, "authors": []}
        if src.get("arxiv"):
            p = papers.get(src["arxiv"])
            if p is None:
                rec["status"] = "arxiv_id_not_found"
            else:
                rec.update(status="ok", arxiv=p["arxiv"], title=p["title"], authors=p["authors"], date=p["published"])
                if src.get("title") and norm_title(src["title"]) != norm_title(p["title"]):
                    rec["status"] = "title_mismatch"
        elif src.get("url"):
            rec.update(status="non_arxiv", title=src.get("title"), date=src.get("date"), url=src["url"])
        elif src.get("title"):
            q = 'ti:"' + re.sub(r"[^A-Za-z0-9 ]+", " ", src["title"]).strip() + '"'
            hits = fetch({"search_query": q, "max_results": 5})
            exact = [h for h in hits if norm_title(h["title"]) == norm_title(src["title"])]
            if exact:
                p = sorted(exact, key=lambda h: h["published"])[0]
                papers[p["arxiv"]] = p
                rec.update(status="ok_by_title", arxiv=p["arxiv"], title=p["title"], authors=p["authors"],
                           date=p["published"])
            else:
                rec.update(status="title_not_found", candidates=[(h["arxiv"], h["title"]) for h in hits])
        if m.get("review"):
            rec["review"] = True
        resolved[m["id"]] = rec

    cache["methods"] = resolved
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    for mid, r in resolved.items():
        if r["status"] not in ("ok", "ok_by_title"):
            print(f"  {mid:28s} {r['status']:18s} {r.get('title') or ''} {r.get('candidates', '')}")
    print("status counts:", {s: sum(r["status"] == s for r in resolved.values()) for s in {r["status"] for r in resolved.values()}})


if __name__ == "__main__":
    main()
