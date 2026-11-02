"""Light and dark themes from one set of design tokens: Fusion style, a palette and one stylesheet."""
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QMenu, QProxyStyle, QStyle, QWidget

from .icons import chevrons

# One set of names for both themes, so every widget, stylesheet rule and custom painter reads the same palette.
# ground: window background; panel: cards; raised: inputs and pills; ink/ink2/ink3: text, secondary, hint.
# Light lifts cards on a shadow; dark lifts them on a crisp top edge (shadows vanish on a dark ground).
THEMES = {
    "light": {"ground": "#e9ecf1", "panel": "#ffffff", "raised": "#f4f6f9", "hover": "#eceff4", "line": "#d6dae3",
              "ink": "#0f1216", "ink2": "#5a6372", "ink3": "#757d8c", "accent": "#4361ee", "accent_soft": "#e4e9fd",
              "accent_text": "#3a56d9", "accent_ink": "#ffffff", "bad": "#e5484d", "bad_soft": "#fde4e5",
              "ok": "#137538", "ok_soft": "#dcf5e5", "warn": "#a14a06", "warn_soft": "#fdebd0", "select": "#4361ee",
              "shadow_alpha": 70, "shadow_blur": 28, "shadow_y": 6, "edge": "transparent", "card_line": "transparent"},
    "dark": {"ground": "#050608", "panel": "#181c24", "raised": "#20252f", "hover": "#2a303c", "line": "#303746",
             "ink": "#f5f7fa", "ink2": "#a3acba", "ink3": "#7d8696", "accent": "#7b93ff", "accent_soft": "#252d4d",
             "accent_text": "#7b93ff", "accent_ink": "#0d0f13", "bad": "#ff6369", "bad_soft": "#3a1d20",
             "ok": "#3ecf8e", "ok_soft": "#16342a", "warn": "#f5b14c", "warn_soft": "#3b2d14", "select": "#7b93ff",
             "shadow_alpha": 0, "shadow_blur": 44, "shadow_y": 12, "edge": "#3d4555", "card_line": "#303746"},
}
THEME_MODES = ("system", "light", "dark")
THEME_ICONS = {"system": "monitor", "light": "sun", "dark": "moon"}


def theme_name(app, mode="system"):
    """light or dark: the mode itself, or what the system uses when the mode is system."""
    if mode in ("light", "dark"):
        return mode
    try:
        return "dark" if app.styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"
    except AttributeError:             # Qt before 6.5
        return "light"


QSS = """
QWidget {{ color: {ink}; font-size: 13px; }}
QMainWindow, QWidget#ground {{ background: {ground}; }}
/* cards lift on a shadow in light and on a crisp edge in dark, never both */
QFrame#card {{ background: {panel}; border: 1px solid {card_line}; border-top-color: {edge}; border-radius: 14px; }}
QFrame#bar {{ background: {panel}; border: 1px solid {card_line}; border-top-color: {edge}; border-radius: 12px; }}
QToolBar#shell {{ background: {panel}; border: 0; border-bottom: 1px solid {line}; padding: 10px 16px; spacing: 4px; }}
QToolBar#shell QToolButton, QFrame#bar QToolButton {{ background: transparent; border: 1px solid transparent;
    border-radius: 8px; padding: 6px 10px; color: {ink}; }}
QToolBar#shell QToolButton:hover, QFrame#bar QToolButton:hover {{ background: {hover}; }}
QToolBar#shell QToolButton:checked, QFrame#bar QToolButton:checked {{ background: {accent_soft}; color: {accent}; }}
QToolBar#shell QToolButton:disabled, QFrame#bar QToolButton:disabled {{ color: {ink3}; }}
QToolBar#shell QToolButton:focus, QFrame#bar QToolButton:focus {{ border-color: {accent}; }}
QFrame#bar QToolButton {{ padding: 4px 6px; font-size: 12px; }}
QToolBar#shell QToolButton::menu-indicator {{ image: none; width: 0px; }}
QFrame#seg {{ background: {raised}; border: 1px solid {line}; border-radius: 11px; }}
QToolBar#shell QFrame#seg QToolButton {{ border-radius: 8px; padding: 5px 14px; }}
QToolBar#shell QFrame#seg QToolButton:hover {{ background: {hover}; }}
QToolBar#shell QFrame#seg QToolButton:checked {{ background: {accent}; color: {accent_ink}; }}
QFrame#pill {{ background: {raised}; border: 1px solid {line}; border-radius: 14px; }}
QFrame#pill QLabel {{ background: transparent; }}
QFrame#pill[menu="true"]:hover {{ background: {hover}; }}
QLabel#product {{ font-size: 17px; font-weight: 700; padding-right: 8px; }}
QLabel#title {{ font-size: 17px; font-weight: 700; color: {ink}; }}
QLabel#hint, QLabel#message {{ color: {ink2}; font-size: 12px; }}
QLabel#chip {{ background: {accent_soft}; color: {accent_text}; font-size: 11px; font-weight: 600; border-radius: 9px;
    padding: 2px 8px; }}
QLabel#empty_title {{ font-size: 14px; font-weight: 600; color: {ink}; }}
QLabel#empty_text {{ font-size: 12px; color: {ink2}; }}
QPushButton {{ background: {raised}; border: 1px solid {line}; border-radius: 8px; padding: 6px 12px; }}
QPushButton:hover {{ background: {hover}; }}
QPushButton:pressed {{ background: {line}; }}
QPushButton:focus {{ border-color: {accent}; }}
QPushButton#primary {{ background: {accent}; color: {accent_ink}; border-color: {accent}; font-weight: 600; }}
QPushButton#primary:hover {{ background: {select}; }}
QLineEdit {{ background: {raised}; border: 1px solid {line}; border-radius: 8px; padding: 6px 10px;
    selection-background-color: {accent_soft}; selection-color: {ink}; }}
QLineEdit:focus {{ border-color: {accent}; background: {panel}; }}
QTableWidget, QTreeWidget, QListWidget {{ background: transparent; border: 0; outline: 0; gridline-color: transparent; }}
QTableWidget::item, QListWidget::item {{ padding: 4px 8px; border: 0; border-radius: 6px; }}
QTableWidget::item:hover, QListWidget::item:hover {{ background: {hover}; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: {accent_soft}; color: {ink}; }}
QTreeView {{ show-decoration-selected: 1; }}
QTreeView::item {{ padding: 4px 8px 4px 6px; border: 0; }}
QTreeView::item:selected, QTreeView::item:selected:active, QTreeView::item:selected:!active {{
    background: {accent_soft}; color: {ink}; }}
QTreeView::branch {{ background: transparent; }}
QTreeView::branch:selected {{ background: {accent_soft}; }}
QTreeView::branch:closed:has-children {{ image: url({chevron_right}); }}
QTreeView::branch:open:has-children {{ image: url({chevron_down}); }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {ink2}; border: 0; border-bottom: 1px solid {line};
    padding: 6px 8px; font-size: 12px; font-weight: 600; }}
QTableCornerButton::section {{ background: transparent; border: 0; }}
QScrollBar:vertical {{ background: transparent; border: 0; width: 8px; margin: 6px 2px; }}
QScrollBar:horizontal {{ background: transparent; border: 0; height: 8px; margin: 2px 6px; }}
QScrollBar::handle {{ background: {line}; border-radius: 4px; min-height: 28px; min-width: 28px; }}
QScrollBar::handle:hover {{ background: {ink3}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; border: 0; background: none;
    subcontrol-origin: margin; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QSplitter::handle {{ background: transparent; }}
QMenu {{ background: {panel}; border: 1px solid {line}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 16px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {accent_soft}; color: {ink}; }}
QMenu::item:disabled {{ color: {ink2}; }}
QMenu::separator {{ height: 1px; background: {line}; margin: 4px 8px; }}
QMenu::indicator {{ width: 0; }}
QToolTip {{ background: {raised}; color: {ink}; border: 1px solid {line}; border-radius: 6px; padding: 4px 8px; }}
"""

