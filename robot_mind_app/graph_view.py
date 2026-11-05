"""Draws a Drawing as a force-directed cloud of dots coloured by repo or folder, with the list that filters it."""
from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QGraphicsEllipseItem, QGraphicsItem, QGraphicsScene, QGraphicsSimpleTextItem,
                               QGraphicsView, QHBoxLayout, QWidget)

from robot_mind import strip_controls

from .community_panel import CommunityPanel
from .graph_layout import Drawing, neighbors

COLORS = ("#5b7fbf", "#f0a04b", "#e05c5c", "#7cc4b8", "#6ab04c", "#e8c547", "#b585b5", "#f7a1a8", "#a07855",
          "#9aa3ad")
LABEL_LIMIT = 28           # characters of a label drawn beside its dot
LABELLED_FOCUS = 12        # more nodes searched for than this: labels only on hover, or they bury the dots
DIMMED = 0.18              # opacity of dots and links outside a highlighted repo


def color(group: int) -> QColor:
    return QColor(COLORS[group % len(COLORS)])


def place(anchor: QPointF, size: QSizeF, radius: float, taken: list[QRectF]) -> QPointF | None:
    """Where a label goes beside its dot (in screen pixels): right, left, above right, below right, whichever is
    free of the labels already placed; None when all four would overlap. A placed label is added to taken."""
    w, h, gap = size.width(), size.height(), radius + 4
    for dx, dy in ((gap, -h / 2), (-gap - w, -h / 2), (gap, -h - radius), (gap, radius)):
        rect = QRectF(anchor.x() + dx, anchor.y() + dy, w, h)
        if not any(rect.intersects(other) for other in taken):
            taken.append(rect)
            return QPointF(dx, dy)
    return None


def short(text: str) -> str:
    text = strip_controls(text)
    return text if len(text) <= LABEL_LIMIT else text[:LABEL_LIMIT] + "..."


class NodeItem(QGraphicsEllipseItem):
    """A dot sized by how linked the node is; the nodes searched for get an accent ring (and a label when few)."""

    def __init__(self, node, group, view):
        radius = 3.5 + min(view.degree(node.id), 12) * 0.45
        super().__init__(QRectF(-radius, -radius, radius * 2, radius * 2))
        self.node, self.group, self.view = node, group, view
        self.focus = view.is_focus(node.id)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)   # same dot size at any zoom
        self.setAcceptHoverEvents(True)
        self.setZValue(2 if self.focus else 1)
        self.label, self.ring = None, QColor(Qt.GlobalColor.white)
        if self.focus and view.labelled:
            self.label = QGraphicsSimpleTextItem(short(node.label), self)
            self.label.setPos(radius + 4, -self.label.boundingRect().height() / 2)

    def retheme(self, t):
        self.setBrush(color(self.group))
        self.setPen(QPen(QColor(t["accent"]), 2) if self.focus else QPen(Qt.PenStyle.NoPen))
        if self.label:
            self.label.setBrush(QColor(t["ink"]))
        self.ring = QColor(t["ink"])

    def hoverEnterEvent(self, event):
        self.view.hover(self)

    def hoverLeaveEvent(self, event):
        self.view.hover(None)

    def paint(self, painter, option, widget=None):
        painter.setBrush(self.brush())
        painter.setPen(QPen(self.ring, 2.5) if self.isSelected() else self.pen())
        painter.drawEllipse(self.rect())


class Canvas(QGraphicsView):
    """Pans with a drag, zooms with Ctrl and the wheel; a double click on a dot emits activated(Node)."""

    activated = Signal(object)

    def __init__(self):
        super().__init__()
        self.setObjectName("graph")
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)

    def fit(self):
        """The whole cloud in view, never zoomed in past 150 percent."""
        self.resetTransform()
        rect = self.scene().itemsBoundingRect().adjusted(-30, -30, 30, 30)
        self.setSceneRect(rect)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        if self.transform().m11() > 1.5:
            self.resetTransform()
            self.scale(1.5, 1.5)
        self.centerOn(rect.center())

    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        while item is not None and not isinstance(item, NodeItem):
            item = item.parentItem()
        if item is not None:
            self.scene().clearSelection()
            item.setSelected(True)
            self.activated.emit(item.node)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)


