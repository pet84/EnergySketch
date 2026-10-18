# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Original flat drawings in the host's ink/accent, with its live refresh.

No image assets or fixed colours: the same QPainter paths, 48-unit canvas,
round strokes and palette as views.icons. Namespaced registration lets
the host repaint toolbar AND menu actions on theme/accent changes.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainterPath, QPen, QPolygonF

from views import icons as host


def _pen(color, width=3):
    pen = QPen(color, width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _poly(p, points, fill=Qt.NoBrush):
    p.setBrush(fill)
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))


def _line(p, a, b):
    p.drawLine(QPointF(*a), QPointF(*b))


def _arrow(p, start, end, color):
    p.setPen(_pen(color))
    _line(p, start, end)
    x, y = end
    if start[0] == x:
        dy = 5 if end[1] < start[1] else -5
        _line(p, (x-5, y+dy), end)
        _line(p, (x+5, y+dy), end)
    else:
        dx = 5 if end[0] < start[0] else -5
        _line(p, (x+dx, y-5), end)
        _line(p, (x+dx, y+5), end)


def _panel(p, ink):
    p.drawRoundedRect(QRectF(9, 10, 30, 28), 2, 2)
    _line(p, (9, 18), (39, 18))
    _line(p, (19, 18), (19, 38))
    _line(p, (24, 30), (34, 30))
    _line(p, (24, 35), (31, 35))
    p.setPen(_pen(host._accent()))
    _line(p, (24, 24), (34, 24))


def _live(p, ink):
    p.drawRoundedRect(QRectF(8, 16, 12, 20), 2, 2)
    p.drawRoundedRect(QRectF(28, 12, 12, 20), 2, 2)
    _arrow(p, (12, 10), (25, 10), host._accent())
    _arrow(p, (36, 38), (23, 38), host._accent())


def _materials(p, ink):
    path = QPainterPath(QPointF(36, 30))
    path.cubicTo(45, 17, 33, 7, 22, 9)
    path.cubicTo(9, 10, 4, 23, 11, 34)
    path.cubicTo(17, 42, 31, 41, 29, 34)
    path.cubicTo(27, 27, 33, 26, 36, 30)
    p.drawPath(path)
    for x, y in ((15, 23), (22, 16), (31, 18)):
        host._dot(p, x, y, 2.8)


def _zones(p, ink):
    _poly(p, [(10, 15), (24, 8), (38, 15), (38, 33), (24, 40), (10, 33)])
    _line(p, (10, 15), (24, 22))
    _line(p, (24, 22), (38, 15))
    _line(p, (24, 22), (24, 40))
    p.setPen(_pen(host._accent()))
    _line(p, (17, 12), (31, 19))
    _line(p, (31, 19), (31, 36))


def _new_material(p, ink):
    _poly(p, [(10, 12), (28, 12), (28, 30), (10, 30)])
    p.setPen(_pen(host._accent()))
    _line(p, (15, 24), (23, 16))
    _line(p, (26, 34), (40, 34))
    _line(p, (33, 27), (33, 41))


def _windows(p, ink):
    p.drawRect(QRectF(9, 9, 30, 30))
    p.drawRect(QRectF(14, 14, 20, 20))
    _line(p, (24, 14), (24, 34))
    p.setPen(_pen(host._accent()))
    _line(p, (14, 24), (34, 24))


def _folder(p):
    path = QPainterPath(QPointF(9, 36))
    path.lineTo(9, 14)
    path.lineTo(20, 14)
    path.lineTo(24, 19)
    path.lineTo(39, 19)
    path.lineTo(39, 36)
    path.closeSubpath()
    p.drawPath(path)


def _library_import(p, ink):
    _folder(p)
    _arrow(p, (28, 8), (28, 29), host._accent())


def _library_export(p, ink):
    _folder(p)
    _arrow(p, (28, 29), (28, 8), host._accent())


def _csv_complex(p, ink):
    p.drawRect(QRectF(9, 10, 30, 28))
    _line(p, (9, 19), (39, 19))
    _line(p, (19, 10), (19, 38))
    _line(p, (9, 28), (39, 28))
    p.setPen(_pen(host._accent()))
    _line(p, (29, 10), (29, 38))


def _house(p):
    _line(p, (8, 22), (24, 9))
    _line(p, (24, 9), (40, 22))
    _line(p, (13, 20), (13, 38))
    _line(p, (13, 38), (35, 38))
    _line(p, (35, 38), (35, 20))


def _csv_energy(p, ink):
    _house(p)
    p.setPen(_pen(host._accent(), 2))
    _poly(p, [(25, 19), (19, 29), (25, 29), (22, 36), (30, 25), (24, 25)], host._accent())


def _csv_rp(p, ink):
    _poly(p, [(11, 8), (30, 8), (38, 16), (38, 40), (11, 40)])
    _line(p, (30, 8), (30, 16))
    _line(p, (30, 16), (38, 16))
    _line(p, (17, 33), (23, 33))
    _line(p, (17, 24), (21, 20))
    _line(p, (21, 20), (25, 24))
    p.setPen(_pen(host._accent()))
    _line(p, (26, 32), (29, 35))
    _line(p, (29, 35), (35, 27))


def _north(p, ink):
    p.drawEllipse(QRectF(9, 9, 30, 30))
    _line(p, (24, 6), (24, 10))
    _line(p, (24, 38), (24, 42))
    _line(p, (6, 24), (10, 24))
    _line(p, (38, 24), (42, 24))
    _poly(p, [(24, 13), (18, 32), (24, 28), (30, 32)])
    p.setPen(Qt.NoPen)
    _poly(p, [(24, 14), (19, 30), (24, 27)], host._accent())


def _help(p, ink):
    p.drawEllipse(QRectF(9, 9, 30, 30))
    path = QPainterPath(QPointF(19, 20))
    path.cubicTo(19, 12, 33, 14, 29, 23)
    path.cubicTo(28, 25, 24, 25, 24, 28)
    p.drawPath(path)
    host._dot(p, 24, 33, 2.1)


DRAWINGS = {
    "panel": _panel, "live": _live, "materials": _materials,
    "zones": _zones, "material_new": _new_material, "windows": _windows,
    "library_import": _library_import, "library_export": _library_export,
    "csv_complex": _csv_complex, "csv_energy": _csv_energy, "csv_rp": _csv_rp,
    "north": _north, "help": _help,
}


def register_icons():
    # Existing native refresh paths use icon_key and _icon_actions. Keeping
    # this adaptation here avoids edits to any host file or theme handler.
    for key, draw in DRAWINGS.items():
        host._DRAW[f"archcontrol_{key}"] = draw
