"""The COMMUNITIES list beside the graph: tick to show or hide a repo's dots, click a name to highlight them."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from robot_mind import strip_controls

from .widgets import ElidedLabel, plain_label

PANEL_W = 250


class Row(QWidget):
    """One community: tick box, colour dot, name and count; a click outside the box highlights it."""

    clicked = Signal(int)

    def __init__(self, group, name, size, color):
        super().__init__()
        self.group = group
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{strip_controls(name)}: click to highlight, untick to hide")
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        self.box = QCheckBox()
        self.box.setChecked(True)
        dot = plain_label("", "dot")
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background: {color}; border-radius: 5px;")
        self.name = ElidedLabel(strip_controls(name))                  # ends in ... when long, never scrolls
        line.addWidget(self.box)
        line.addWidget(dot)
        line.addWidget(self.name, 1)
        line.addWidget(plain_label(str(size), "hint"))

    def mousePressEvent(self, event):
        self.clicked.emit(self.group)


class CommunityPanel(QFrame):
    """Emits shown(set of community numbers) on a tick change and highlighted(number, or -1 for none)."""

    shown = Signal(object)
    highlighted = Signal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("communities")
        self.setFixedWidth(PANEL_W)
        self.rows: list[Row] = []
        self.current = -1
        col = QVBoxLayout(self)
        col.setContentsMargins(12, 10, 8, 10)
        col.setSpacing(6)
        col.addWidget(plain_label("REPOS AND FOLDERS", "label"))
        self.select_all = QCheckBox("Show all")
        self.select_all.setChecked(True)
        self.select_all.clicked.connect(self._select_all)
        col.addWidget(self.select_all)
        self.list = QVBoxLayout()
        self.list.setSpacing(4)
        holder = QWidget()
        holder.setObjectName("community_rows")
        holder.setLayout(self.list)
        scroll = QScrollArea()
        scroll.setObjectName("community_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(holder)
        col.addWidget(scroll, 1)

    def fill(self, names, sizes, colors):
        while self.list.count():
            old = self.list.takeAt(0).widget()          # None for the closing stretch
            if old is not None:
                old.setParent(None)                     # gone now, not at the next event loop turn
                old.deleteLater()
        self.rows, self.current = [], -1
        for group, (name, size) in enumerate(zip(names, sizes)):
            row = Row(group, name, size, colors[group])
            row.box.toggled.connect(self._ticked)
            row.clicked.connect(self.highlight)
            self.list.addWidget(row)
            self.rows.append(row)
        self.list.addStretch(1)
        self.select_all.setChecked(True)

    def highlight(self, group):
        """Click a name to light its dots up; click it again to go back to all."""
        self.current = -1 if group == self.current else group
        for row in self.rows:
            row.name.setObjectName("label" if row.group == self.current else "")
            row.name.style().polish(row.name)
        self.highlighted.emit(self.current)

    def _select_all(self, checked):
        for row in self.rows:
            row.box.blockSignals(True)
            row.box.setChecked(checked)
            row.box.blockSignals(False)
        self._ticked()

    def _ticked(self):
        visible = {row.group for row in self.rows if row.box.isChecked()}
        self.select_all.setChecked(len(visible) == len(self.rows))
        self.shown.emit(visible)
