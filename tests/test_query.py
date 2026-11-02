"""Facade tests: query() returns typed Hit records for each command."""
import shutil
import tempfile
import unittest
from pathlib import Path

from robot_mind import Hit, query

FIXTURE = Path(__file__).parent / "fixture"


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "repo"
        shutil.copytree(FIXTURE, self.root)
        self.cache = self.tmp / "cache"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ticket_returns_a_hit_with_tags_and_location(self):
        hits = query(self.root, "ticket", "PROJ-2120", cache_dir=self.cache)
        hit = next(h for h in hits if h.kind == "test")
        self.assertEqual((hit.name, hit.file), ("Change Zone NEW Lists Zones", "tests/cases.robot"))
        self.assertIn("bug:PROJ-2120", hit.tags)

    def test_callers_sets_call_line_and_keeps_entry_line(self):
        hits = query(self.root, "callers", "Open Profile Browser", cache_dir=self.cache)
        h = next(h for h in hits if h.name == "Open Authenticated Browser")
        self.assertGreater(h.call_line, 0)
        self.assertNotEqual(h.call_line, h.line)

    def test_find_returns_var_and_keyword(self):
        hits = query(self.root, "find", "/api/items/query", cache_dir=self.cache)
        kinds = {h.kind for h in hits}
        self.assertIn("var", kinds)
        self.assertIn("keyword", kinds)

    def test_no_match_returns_an_empty_list(self):
        self.assertEqual(query(self.root, "ticket", "PROJ-9999", cache_dir=self.cache), [])


if __name__ == "__main__":
    unittest.main()
