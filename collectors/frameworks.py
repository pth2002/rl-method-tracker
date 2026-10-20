"""Trace when each RL algorithm option landed in each training framework.

Reads config/frameworks.yaml (where each framework exposes its algorithms) and
config/token_map.yaml (which framework token is which method). Writes:

  data/generated/framework_events.jsonl   one line per add / remove / default change
  data/generated/framework_head.json      tokens present at HEAD, per framework and surface
  data/generated/unmapped.json            tokens with no entry in token_map.yaml (needs curation)

Usage:
  python collectors/frameworks.py              # use cached clones as they are
  python collectors/frameworks.py --fetch      # git fetch every framework first
  python collectors/frameworks.py --only verl  # one framework
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gitwalk import (BlobReader, Commit, commit_info, commits_pickaxe,  # noqa: E402
                     commits_touching, files_containing, git, list_dir, list_files)

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "repos"
OUT = ROOT / "data" / "generated"


def normalize(token: str, how: str | None) -> str:
    token = token.strip()
    if how == "lower":
        return token.lower()
    if how == "snake":
        # CamelCase class names -> snake_case; acronyms stay whole (GDPO -> gdpo)
        return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", token).lower()
    if how == "dash_to_underscore":
        return token.replace("-", "_")
    return token


def extract_values(text: str, pattern: dict) -> set[str]:
    flags = re.DOTALL if pattern.get("dotall") else 0
    found: set[str] = set()
    for m in re.finditer(pattern["regex"], text, flags):
        groups = [g for g in m.groups() if g] or [m.group(0)]
        for g in groups:
            if "split" in pattern:
                parts = re.findall(pattern["split"], g)
            else:
                parts = [g]
            for p in parts:
                tok = normalize(p, pattern.get("normalize"))
                for suffix in pattern.get("strip_suffix", []):
                    if tok.endswith(suffix):
                        tok = tok[: -len(suffix)]
                if tok:
                    found.add(tok)
    return found


def walk_values(repo: Path, surface: dict) -> tuple[list[dict], set[str]]:
    """Track the token set of a 'values' surface across history."""
    paths = sorted({p for pat in surface["patterns"] for p in pat["paths"]})
    commits = commits_touching(repo, paths)
    reader = BlobReader(repo)
    events, prev = [], set()
    try:
        for c in commits:
            cur: set[str] = set()
            for pat in surface["patterns"]:
                for path in pat["paths"]:
                    text = reader.read(c.sha, path)
                    if text is not None:
                        cur |= extract_values(text, pat)
            for tok in sorted(cur - prev):
                events.append({"event": "added", "token": tok, **c.as_dict()})
            for tok in sorted(prev - cur):
                events.append({"event": "removed", "token": tok, **c.as_dict()})
            prev = cur
    finally:
        reader.close()
    return events, prev


def walk_dirs(repo: Path, surface: dict) -> tuple[list[dict], set[str]]:
    directory = surface["dir"]
    commits = commits_touching(repo, [directory if directory not in ("", ".") else "."])
    events, prev = [], set()
    ignore = set(surface.get("ignore", []))
    for c in commits:
        cur = set(list_dir(repo, c.sha, directory)) - ignore
        for tok in sorted(cur - prev):
            events.append({"event": "added", "token": tok, **c.as_dict()})
        for tok in sorted(prev - cur):
            events.append({"event": "removed", "token": tok, **c.as_dict()})
        prev = cur
    return events, prev


def walk_files(repo: Path, surface: dict) -> tuple[list[dict], set[str]]:
    """Every file in `dir` whose name matches `regex` is one option (token = first group)."""
    directory, rx = surface["dir"], re.compile(surface["regex"])
    events, prev = [], set()
    for c in commits_touching(repo, [directory]):
        cur = {m.group(1) for f in list_files(repo, c.sha, directory) if (m := rx.match(f))}
        for tok in sorted(cur - prev):
            events.append({"event": "added", "token": tok, **c.as_dict()})
        for tok in sorted(prev - cur):
            events.append({"event": "removed", "token": tok, **c.as_dict()})
        prev = cur
    return events, prev


def flag_present(repo: Path, reader: BlobReader, sha: str, flag: dict, scope: list[str]) -> bool:
    literal = flag["literal"]
    regex = re.compile(flag.get("regex", re.escape(literal)))
    for path in files_containing(repo, sha, literal, scope):
        text = reader.read(sha, path)
        if text and regex.search(text):
            return True
    return False


def walk_flags(repo: Path, surface: dict) -> tuple[list[dict], set[str]]:
    scope = surface["scope"]
    events, present = [], set()
    reader = BlobReader(repo)
    try:
        for flag in surface["flags"]:
            state = False
            for c in commits_pickaxe(repo, flag["literal"], flag.get("scope", scope)):
                now = flag_present(repo, reader, c.sha, flag, flag.get("scope", scope))
                if now != state:
                    events.append({"event": "added" if now else "removed",
                                   "token": flag["token"], **c.as_dict()})
                    state = now
            if state:
                present.add(flag["token"])
    finally:
        reader.close()
    return events, present


def walk_defaults(repo: Path, surface: dict) -> tuple[list[dict], set[str]]:
    """Each entry tracks one setting's default value; emits an event whenever it changes."""
    events, current = [], set()
    reader = BlobReader(repo)
    try:
        for d in surface["defaults"]:
            commits = commits_touching(repo, d["paths"])
            prev = None
            for c in commits:
                val = None
                for path in d["paths"]:
                    text = reader.read(c.sha, path)
                    if text is None:
                        continue
                    m = re.search(d["regex"], text, re.DOTALL if d.get("dotall") else 0)
                    if m:
                        val = m.group(1).strip().strip("'\"")
                        break
                if val != prev:
                    events.append({"event": "default_changed", "token": d["token"],
                                   "value": val, "previous": prev, **c.as_dict()})
                    prev = val
            if prev is not None:
                current.add(f"{d['token']}={prev}")
    finally:
        reader.close()
    return events, current


