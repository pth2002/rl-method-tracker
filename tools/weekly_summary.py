"""Describe what a refresh changed and decide whether it can merge without a person.

  python tools/weekly_summary.py --refresh-rc 0 --out summary.md

Compares the working tree with the last commit: new landings, methods that left a framework, tier
changes and the number of included papers. --refresh-rc is the exit code of tools/update.py: 0 for a
clean run, 3 when validation found problems, anything else for a crash. Validation runs again here,
after any drafts. A refresh is clean when it did not crash, validation passes, no framework option
lacks a mapping, no new proposal thread waits for a code and tools/draft_reviews.py drafted nothing
(.cache/drafts.json). Automatic merging additionally requires --auto-merge-enabled true, which the
workflow supplies from WEEKLY_AUTO_MERGE only after the first real run has been reviewed.
The verdict also goes to $GITHUB_OUTPUT as clean=true or clean=false when that variable is set.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"
LABEL = {"verl": "verl", "trl": "TRL", "openrlhf": "OpenRLHF", "nemo-rl": "NeMo-RL", "roll": "ROLL",
         "slime": "slime", "areal": "AReaL"}


def at_head(rel: str) -> str | None:
    r = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else None


def jl(text: str | None) -> list[dict]:
    return [json.loads(l) for l in (text or "").splitlines() if l.strip()]


def read(rel: str) -> str | None:
    p = ROOT / rel
    return p.read_text(encoding="utf-8") if p.exists() else None


def landing_url(fw: str, v: dict, head: dict, recipe: set[str]) -> str:
    repo = head["verl_recipe" if fw == "verl" and (v.get("commit") or "")[:10] in recipe else fw]["url"]
    return f"{repo}/pull/{v['pr']}" if v.get("pr") else f"{repo}/commit/{v['commit']}"


def ref(url: str) -> str:
    kind, ident = url.rsplit("/", 2)[-2:]
    return f"PR #{ident}" if kind == "pull" else f"commit {ident[:7]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-rc", default="0")
    ap.add_argument("--draft-outcome", default="", help="outcome of the drafting step in the workflow")
    ap.add_argument("--auto-merge-enabled", default="", help="only the literal true enables automatic merging")
    ap.add_argument("--out", default="weekly_summary.md")
    args = ap.parse_args()
    crashed = args.refresh_rc.strip() not in ("0", "3")
    draft_failed = args.draft_outcome == "failure"
    passed = subprocess.run([sys.executable, "tools/validate.py"], cwd=ROOT).returncode == 0
    drafts = json.loads(read(".cache/drafts.json") or "[]")

    before = {r["id"]: r for r in json.loads(at_head("data/generated/adoption.json") or "[]")}
    after = {r["id"]: r for r in json.loads(read("data/generated/adoption.json") or "[]")}
    head = json.loads(read("data/generated/framework_head.json") or "{}")
    recipe = {e["sha"][:10] for e in jl(read("data/generated/framework_events.jsonl"))
              if e.get("framework") == "verl_recipe"}

    landings, removed, tiers = [], [], []
    for mid, r in after.items():
        b = before.get(mid, {"per_framework": {}, "frameworks_at_head": {}})
        name = r["name"].split(" (")[0]
        for fw, v in r["per_framework"].items():
            if fw not in b["per_framework"]:
                landings.append((v["first_date"], name, LABEL.get(fw, fw), landing_url(fw, v, head, recipe)))
        for fw, tier in b["frameworks_at_head"].items():
            now = r["frameworks_at_head"].get(fw)
            if not now:
                removed.append((name, LABEL.get(fw, fw), tier))
            elif now != tier:
                tiers.append((name, LABEL.get(fw, fw), tier, now))
    landings.sort(reverse=True)

    def included(text: str | None) -> int:
        return sum(1 for r in jl(text) if r.get("strict_general") and r.get("adopted"))
    inc_before = included(at_head("data/generated/pool_adoption.jsonl"))
    inc_after = included(read("data/generated/pool_adoption.jsonl"))

    unmapped = json.loads(read("data/generated/unmapped.json") or "{}")
    tokens = [(fw, surface, t) for fw, s in unmapped.get("tokens", {}).items() for surface, ts in s.items() for t in ts]
    cites = unmapped.get("suggestions", {})
    uncoded = jl(read("data/generated/process/uncoded_threads.jsonl"))
    enabled = args.auto_merge_enabled == "true"
    clean = enabled and not crashed and not draft_failed and passed and not tokens and not uncoded and not drafts

    snap = max((h["head_date"] for k, h in head.items() if k != "verl_recipe"), default="")
    lines = [f"Framework histories as of {snap}.", ""]
    if clean:
        lines += ["**This pull request merges itself:** validation passed and nothing needs a person's judgment.", ""]
    else:
        lines += ["**Left open for review.** The checklist below says what needs a person.", ""]
    if not enabled:
        lines += ["Automatic merging is disabled. Review the first real run, including its data and page build, "
                  "before setting the repository variable WEEKLY_AUTO_MERGE to true.", ""]
    if crashed:
        lines += [f"**The refresh stopped with an error (exit code {args.refresh_rc or 'missing'}).** Some files "
                  "may be from the previous week. See the job log before merging.", ""]
    if draft_failed:
        lines += ["**Drafting stopped with an error.** Drafts written before the error are in this pull request, "
                  "and the derived files may not include them yet. See the job log.", ""]
    if drafts:
        lines += ["### Drafted for your review", "",
                  "A language model drafted these from the evidence below and they are already in this pull request. "
                  "Merge to confirm them, or correct the files on this branch first.", "",
                  "A pending write may be only partially applied; inspect the files before confirming it.", "",
                  "| Item | Draft | Evidence | Confidence | Write state |", "|---|---|---|---|---|"]
        lines += [f"| {d['item']} | {d['draft']} | {d['evidence'].replace('|', '/')} | {d['confidence']} | "
                  f"{d.get('state', 'applied')} |" for d in drafts]
        lines += [""]

    lines += ["### New landings", ""]
    if landings:
        lines += ["| Date | Method | Framework | Change |", "|---|---|---|---|"]
        lines += [f"| {d} | {m} | {f} | [{ref(u)}]({u}) |" for d, m, f, u in landings]
    else:
        lines += ["None this week."]
    lines += [""]
    if removed:
        lines += ["### Removed from a framework", ""] + [f"- {m} left {f}, where it was offered as {t}." for m, f, t in removed] + [""]
    if tiers:
        lines += ["### Changed how a framework offers a method", ""] + [f"- {m} in {f}: {a} to {b}." for m, f, a, b in tiers] + [""]
    if inc_after != inc_before:
        lines += [f"Included papers in the pool: {inc_before} to {inc_after}.", ""]

    lines += ["### Needs a person", ""]
    if drafts:
        lines += [f"- [ ] Check the {len(drafts)} draft(s) above."]
    lines += [f"- [{'x' if passed else ' '}] Validation {'passed' if passed else 'FAILED, see the job log'}."]
    if tokens:
        lines += [f"- [ ] {len(tokens)} framework option(s) without a mapping. Add each to `config/token_map.yaml`, "
                  "and add the method to `data/methods.yaml` when it is new:"]
        for fw, surface, t in tokens:
            s = cites.get(f"{fw}/{surface}/{t}", {})
            where = f", first seen {s['first_seen']} in {s['commit']} \"{s['subject']}\"" if s else ""
            ids = ", ".join(s.get("arxiv_in_commit", []))
            lines += [f"  - {LABEL.get(fw, fw)}, {surface}: `{t}`{where}" + (f", cites {ids}" if ids else "")]
    else:
        lines += ["- [x] Every framework option has a mapping."]
    if uncoded:
        lines += [f"- [ ] {len(uncoded)} new proposal thread(s) to code into `attempts_coded.jsonl`:"]
        lines += [f"  - [{LABEL.get(u['framework'], u['framework'])} #{u['number']}]({u['url']}), cites {u['arxiv']}"
                  + (f"; left for a person: {u['draft_blocked']}" if u.get("draft_blocked") else "") for u in uncoded]
    else:
        lines += ["- [x] No new proposal thread waits for a code."]

    (ROOT / args.out).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"clean={'true' if clean else 'false'}\n")
    print(f"{len(landings)} new landings, {len(removed)} removals, {len(tiers)} tier changes, "
          f"{len(tokens)} unmapped, {len(uncoded)} uncoded, clean={clean}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
