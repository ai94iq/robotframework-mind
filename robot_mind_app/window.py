"""Main window: a sidebar (repo + saved + recent), a query bar, and a styled results table."""
import subprocess
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QInputDialog, QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QPushButton, QSizePolicy, QSpinBox, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from robot_mind import strip_controls

from . import engine
from .icons import ICON_SIZE, app_icon, icon
from .settings import AppSettings, open_in_editor
from .theme import THEME_ICONS, THEME_MODES, apply_theme
from .widgets import EmptyState, card, plain_label, shade
from .worker import Worker

APP_NAME = "Robot Framework Mind"
ORG = "robotframework-mind"
COMMANDS = ("ticket", "kw", "callers", "tag", "find")
KIND_TOKENS = {"test": "accent_text", "keyword": "ok", "var": "warn", "json": "ink2"}


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
        self._status_base = ""
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self._build()
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
        sidebar.setFixedWidth(252)
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
        self.editor_button.setToolTip("Set the command used by Open")
        self.editor_button.clicked.connect(self.edit_editor_command)
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
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.results)
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
        self.command = QPushButton(COMMANDS[0])
        self.command.setObjectName("command")
        self.command.setFixedWidth(108)
        self.command_menu = QMenu(self.command)
        for name in COMMANDS:
            action = self.command_menu.addAction(name)
            action.triggered.connect(lambda _=False, n=name: self.set_command(n))
        self.command.setMenu(self.command_menu)
        self.term = QLineEdit()
        self.term.setPlaceholderText("ticket key, keyword, tag, or text")
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
        row.addWidget(plain_label("rows", "hint"))
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
        self.count_chip = plain_label("0 hits", "chip")
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("filter by tag, name or text")
        self.filter.textChanged.connect(self._apply_filter)
        self.copy_button = QPushButton("Copy")
        self.copy_button.setToolTip("Copy the selected hit")
        self.copy_button.clicked.connect(self.copy_selected)
        self.open_button = QPushButton("Open")
        self.open_button.setToolTip("Open the selected hit at its line in the editor")
        self.open_button.clicked.connect(self.open_selected)
        head.addWidget(self.count_chip)
        head.addWidget(self.filter, 1)
        head.addWidget(self.copy_button)
        head.addWidget(self.open_button)
        column.addLayout(head)
        column.addWidget(self.stack, 1)
        return pane

    # ---------------------------------------------------------------- repo and theme
    def choose_repo(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a robot repo", self.repo or "")
        if path:
            self.set_repo(path)

    def set_repo(self, path):
        self.repo = str(path)
        name = Path(self.repo).name or self.repo
        self.page_title.setText(name)
        self.page_title.setToolTip(self.repo)
        self.page_sub.setText(self.repo)
        self.saved.add_repo(self.repo)
        self.refresh_repos()
        self._brand_icon()

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

    def edit_editor_command(self):
        current = self.saved.editor_command()
        text, ok = QInputDialog.getText(self, "Editor command", "Use {file} and {line}:", text=current)
        if ok and text.strip():
            self.saved.set_editor_command(text.strip())

    def set_theme(self, mode, save=True):
        self.theme_mode = mode if mode in THEME_MODES else "system"
        if save:
            self.settings.setValue("theme", self.theme_mode)
        self.t = apply_theme(QApplication.instance(), self.theme_mode)
        self.empty_state.retheme(self.t)
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
            self.status.setText("Choose a repo first.")
            return None
        command, term = self.command.text(), self.term.text()
        self.saved.add_history(command, term)
        self.refresh_history()
        job = self.worker.reserve()
        self._status_base = f"Searching {command} {term}..."
        self.status.setText(self._status_base)
        self.empty_state.show_text("Searching...", "Reading the index; results show when it finishes.")
        self.stack.setCurrentWidget(self.empty_state)
        return self.worker.submit(
            lambda: engine.query(self.repo, command, term, cache_dir=self.cache_dir), job)

    def _finished(self, job, hits):
        self.set_results(hits)

    def _failed(self, job, text):
        self._status_base = strip_controls(text[:200])
        self.status.setText(self._status_base)

    def _timed(self, job, seconds):
        if self._status_base:
            self.status.setText(f"{self._status_base} in {round(seconds * 1000)} ms")

    def refresh_history(self):
        self.history_list.clear()
        history = self.saved.history()
        for command, term in history:
            item = QListWidgetItem(f"{command}: {term}")
            item.setData(Qt.ItemDataRole.UserRole, (command, term))
            self.history_list.addItem(item)
        self.history_list.setVisible(bool(history))
        self.history_hint.setVisible(not history)

    def run_history(self, command, term):
        self.set_command(command)
        self.term.setText(term)
        self.search()

    def set_command(self, name):
        if name in COMMANDS:
            self.command.setText(name)

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

    def copy_selected(self):
        hit = self._selected_hit()
        if hit is None:
            return
        QApplication.clipboard().setText(f"{hit.kind}  {hit.name}  {self._location(hit)}")
        self.status.setText("Copied to clipboard")

    def open_selected(self):
        hit = self._selected_hit()
        if hit is None or not self.repo:
            return
        argv = open_in_editor(hit.file, hit.call_line or hit.line, self.saved.editor_command())
        try:
            subprocess.Popen(argv, cwd=self.repo)
            self.status.setText(f"Opened {self._location(hit)}")
        except OSError as err:
            self.status.setText(f"Could not open editor: {err}")

    @staticmethod
    def _location(hit):
        line = hit.call_line or hit.line
        return f"{hit.file}:{line}" if line else hit.file
