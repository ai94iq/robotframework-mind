"""Icons drawn from SVG at the exact size and pixel ratio asked for, so they stay sharp at any scale."""
import math
import os
import tempfile

from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QIconEngine, QImage, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .lucide import ICONS

ICON_SIZE = QSize(16, 16)       # square icons only; the icon-text gap is the stylesheet's padding
# What the app calls an icon -> the Lucide name. Rename here, never at call sites.
ICON_NAMES = {"edit": "mouse-pointer-click", "inspect": "scan-search", "run": "play", "clear": "trash-2",
              "undo": "undo-2", "target": "monitor", "secret": "lock", "record": "circle-dot"}
BRAND = "#4361ee"               # the app icon's background; keep it equal to the light theme's accent


def svg_bytes(name, color, opacity=1.0, pixels=24):
    """The icon's SVG; `pixels` is the physical size it is drawn at, so the stroke can land on whole pixels."""
    # Lucide strokes are 2 units on a 24-unit grid: 1.67 px at 20 px (16 px at 125%), which antialiasing
    # smears over two pixels. Round the stroke to whole device pixels instead.
    width = max(1, round(2 * pixels / 24)) * 24 / pixels
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%s" stroke-opacity="%s" '
            'stroke-width="%.3f" stroke-linecap="round" stroke-linejoin="round">%s</svg>'
            % (QColor(color).name(), opacity, width, ICONS[ICON_NAMES.get(name, name)])).encode()


class SvgIconEngine(QIconEngine):
    """Draws the SVG at the painter's real size and device pixel ratio; `on_color` is the checked state."""

    def __init__(self, name, color, on_color=None):
        super().__init__()
        self.name, self.color, self.on_color = name, color, on_color

    def paint(self, painter, rect, mode, state):
        color = self.on_color if state == QIcon.State.On and self.on_color else self.color
        side = min(rect.width(), rect.height())
        ratio = painter.device().devicePixelRatioF() if painter.device() else 1.0
        renderer = QSvgRenderer(QByteArray(svg_bytes(self.name, color, 0.4 if mode == QIcon.Mode.Disabled else 1.0,
                                                     side * ratio)))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(rect.x() + (rect.width() - side) / 2, rect.y() + (rect.height() - side) / 2,
                                        side, side))
        painter.restore()

    def pixmap(self, size, mode, state):
        pm = QPixmap(size)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        self.paint(painter, pm.rect(), mode, state)
        painter.end()
        return pm

    def clone(self):
        return SvgIconEngine(self.name, self.color, self.on_color)


def icon(name, color, on_color=None):
    """An outline icon drawn in `color`; `on_color` draws the checked state (for example on an accent fill)."""
    return QIcon(SvgIconEngine(name, color, on_color))


def chevrons(color):
    """Paths of chevron PNGs (plus @2x) in a temp folder: stylesheets take image files, not icons."""
    folder = os.path.join(tempfile.gettempdir(), "__app__-icons")
    os.makedirs(folder, exist_ok=True)
    paths = {}
    for name in ("chevron-right", "chevron-down"):
        base = os.path.join(folder, "%s-%s" % (name, QColor(color).name()[1:]))
        for suffix, side in (("", 16), ("@2x", 32)):
            image = QImage(side, side, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            QSvgRenderer(QByteArray(svg_bytes(name, color, pixels=side))).render(painter, QRectF(0, 0, side, side))
            painter.end()
            image.save(base + suffix + ".png")
        paths[name.replace("-", "_")] = (base + ".png").replace("\\", "/")     # QSS wants forward slashes
    return paths


DOT_MARGIN = 1                  # px of clear space around a dot, so its antialiased edge is never cut


def dot_pixmap(color, size=10, hollow=False, ratio=None):
    """A filled (or hollow) status dot of `size` px plus DOT_MARGIN all round, drawn at the device pixel ratio."""
    if ratio is None:
        screen = QGuiApplication.primaryScreen()
        ratio = screen.devicePixelRatio() if screen else 1.0
    side = math.ceil((size + 2 * DOT_MARGIN) * ratio)
    pm = QPixmap(side, side)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    box = QRectF(0, 0, size * ratio, size * ratio)
    box.moveCenter(QPointF(side / 2, side / 2))
    if hollow:
        pen = 1.5 * ratio
        p.setPen(QPen(QColor(color), pen))
        p.setBrush(Qt.BrushStyle.NoBrush)
        box = box.adjusted(pen / 2, pen / 2, -pen / 2, -pen / 2)
    else:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
    p.drawEllipse(box)
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def app_icon(glyph="target"):
    """The window, taskbar and bundle icon: a white glyph on a rounded brand square, drawn for each size."""
    result = QIcon()
    for side in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(side, side)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(BRAND))
        p.drawRoundedRect(QRectF(0, 0, side, side), side * 0.22, side * 0.22)
        inset = side * 0.18
        QSvgRenderer(QByteArray(svg_bytes(glyph, "#ffffff", pixels=side - 2 * inset))).render(
            p, QRectF(inset, inset, side - 2 * inset, side - 2 * inset))
        p.end()
        result.addPixmap(pm)
    return result
