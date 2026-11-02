"""UI invariants: theme tokens, contrast, and the offscreen self-check."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication

FIXTURE = Path(__file__).parent / "fixture"


class FakeWorker(QObject):
    """Takes jobs without running them, so a test decides when each one ends."""

    finished = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self):
        super().__init__()
        self.jobs = []

    def reserve(self):
        return len(self.jobs) + 1

    def submit(self, call, job=None):
        self.jobs.append(call)
        return job or len(self.jobs)


class ThemeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_both_themes_have_the_same_tokens(self):
        from robot_mind_app.theme import THEMES
        self.assertEqual(set(THEMES["light"]), set(THEMES["dark"]))

    def test_text_has_enough_contrast(self):
        from robot_mind_app.theme import THEMES, contrast
        for name, t in THEMES.items():
            with self.subTest(theme=name):
                self.assertGreaterEqual(contrast(t["ink"], t["panel"]), 7)


class SelfCheckTest(unittest.TestCase):
    def test_self_check_writes_a_sound_report(self):
        from robot_mind_app.__main__ import main
        report = os.path.join(tempfile.mkdtemp(), "r.txt")
        self.assertEqual(main(["--self-check", report]), 0)
        with open(report, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("theme dark: ok", text)
        self.assertNotIn("error", text)


class LookupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "repo"
        shutil.copytree(FIXTURE, self.root)
        self.settings = QSettings(os.path.join(self.tmp, "t.ini"), QSettings.Format.IniFormat)
        self.worker = FakeWorker()
        from robot_mind_app.window import MainWindow
        self.window = MainWindow(worker=self.worker, settings=self.settings, cache_dir=self.tmp / "cache")
        self.addCleanup(self.window.close)
        self.window.set_repo(str(self.root))

    def test_command_dropdown_has_the_five_commands(self):
        self.assertEqual([self.window.command.itemText(i) for i in range(self.window.command.count())],
                         ["ticket", "kw", "callers", "tag", "find"])

    def test_a_search_fills_the_results_table(self):
        from robot_mind_app import engine
        self.window.command.setCurrentText("ticket")
        self.window.term.setText("PROJ-2120")
        job = self.window.search()
        hits = engine.query(self.root, "ticket", "PROJ-2120", cache_dir=self.tmp / "cache")
        self.worker.finished.emit(job, hits)
        self.assertGreater(self.window.results.rowCount(), 0)
        self.assertEqual(self.window.results.item(0, 1).text(), "Change Zone NEW Lists Zones")

    def test_search_without_a_repo_asks_for_one(self):
        self.window.repo = None
        self.assertIsNone(self.window.search())
        self.assertIn("Pick a robot repo", self.window.status.text())

    def test_no_match_shows_the_empty_state(self):
        job = self.window.search()
        self.worker.finished.emit(job, [])
        self.assertIs(self.window.stack.currentWidget(), self.window.empty_state)
        self.assertIn("No match", self.window.status.text())

    def test_a_large_result_set_is_bounded_and_counted(self):
        from robot_mind import Hit
        hits = [Hit("keyword", f"K{i}", "a.robot", line=1) for i in range(1000)]
        self.window.set_results(hits)
        self.assertEqual(self.window.results.rowCount(), self.window.DISPLAY_LIMIT)
        self.assertIn("1000", self.window.status.text())

    def test_a_broken_file_does_not_hide_the_rest_of_the_index(self):
        from robot_mind_app import engine
        hits = engine.query(self.root, "find", "/api/items/query", cache_dir=self.tmp / "cache")
        self.assertTrue(hits)

    def test_engine_query_returns_hits(self):
        from robot_mind_app import engine
        hits = engine.query(self.root, "kw", "Open Profile Browser", cache_dir=self.tmp / "cache")
        self.assertTrue(any(h.name == "Open Profile Browser" for h in hits))

    def test_saved_repo_persists(self):
        from robot_mind_app.settings import AppSettings
        AppSettings(self.settings).add_repo("C:/repos/a")
        self.assertIn("C:/repos/a", AppSettings(self.settings).repos())

    def test_history_records_a_query(self):
        from robot_mind_app.settings import AppSettings
        AppSettings(self.settings).add_history("ticket", "PROJ-1")
        self.assertEqual(AppSettings(self.settings).history()[0], ("ticket", "PROJ-1"))

    def test_open_in_editor_builds_an_argv_without_a_shell(self):
        from robot_mind_app.settings import open_in_editor
        self.assertEqual(open_in_editor("a b.robot", 12, "code --goto {file}:{line}"),
                         ["code", "--goto", "a b.robot:12"])

    def test_open_in_editor_unquotes_a_configured_path(self):
        from robot_mind_app.settings import open_in_editor
        argv = open_in_editor("a b.robot", 12, '"C:/Program Files/Code/code.exe" --goto {file}:{line}')
        self.assertEqual(argv, ["C:/Program Files/Code/code.exe", "--goto", "a b.robot:12"])

    def test_tag_filter_narrows_results(self):
        from robot_mind import Hit
        hits = [Hit("test", "T1", "a.robot", 1, tags=["role:admin"]),
                Hit("test", "T2", "a.robot", 2, tags=["role:guest"])]
        self.window.set_results(hits)
        self.window.filter.setText("role:admin")
        self.assertFalse(self.window.results.isRowHidden(0))
        self.assertTrue(self.window.results.isRowHidden(1))

    def test_copy_selected_puts_the_hit_on_the_clipboard(self):
        from robot_mind import Hit
        self.window.set_results([Hit("keyword", "Open X", "a.robot", 7)])
        self.window.results.selectRow(0)
        self.window.copy_selected()
        self.assertIn("Open X", QApplication.clipboard().text())

    def test_history_records_a_search(self):
        from robot_mind_app.settings import AppSettings
        self.window.command.setCurrentText("kw")
        self.window.term.setText("Open Profile Browser")
        self.window.search()
        self.assertEqual(AppSettings(self.settings).history()[0], ("kw", "Open Profile Browser"))

    def test_the_limit_control_caps_the_displayed_rows(self):
        from robot_mind import Hit
        self.window.limit.setValue(2)
        self.window.set_results([Hit("keyword", f"K{i}", "a.robot", line=1) for i in range(5)])
        self.assertEqual(self.window.results.rowCount(), 2)
        self.assertIn("5", self.window.status.text())

    def test_history_menu_shows_saved_history_on_startup(self):
        from robot_mind_app.settings import AppSettings
        from robot_mind_app.window import MainWindow
        AppSettings(self.settings).add_history("tag", "role:admin")
        window = MainWindow(worker=self.worker, settings=self.settings, cache_dir=self.tmp / "cache")
        self.addCleanup(window.close)
        self.assertIn("tag: role:admin", [a.text() for a in window.history_menu.actions()])


if __name__ == "__main__":
    unittest.main()