def surface_paths(surface: dict) -> list[str]:
    """Files a surface reads, used to test whether a token existed there before it was parsed."""
    if surface["kind"] == "values":
        return sorted({p for pat in surface["patterns"] for p in pat["paths"]})
    if surface["kind"] in ("dirs", "files"):
        return []  # a directory or file name is concrete; a renamed one counts as a new addition
    return []  # flags are found by pickaxe from the start of history; defaults carry no lag


def existed_before(repo: Path, sha: str, token: str, paths: list[str]) -> bool:
    """True when the token already appeared as a quoted option name in these paths before `sha`.

    Quoting avoids matching the token inside longer words (for example "dro" inside "dropout").
    """
    if len(token) < 2:
        return False
    for quoted in (f'"{token}"', f"'{token}'"):
        out = git(repo, "log", "--first-parent", "-1", "--format=%H", f"-S{quoted}", f"{sha}~1", "--", *paths,
                  check=False)
        if out.strip():
            return True
    return False


def walk_manual(repo: Path, surface: dict) -> tuple[list[dict], set[str]]:
    """Changes to existing code that implement a method without adding an option.

    Each entry names the commit and a literal that marks the implementation in `path`. The commit
    must lie on the first-parent main branch; its date and author come from git. The method counts
    as present at HEAD while the literal is still in the file there.
    """
    main_line = set(git(repo, "rev-list", "--first-parent", "HEAD").split())
    events, present = [], set()
    for ent in surface["entries"]:
        c = commit_info(repo, ent["sha"])
        if c.sha not in main_line:
            raise SystemExit(f"manual entry {ent['token']}: {ent['sha'][:10]} is not on the main branch")
        events.append({"event": "added", "token": ent["token"], **c.as_dict(),
                       "condition": ent.get("condition")})
        if ent["literal"] in git(repo, "show", f"HEAD:{ent['path']}", check=False):
            present.add(ent["token"])
    return events, present


WALKERS = {"values": walk_values, "dirs": walk_dirs, "files": walk_files, "flags": walk_flags,
           "defaults": walk_defaults, "manual": walk_manual}


