"""Main window: a sidebar (repo + saved + folders + recent), a query bar, and a styled results table."""
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QUrl
from PySide6.QtGui import QAction, QActionGroup, QColor, QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QPushButton, QSizePolicy, QSpinBox, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from robot_mind import strip_controls

from . import editors, engine
from .folders import FolderTree
from .graph_layout import Drawing, plan
from .graph_view import GraphView
from .icons import ICON_SIZE, app_icon, icon
from .settings import AppSettings, check_program, editor_url, open_in_editor
from .theme import THEME_ICONS, THEME_MODES, apply_theme
from .widgets import EmptyState, card, plain_label, segmented, shade
from .worker import Worker

APP_NAME = "Robot Framework Mind"
ORG = "robotframework-mind"
# command key: (button label, what it finds, search box hint)
COMMAND_INFO = {
    "ticket": ("Ticket", "Tests and keywords whose tags, name or docs mention it", "ticket key or word, e.g. PROJ-2120"),
    "kw": ("Keyword", "Where a keyword is defined", "keyword name, e.g. Open Cases Page"),
    "callers": ("Who calls it", "Every place a keyword is called, with the line", "keyword name"),
    "tag": ("Tag", "Tests and keywords with this exact tag; end with * for a prefix", "tag, e.g. smoke or role:*"),
    "find": ("Anything", "Any name, tag, doc, argument or value that contains it", "any text, e.g. /api/items"),
}
COMMANDS = tuple(COMMAND_INFO)
KIND_TOKENS = {"test": "accent_text", "keyword": "ok", "var": "warn", "json": "ink2"}


@dataclass(frozen=True)
class FoundRepos:
    """The worker's answer to "which repos does this folder hold?"."""
    root: str
    repos: list[str]


def hit_detail(hit) -> str:
    """The detail column: tags for a test, signature and doc for a keyword, value otherwise."""
    if hit.kind == "test":
        return " ".join(hit.tags)
    if hit.kind == "keyword":
        args = f"({hit.args})" if hit.args else ""
        doc = f" - {hit.doc}" if hit.doc else ""
        return args + doc
    return hit.value


