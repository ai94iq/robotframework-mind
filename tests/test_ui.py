"""UI invariants: theme tokens, contrast, and the offscreen self-check."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QSettings, Qt, Signal
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
        self.assertIn("query: 1 hit", text)
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

    def test_command_menu_has_the_five_commands(self):
        self.assertEqual([a.data() for a in self.window.command_menu.actions()],
                         ["ticket", "kw", "callers", "tag", "find"])

    def test_search_types_explain_themselves(self):
        self.window.set_command("callers")
        self.assertEqual(self.window.command.text(), "Who calls it", "button label")
        self.assertIn("called", self.window.command_hint.text(), "description under the bar")
        action = self.window.command_menu.actions()[2]
        self.assertIn("\t", action.text(), "menu row carries the description")

    def test_open_without_selection_says_so(self):
        self.window.open_selected()
        self.assertIn("Select", self.window.status.text())

    def test_a_search_fills_the_results_table(self):
        from robot_mind_app import engine
        self.window.set_command("ticket")
        self.window.term.setText("PROJ-2120")
        job = self.window.search()
        hits = engine.query(self.root, "ticket", "PROJ-2120", cache_dir=self.tmp / "cache")
        self.worker.finished.emit(job, hits)
        self.assertGreater(self.window.results.rowCount(), 0)
        self.assertEqual(self.window.results.item(0, 1).text(), "Change Zone NEW Lists Zones")

    def test_search_without_a_repo_asks_for_one(self):
        self.window.repo = None
        self.assertIsNone(self.window.search())
        self.assertIs(self.window.stack.currentWidget(), self.window.empty_state)
        self.assertEqual(self.window.empty_state.title.text(), "Please pick a repo first")

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

    def test_vscode_url_opens_at_the_line(self):
        from robot_mind_app.settings import editor_url
        self.assertEqual(editor_url("C:/repos/r", "a b/x.robot", 12), "vscode://file/C:/repos/r/a%20b/x.robot:12")

    def test_editor_menu_picks_the_editor(self):
        actions = {a.text(): a for a in self.window.editor_menu.actions() if a.text()}
        self.assertIn("System default app", actions)
        actions["System default app"].trigger()
        self.assertEqual(self.window.saved.editor_command(), "default", "stored")
        self.assertEqual(self.window.editor_button.text(), "Editor: System default app", "shown")

    def test_script_editor_is_refused(self):
        from robot_mind_app.settings import check_program
        with self.assertRaises(ValueError):
            check_program("C:/Program Files/Microsoft VS Code/bin/code.cmd")
        self.assertEqual(check_program("C:/x/notepad.exe"), "C:/x/notepad.exe")

    def workspace(self):
        root = self.tmp / "workspace"
        for rel in ("repo-a", "group/repo-b"):
            shutil.copytree(FIXTURE, root / rel)
            (root / rel / ".git").mkdir()
        return root

    def test_folders_show_for_a_workspace(self):
        self.window.set_repo(str(self.workspace()))
        self.worker.finished.emit(len(self.worker.jobs), self.worker.jobs[-1]())
        self.assertFalse(self.window.folders_toggle.isHidden(), "offered")
        self.assertIn("2 repos", self.window.folders_toggle.text(), "count")
        self.assertTrue(self.window.folders.isHidden(), "collapsed until opened")
        self.assertEqual(self.window.scope(), None, "all ticked searches everything")

    def test_unticked_folder_leaves_the_search(self):
        root = self.workspace()
        self.window.set_repo(str(root))
        self.worker.finished.emit(len(self.worker.jobs), self.worker.jobs[-1]())
        self.window.folders.topLevelItem(1).setCheckState(0, Qt.CheckState.Unchecked)   # repo-a
        self.assertEqual(self.window.scope(), ["group/repo-b"])
        self.window.set_command("kw")
        self.window.term.setText("Open Cases Page")
        hits = self.worker.jobs[self.window.search() - 1]()
        self.assertTrue(hits and all(h.file.startswith("group/repo-b/") for h in hits))

    def test_folders_hidden_for_one_repo(self):
        self.worker.finished.emit(len(self.worker.jobs), self.worker.jobs[-1]())
        self.assertTrue(self.window.folders_toggle.isHidden())

    def test_open_in_editor_builds_an_argv_without_a_shell(self):
        from robot_mind_app.settings import open_in_editor
        self.assertEqual(open_in_editor("a b.robot", 12, "code --goto {file}:{line}"),
                         ["code", "--goto", "a b.robot:12"])

    def test_open_in_editor_unquotes_a_configured_path(self):
        from robot_mind_app.settings import open_in_editor
        argv = open_in_editor("a b.robot", 12, '"C:/Program Files/Code/code.exe" --goto {file}:{line}')
        self.assertEqual(argv, ["C:/Program Files/Code/code.exe", "--goto", "a b.robot:12"])

    def test_open_in_editor_prefixes_a_dash_filename(self):
        from robot_mind_app.settings import open_in_editor
        self.assertEqual(open_in_editor("--x.robot", 3, "code --goto {file}:{line}"),
                         ["code", "--goto", "./--x.robot:3"])

    def test_editor_command_ignores_a_blank_stored_value(self):
        from robot_mind_app.settings import AppSettings, DEFAULT_EDITOR
        AppSettings(self.settings).set_editor_command("   ")
        self.assertEqual(AppSettings(self.settings).editor_command(), DEFAULT_EDITOR)

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
        self.window.set_command("kw")
        self.window.term.setText("Open Profile Browser")
        self.window.search()
        self.assertEqual(AppSettings(self.settings).history()[0], ("kw", "Open Profile Browser"))

    def test_the_limit_control_caps_the_displayed_rows(self):
        from robot_mind import Hit
        self.window.limit.setValue(2)
        self.window.set_results([Hit("keyword", f"K{i}", "a.robot", line=1) for i in range(5)])
        self.assertEqual(self.window.results.rowCount(), 2)
        self.assertIn("5", self.window.status.text())

    def test_recent_shows_saved_history_on_startup(self):
        from robot_mind_app.settings import AppSettings
        from robot_mind_app.window import MainWindow
        AppSettings(self.settings).add_history("tag", "role:admin")
        window = MainWindow(worker=self.worker, settings=self.settings, cache_dir=self.tmp / "cache")
        self.addCleanup(window.close)
        texts = [window.history_list.item(i).text() for i in range(window.history_list.count())]
        self.assertIn("Tag: role:admin", texts)

    def graph_search(self, command, term):
        self.window.set_mode("graph")
        self.window.set_command(command)
        self.window.term.setText(term)
        job = self.window.search()
        self.worker.finished.emit(job, self.worker.jobs[-1]())

    def test_graph_mode_draws_the_graph(self):
        self.graph_search("ticket", "PROJ-2120")
        self.assertIs(self.window.stack.currentWidget(), self.window.graph_view)
        labels = {item.node.label for item in self.window.graph_view.node_items()}
        self.assertIn("Open Cases Page", labels)
        self.assertIn("GET /api/zones/list", labels)

    def test_second_graph_search_redraws(self):
        self.graph_search("ticket", "PROJ-2120")
        self.graph_search("kw", "Query Items")
        labels = {item.node.label for item in self.window.graph_view.node_items()}
        self.assertIn("${ENDPOINT_ITEMS_QUERY}", labels)

    def test_unticked_community_hides_its_dots(self):
        self.graph_search("kw", "Query Items")
        self.window.graph_view.panel.rows[0].box.setChecked(False)
        hidden = [i for i in self.window.graph_view.node_items() if i.group == 0]
        self.assertTrue(hidden and not any(i.isVisible() for i in hidden))

    def test_community_click_highlights(self):
        self.graph_search("kw", "Query Items")
        self.window.graph_view.panel.highlight(0)
        dimmed = [i for i in self.window.graph_view.node_items() if i.group != 0]
        lit = [i for i in self.window.graph_view.node_items() if i.group == 0]
        self.assertTrue(dimmed and all(i.opacity() < 1 for i in dimmed), "others dimmed")
        self.assertTrue(all(i.opacity() == 1 for i in lit), "chosen stays bright")

    def test_hover_names_the_neighbours(self):
        self.graph_search("kw", "Query Items")
        view = self.window.graph_view
        caller = next(i for i in view.node_items() if i.node.label == "Open Authenticated Browser")
        view.hover(caller)
        names = {label.text() for label in view.hover_labels}
        self.assertIn("Open Authenticated Browser", names)
        view.hover(None)
        self.assertEqual(view.hover_labels, [])

    def test_long_name_ends_with_dots(self):
        from robot_mind_app.widgets import ElidedLabel
        label = ElidedLabel("sample-team-checkout-api-automation")
        label.show()                       # Qt sends resize events to shown widgets only
        self.addCleanup(label.close)
        label.resize(80, 20)
        self.assertTrue(label.text().endswith("…"), label.text())
        self.assertEqual(label.toolTip(), "sample-team-checkout-api-automation")

    def test_crowded_labels_move_aside(self):
        from PySide6.QtCore import QPointF, QSizeF
        from robot_mind_app.graph_view import place
        taken = []
        first = place(QPointF(0, 0), QSizeF(80, 14), 5, taken)
        second = place(QPointF(0, 0), QSizeF(80, 14), 5, taken)
        self.assertGreater(first.x(), 0, "first label to the right")
        self.assertNotEqual(first, second, "second label elsewhere")
        self.assertFalse(taken[0].intersects(taken[1]), "no overlap")

    def test_graph_chip_shows_drawn_of_total(self):
        self.graph_search("ticket", "PROJ-2120")
        self.assertRegex(self.window.count_chip.text(), r"^\d+ of \d+ nodes$")

    def test_failure_shows_a_banner(self):
        self.window.worker.failed.emit(1, "index broke")
        self.assertFalse(self.window.banner.isHidden())
        self.assertIn("index broke", self.window.banner.text())

    def test_graph_mode_hides_table_controls(self):
        self.window.set_mode("graph")
        self.assertTrue(self.window.filter.isHidden(), "filter")
        self.assertTrue(self.window.limit.isHidden(), "rows")

    def test_graph_copy_uses_the_node(self):
        self.graph_search("kw", "Query Items")
        item = next(i for i in self.window.graph_view.node_items() if i.node.label == "Query Items")
        item.setSelected(True)
        self.window.copy_selected()
        self.assertIn("Query Items", QApplication.clipboard().text())

    def test_graph_no_match_is_empty(self):
        self.graph_search("ticket", "PROJ-9999")
        self.assertIs(self.window.stack.currentWidget(), self.window.empty_state)
        self.assertIn("No match", self.window.status.text())

    def test_clicking_a_saved_repo_activates_it_and_resets_the_view(self):
        from robot_mind_app.settings import AppSettings
        from robot_mind_app.window import MainWindow
        AppSettings(self.settings).add_repo("C:/repoA")
        window = MainWindow(worker=self.worker, settings=self.settings, cache_dir=self.tmp / "cache")
        self.addCleanup(window.close)
        item = next(window.repos_list.item(i) for i in range(window.repos_list.count())
                    if window.repos_list.item(i).data(Qt.ItemDataRole.UserRole) == "C:/repoA")
        window.repos_list.itemClicked.emit(item)
        self.assertEqual(window.repo, "C:/repoA")
        self.assertEqual(window.page_title.text(), "repoA")
        self.assertIn("Ready", window.status.text())
        self.assertIs(window.stack.currentWidget(), window.empty_state)


if __name__ == "__main__":
    unittest.main()
