"""Batch bookkeeping for labelling the candidate pool by reading abstracts.

The labeller only ever opens batch files, which carry arxiv id, title
and abstract and nothing else, so known adopted methods and repeated papers stay blind.

  python tools/triage_batches.py make          # once: write batches and the hidden manifest
  python tools/triage_batches.py status        # progress, plus format errors in label files
  python tools/triage_batches.py check-pilot   # after the pilot batches: recall, repeats, review sample
  python tools/triage_batches.py merge         # after all batches: final labels and counts
  python tools/triage_batches.py extend        # new pool papers after a filter change -> new batches
  python tools/triage_batches.py compare-review # after the review sample is filled in

Layout under data/generated/triage/:
  batches/batch_0001.jsonl    input, 40 papers each
  labels/labels_0001.jsonl    output written by the labeller, one JSON object per input line
  validation.md, review_sample.csv, labels.jsonl
The manifest (which ids are known methods, which are repeats) lives in .cache/triage_manifest.json.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FRAME = ROOT / "data" / "generated" / "arxiv_frame.jsonl"
TRI = ROOT / "data" / "generated" / "triage"
BATCHES, LABELS = TRI / "batches", TRI / "labels"
MANIFEST = ROOT / ".cache" / "triage_manifest.json"
SEED, BATCH, PILOT_RANDOM, N_REPEAT = 20261018, 40, 300, 100
LABEL_SET = {"rl_method", "rl_application", "analysis", "systems", "preference_offline", "distillation", "other"}
COMPONENTS = {"advantage", "clipping", "aggregation", "sampling", "length", "offpolicy", "moe", "entropy", "kl",
              "multi_reward", "credit_assignment", "other", None}
CONF = {"high", "medium", "low"}
SCOPES = {"general", "embedded", None}
# Known methods that the v1 rules named as examples; pilot recall is also reported without them.
CONTAMINATED = {"2503.14476", "2512.02556"}
REVIEW = {"general", "embedded", "no"}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").split(chr(10)) if l.strip()]


def make() -> None:
    if MANIFEST.exists():
        sys.exit("batches already made; delete .cache/triage_manifest.json and data/generated/triage/batches to redo")
    rows = read_jsonl(FRAME)
    rng = random.Random(SEED)
    gold = [r for r in rows if r["flags"]["in_catalog"]]
    rest = [r for r in rows if not r["flags"]["in_catalog"]]
    rng.shuffle(rest)
    pilot_random, remainder = rest[:PILOT_RANDOM], rest[PILOT_RANDOM:]
    pilot = gold + pilot_random
    rng.shuffle(pilot)
    repeats = rng.sample([r["arxiv"] for r in pilot_random], N_REPEAT)
    by_id = {r["arxiv"]: r for r in rows}
    later = remainder + [by_id[a] for a in repeats]
    rng.shuffle(later)

    BATCHES.mkdir(parents=True, exist_ok=True)
    LABELS.mkdir(parents=True, exist_ok=True)
    order = pilot + later
    n_pilot_batches = -(-len(pilot) // BATCH)
    # pad the pilot so that it fills whole batches with papers from the remainder
    names = []
    for i in range(0, len(order), BATCH):
        name = f"batch_{i // BATCH + 1:04d}"
        names.append(name)
        with (BATCHES / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for r in order[i:i + BATCH]:
                f.write(json.dumps({"arxiv": r["arxiv"], "title": r["title"], "abstract": r["abstract"]},
                                   ensure_ascii=False) + "\n")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps({
        "seed": SEED, "batch_size": BATCH, "pilot_batches": names[:n_pilot_batches], "all_batches": names,
        "gold": [r["arxiv"] for r in gold], "pilot_random": [r["arxiv"] for r in pilot_random], "repeats": repeats,
    }, indent=1), encoding="utf-8")
    print(f"{len(names)} batches ({len(order)} papers incl. {N_REPEAT} repeats); pilot = {names[0]}..{names[n_pilot_batches - 1]}")


def extend() -> None:
    """Add batches for papers that entered the pool after the first run, with 40 earlier papers
    mixed in again so the labels of both runs can be compared."""
    m = manifest()
    labelled = {g["arxiv"] for g in read_jsonl(TRI / "labels.jsonl")}
    rows = read_jsonl(FRAME)
    new = [r for r in rows if r["arxiv"] not in labelled and r["arxiv"] not in set(m.get("extension_ids", []))]
    if not new:
        sys.exit("no new papers in the pool")
    rng = random.Random(SEED + 7)
    by_id = {r["arxiv"]: r for r in rows}
    repeat_pool = sorted(a for a in labelled if a in by_id and a not in set(m["gold"]))
    repeats = rng.sample(repeat_pool, 40)
    order = new + [by_id[a] for a in repeats]
    rng.shuffle(order)
    start = len(m["all_batches"])
    names = []
    for i in range(0, len(order), BATCH):
        name = f"batch_{start + i // BATCH + 1:04d}"
        names.append(name)
        with (BATCHES / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for r in order[i:i + BATCH]:
                f.write(json.dumps({"arxiv": r["arxiv"], "title": r["title"], "abstract": r["abstract"]},
                                   ensure_ascii=False) + "\n")
    m["all_batches"] += names
    m["extension_batches"] = m.get("extension_batches", []) + names
    m["extension_ids"] = m.get("extension_ids", []) + [r["arxiv"] for r in new]
    m["extension_repeats"] = m.get("extension_repeats", []) + repeats
    MANIFEST.write_text(json.dumps(m, indent=1), encoding="utf-8")
    print(f"{len(new)} new papers + {len(repeats)} repeats in {names[0]}..{names[-1]}")


def load_labels(names: list[str]) -> tuple[dict[str, list[dict]], list[str]]:
    """Returns labels per batch and a list of problems."""
    out, problems = {}, []
    symptoms = {s["id"] for s in yaml.safe_load((ROOT / "data" / "symptoms.yaml").read_text(encoding="utf-8"))}
    for name in names:
        lp = LABELS / f"labels_{name.split('_')[1]}.jsonl"
        if not lp.exists():
            continue
        want = [r["arxiv"] for r in read_jsonl(BATCHES / f"{name}.jsonl")]
        try:
            got = read_jsonl(lp)
        except json.JSONDecodeError as e:
            problems.append(f"{lp.name}: not valid JSONL ({e})")
            continue
        if [g.get("arxiv") for g in got] != want:
            problems.append(f"{lp.name}: arxiv ids do not match {name} line by line")
        for g in got:
            if g.get("label") not in LABEL_SET:
                problems.append(f"{lp.name} {g.get('arxiv')}: bad label {g.get('label')!r}")
            if g.get("component") not in COMPONENTS:
                problems.append(f"{lp.name} {g.get('arxiv')}: bad component {g.get('component')!r}")
            if g.get("confidence") not in CONF:
                problems.append(f"{lp.name} {g.get('arxiv')}: bad confidence {g.get('confidence')!r}")
            if g.get("scope", "missing") not in SCOPES:
                problems.append(f"{lp.name} {g.get('arxiv')}: bad or missing scope {g.get('scope', 'missing')!r}")
            if (g.get("label") == "rl_method") != (g.get("scope") is not None):
                problems.append(f"{lp.name} {g.get('arxiv')}: scope must be set exactly when label is rl_method")
            if not isinstance(g.get("is_model_report"), bool):
                problems.append(f"{lp.name} {g.get('arxiv')}: is_model_report must be true or false")
            bad_sym = [s for s in g.get("symptoms") or [] if s not in symptoms]
            if bad_sym:
                problems.append(f"{lp.name} {g.get('arxiv')}: unknown symptoms {bad_sym}")
        out[name] = got
    return out, problems


def manifest() -> dict:
    if not MANIFEST.exists():
        sys.exit("run `make` first")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def status() -> None:
    m = manifest()
    labels, problems = load_labels(m["all_batches"])
    pilot_done = all(b in labels for b in m["pilot_batches"])
    print(f"labelled {len(labels)}/{len(m['all_batches'])} batches; pilot {'done' if pilot_done else 'in progress'}"
          f" ({sum(b in labels for b in m['pilot_batches'])}/{len(m['pilot_batches'])})")
    nxt = next((b for b in m["all_batches"] if b not in labels), None)
    print("next batch:", nxt)
    for p in problems[:30]:
        print("PROBLEM", p)


def first_labels(labels: dict[str, list[dict]], order: list[str]) -> tuple[dict, dict]:
    first, second = {}, {}
    for b in order:
        for g in labels.get(b, []):
            (second if g["arxiv"] in first else first)[g["arxiv"]] = g
    return first, second


def check_pilot() -> None:
    m = manifest()
    labels, problems = load_labels(m["pilot_batches"])
    if problems or len(labels) < len(m["pilot_batches"]):
        for p in problems:
            print("PROBLEM", p)
        sys.exit(f"pilot incomplete: {len(labels)}/{len(m['pilot_batches'])} batches labelled cleanly")
    first, _ = first_labels(labels, m["pilot_batches"])
    gold = m["gold"]
    gold_hits = [a for a in gold if first[a]["label"] == "rl_method"]
    misses = [(a, first[a]["label"]) for a in gold if first[a]["label"] != "rl_method"]
    rand = [first[a] for a in m["pilot_random"] if a in first]
    dist = Counter(g["label"] for g in rand)

    clean = [a for a in gold if a not in CONTAMINATED]
    clean_hits = [a for a in clean if first[a]["label"] == "rl_method"]
    meth = [g for g in rand if g["label"] == "rl_method"]
    scope = Counter(g["scope"] for g in meth)
    conf = Counter(g["confidence"] for g in first.values())
    reports = sum(bool(g.get("is_model_report")) for g in first.values())

    rng = random.Random(SEED + 1)
    pos = [g for g in rand if g["label"] == "rl_method"]
    neg = [g for g in rand if g["label"] != "rl_method"]
    sample = rng.sample(pos, min(100, len(pos))) + rng.sample(neg, min(200 - min(100, len(pos)), len(neg)))
    rng.shuffle(sample)
    frame = {r["arxiv"]: r for r in read_jsonl(FRAME)}
    review = TRI / "review_sample.csv"
    if review.exists():
        print("review_sample.csv already exists; left untouched")
    else:
        with review.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["arxiv", "title", "abstract", "review_label"])
            for g in sample:
                r = frame[g["arxiv"]]
                w.writerow([r["arxiv"], r["title"], r["abstract"], ""])

    lines = ["# Triage validation", "", "## Pilot", "",
             f"- Known adopted methods labelled `rl_method`: {len(gold_hits)}/{len(gold)}",
             f"- Same, leaving out the {len(CONTAMINATED)} named as examples in the v1 rules: {len(clean_hits)}/{len(clean)}",
             f"- Misses: {misses if misses else 'none'}",
             f"- `rl_method` in the random sample by scope: " + ", ".join(f"{k} {v}" for k, v in scope.most_common()),
             f"- Confidence over all pilot papers: " + ", ".join(f"{k} {v}" for k, v in conf.most_common()),
             f"- Model reports in the pilot: {reports}",
             f"- Random pilot sample ({len(rand)} papers) by label: " +
             ", ".join(f"{k} {v}" for k, v in dist.most_common()),
             f"- Review sample written to `review_sample.csv` ({len(sample)} papers: "
             f"{min(100, len(pos))} labelled `rl_method`, the rest not). Repeats are scored after `merge`.",
             ""]
    (TRI / "validation.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    if len(gold_hits) < len(gold) - 2:
        print("RECALL TOO LOW: revise how the rules are applied and relabel the pilot before continuing.")


def merge() -> None:
    m = manifest()
    labels, problems = load_labels(m["all_batches"])
    if problems or len(labels) < len(m["all_batches"]):
        for p in problems[:30]:
            print("PROBLEM", p)
        sys.exit(f"not finished: {len(labels)}/{len(m['all_batches'])} batches labelled cleanly")
    first, second = first_labels(labels, m["all_batches"])
    with (TRI / "labels.jsonl").open("w", encoding="utf-8") as f:
        for a in sorted(first):
            f.write(json.dumps(first[a], ensure_ascii=False) + "\n")
    agree = sum(first[a]["label"] == second[a]["label"] for a in second)
    flips = [(a, first[a]["label"], second[a]["label"]) for a in second if first[a]["label"] != second[a]["label"]]
    dist = Counter(g["label"] for g in first.values())
    meth = [g for g in first.values() if g["label"] == "rl_method"]
    frame = {r["arxiv"]: r for r in read_jsonl(FRAME)}
    by_month = Counter(frame[g["arxiv"]]["month"] for g in meth)
    lines = ["", "## Full run", "",
             f"- Papers labelled: {len(first)}",
             "- By label: " + ", ".join(f"{k} {v}" for k, v in dist.most_common()),
             f"- `rl_method`: {len(meth)}; scope general {sum(g['scope'] == 'general' for g in meth)}, "
             f"embedded {sum(g['scope'] == 'embedded' for g in meth)}; general without low confidence "
             f"{sum(g['scope'] == 'general' and g['confidence'] != 'low' for g in meth)}",
             f"- Model reports (any label): {sum(bool(g.get('is_model_report')) for g in first.values())}; "
             f"of those labelled `rl_method`: {sum(bool(g.get('is_model_report')) for g in meth)}",
             f"- Repeated papers with the same label both times: {agree}/{len(second)}",
             f"- Label changes on repeats ({len(flips)}): {flips[:30] if flips else 'none'}"
             + (" ..." if len(flips) > 30 else ""),
             "- `rl_method` per month: " + ", ".join(f"{k} {v}" for k, v in sorted(by_month.items())),
             "- Components: " + ", ".join(f"{k} {v}" for k, v in Counter(g.get('component') for g in meth).most_common()),
             ""]
    with (TRI / "validation.md").open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


def compare_review() -> None:
    m = manifest()
    labels, _ = load_labels(m["all_batches"])
    first, _ = first_labels(labels, m["all_batches"])
    with (TRI / "review_sample.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    filled = [r for r in rows if r["review_label"].strip()]
    if not filled:
        sys.exit("review_sample.csv has no review_label values yet; nothing compared")
    bad = [r["arxiv"] for r in filled if r["review_label"].strip().lower() not in REVIEW]
    if bad:
        sys.exit(f"review_label must be one of {sorted(REVIEW)}; check {bad[:10]}")

    def label_view(g: dict) -> str:
        return g["scope"] if g["label"] == "rl_method" else "no"

    pairs = Counter((r["review_label"].strip().lower(), label_view(first[r["arxiv"]])) for r in filled)
    cats = ["general", "embedded", "no"]
    lines = ["", f"## Review sample ({len(filled)}/{len(rows)} labelled)", "",
             "| review / labels | " + " | ".join(cats) + " |", "|---|" + "---|" * len(cats)]
    for h in cats:
        lines.append(f"| {h} | " + " | ".join(str(pairs[(h, c)]) for c in cats) + " |")
    agree = sum(pairs[(c, c)] for c in cats)
    lines += ["", f"- Exact agreement: {agree}/{len(filled)}",
              f"- Labelled general, reviewed as no: {pairs[('no', 'general')]}; "
              f"reviewed as general, labelled no: {pairs[('general', 'no')]}", ""]
    with (TRI / "validation.md").open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"make": make, "extend": extend, "status": status, "check-pilot": check_pilot, "merge": merge,
     "compare-review": compare_review}[cmd]()
