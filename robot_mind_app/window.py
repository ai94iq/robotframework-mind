"""Main window: repo picker, a command/term query bar, and a results table."""
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
                               QLineEdit, QMainWindow, QPushButton, QSizePolicy, QSpinBox, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout, QWidget)

from robot_mind import strip_controls

from . import engine
from .icons import ICON_SIZE, app_icon, icon
from .theme import THEME_ICONS, THEME_MODES, apply_theme
from .widgets import EmptyState, card, gap, plain_label, shade
from .worker import Worker

APP_NAME = "Robot Framework Mind"
ORG = "robotframework-mind"
COMMANDS = ("ticket", "kw", "callers", "tag", "find")


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
        mode = self.settings.value("theme", "system")
        self.theme_mode = mode if mode in THEME_MODES else "system"
        self.t = apply_theme(QApplication.instance(), self.theme_mode)
        self.cache_dir = cache_dir
        self.repo = None
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self._toolbar()
        self._body()
        self.worker.finished.connect(self._finished)
        self.worker.failed.connect(self._failed)
        self.resize(1100, 720)

    # ---------------------------------------------------------------- layout
    def _toolbar(self):
        bar = QToolBar("Main")
        bar.setObjectName("shell")
        bar.setMovable(False)
        bar.setIconSize(ICON_SIZE)
        self.addToolBar(bar)
        bar.addWidget(plain_label(APP_NAME, "product"))
        bar.addWidget(gap())
        self.repo_action = QAction("Pick repo", self)
        self.repo_action.setToolTip("Choose the Robot Framework repo to look up")
        self.repo_action.triggered.connect(self.choose_repo)
        bar.addAction(self.repo_action)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        self.theme_action = QAction("Theme", self)
        self.theme_action.triggered.connect(self.next_theme)
        bar.addAction(self.theme_action)
        self.theme_button = bar.widgetForAction(self.theme_action)
        self.theme_button.setAccessibleName("Theme")
        self.toolbar = bar
        self._theme_look()

    def _body(self):
        ground = QWidget()
        ground.setObjectName("ground")
        outer = QVBoxLayout(ground)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(self._query_bar())
        self.empty_state = EmptyState(self.t, "scan-search", "Nothing to show yet",
                                      "Pick a robot repo and run a lookup.")
        self.results = QTableWidget(0, 4)
        self.results.setHorizontalHeaderLabels(["Kind", "Name", "Location", "Detail"])
        self.results.verticalHeader().setVisible(False)
        self.results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results.horizontalHeader().setStretchLastSection(True)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(self.results)
        self.results_holder = card(self.stack, self.t)
        self.cards = [self.results_holder]
        outer.addWidget(self.results_holder, 1)
        self.status = plain_label("", "hint")
        outer.addWidget(self.status)
        self.setCentralWidget(ground)

    def _query_bar(self):
        box = QFrame()
        box.setObjectName("bar")
        self.query_bar = box
        row = QHBoxLayout(box)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(6)
        self.command = QComboBox()
        self.command.addItems(COMMANDS)
        self.term = QLineEdit()
        self.term.setPlaceholderText("ticket key, keyword, tag, or text")
        self.term.returnPressed.connect(self.search)
        self.limit = QSpinBox()
        self.limit.setRange(1, 5000)
        self.limit.setValue(200)
        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("primary")
        self.search_button.clicked.connect(self.search)
        row.addWidget(self.command)
        row.addWidget(self.term, 1)
        row.addWidget(plain_label("limit", "hint"))
        row.addWidget(self.limit)
        row.addWidget(self.search_button)
        return box

    # ---------------------------------------------------------------- repo and theme
    def choose_repo(self):
        path = QFileDialog.getExistingDirectory(self, "Choose a robot repo", self.repo or "")
        if path:
            self.set_repo(path)

    def set_repo(self, path):
        self.repo = str(path)
        self.repo_action.setText(Path(self.repo).name or self.repo)
        self.repo_action.setToolTip(self.repo)

    def set_theme(self, mode, save=True):
        self.theme_mode = mode if mode in THEME_MODES else "system"
        if save:
            self.settings.setValue("theme", self.theme_mode)
        self.t = apply_theme(QApplication.instance(), self.theme_mode)
        self.empty_state.retheme(self.t)
        for holder in self.cards:
            shade(holder.frame, self.t)
        self._theme_look()

    def next_theme(self):
        self.set_theme(THEME_MODES[(THEME_MODES.index(self.theme_mode) + 1) % len(THEME_MODES)])

    def _theme_look(self):
        self.theme_action.setIcon(icon(THEME_ICONS[self.theme_mode], self.t["ink2"]))
        self.theme_action.setToolTip(f"Theme: {self.theme_mode.title()} (click to change)")

    # ---------------------------------------------------------------- work
    def search(self):
        if not self.repo:
            self.status.setText("Pick a robot repo first.")
            return None
        command, term = self.command.currentText(), self.term.text()
        job = self.worker.reserve()
        self.status.setText(f"Searching {command} {term}...")
        self.empty_state.show_text("Searching...", "Reading the index; results show when it finishes.")
        self.stack.setCurrentWidget(self.empty_state)
        return self.worker.submit(
            lambda: engine.query(self.repo, command, term, cache_dir=self.cache_dir), job)

    def _finished(self, job, hits):
        self.set_results(hits)

    def _failed(self, job, text):
        self.status.setText(strip_controls(text[:200]))

    def set_results(self, hits):
        self.results.setRowCount(0)
        shown = hits[: self.DISPLAY_LIMIT]
        for hit in shown:
            row = self.results.rowCount()
            self.results.insertRow(row)
            for column, text in enumerate((hit.kind, hit.name, self._location(hit), hit_detail(hit))):
                self.results.setItem(row, column, QTableWidgetItem(strip_controls(str(text))))
        if hits:
            self.stack.setCurrentWidget(self.results)
            extra = len(hits) - len(shown)
            self.status.setText(f"{len(hits)} hits" + (f" (showing {len(shown)})" if extra > 0 else ""))
        else:
            self.empty_state.show_text("No match", "Nothing in this repo matched that lookup.")
            self.stack.setCurrentWidget(self.empty_state)
            self.status.setText("No match")

    @staticmethod
    def _location(hit):
        line = hit.call_line or hit.line
        return f"{hit.file}:{line}" if line else hit.file