class GraphView(QWidget):
    """The canvas beside the repos and folders list; a hovered dot names itself and its neighbours."""

    activated = Signal(object)

    def __init__(self, theme):
        super().__init__()
        self.t, self.drawing = theme, None
        self.near, self.focus, self.labelled = {}, set(), False
        self.edge_items, self.hover_labels, self.items = [], [], {}
        self.canvas = Canvas()
        self.canvas.activated.connect(self.activated)
        self.panel = CommunityPanel()
        self.panel.shown.connect(self._show_groups)
        self.panel.highlighted.connect(self._highlight)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.canvas, 1)
        row.addWidget(self.panel)

    # what a NodeItem asks its view
    def degree(self, nid):
        return len(self.near[nid])

    def is_focus(self, nid):
        return nid in self.focus

    def show_graph(self, drawing: Drawing):
        self.drawing = drawing
        self.near, self.focus = neighbors(drawing.graph), set(drawing.graph.focus)
        self.labelled = len(self.focus) <= LABELLED_FOCUS
        scene = self.canvas.scene()
        scene.clear()
        self.edge_items, self.hover_labels, self.items = [], [], {}
        for nid, node in drawing.graph.nodes.items():
            item = NodeItem(node, drawing.group[nid], self)
            item.setPos(QPointF(*drawing.pos[nid]))
            item.setToolTip(self._tip(node, drawing.names[drawing.group[nid]]))
            scene.addItem(item)
            self.items[nid] = item
        sizes = [list(drawing.group.values()).count(g) for g in range(len(drawing.names))]
        self.panel.fill(drawing.names, sizes, [COLORS[g % len(COLORS)] for g in range(len(drawing.names))])
        self._draw_edges()
        self.retheme(self.t)
        self.canvas.fit()

    @staticmethod
    def _tip(node, home):
        where = f"{node.file}:{node.line}" if node.line else node.file
        return strip_controls("\n".join(p for p in (f"{node.kind}: {node.label}", where, f"in {home}") if p))

    def hover(self, item):
        """Names the hovered dot and its neighbours for as long as the pointer stays on it."""
        for label in self.hover_labels:
            self.canvas.scene().removeItem(label)
        self.hover_labels = []
        if item is None:
            return
        taken = [QRectF(self._screen(i) + i.label.pos(), i.label.boundingRect().size())
                 for i in self.items.values() if i.label and i.isVisible()]
        others = sorted(self.near[item.node.id], key=lambda nid: self._screen(self.items[nid]).y())
        for nid in [item.node.id, *others]:                     # the hovered dot gets the first free spot
            other = self.items[nid]
            if other.label is None and other.isVisible():
                label = QGraphicsSimpleTextItem(short(other.node.label), other)     # beside its dot, any zoom
                spot = place(self._screen(other), label.boundingRect().size(), other.rect().right(), taken)
                if spot is None:                                # no free spot: the tooltip still names it
                    self.canvas.scene().removeItem(label)
                    continue
                label.setBrush(QColor(self.t["ink"]))
                label.setPos(spot)
                self.hover_labels.append(label)

    def _screen(self, item) -> QPointF:
        return QPointF(self.canvas.mapFromScene(item.pos()))

    def _show_groups(self, visible):
        for item in self.items.values():
            item.setVisible(item.group in visible)
        self._draw_edges()
        self.retheme(self.t)

    def _highlight(self, group):
        for item in self.items.values():
            item.setOpacity(1.0 if group in (-1, item.group) else DIMMED)
        for item in self.edge_items:
            item.setOpacity(1.0 if group in (-1, item.data(0)) else DIMMED)

    def _draw_edges(self):
        """One path per repo or folder, so a few hundred links stay a handful of items."""
        for item in self.edge_items:
            self.canvas.scene().removeItem(item)
        visible = {nid for nid, item in self.items.items() if item.isVisible()}
        paths: dict[int, QPainterPath] = {}
        d = self.drawing
        for ed in d.graph.edges:
            if ed.src in visible and ed.dst in visible and ed.src != ed.dst:
                path = paths.setdefault(d.group[ed.src], QPainterPath())
                path.moveTo(*d.pos[ed.src])
                path.lineTo(*d.pos[ed.dst])
        self.edge_items = []
        for group, path in paths.items():
            item = self.canvas.scene().addPath(path)
            item.setData(0, group)
            item.setZValue(0)
            self.edge_items.append(item)
        self._highlight(self.panel.current)

    def retheme(self, theme):
        self.t = theme
        for item in self.items.values():
            item.retheme(theme)
        light = QColor(theme["panel"]).lightness() > 128
        for item in self.edge_items:
            edge = color(item.data(0))
            edge.setAlpha(190 if light else 110)            # faint lines vanish on a white card
            pen = QPen(edge, 1)
            pen.setCosmetic(True)
            item.setPen(pen)

    def node_items(self) -> list[NodeItem]:
        return list(self.items.values())

    def selected_node(self):
        chosen = [item for item in self.canvas.scene().selectedItems() if isinstance(item, NodeItem)]
        return chosen[0].node if chosen else None
