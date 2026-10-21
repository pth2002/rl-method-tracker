"""The project page data links every paper, landing and method page it offers to a method that exists."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def page_data() -> dict:
    src = (ROOT / "docs" / "data.js").read_text(encoding="utf-8")
    return json.loads(src[src.index("{"):src.rindex("}") + 1])


class PageDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = page_data()

    def test_paper_method_links_point_to_method_pages(self):
        methods = self.d["methods"]
        for p in self.d["papers"]:
            self.assertEqual(len(p), 8, p[0])
            for mid in p[7]:
                self.assertIn(mid, methods, p[0])

    def test_landings_link_to_existing_methods(self):
        for x in self.d["landings"]:
            self.assertTrue(x["id"] is None or x["id"] in self.d["methods"], x)

    def test_every_offered_cell_has_its_code_and_landing(self):
        for mid, m in self.d["methods"].items():
            self.assertIsInstance(m["symptoms"], list, mid)
            for fw, c in m["cells"].items():
                if c["tier"] == "removed":
                    self.assertTrue(c["date"], (mid, fw))
                    continue
                self.assertTrue(c.get("url"), (mid, fw))
                if "landed" in c:
                    self.assertRegex(c["ref"], r"^https://github\.com/[^/]+/[^/]+/(pull/\d+|commit/[0-9a-f]+)$")


if __name__ == "__main__":
    unittest.main()