TIP_DELAY = 50                 # ms before a tooltip shows; Qt's default of 700 reads as lag


class AppStyle(QProxyStyle):
    """Fusion with quick tooltips."""

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return TIP_DELAY
        return super().styleHint(hint, option, widget, returnData)


class SurfaceFilter(QObject):
    """Menus and tooltips are popup windows: make them frameless and see-through before they show, so only the
    stylesheet's rounded surface is drawn and not a square window behind it (the "two backgrounds" look)."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Polish and isinstance(obj, QWidget) and (
                isinstance(obj, QMenu) or obj.metaObject().className() == "QTipLabel"):
            if not obj.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground):
                obj.setWindowFlags(obj.windowFlags() | Qt.WindowType.FramelessWindowHint
                                   | Qt.WindowType.NoDropShadowWindowHint)
                obj.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        return False


def apply_theme(app, mode="system"):
    """Themes the whole app (Fusion looks the same on Windows, Linux and macOS); returns the tokens in use."""
    t = dict(THEMES[theme_name(app, mode)])
    if not hasattr(app, "app_style"):                  # set once; these objects must outlive every call
        app.app_style, app.surface_filter = AppStyle("Fusion"), SurfaceFilter(app)
        app.setStyle(app.app_style)
        app.installEventFilter(app.surface_filter)
        for effect in (Qt.UIEffect.UI_FadeTooltip, Qt.UIEffect.UI_AnimateTooltip):     # no fade on top of the wait
            app.setEffectEnabled(effect, False)
    p = QPalette()
    for role, key in ((QPalette.ColorRole.Window, "ground"), (QPalette.ColorRole.Base, "panel"),
                      (QPalette.ColorRole.AlternateBase, "raised"), (QPalette.ColorRole.Button, "raised"),
                      (QPalette.ColorRole.Text, "ink"), (QPalette.ColorRole.WindowText, "ink"),
                      (QPalette.ColorRole.ButtonText, "ink"), (QPalette.ColorRole.Highlight, "accent"),
                      (QPalette.ColorRole.HighlightedText, "accent_ink"), (QPalette.ColorRole.PlaceholderText, "ink3"),
                      (QPalette.ColorRole.ToolTipBase, "raised"), (QPalette.ColorRole.ToolTipText, "ink")):
        p.setColor(role, QColor(t[key]))
    app.setPalette(p)
    app.setStyleSheet(QSS.format(**t, **chevrons(t["ink2"])))
    return t


def contrast(fg, bg):
    """WCAG contrast ratio of two colors; text needs 4.5, large text and icons 3."""
    def lum(color):
        c = QColor(color)
        parts = [v / 255 for v in (c.red(), c.green(), c.blue())]
        r, g, b = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in parts]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)
