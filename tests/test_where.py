"""Behavior tests: call the CLI the way a script does and check the lines it prints."""
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

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

    def test_git_ignored_files_are_left_out_in_a_git_repo(self):
        probe = self.root / "probes" / "scratch.robot"
        probe.parent.mkdir()
        probe.write_text("*** Keywords ***\nThrowaway Probe Keyword\n    Log    x\n")
        (self.root / ".gitignore").write_text("probes/\n")
        for cmd in (["init", "-q"], ["add", "."]):
            subprocess.run(["git", *cmd], cwd=self.root, check=True)
        self.assertEqual(self.where("kw", "Throwaway Probe Keyword").strip(), "no match")
        self.assertIn("resources/common.resource:11", self.where("kw", "Open Profile Browser"))

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
        for repo in (repo_a, repo_b):
            for cmd in (["init", "-q"], ["add", "."]):
                subprocess.run(["git", *cmd], cwd=repo, check=True)
        out = run(["kw", "Open Cases Page"], root=workspace, cache_dir=self.cache)
        self.assertIn("repo-a/collections/cases_page.resource:9", out)
        self.assertNotIn("repo-b", out)
        self.assertIn("group/repo-b/tests/cases.robot:6",
                      run(["ticket", "PROJ-2120"], root=workspace, cache_dir=self.cache))

    def test_json_top_level_values_print_without_a_stray_equals(self):
        out = self.where("find", "principals")
        self.assertIn('json  principals  docs/roles.json  = ["apikey:PARTNER"', out)

    def test_no_match_says_so(self):
        self.assertEqual(self.where("ticket", "PROJ-9999").strip(), "no match")


if __name__ == "__main__":
    unittest.main()
