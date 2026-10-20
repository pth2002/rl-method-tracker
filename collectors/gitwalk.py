"""Small git helpers shared by the collectors.

All history walks use --first-parent on the default branch, so a date is the
day a change landed on main, not the day it was written on a feature branch.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


def git(repo: Path, *args: str, check: bool = True) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {repo}: {out.stderr.strip()}")
    return out.stdout


@dataclass(frozen=True)
class Commit:
    sha: str
    date: str          # committer date on main, YYYY-MM-DD
    author: str
    subject: str

    @property
    def pr(self) -> int | None:
        m = re.search(r"\(#(\d+)\)\s*$", self.subject)
        return int(m.group(1)) if m else None

    def as_dict(self) -> dict:
        return {"sha": self.sha, "date": self.date, "author": self.author,
                "subject": self.subject, "pr": self.pr}


_SEP = "\x1f"
_FMT = _SEP.join(["%H", "%cs", "%an", "%s"])


def _parse(lines: str) -> list[Commit]:
    out = []
    for line in lines.splitlines():
        if not line.strip():
            continue
        sha, date, an, subj = line.split(_SEP, 3)
        out.append(Commit(sha, date, an, subj))
    return out


def head_branch(repo: Path) -> str:
    ref = git(repo, "symbolic-ref", "--short", "HEAD").strip()
    return ref


def commits_touching(repo: Path, paths: list[str]) -> list[Commit]:
    """First-parent commits on HEAD that touch any of `paths`, oldest first."""
    return _parse(git(repo, "log", "--first-parent", "--reverse", f"--format={_FMT}", "HEAD", "--", *paths))


def commits_pickaxe(repo: Path, literal: str, scope: list[str]) -> list[Commit]:
    """First-parent commits that change the number of occurrences of `literal`."""
    return _parse(git(repo, "log", "--first-parent", "--reverse", f"-S{literal}",
                      f"--format={_FMT}", "HEAD", "--", *scope))


def commit_info(repo: Path, rev: str) -> Commit:
    return _parse(git(repo, "log", "-1", f"--format={_FMT}", rev))[0]


class BlobReader:
    """Streams file contents at given commits through one `git cat-file --batch`."""

    def __init__(self, repo: Path):
        self.proc = subprocess.Popen(
            ["git", "-C", str(repo), "cat-file", "--batch"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )

    def read(self, sha: str, path: str) -> str | None:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(f"{sha}:{path}\n".encode())
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().decode()
        if header.endswith("missing\n") or not header.strip():
            return None
        size = int(header.split()[2])
        data = self.proc.stdout.read(size)
        self.proc.stdout.read(1)  # trailing newline
        return data.decode("utf-8", errors="replace")

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait()


def list_dir(repo: Path, sha: str, directory: str) -> list[str]:
    """Immediate subdirectory names of `directory` at commit `sha`."""
    if directory in ("", "."):
        out = git(repo, "ls-tree", "-d", "--name-only", sha, check=False)
    else:
        out = git(repo, "ls-tree", "-d", "--name-only", sha, directory.rstrip("/") + "/", check=False)
    return sorted(Path(p).name for p in out.splitlines() if p.strip())


def list_files(repo: Path, sha: str, directory: str) -> list[str]:
    """File names directly inside `directory` at commit `sha`."""
    out = git(repo, "ls-tree", "--name-only", sha, directory.rstrip("/") + "/", check=False)
    return sorted(Path(p).name for p in out.splitlines() if p.strip())


def files_containing(repo: Path, sha: str, literal: str, scope: list[str]) -> list[str]:
    out = git(repo, "grep", "-l", "-I", "-F", "-e", literal, sha, "--", *scope, check=False)
    # output lines look like "<sha>:<path>"
    return [line.split(":", 1)[1] for line in out.splitlines() if ":" in line]
