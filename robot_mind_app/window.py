"""Main window: a toolbar shell and one results card; the lookup panes land next."""
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QSizePolicy, QToolBar, QVBoxLayout, QWidget

from .icons import ICON_SIZE, app_icon, icon
from .theme import THEME_ICONS, THEME_MODES, apply_theme
from .widgets import EmptyState, card, gap, plain_label, shade
from .worker import Worker

APP_NAME = "Robot Framework Mind"
ORG = "robotframework-mind"


class MainWindow(QMainWindow):
    def __init__(self, worker=None, settings=None, targets=(), task=None):
        super().__init__()
        self.worker = worker or Worker()
        self.settings = settings if settings is not None else QSettings(ORG, APP_NAME)
        mode = self.settings.value("theme", "system")
        self.theme_mode = mode if mode in THEME_MODES else "system"
        self.t = apply_theme(QApplication.instance(), self.theme_mode)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self._toolbar()
        self.empty_state = EmptyState(self.t, "scan-search", "Nothing to show yet",
                                      "Pick a robot repo and run a lookup.")
        self.results_holder = card(self.empty_state, self.t)
        self.cards = [self.results_holder]
        ground = QWidget()
        ground.setObjectName("ground")
        outer = QVBoxLayout(ground)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(self.results_holder, 1)
        self.setCentralWidget(ground)
        self.resize(1100, 720)

    def _toolbar(self):
        bar = QToolBar("Main")
        bar.setObjectName("shell")
        bar.setMovable(False)
        bar.setIconSize(ICON_SIZE)
        self.addToolBar(bar)
        bar.addWidget(plain_label(APP_NAME, "product"))
        bar.addWidget(gap())
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
