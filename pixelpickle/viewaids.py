"""Hulpmiddelen in beeld: raster, linialen, hulplijnen en uitlijnen (snappen) op raster of hulplijnen.
De instellingen staan in main.view_opts (bewaard in de programma-instellingen); de hulplijnen horen bij
de afbeelding (doc.guides)."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPen

DEFAULTS = {"grid": False, "rulers": False, "guides": True, "snap_grid": False, "snap_guides": True,
            "grid_h": 50, "grid_v": 50, "grid_color": "#7878ff", "guide_color": "#00c8ff", "snap_dist": 8}


def snap(cv, pt):
    """Punt naar het dichtstbijzijnde rasterpunt of de dichtstbijzijnde hulplijn trekken, als die binnen de
    uitlijnafstand (in schermpixels) ligt."""
    o = cv.main.view_opts
    tol = o["snap_dist"] / max(cv.zoom, 1e-6)
    x, y = pt.x(), pt.y()
    best_x = best_y = None
    if o["snap_grid"]:
        gx, gy = max(1, o["grid_v"]), max(1, o["grid_h"])
        cx, cy = round(x / gx) * gx, round(y / gy) * gy
        if abs(cx - x) <= tol:
            best_x = cx
        if abs(cy - y) <= tol:
            best_y = cy
    if o["snap_guides"] and o["guides"]:
        for gxp in cv.doc.guides["v"]:
            if abs(gxp - x) <= tol and (best_x is None or abs(gxp - x) < abs(best_x - x)):
                best_x = gxp
        for gyp in cv.doc.guides["h"]:
            if abs(gyp - y) <= tol and (best_y is None or abs(gyp - y) < abs(best_y - y)):
                best_y = gyp
    return QPointF(best_x if best_x is not None else x, best_y if best_y is not None else y)


def paint_grid(cv, p, vis):
    o = cv.main.view_opts
    if not getattr(cv, "show_grid", False) or cv.zoom * min(o["grid_h"], o["grid_v"]) < 4:
        return
    p.save()
    p.setClipRect(vis)
    c = QColor(o["grid_color"])
    c.setAlpha(140)
    p.setPen(QPen(c, 0))
    d, z = cv.doc, cv.zoom
    x = 0
    while x <= d.w:
        wx = cv.ox + x * z
        p.drawLine(QPointF(wx, vis.top()), QPointF(wx, vis.bottom()))
        x += o["grid_v"]
    y = 0
    while y <= d.h:
        wy = cv.oy + y * z
        p.drawLine(QPointF(vis.left(), wy), QPointF(vis.right(), wy))
        y += o["grid_h"]
    p.restore()


def paint_guides(cv, p, vis):
    o = cv.main.view_opts
    g = cv.doc.guides
    if not o["guides"] or not (g["h"] or g["v"]):
        return
    p.save()
    p.setClipRect(vis)
    p.setPen(QPen(QColor(o["guide_color"]), 0))
    for y in g["h"]:
        wy = cv.oy + y * cv.zoom
        p.drawLine(QPointF(vis.left(), wy), QPointF(vis.right(), wy))
    for x in g["v"]:
        wx = cv.ox + x * cv.zoom
        p.drawLine(QPointF(wx, vis.top()), QPointF(wx, vis.bottom()))
    p.restore()


def _step(zoom):
    """Afstand (in afbeeldingspixels) tussen de genummerde streepjes, zodat ze niet te dicht op elkaar staan."""
    for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000):
        if s * zoom >= 50:
            return s
    return 10000


def paint_rulers(cv, p):
    if not cv.rulers_on():
        return
    R = cv.RULER
    pal = cv.palette()
    bg, fg = pal.window().color(), pal.windowText().color()
    p.save()
    p.fillRect(QRectF(0, 0, cv.width(), R), bg)
    p.fillRect(QRectF(0, 0, R, cv.height()), bg)
    f = QFont(p.font())
    f.setPixelSize(9)
    p.setFont(f)
    p.setPen(QPen(fg, 0))
    z = cv.zoom
    step = _step(z)
    minor = step / 5 if step >= 5 else step
    # boven
    first = int(max(0, (R - cv.ox) / z) // minor) * minor
    v = first
    while cv.ox + v * z <= cv.width() and v <= cv.doc.w:
        x = cv.ox + v * z
        if x >= R:
            big = abs(v / step - round(v / step)) < 1e-6
            p.drawLine(QPointF(x, R - (8 if big else 3)), QPointF(x, R))
            if big:
                p.drawText(QPointF(x + 2, 9), str(int(v)))
        v += minor
    # links
    first = int(max(0, (R - cv.oy) / z) // minor) * minor
    v = first
    while cv.oy + v * z <= cv.height() and v <= cv.doc.h:
        y = cv.oy + v * z
        if y >= R:
            big = abs(v / step - round(v / step)) < 1e-6
            p.drawLine(QPointF(R - (8 if big else 3), y), QPointF(R, y))
            if big:
                p.save()
                p.translate(9, y + 2)
                p.rotate(90)
                p.drawText(QPointF(0, 0), str(int(v)))
                p.restore()
        v += minor
    p.drawLine(QPointF(0, R), QPointF(cv.width(), R))
    p.drawLine(QPointF(R, 0), QPointF(R, cv.height()))
    # grepen van de hulplijnen en de muispositie
    gc = QColor(cv.main.view_opts["guide_color"])
    p.setPen(QPen(gc, 0))
    p.setBrush(gc)
    for x in cv.doc.guides["v"]:
        wx = cv.ox + x * z
        if wx >= R:
            p.drawRect(QRectF(wx - 3, 2, 6, R - 4))
    for y in cv.doc.guides["h"]:
        wy = cv.oy + y * z
        if wy >= R:
            p.drawRect(QRectF(2, wy - 3, R - 4, 6))
    m = getattr(cv, "mouse_doc", None)
    if m is not None:
        p.setPen(QPen(QColor(220, 50, 50), 0))
        mx, my = cv.ox + m.x() * z, cv.oy + m.y() * z
        if mx >= R:
            p.drawLine(QPointF(mx, 0), QPointF(mx, R))
        if my >= R:
            p.drawLine(QPointF(0, my), QPointF(R, my))
    p.restore()