def ensure_repo(name: str, spec: dict, fetch: bool) -> Path:
    repo = CACHE / name
    if not repo.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        git(CACHE, "clone", "--quiet", "--no-checkout", spec["url"], name)
    elif fetch:
        git(repo, "fetch", "--quiet", "origin")
        branch = git(repo, "symbolic-ref", "--short", "HEAD").strip()
        git(repo, "update-ref", f"refs/heads/{branch}", f"origin/{branch}")
    return repo


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()

    cfg = yaml.safe_load((ROOT / "config" / "frameworks.yaml").read_text(encoding="utf-8"))
    token_map = yaml.safe_load((ROOT / "config" / "token_map.yaml").read_text(encoding="utf-8")) or {}
    OUT.mkdir(parents=True, exist_ok=True)

    events_path = OUT / "framework_events.jsonl"
    head_path = OUT / "framework_head.json"
    old_events = []
    if args.only and events_path.exists():
        old_events = [json.loads(l) for l in events_path.read_text(encoding="utf-8").split(chr(10)) if l.strip()]
        old_events = [e for e in old_events if e["framework"] not in args.only]
    head = json.loads(head_path.read_text(encoding="utf-8")) if (args.only and head_path.exists()) else {}

    all_events = list(old_events)
    unmapped: dict[str, dict[str, list[str]]] = {}
    for name, spec in cfg["frameworks"].items():
        if args.only and name not in args.only:
            continue
        repo = ensure_repo(name, spec, args.fetch)
        tip = commit_info(repo, "HEAD")
        root_sha = git(repo, "rev-list", "--max-parents=0", "HEAD").split()[0]
        head[name] = {"url": spec["url"], "head_sha": tip.sha, "head_date": tip.date, "surfaces": {}}
        fmap = token_map.get(name, {})
        for surface in spec["surfaces"]:
            sid = surface["id"]
            events, present = WALKERS[surface["kind"]](repo, surface)
            smap = fmap.get(sid, {})
            bulk = re.compile(spec["bulk_commit_regex"], re.I) if spec.get("bulk_commit_regex") else None
            paths = surface_paths(surface)
            for e in events:
                # An addition is censored only when its true start is unknowable from this history:
                # the repository's root commit, a bulk code release, or a refactor that renamed a
                # token already present in the same files.
                reason = None
                if e["event"] == "added":
                    if e["sha"] == root_sha:
                        reason = "root_commit"
                    elif bulk and bulk.search(e["subject"]):
                        reason = "bulk_release"
                    elif paths and existed_before(repo, e["sha"], e["token"].split("=")[0], paths):
                        reason = "present_before_in_other_form"
                e["left_censored"] = reason is not None
                e["censor_reason"] = reason
                tok = e["token"].split("=")[0]
                mapped = smap.get(tok)
                if isinstance(mapped, str) and mapped.startswith("~"):
                    methods, family = [], mapped[1:]
                elif mapped is None:
                    methods, family = [], None
                else:
                    methods, family = (mapped if isinstance(mapped, list) else [mapped]), "in_scope"
                e.update({"framework": name, "surface": sid, "tier": surface["tier"],
                          "methods": methods, "family": family})
            all_events.extend(events)
            head[name]["surfaces"][sid] = sorted(present)
            print(f"{name:11s} {sid:22s} {len(events):4d} events, {len(present):3d} at HEAD")

    # Every token ever seen (not only at HEAD) needs a mapping, so removed methods are curated too.
    kinds = {(n, s["id"]): s["kind"] for n, spec in cfg["frameworks"].items() for s in spec["surfaces"]}
    for e in all_events:
        if kinds.get((e["framework"], e["surface"])) == "defaults":
            continue
        if e["token"] not in token_map.get(e["framework"], {}).get(e["surface"], {}):
            bucket = unmapped.setdefault(e["framework"], {}).setdefault(e["surface"], [])
            if e["token"] not in bucket:
                bucket.append(e["token"])
    # For each unmapped token, list arXiv ids cited in the commit that introduced it.
    first_add = {}
    for e in all_events:
        if e["event"] == "added":
            first_add.setdefault((e["framework"], e["surface"], e["token"]), e)
    suggestions = {}
    for fw, surfaces in unmapped.items():
        repo = CACHE / fw
        for sid, toks in surfaces.items():
            toks.sort()
            for tok in toks:
                e = first_add.get((fw, sid, tok))
                if not e:
                    continue
                diff = git(repo, "show", "--format=%B", e["sha"], check=False)
                ids = re.findall(r"arxiv\.org/(?:abs|pdf|html)/(\d{4}\.\d{4,5})", diff)
                ranked = sorted(set(ids), key=lambda i: -ids.count(i))[:4]
                suggestions[f"{fw}/{sid}/{tok}"] = {
                    "first_seen": e["date"], "commit": e["sha"][:10], "subject": e["subject"][:120],
                    "arxiv_in_commit": ranked}

    all_events.sort(key=lambda e: (e["framework"], e["date"], e["surface"], e["token"]))
    with events_path.open("w", encoding="utf-8") as f:
        for e in all_events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    head_path.write_text(json.dumps(head, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "unmapped.json").write_text(json.dumps({"tokens": unmapped, "suggestions": suggestions},
                                                  indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(all_events)} events; {sum(len(v) for s in unmapped.values() for v in s.values())} unmapped tokens")


if __name__ == "__main__":
    main()
