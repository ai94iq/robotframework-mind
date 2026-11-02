"""Building blocks: plain labels, empty states, cards with shadows, the target pill and a segmented switch."""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QSizePolicy, QToolButton,
                               QVBoxLayout, QWidget)

from .icons import ICON_SIZE, icon


def plain_label(text="", name=""):
    """Text from files, servers or users is shown as text, never parsed as HTML."""
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setOpenExternalLinks(False)
    label.setObjectName(name)
    return label


class EmptyState(QWidget):
    """A centred icon, title and one line of help, for a pane with nothing to show yet."""

    def __init__(self, theme, name, title, text):
        super().__init__()
        self.t, self.name = theme, name
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(6)
        layout.addStretch()
        self.icon = plain_label("", "empty_icon")
        self.title, self.text = plain_label("", "empty_title"), plain_label("", "empty_text")
        self.text.setWordWrap(True)
        for widget in (self.icon, self.title, self.text):
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(widget)
        layout.addStretch()
        self.show_text(title, text)

    def show_text(self, title, text, name=None):
        self.name = name or self.name
        self.title.setText(title)
        self.text.setText(text)
        self.retheme(self.t)

    def retheme(self, theme):
        self.t = theme
        self.icon.setPixmap(icon(self.name, theme["ink3"]).pixmap(QSize(32, 32), self.devicePixelRatioF()))


SHADOW_ROOM = 14       # px around a card for its shadow; the bottom gets twice that (the shadow falls down)


def card(widget, theme):
    """A pane on the window's ground: a rounded panel with a soft drop shadow (light) or a crisp edge (dark).

    The content is inset a little, so its square children never paint over the rounded corners."""
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.addWidget(widget)
    frame.setGraphicsEffect(QGraphicsDropShadowEffect(frame))
    return floating(frame, theme)


def floating(frame, theme):
    """Holds a frame that has a drop shadow in a transparent widget with room for that shadow."""
    shade(frame, theme)
    # A shadow is drawn outside the frame and whatever holds the frame clips it: give it room on every side,
    # most at the bottom, sized for the deepest shadow in THEMES.
    holder = QWidget()
    holder.frame = frame
    room = QVBoxLayout(holder)
    room.setContentsMargins(SHADOW_ROOM, SHADOW_ROOM // 2, SHADOW_ROOM, SHADOW_ROOM * 2)
    room.addWidget(frame)
    return holder


def shade(frame, theme):
    """(Re)applies the theme's shadow; call it for every card on a theme change."""
    effect = frame.graphicsEffect()
    effect.setEnabled(theme["shadow_alpha"] > 0)       # dark cards use an edge instead
    effect.setColor(QColor(0, 0, 0, theme["shadow_alpha"]))
    effect.setBlurRadius(theme["shadow_blur"])
    effect.setOffset(0, theme["shadow_y"])


class Pill(QFrame):
    """A rounded status pill (icon, dot, text, chevron); with a menu set, a click on it opens the menu."""

    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("pill")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)     # a toolbar would stretch it
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 4, 12, 4)
        row.setSpacing(6)
        self.glyph, self.dot = plain_label("", "glyph"), plain_label("", "dot")
        self.text, self.chevron = plain_label("", "state"), plain_label("", "chevron")
        for widget in (self.glyph, self.dot, self.text):
            row.addWidget(widget)
        row.addStretch(1)              # the pill is as wide as its menu: spare room goes before the chevron
        row.addWidget(self.chevron)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.property("menu"):
            self.clicked.emit()


def segmented(actions):
    """A pill-shaped exclusive switch from checkable actions (put them in one exclusive QActionGroup)."""
    seg = QFrame()
    seg.setObjectName("seg")
    seg.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    row = QHBoxLayout(seg)
    row.setContentsMargins(3, 3, 3, 3)
    row.setSpacing(2)
    for action in actions:
        row.addWidget(tool_button(action))
    return seg


def tool_button(action, text=True):
    """A flat button for an action: icon beside text, or icon only (then the action's text is its accessible name)."""
    button = QToolButton()
    button.setDefaultAction(action)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if text
                              else Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setIconSize(ICON_SIZE)
    button.setAutoRaise(True)
    button.setAccessibleName(action.text())
    return button


def gap(width=8):
    """Blank space between toolbar groups (the toolbar's own spacing is added on both sides)."""
    spacer = QWidget()
    spacer.setFixedWidth(width)
    return spacer
