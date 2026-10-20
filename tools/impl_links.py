"""Locate each included method's implementation at the snapshot and write permanent GitHub links.

For every option a framework exposes at its snapshot commit and the catalog maps to a method, this
finds the file and line where the option lives: the registry or config file for values and flags, the
folder for recipes and experimental trainers, the listed file for manual entries. Links point at the
snapshot commit, so they keep working when the framework moves on.

Needs the framework clones in .cache/repos. Writes data/generated/impl_links.json:
  {method_id: {framework: [{"token", "tier", "setting", "path", "line", "url"}]}}
`setting` is what a user writes to select the option: a value, a flag as the framework spells it, or
a default with its value. It is null for folders and for implementations without an option.

  python tools/impl_links.py
"""
from __future__ import annotations

import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"
REPOS = ROOT / ".cache" / "repos"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def definition_rank(text: str, needle: str, by_name: bool) -> int:
    """How directly a grep hit shows the option, lower first. For registry values (`by_name`) the
    quoted name comes first, as in `GRPO = "grpo"`. For fields and flags the line a user sets comes
    first: a command-line flag that carries the name or a field such as `loss_type: str = ...`, then an
    assignment such as `x = config.x` or a class that carries the name. Reads such as `cfg.get("name")`,
    comments and docstring bullets come last."""
    body = text.strip()
    if body.startswith(("#", "- ", "* ")):
        return 3
    raw = needle.strip("'\"")
    bare = re.escape(raw)
    read = re.search(rf"""(\.get\(|\[)\s*["']{bare}["']""", body)
    quoted = re.search(rf"""["']{bare}["']""", body) and not read
    flag = re.search(rf"""["']--[\w.-]*{bare}[\w.-]*["']""", body, re.I)
    field = re.match(rf"{bare}\s*:", body, re.I)
    assign = re.match(rf"{bare}\s*=", body, re.I)
    named = re.match(rf"class\s+\w*{re.escape(raw.replace('_', ''))}", body.replace("_", ""), re.I)
    listed = re.match(rf"""["']{bare}[\w.-]*["'],?$""", body)
    if by_name or needle.startswith("-"):
        return 0 if quoted else 1 if (flag or field or assign or named) else 2
    return 0 if (flag or field) else 1 if (quoted or assign or named or listed) else 2


def setting_from(literal: str, text: str) -> str | None:
    """The name a user writes for a flag: the command-line flag on the matched line when it carries the
    literal, otherwise the identifier in the literal. None for functions, classes and value lists."""
    bare = literal.strip().strip("'\"")
    flag = re.search(rf"""["'](--[\w.-]*{re.escape(bare)}[\w.-]*)["']""", text)
    if flag:
        return flag.group(1)
    if re.match(r"(def|class)\s|[A-Z]", bare) or re.search(r"[(\[]", bare):
        return None
    return re.split(r"[:=\s]", bare)[0] or None


