"""The citation scan reads text diffs only, so a run on Windows and the weekly run on Linux agree."""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))
import code_citations  # noqa: E402


class FakeProcess:
    """Stands in for `git log` and records the command it was given."""
    cmd: list[str] = []

    def __init__(self, cmd, **kwargs):
        FakeProcess.cmd = cmd
        self.stdout = io.StringIO(
            "@@COMMIT\tabc123\t2026-10-20\tA Person\tadd a loss\n"
            "+++ b/trainer/loss.py\n"
            "+# see https://arxiv.org/abs/2501.00001\n")

    def wait(self) -> int:
        return 0


class ScanTests(unittest.TestCase):
    def test_scan_never_converts_binary_files_to_text(self):
        with patch.object(code_citations.subprocess, "Popen", FakeProcess):
            code_citations.scan("areal", {"2501.00001"})
        self.assertIn("--no-textconv", FakeProcess.cmd)
        self.assertIn("--no-ext-diff", FakeProcess.cmd)

    def test_scan_records_a_linked_citation_in_a_text_file(self):
        with patch.object(code_citations.subprocess, "Popen", FakeProcess):
            rows = code_citations.scan("areal", {"2501.00001"})
        self.assertEqual([(r["arxiv"], r["path"], r["linked"]) for r in rows],
                         [("2501.00001", "trainer/loss.py", True)])


if __name__ == "__main__":
    unittest.main()
