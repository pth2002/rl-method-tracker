"""Other open-source RL frameworks against the selection criteria, and what the qualifying ones add.

Criteria: built for RL post-training of language models, runs its own training loop with several
selectable RL algorithms, developed in a public repository, and at least 2,000 GitHub stars.
The seven tracked frameworks meet them. For other candidates the table records stars and the
reason a framework falls outside. Qualifying frameworks that are not tracked are scanned at their
latest commit for arXiv identifiers of general pool papers, and an inspected list records which
citations sit next to an implementation.

  python tools/framework_candidates.py --fetch   # GitHub stars and shallow clones (network)
  python tools/framework_candidates.py           # rebuild the json from the last fetch

Writes data/generated/framework_candidates.json.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"
CLONES = ROOT / ".cache" / "extra_repos"
MIN_STARS = 2000

# repository, own training loop with several RL algorithms, built for RL post-training, reason if outside
CANDIDATES = [
    ("volcengine/verl", True, True, None),
    ("huggingface/trl", True, True, None),
    ("OpenRLHF/OpenRLHF", True, True, None),
    ("NVIDIA-NeMo/RL", True, True, None),
    ("alibaba/ROLL", True, True, None),
    ("THUDM/slime", True, True, None),
    ("inclusionAI/AReaL", True, True, None),
    ("allenai/open-instruct", True, True, None),
    ("NovaSky-AI/SkyRL", True, True, None),
    ("PrimeIntellect-ai/prime-rl", True, True, None),
    ("RLinf/RLinf", True, True, None),
    ("modelscope/ms-swift", False, False, "general fine-tuning; its RL trainers build on TRL"),
    ("hiyouga/LLaMA-Factory", False, False, "general fine-tuning"),
    ("unslothai/unsloth", False, False, "general fine-tuning; its RL trainers build on TRL"),
    ("huggingface/open-r1", False, True, "a recipe that trains with TRL"),
    ("OpenPipe/ART", False, True, "trains through Unsloth and TRL"),
    ("rllm-org/rllm", False, True, "trains through verl"),
    ("radixark/miles", False, True, "a fork of slime"),
    ("PrimeIntellect-ai/verifiers", False, True, "an environment library"),
    ("meta-pytorch/torchtune", False, False, "general fine-tuning"),
    ("sail-sg/oat", True, True, "fewer than 2,000 stars"),
    ("ChenmienTan/RL2", True, True, "fewer than 2,000 stars"),
    ("meta-pytorch/torchforge", True, True, "fewer than 2,000 stars"),
]
TRACKED = {"volcengine/verl", "huggingface/trl", "OpenRLHF/OpenRLHF", "NVIDIA-NeMo/RL", "alibaba/ROLL",
           "THUDM/slime", "inclusionAI/AReaL"}
# citations at the latest commit that sit next to an implementation, checked by reading the code
IMPLEMENTED = {"allenai/open-instruct": {"2603.01365": "open_instruct/grpo_utils.py, rho_mask_tv_divergence"},
               "PrimeIntellect-ai/prime-rl": {"2506.24119": "configs/algorithm.py, type rae"}}
ID = re.compile(r"(?<![\d.])(2[56]\d{2}\.\d{5})(?:v\d)?(?!\d)")


def fetch() -> dict:
    out = {}
    for repo, *_ in CANDIDATES:
        r = subprocess.run(["gh", "api", f"repos/{repo}", "--jq",
                            "[.full_name, .stargazers_count, .archived] | @tsv"], capture_output=True, text=True)
        name, stars, archived = r.stdout.strip().split("\t")
        out[repo] = {"current_name": name, "stars": int(stars), "archived": archived == "true"}
    CLONES.mkdir(parents=True, exist_ok=True)
    for repo, *_ in CANDIDATES:
        if repo in TRACKED or not qualifies(repo, out[repo]["stars"]):
            continue
        d = CLONES / repo.split("/")[1]
        if not d.exists():
            subprocess.run(["git", "clone", "-q", "--depth", "1", f"https://github.com/{repo}.git", str(d)], check=True)
        else:
            subprocess.run(["git", "-C", str(d), "pull", "-q", "--depth", "1"], check=False)
        log = subprocess.run(["git", "-C", str(d), "log", "-1", "--format=%H %cs"], capture_output=True, text=True).stdout.split()
        grep = subprocess.run(["git", "-C", str(d), "grep", "-I", "-h", "-E", r"2[56][0-9]{2}\.[0-9]{5}"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        out[repo].update({"commit": log[0], "date": log[1], "cited": sorted(set(ID.findall(grep)))})
    return out


def qualifies(repo: str, stars: int) -> bool:
    own, rl, _ = next(c[1:] for c in CANDIDATES if c[0] == repo)
    return own and rl and stars >= MIN_STARS


def main() -> None:
    path = GEN / "framework_candidates.json"
    raw = fetch() if "--fetch" in sys.argv else {r["repo"]: r for r in json.loads(path.read_text(encoding="utf-8"))["candidates"]}
    pool = {json.loads(l)["arxiv"]: json.loads(l) for l in (GEN / "pool_adoption.jsonl").read_text(encoding="utf-8").splitlines() if l}
    general = {a for a, r in pool.items() if r["strict_general"]}
    included = {a for a in general if pool[a]["adopted"]}
    rows = []
    for repo, own, rl, reason in CANDIDATES:
        d = raw[repo]
        q = qualifies(repo, d["stars"])
        row = {"repo": repo, "current_name": d["current_name"], "stars": d["stars"], "archived": d["archived"],
               "tracked": repo in TRACKED, "meets_criteria": q, "reason_outside": None if q else reason}
        if q and repo not in TRACKED:
            cited = [a for a in d["cited"] if a in general]
            row.update({"commit": d["commit"], "date": d["date"], "cited": d["cited"],
                        "general_cited": cited, "general_cited_included": [a for a in cited if a in included],
                        "general_new_implemented": sorted(a for a in IMPLEMENTED.get(repo, {}) if a in general and a not in included)})
        rows.append(row)
    path.write_text(json.dumps({"min_stars": MIN_STARS, "candidates": rows}, indent=1, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    new = sorted({a for r in rows for a in r.get("general_new_implemented", [])})
    print(f"{sum(r['meets_criteria'] for r in rows)} meet the criteria, {sum(r['tracked'] for r in rows)} tracked; "
          f"untracked qualifying frameworks add {len(new)} general methods: {new}")


if __name__ == "__main__":
    main()
