"""Mechanical checks for the house writing rules on the rendered text of paper/main.pdf.

Flags: dashes used as punctuation, semicolons, relative clauses with which/where/whose/what,
sentences longer than about three lines (45 words in the single-column layout), sentences that
start with a digit, and banned words. Prints every hit with its page.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
BANNED = ["delve", "leverage", "crucial", "crucially", "furthermore", "moreover", "notably", "in conclusion"]


def main() -> int:
    doc = fitz.open(ROOT / "paper" / "main.pdf")
    hits = 0
    for pno, page in enumerate(doc, 1):
        text = page.get_text()
        if "References" in text and pno > 2:
            text = text.split("References")[0]
        body = re.sub(r"-\n", "", text).replace("\n", " ")
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", body):
            words = s.split()
            probs = []
            if re.search(r"\s[—–]\s|—", s):
                probs.append("dash")
            if ";" in s:
                probs.append("semicolon")
            if re.search(r",? (which|whose) ", s) or re.search(r"\b(where|what) [a-z]+ (is|are|was|were)\b", s):
                probs.append("relative clause")
            if len(words) > 45:
                probs.append(f"{len(words)} words")
            if re.match(r"^\d", s.strip()) and not re.match(r"^\d+(\.\d+)? ", s.strip()) is None:
                probs.append("starts with digit")
            for b in BANNED:
                if re.search(rf"\b{b}\b", s, re.I):
                    probs.append(f"word '{b}'")
            if probs:
                hits += 1
                print(f"p{pno} [{', '.join(probs)}] {s[:160]}")
    print(f"{hits} flagged sentences")
    return 0


if __name__ == "__main__":
    sys.exit(main())
