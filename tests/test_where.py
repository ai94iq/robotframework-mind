"""Behavior tests: call the CLI the way a script does and check the lines it prints."""
import json
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

import robot_mind
from robot_mind import run

FIXTURE = Path(__file__).parent / "fixture"


class WhereTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "repo"
        shutil.copytree(FIXTURE, self.root)
        self.cache = self.tmp / "cache"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def where(self, *argv):
        return run(list(argv), root=self.root, cache_dir=self.cache)

    def test_ticket_lists_the_tagged_test_with_its_role_and_location(self):
        out = self.where("ticket", "PROJ-2120")
        self.assertIn("test  Change Zone NEW Lists Zones  tests/cases.robot:6", out)
        self.assertIn("role:role_team_lead", out)
        self.assertNotIn("Cases Page Opens For QC", out)

    def test_kw_shows_every_definition_with_args_and_first_doc_line(self):
        out = self.where("kw", "open profile browser")
        self.assertIn("resources/common.resource:11", out)
        self.assertIn("collections/cases_page.resource:5", out)
        self.assertIn("${profile}, ${headless}=${True}", out)
        self.assertIn("Opens a browser on a fresh profile.", out)
        self.assertNotIn("Second line of docs.", out)

    def test_callers_lists_keywords_tests_and_suite_fixtures(self):
        out = self.where("callers", "Open Profile Browser")
        self.assertIn("keyword  Open Authenticated Browser  resources/common.resource:19", out)
        self.assertNotIn("(${role})", out)
        self.assertIn("suite setup  tests/cases.robot:3", out)

    def test_tag_finds_tests_by_role(self):
        out = self.where("tag", "role:role_quality_control")
        self.assertIn("Cases Page Opens For QC", out)
        self.assertNotIn("Change Zone NEW Lists Zones", out)

    def test_find_matches_variable_values(self):
        out = self.where("find", "role_quality_control")
        self.assertIn("var  &{SHELL_RULES}  resources/common.resource:6", out)

    def test_find_reaches_json_docs_entries(self):
        out = self.where("find", "POST /api/items/query")
        self.assertIn("json  endpoints.POST /api/items/query  docs/roles.json", out)
        self.assertIn("apikey:PARTNER.status=403", out)

    def test_op_lists_the_endpoint_variable_and_the_keyword_using_it(self):
        out = self.where("find", "/api/items/query")
        self.assertIn("var  ${ENDPOINT_ITEMS_QUERY}", out)
        self.assertIn("keyword  Query Items", out)

    def test_index_rebuilds_after_a_file_changes(self):
        self.where("kw", "Open Cases Page")
        res = self.root / "collections" / "cases_page.resource"
        time.sleep(0.05)
        res.write_text(res.read_text() + "\nBrand New Keyword\n    Log    hi\n")
        out = self.where("kw", "Brand New Keyword")
        self.assertIn("collections/cases_page.resource:", out)

    def test_limit_caps_the_lines_printed(self):
        out = self.where("find", "Open", "--limit", "2")
        body = [line for line in out.splitlines() if line and not line.startswith("(")]
        self.assertEqual(len(body), 2)
        self.assertIn("more, raise --limit", out)

    def probe_keyword(self, rel, name):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"*** Keywords ***\n{name}\n    Log    x\n")

    def test_gitignored_folder_is_left_out(self):
        self.probe_keyword("probes/scratch.robot", "Throwaway Probe Keyword")
        (self.root / ".gitignore").write_text("# scratch\nprobes/\n")
        self.assertEqual(self.where("kw", "Throwaway Probe Keyword").strip(), "no match")
        self.assertIn("resources/common.resource:11", self.where("kw", "Open Profile Browser"))

    def test_gitignore_negation_keeps_a_file(self):
        self.probe_keyword("tmp/a.robot", "Dropped Keyword")
        self.probe_keyword("tmp/keep.robot", "Kept Keyword")
        (self.root / ".gitignore").write_text("tmp/*.robot\n!tmp/keep.robot\n")
        self.assertEqual(self.where("kw", "Dropped Keyword").strip(), "no match")
        self.assertIn("tmp/keep.robot", self.where("kw", "Kept Keyword"))

    def test_gitignore_glob_matches_any_depth(self):
        self.probe_keyword("a/b/c.draft.robot", "Draft Keyword")
        (self.root / ".gitignore").write_text("*.draft.robot\n")
        self.assertEqual(self.where("kw", "Draft Keyword").strip(), "no match")

    def test_anchored_gitignore_stays_at_its_folder(self):
        self.probe_keyword("out/top.robot", "Top Out Keyword")
        self.probe_keyword("sub/out/deep.robot", "Deep Out Keyword")
        (self.root / ".gitignore").write_text("/out\n")
        self.assertEqual(self.where("kw", "Top Out Keyword").strip(), "no match")
        self.assertIn("sub/out/deep.robot", self.where("kw", "Deep Out Keyword"))

    def test_callers_lines_leave_out_docs(self):
        out = self.where("callers", "Open Authenticated Browser")
        self.assertIn("keyword  Open Cases Page  collections/cases_page.resource:11", out)
        self.assertNotIn("(${role})", out)

    def test_a_folder_of_repos_indexes_each_repo_by_its_own_git_rules(self):
        workspace = self.tmp / "workspace"
        repo_a, repo_b = workspace / "repo-a", workspace / "group" / "repo-b"
        shutil.copytree(FIXTURE, repo_a)
        shutil.copytree(FIXTURE, repo_b)
        (repo_b / ".gitignore").write_text("collections/\n")
        (workspace / ".gitignore").write_text("repo-a/\n")          # a nested repo keeps only its own rules
        for repo in (repo_a, repo_b):
            (repo / ".git").mkdir()
        out = run(["kw", "Open Cases Page"], root=workspace, cache_dir=self.cache)
        self.assertIn("repo-a/collections/cases_page.resource:9", out)
        self.assertNotIn("repo-b", out)
        self.assertIn("group/repo-b/tests/cases.robot:6",
                      run(["ticket", "PROJ-2120"], root=workspace, cache_dir=self.cache))

    def test_find_repos_lists_nested_repos(self):
        workspace = self.tmp / "ws"
        for rel in ("repo-a", "group/repo-b", "repo-a/inner"):
            (workspace / rel / ".git").mkdir(parents=True)
        self.assertEqual(robot_mind.find_repos(workspace), ["group/repo-b", "repo-a"])

    def test_json_top_level_values_print_without_a_stray_equals(self):
        out = self.where("find", "principals")
        self.assertIn('json  principals  docs/roles.json  = ["apikey:PARTNER"', out)

    def test_callers_include_test_setup_and_teardown(self):
        out = self.where("callers", "Query Items")
        self.assertIn("test  Cases Page Cleans Up  tests/cases.robot:16", out)
        self.assertIn("test  Cases Page Cleans Up  tests/cases.robot:18", out)

    def test_default_tags_apply_only_to_tests_without_their_own(self):
        out = self.where("tag", "dflt:yes")
        self.assertIn("No Own Tags", out)
        self.assertNotIn("Has Own Tags", out)
        self.assertIn("own:yes", self.where("tag", "own:yes"))

    def test_find_matches_inline_var(self):
        out = self.where("find", "/api/inline/query")
        self.assertIn("var  ${END_INLINE}", out)
        self.assertIn("test  Inline Var Test", out)

    def test_callers_falls_back_to_substring_when_no_exact(self):
        out = self.where("callers", "Authenticated")
        self.assertIn("Open Cases Page", out)

    def test_find_suppresses_error_entries(self):
        self.assertEqual(self.where("find", "JSONDecodeError").strip(), "no match")

    def test_json_flag_prints_structured_hits(self):
        data = json.loads(self.where("find", "/api/items/query", "--json"))
        self.assertIsInstance(data, list)
        kinds = {d["kind"] for d in data}
        self.assertIn("var", kinds)
        self.assertIn("keyword", kinds)
        self.assertTrue(all("file" in d and "line" in d for d in data))

    def test_no_match_says_so(self):
        self.assertEqual(self.where("ticket", "PROJ-9999").strip(), "no match")

    def test_robot_files_over_the_size_cap_are_skipped(self):
        root = self.tmp / "big"
        root.mkdir()
        (root / "small.robot").write_text("*** Test Cases ***\nT\n    Log    x\n")
        (root / "big.robot").write_text("x" * 4096)
        old = robot_mind.ROBOT_MAX_BYTES
        robot_mind.ROBOT_MAX_BYTES = 100
        try:
            names = {p.name for p in robot_mind.source_files(root)}
        finally:
            robot_mind.ROBOT_MAX_BYTES = old
        self.assertIn("small.robot", names)
        self.assertNotIn("big.robot", names)

    def test_printed_lines_strip_escape_sequences(self):
        root = self.tmp / "esc"
        (root / "tests").mkdir(parents=True)
        (root / "tests" / "evil.robot").write_text(
            "*** Keywords ***\nEvil KW\n    [Documentation]    \x1b[31mRED\n    Log    x\n",
            encoding="utf-8")
        out = run(["kw", "Evil KW"], root=root, cache_dir=self.cache)
        self.assertNotIn("\x1b", out)
        self.assertIn("[31mRED", out)


if __name__ == "__main__":
    unittest.main()