class MainWindow(QMainWindow):
    DISPLAY_LIMIT = 500
    GRAPH_LIMIT = 80             # nodes drawn at most; more than that stops reading as a picture

    def __init__(self, worker=None, settings=None, targets=(), task=None, cache_dir=None):
        super().__init__()
        self.worker = worker or Worker()
        self.settings = settings if settings is not None else QSettings(ORG, APP_NAME)
        self.saved = AppSettings(self.settings)
        mode = self.settings.value("theme", "system")
        self.theme_mode = mode if mode in THEME_MODES else "system"
        self.t = apply_theme(QApplication.instance(), self.theme_mode)
        self.cache_dir = cache_dir
        self.repo = None
        self.repo_list = []              # repos inside the chosen folder, when it holds several
        self.mode = "table"
        self._status_base = ""
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self._build()
        self.set_command(COMMANDS[0])
        self.refresh_repos()
        self.refresh_history()
        self.worker.finished.connect(self._finished)
        self.worker.failed.connect(self._failed)
        if hasattr(self.worker, "timed"):
            self.worker.timed.connect(self._timed)
        self.resize(1180, 760)

    # ---------------------------------------------------------------- layout
    def _build(self):
        central = QWidget()
        central.setObjectName("app")
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._sidebar())
        row.addWidget(self._main(), 1)
        self.setCentralWidget(central)

    def _sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(280)
        col = QVBoxLayout(sidebar)
        col.setContentsMargins(16, 18, 16, 14)
        col.setSpacing(10)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        self.brand_mark = plain_label()
        self.brand_mark.setFixedSize(24, 24)
        self.brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._brand_icon()
        brand.addWidget(self.brand_mark)
        brand.addWidget(plain_label("Robot Framework Mind", "brand"), 1)
        col.addLayout(brand)
        col.addWidget(plain_label("Exact lookups, one file:line per hit", "hint"))
        col.addSpacing(6)

        self.choose_button = QPushButton("Choose repo")
        self.choose_button.setObjectName("primary")
        self.choose_button.clicked.connect(self.choose_repo)
        col.addWidget(self.choose_button)
        col.addSpacing(6)

        col.addWidget(plain_label("Saved repos", "label"))
        self.repos_hint = plain_label("No saved repos yet", "hint")
        col.addWidget(self.repos_hint)
        self.repos_list = QListWidget()
        self.repos_list.setObjectName("nav")
        self.repos_list.itemClicked.connect(lambda item: self.set_repo(item.data(Qt.ItemDataRole.UserRole)))
        col.addWidget(self.repos_list, 2)

        self.folders_toggle = QToolButton()          # shown only when the folder holds two repos or more
        self.folders_toggle.setObjectName("folders_toggle")
        self.folders_toggle.setCheckable(True)
        self.folders_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.folders_toggle.setToolTip("Untick a repo to leave it out of the search")
        self.folders_toggle.toggled.connect(self._folders_look)
        self.folders_toggle.setHidden(True)
        self.folders = FolderTree()
        self.folders.itemChanged.connect(lambda *_: self._folders_look())
        col.addWidget(self.folders_toggle)
        col.addWidget(self.folders, 3)

        col.addWidget(plain_label("Recent", "label"))
        self.history_hint = plain_label("No recent queries", "hint")
        col.addWidget(self.history_hint)
        self.history_list = QListWidget()
        self.history_list.setObjectName("nav")
        self.history_list.itemClicked.connect(
            lambda item: self.run_history(*item.data(Qt.ItemDataRole.UserRole)))
        col.addWidget(self.history_list, 2)

        col.addStretch(1)
        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        self.theme_action = QAction("Theme", self)
        self.theme_action.triggered.connect(self.next_theme)
        self.theme_button = QToolButton()
        self.theme_button.setObjectName("theme")
        self.theme_button.setDefaultAction(self.theme_action)
        self.theme_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.theme_button.setIconSize(ICON_SIZE)
        self.theme_button.setAccessibleName("Theme")
        self.editor_button = QPushButton("Editor")
        self.editor_button.setToolTip("Which program Open uses to show a result")
        self._editor_menu()
        bottom.addWidget(self.theme_button)
        bottom.addWidget(self.editor_button)
        bottom.addStretch(1)
        col.addLayout(bottom)
        self._theme_look()
        return sidebar

    def _main(self):
        ground = QWidget()
        ground.setObjectName("ground")
        outer = QVBoxLayout(ground)
        outer.setContentsMargins(22, 18, 22, 12)
        outer.setSpacing(12)

        top = QWidget()
        top_col = QVBoxLayout(top)
        top_col.setContentsMargins(14, 0, 14, 0)
        top_col.setSpacing(12)
        self.page_title = plain_label("No repo selected", "pagetitle")
        self.page_sub = plain_label("Choose a repo to index its tests, keywords and docs", "hint")
        top_col.addWidget(self.page_title)
        top_col.addWidget(self.page_sub)
        top_col.addWidget(self._query_bar())
        self.command_hint = plain_label("", "hint")
        top_col.addWidget(self.command_hint)
        outer.addWidget(top)

        self.empty_state = EmptyState(self.t, "scan-search", "Ready when you are",
                                      "Choose a repo on the left, then search a ticket, keyword, tag or endpoint.")
        self.results = QTableWidget(0, 4)
        self.results.setHorizontalHeaderLabels(["Kind", "Name", "Location", "Detail"])
        self.results.verticalHeader().setVisible(False)
        self.results.setShowGrid(False)
        self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.setWordWrap(False)
        self.results.setIconSize(QSize(12, 12))
        self.results.verticalHeader().setDefaultSectionSize(34)
        header = self.results.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setFixedHeight(34)
        self.results.setColumnWidth(1, 250)
        self.results.setColumnWidth(2, 300)
        self.graph_view = GraphView(self.t)
        self.graph_view.activated.connect(lambda _node: self.open_selected())
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.results)
        self.stack.addWidget(self.graph_view)
        self.results_holder = card(self._results_pane(), self.t)
        self.cards = [self.results_holder]
        outer.addWidget(self.results_holder, 1)
        self.status = plain_label("", "hint")
        status_wrap = QWidget()
        status_col = QVBoxLayout(status_wrap)
        status_col.setContentsMargins(14, 0, 14, 0)
        status_col.addWidget(self.status)
        outer.addWidget(status_wrap)
        return ground

    def _query_bar(self):
        box = QFrame()
        box.setObjectName("bar")
        self.query_bar = box
        row = QHBoxLayout(box)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(8)
        self.command = QPushButton()
        self.command.setObjectName("command")
        self.command.setFixedWidth(140)
        self.command.setToolTip("What to search for")
        self.command_menu = QMenu(self.command)
        for key, (label, what, _hint) in COMMAND_INFO.items():
            action = self.command_menu.addAction(f"{label}\t{what}")      # the tab puts the description right
            action.setData(key)
            action.triggered.connect(lambda _=False, k=key: self.set_command(k))
        self.command.setMenu(self.command_menu)
        self.term = QLineEdit()
        self.term.returnPressed.connect(self.search)
        self.limit = QSpinBox()
        self.limit.setRange(1, self.DISPLAY_LIMIT)
        self.limit.setValue(self.DISPLAY_LIMIT)
        self.limit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.limit.setFixedWidth(76)
        self.limit.setToolTip("Most rows to show")
        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("primary")
        self.search_button.clicked.connect(self.search)
        row.addWidget(self.command)
        row.addWidget(self.term, 1)
        self.rows_label = plain_label("rows", "hint")
        row.addWidget(self.rows_label)
        row.addWidget(self.limit)
        row.addWidget(self.search_button)
        return box

    def _results_pane(self):
        pane = QWidget()
        column = QVBoxLayout(pane)
        column.setContentsMargins(12, 10, 12, 10)
        column.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.count_chip = plain_label("0 hits", "hint")     # a caption under the header, not a pill inside it
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("filter by tag, name or text")
        self.filter.textChanged.connect(self._apply_filter)
        self.copy_button = QPushButton("Copy")
        self.copy_button.setToolTip("Copy the selected hit")
        self.copy_button.clicked.connect(self.copy_selected)
        self.open_button = QPushButton("Open")
        self.open_button.setToolTip("Open the selected hit at its line in the editor")
        self.open_button.clicked.connect(self.open_selected)
        self.modes = QActionGroup(self)
        for name in ("Table", "Graph"):
            action = self.modes.addAction(name)
            action.setCheckable(True)
            action.setChecked(name == "Table")
            action.triggered.connect(lambda _=False, n=name.lower(): self.set_mode(n))
        head.addWidget(segmented(self.modes.actions()))
        head.addWidget(self.filter, 1)
        head.addStretch(0)                  # takes the filter's room when Graph mode hides it
        head.addWidget(self.copy_button)
        head.addWidget(self.open_button)
        column.addLayout(head)
        column.addWidget(self.count_chip)
        self.banner = plain_label("", "banner")       # a failure shows here, where the eyes are
        self.banner.setWordWrap(True)
        self.banner.setHidden(True)
        column.addWidget(self.banner)
        column.addWidget(self.stack, 1)
        return pane

    def show_error(self, text):
        self.banner.setText(strip_controls(text[:300]))
        self.banner.setHidden(False)

    # ---------------------------------------------------------------- repo and theme
    def choose_repo(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a robot repo", self.repo or "")
        if path:
            self.set_repo(path)
            self.saved.add_repo(self.repo)
            self.refresh_repos()

    def set_repo(self, path):
        self.repo = str(path)
        name = Path(self.repo).name or self.repo
        self.page_title.setText(name)
        self.page_title.setToolTip(self.repo)
        self.page_sub.setText(self.repo)
        self._brand_icon()
        self.results.setRowCount(0)
        self.count_chip.setText("0 hits")
        self._status_base = f"Ready - {name}"
        self.status.setText(self._status_base)
        self.empty_state.show_text("Ready when you are",
                                   f"Search {name} for a ticket, keyword, tag or endpoint.")
        self.stack.setCurrentWidget(self.empty_state)
        self.banner.setHidden(True)
        self.repo_list = []
        self.folders.set_repos([])
        self.folders_toggle.setChecked(False)
        self.folders_toggle.setHidden(True)
        self._folders_look()
        root = self.repo                  # which repos it holds is a folder walk: worker thread
        self.worker.submit(lambda: FoundRepos(root, engine.repos(root)), self.worker.reserve())

    def show_folders(self, found):
        if found.root != self.repo:       # an answer for a folder the user has already left
            return
        self.repo_list = found.repos
        self.folders.set_repos(found.repos)
        self.folders_toggle.setHidden(len(found.repos) < 2)
        self._folders_look()

    def _folders_look(self):
        """Collapsed by default: a count and an arrow; open, the tree of repos to untick."""
        shown = self.folders_toggle.isChecked() and not self.folders_toggle.isHidden()
        self.folders.setHidden(not shown)
        self.folders_toggle.setArrowType(Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow)
        picked = self.folders.scope()
        count = len(self.repo_list) if picked is None else f"{len(picked)} of {len(self.repo_list)}"
        self.folders_toggle.setText(f"Folders  ({count} repos)")

    def scope(self):
        return self.folders.scope()

    def refresh_repos(self):
        self.repos_list.clear()
        repos = self.saved.repos()
        for repo in repos:
            item = QListWidgetItem(Path(repo).name or repo)
            item.setData(Qt.ItemDataRole.UserRole, repo)
            item.setToolTip(repo)
            self.repos_list.addItem(item)
        self.repos_list.setVisible(bool(repos))
        self.repos_hint.setVisible(not repos)

    def _editor_menu(self):
        """Editors found on this machine, the system default, and any other program picked from disk."""
        self.editor_menu = QMenu(self.editor_button)
        self.editor_menu.setToolTipsVisible(True)
        self.editor_menu.aboutToShow.connect(self._fill_editor_menu)
        self.editor_button.setMenu(self.editor_menu)
        self._fill_editor_menu()
        self._editor_look()

    def _fill_editor_menu(self):
        self.editor_menu.clear()
        current = self.saved.editor_command()
        for editor in editors.available():
            action = self.editor_menu.addAction(editor.label)
            action.setCheckable(True)
            action.setChecked(editor.command == current)
            action.triggered.connect(lambda _=False, c=editor.command: self.set_editor(c))
        self.editor_menu.addSeparator()
        other = self.editor_menu.addAction("Other program...")
        other.setToolTip("Pick an .exe; it gets the file (no jump to the line)")
        other.triggered.connect(self.pick_editor_program)

    def pick_editor_program(self):
        path, _ = QFileDialog.getOpenFileName(self, "Program to open files with", "", "Programs (*.exe);;All files (*)")
        if path:
            self.set_editor(editors.program_command(path))

    def set_editor(self, command):
        self.saved.set_editor_command(command)
        self._editor_look()

    def _editor_look(self):
        self.editor_button.setText(f"Editor: {editors.label_for(self.saved.editor_command())}")

    def set_theme(self, mode, save=True):
        self.theme_mode = mode if mode in THEME_MODES else "system"
        if save:
            self.settings.setValue("theme", self.theme_mode)
        self.t = apply_theme(QApplication.instance(), self.theme_mode)
        self.empty_state.retheme(self.t)
        self.graph_view.retheme(self.t)
        for holder in self.cards:
            shade(holder.frame, self.t)
        self._theme_look()
        self._brand_icon()
        self._recolor_kinds()

    def next_theme(self):
        self.set_theme(THEME_MODES[(THEME_MODES.index(self.theme_mode) + 1) % len(THEME_MODES)])

    def _theme_look(self):
        self.theme_action.setIcon(icon(THEME_ICONS[self.theme_mode], self.t["ink2"]))
        self.theme_action.setToolTip(f"Theme: {self.theme_mode.title()} (click to change)")

    def _brand_icon(self):
        ratio = self.devicePixelRatioF()
        self.brand_mark.setPixmap(icon("target", self.t["accent"]).pixmap(QSize(20, 20), ratio))

    # ---------------------------------------------------------------- work
    def search(self):
        if not self.repo:
            self._status_base = "Please pick a repo first"
            self.status.setText(self._status_base)
            self.empty_state.show_text("Please pick a repo first",
                                       "Click Choose repo on the left (or a saved repo), then search again.")
            self.stack.setCurrentWidget(self.empty_state)
            return None
        command, term = self.command_key, self.term.text()
        self.saved.add_history(command, term)
        self.refresh_history()
        job = self.worker.reserve()
        self._status_base = f"Searching {COMMAND_INFO[command][0].lower()} {term}..."
        self.status.setText(self._status_base)
        self.banner.setHidden(True)
        self.empty_state.show_text("Searching...", "Reading the index; results show when it finishes.")
        self.stack.setCurrentWidget(self.empty_state)
        repo, cache, scope, limit = self.repo, self.cache_dir, self.scope(), self.GRAPH_LIMIT
        repos = list(self.repo_list)
        if self.mode == "graph":         # the layout is computed on the worker too, never on the UI thread
            return self.worker.submit(
                lambda: plan(engine.graph(repo, command, term, cache_dir=cache, scope=scope), limit, repos), job)
        return self.worker.submit(lambda: engine.query(repo, command, term, cache_dir=cache, scope=scope), job)

    def _finished(self, job, result):
        if isinstance(result, FoundRepos):
            self.show_folders(result)
        elif isinstance(result, Drawing):
            self.set_graph(result)
        else:
            self.set_results(result)

    def set_mode(self, mode):
        """table or graph; a search already typed runs again in the new mode."""
        self.mode = mode
        next(a for a in self.modes.actions() if a.text().lower() == mode).setChecked(True)
        for widget in (self.filter, self.rows_label, self.limit):      # table-only controls
            widget.setHidden(mode == "graph")
        if self.repo and self.term.text().strip():
            self.search()

    def set_graph(self, drawing):
        shown = drawing.graph
        if not shown.nodes:
            self.set_results([])
            return
        self.graph_view.show_graph(drawing)
        self.stack.setCurrentWidget(self.graph_view)
        self.count_chip.setText(f"{len(shown.nodes)} of {drawing.total} nodes")
        capped = " - the nearest to your search; narrow it to see the rest" if len(shown.nodes) < drawing.total else ""
        self._status_base = f"{len(shown.nodes)} nodes, {len(shown.edges)} links{capped}"
        self.status.setText(self._status_base)

    def _failed(self, job, text):
        self._status_base = strip_controls(text[:200])
        self.status.setText(self._status_base)
        self.show_error(f"Something went wrong: {text}")
        if self.stack.currentWidget() is self.empty_state:
            self.empty_state.show_text("No results", "The search stopped; see the message above.")

    def _timed(self, job, seconds):
        if self._status_base:
            self.status.setText(f"{self._status_base} in {round(seconds * 1000)} ms")

    def refresh_history(self):
        self.history_list.clear()
        history = self.saved.history()
        for command, term in history:
            item = QListWidgetItem(f"{COMMAND_INFO.get(command, (command,))[0]}: {term}")
            item.setData(Qt.ItemDataRole.UserRole, (command, term))
            self.history_list.addItem(item)
        self.history_list.setVisible(bool(history))
        self.history_hint.setVisible(not history)

    def run_history(self, command, term):
        self.set_command(command)
        self.term.setText(term)
        self.search()

    def set_command(self, key):
        if key not in COMMAND_INFO:
            return
        label, what, hint = COMMAND_INFO[key]
        self.command_key = key
        self.command.setText(label)
        self.term.setPlaceholderText(hint)
        self.command_hint.setText(f"{label}: {what}")

    def _kind_color(self, kind):
        return self.t.get(KIND_TOKENS.get(kind, "ink2"), self.t["ink2"])

    def set_results(self, hits):
        self.results.setRowCount(0)
        self.filter.clear()
        shown = hits[: self.limit.value()]
        for hit in shown:
            row = self.results.rowCount()
            self.results.insertRow(row)
            for column, text in enumerate((hit.kind.capitalize(), hit.name, self._location(hit), hit_detail(hit))):
                clean = strip_controls(str(text))
                item = QTableWidgetItem(clean)
                item.setToolTip(clean)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, hit)
                    item.setForeground(QColor(self._kind_color(hit.kind)))
                    item.setIcon(icon("circle-dot", self._kind_color(hit.kind)))
                self.results.setItem(row, column, item)
        if hits:
            self.stack.setCurrentWidget(self.results)
            extra = len(hits) - len(shown)
            self.count_chip.setText(f"{len(hits)} hit" + ("" if len(hits) == 1 else "s"))
            self._status_base = f"{len(shown)} shown" + (f" of {len(hits)}" if extra > 0 else "")
            self.status.setText(self._status_base)
        else:
            self.empty_state.show_text("No match", "Nothing in this repo matched that lookup.")
            self.stack.setCurrentWidget(self.empty_state)
            self.count_chip.setText("0 hits")
            self._status_base = "No match"
            self.status.setText(self._status_base)

    def _recolor_kinds(self):
        for row in range(self.results.rowCount()):
            item = self.results.item(row, 0)
            hit = item.data(Qt.ItemDataRole.UserRole) if item else None
            if hit is not None:
                item.setForeground(QColor(self._kind_color(hit.kind)))
                item.setIcon(icon("circle-dot", self._kind_color(hit.kind)))

    def _apply_filter(self, term=""):
        needle = term.strip().lower()
        for row in range(self.results.rowCount()):
            text = " ".join(self.results.item(row, c).text() if self.results.item(row, c) else ""
                            for c in range(self.results.columnCount())).lower()
            self.results.setRowHidden(row, bool(needle) and needle not in text)

    def _selected_hit(self):
        row = self.results.currentRow()
        if row < 0:
            return None
        item = self.results.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected(self):
        """(kind, name, file, line) of the selected table row or graph node, or None."""
        if self.stack.currentWidget() is self.graph_view:
            node = self.graph_view.selected_node()
            return (node.kind, node.label, node.file, node.line) if node else None
        hit = self._selected_hit()
        return (hit.kind, hit.name, hit.file, hit.call_line or hit.line) if hit else None

    def copy_selected(self):
        chosen = self._selected()
        if chosen is None:
            return
        kind, name, file, line = chosen
        QApplication.clipboard().setText("  ".join(part for part in (kind, name, where(file, line)) if part))
        self.status.setText("Copied to clipboard")

    def open_selected(self):
        chosen = self._selected()
        if chosen is None or not self.repo:
            self.status.setText("Select a result first, then Open")
            return
        _kind, _name, file, line = chosen
        if not file:
            self.status.setText("An endpoint has no file to open")
            return
        try:
            self._launch(file, line)
            self.status.setText(f"Opened {where(file, line)}")
        except (OSError, ValueError) as err:
            self.show_error(f"Could not open the editor: {err}. Pick another with the Editor button, bottom left.")

    def _launch(self, file, line):
        command = self.saved.editor_command()
        if command in editors.URL_EDITORS:
            if not QDesktopServices.openUrl(QUrl(editor_url(self.repo, file, line, command))):
                raise OSError(f"{editors.label_for(command)} is not installed")
            return
        if command == editors.DEFAULT_APP:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.repo) / file))):
                raise OSError("no app is set for this kind of file")
            return
        argv = open_in_editor(file, line, command)
        argv[0] = check_program(shutil.which(argv[0]) or argv[0])
        subprocess.Popen(argv, cwd=self.repo)

    @staticmethod
    def _location(hit):
        return where(hit.file, hit.call_line or hit.line)


def where(file, line):
    return f"{file}:{line}" if line else file