def grep_first(repo: Path, sha: str, needles: list[str], paths: list[str],
               by_name: bool = False) -> tuple[str, int, str] | None:
    """First (path, line) at `sha` that contains any needle, preferring lines that define the option,
    then Python files over others. The last attempt ignores case, for registries that name an option
    through a class name."""
    hits = []
    for needle, flags in [(n, ["-F"]) for n in needles] + [(needles[-1], ["-F", "-i"])]:
        out = git(repo, "grep", "-n", *flags, "-e", needle, sha, "--", *paths)
        for line in out.splitlines():
            m = re.match(rf"{re.escape(sha)}:(.+?):(\d+):(.*)", line)
            if m:
                hits.append((m.group(1), int(m.group(2)), definition_rank(m.group(3), needle, by_name), m.group(3)))
        if hits:
            break
    if not hits:
        return None
    hits.sort(key=lambda h: (h[2], not h[0].endswith(".py"), "/test" in h[0], h[0], h[1]))
    return hits[0][0], hits[0][1], hits[0][3]


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config" / "frameworks.yaml").read_text(encoding="utf-8"))["frameworks"]
    tmap = yaml.safe_load((ROOT / "config" / "token_map.yaml").read_text(encoding="utf-8"))
    head = json.loads((GEN / "framework_head.json").read_text(encoding="utf-8"))
    links: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for fw, spec in cfg.items():
        repo, info = REPOS / fw, head[fw]
        sha = info["head_sha"]
        base = spec["url"].rstrip("/")
        label = "verl" if fw == "verl_recipe" else fw
        for surface in spec["surfaces"]:
            kind, sid = surface["kind"], surface["id"]
            smap = tmap.get(fw, {}).get(sid, {})
            if kind == "defaults":
                dmap = tmap.get("_defaults", {}).get(fw, {})
                for tv in info["surfaces"].get(sid, []):
                    tok, _, val = tv.partition("=")
                    m = (dmap.get(tok) or {}).get(val)
                    mid = m["method"] if isinstance(m, dict) else m
                    if not mid:
                        continue
                    d = next(x for x in surface["defaults"] if x["token"] == tok)
                    loc = grep_first(repo, sha, [tok], d["paths"])
                    if loc:
                        url = f"{base}/blob/{sha}/{loc[0]}#L{loc[1]}"
                        tier = "conditional_default" if isinstance(m, dict) and m.get("condition") else "default"
                        entry = {"token": tv, "tier": tier, "setting": tv, "path": loc[0], "line": loc[1], "url": url}
                        if entry not in links[mid][label]:
                            links[mid][label].append(entry)
                continue
            for tok in info["surfaces"].get(sid, []):
                mapped = smap.get(tok.split("=")[0])
                if not mapped or (isinstance(mapped, str) and mapped.startswith("~")):
                    continue
                loc, is_dir, setting = None, False, None
                if kind == "values":
                    paths = sorted({p for pat in surface["patterns"] for p in pat["paths"]})
                    loc = grep_first(repo, sha, [f'"{tok}"', f"'{tok}'", tok], paths, by_name=True)
                    # a value read from a class name, such as `GeneralizedAdvantageEstimator`, is not one a user writes
                    setting = tok if loc and re.search(rf"""["']{re.escape(tok)}["']""", loc[2]) else None
                elif kind == "flags":
                    flag = next(f for f in surface["flags"] if f["token"] == tok)
                    if "link" in flag:  # the parser's literal is not where a user sets the option
                        loc = grep_first(repo, sha, [flag["link"]["literal"]], [flag["link"]["path"]])
                        setting = flag["link"]["setting"]
                    else:
                        loc = grep_first(repo, sha, [flag["literal"]], surface["scope"])
                        setting = setting_from(flag["literal"], loc[2]) if loc else None
                elif kind == "dirs":
                    d = surface["dir"]
                    loc, is_dir = ((tok if d in ("", ".") else f"{d}/{tok}"), None), True
                elif kind == "files":
                    rx = re.compile(surface["regex"])
                    names = git(repo, "ls-tree", "--name-only", f"{sha}:{surface['dir']}").splitlines()
                    name = next((n for n in names if (m := rx.match(n)) and m.group(1) == tok), None)
                    loc = (f"{surface['dir']}/{name}", None) if name else None
                elif kind == "manual":
                    ent = next(e for e in surface["entries"] if e["token"] == tok)
                    loc = grep_first(repo, sha, [ent["literal"]], [ent["path"]])
                if not loc:
                    continue
                path, line = loc[:2]
                url = f"{base}/{'tree' if is_dir else 'blob'}/{sha}/{path}" + (f"#L{line}" if line else "")
                for mid in (mapped if isinstance(mapped, list) else [mapped]):
                    entry = {"token": tok, "tier": surface["tier"], "setting": setting, "path": path, "line": line,
                             "url": url}
                    if entry not in links[mid][label]:
                        links[mid][label].append(entry)
    out = {m: dict(v) for m, v in sorted(links.items())}
    (GEN / "impl_links.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    n = sum(len(v) for fws in out.values() for v in fws.values())
    print(f"{len(out)} methods, {n} located options")


if __name__ == "__main__":
    main()
