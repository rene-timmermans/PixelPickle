"""Gereedschappen, ingedeeld zoals de PSP XI gereedschapsbalk (zie psplayout.py)."""
import math
import random

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen,
                           QPolygonF, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFontComboBox, QInputDialog, QLabel,
                               QPushButton, QSpinBox)

from . import imageops as ops
from .document import CM, TOOL_BLEND_MODES, Layer, apply_region, blend_onto, new_image, paint_layer
from .psplayout import TOOL_NAMES

LB = Qt.MouseButton.LeftButton
RB = Qt.MouseButton.RightButton
SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier

DEFAULT_OPTS = dict(
    size=25, hardness=100, step=10, density=100, thickness=100, rotation=0, brush_shape=0,
    opacity=100, blend=0, rate=10, tolerance=20, contiguous=True, sample_merged=False,
    sel_shape=0, sel_mode=0, feather=0, antialias=True, lasso_type=0, line_width=3,
    shape_fill=True, shape_stroke=True, radius=0, sym_sides=5, sym_star=True, sym_inner=50,
    preset=0, pen_mode=0, font="Sans Serif", font_size=48, bold=False, italic=False,
    sample_size=0, clone_aligned=True, bg_sampling=0, straighten_mode=0, straighten_crop=False,
    target_mode=0, redeye_strength=80, zoom_step=0, match_mode=1, aa_where=0, lasso_range=10,
    lasso_smooth=0, text_units=0, underline=False, text_align=0, text_stroke=0, leading=0, tracking=0,
)


# ---------------------------------------------------------------- optie widgets
_RECORD = []  # welke opties een gereedschap toont (voor voorinstellingen)


def _rec(key):
    _RECORD.append(key)


def recorded_keys(tool):
    _RECORD.clear()
    widgets = tool.options()
    return widgets, list(dict.fromkeys(_RECORD))


def spin(main, key, label, lo, hi, suffix=""):
    _rec(key)
    w = QSpinBox()
    w.setRange(lo, hi)
    w.setValue(main.opts[key])
    w.setSuffix(suffix)
    w.setAccelerated(True)
    w.valueChanged.connect(lambda v: main.opts.__setitem__(key, v))
    return [QLabel(label), w]


def combo(main, key, label, items):
    _rec(key)
    w = QComboBox()
    w.addItems(items)
    w.setCurrentIndex(min(main.opts[key], len(items) - 1))
    w.currentIndexChanged.connect(lambda v: main.opts.__setitem__(key, v))
    return ([QLabel(label)] if label else []) + [w]


def check(main, key, label):
    _rec(key)
    w = QCheckBox(label)
    w.setChecked(main.opts[key])
    w.toggled.connect(lambda v: main.opts.__setitem__(key, v))
    return [w]


def button(text, fn):
    b = QPushButton(text)
    b.clicked.connect(fn)
    return [b]


def ipt(pt):
    return int(math.floor(pt.x())), int(math.floor(pt.y()))


def sel_mode_from(ev, default):
    m = ev.modifiers()
    if m & CTRL:
        return "sub"
    if m & SHIFT:
        return "add"
    return ["replace", "add", "sub"][default]


class Tool:
    edits_pixels = True  # False voor gereedschappen die geen pixels van de laag wijzigen
    cid = 0
    glyph = "?"
    tip = ""
    cursor = Qt.CursorShape.CrossCursor
    is_pan = False
    wants_cursor_overlay = False
    available = True

    def __init__(self, main):
        self.main = main

    @property
    def name(self):
        return TOOL_NAMES.get(self.cid, "?")

    @property
    def o(self):
        return self.main.opts

    def options(self):
        return []

    def press(self, cv, pt, ev): pass
    def move(self, cv, pt, ev): pass
    def release(self, cv, pt, ev): pass
    def double_click(self, cv, pt, ev): pass
    def overlay(self, cv, p): pass
    def key(self, cv, ev): return False
    def deactivate(self): pass
    def hover_cursor(self, cv, pt): return None

    # Rechtsklik zonder slepen opent het snelmenu bij gereedschappen die de rechterknop niet zelf gebruiken
    context_menu = False

    def wants_context_menu(self, cv):
        return self.context_menu

    def context_actions(self, cv):
        """Extra opdrachten bovenaan het snelmenu: [(tekst, functie)]."""
        return []


class PlaceholderTool(Tool):
    available = False
    tip = "Dit gereedschap volgt in een volgende versie van Pigment."

    def __init__(self, main, cid, glyph):
        super().__init__(main)
        self.cid, self.glyph = cid, glyph

    def press(self, cv, pt, ev):
        self.main.statusBar().showMessage(f"{self.name}: nog niet beschikbaar in deze versie.", 4000)


# ================================================================ navigatie
class PanTool(Tool):
    context_menu = True
    edits_pixels = False
    cid, glyph = 0xd001, "✋"
    tip = "Sleep om het beeld te verschuiven (ook: spatie of middelste muisknop)"
    cursor = Qt.CursorShape.OpenHandCursor
    is_pan = True


class ZoomTool(Tool):
    edits_pixels = False
    cid, glyph = 0xd002, "🔍"
    tip = "Klik om in te zoomen, rechtsklik om uit te zoomen"

    def options(self):
        return (button("100%", lambda: self.main.canvas() and self.main.canvas().actual_size())
                + button("Passend", lambda: self.main.canvas() and self.main.canvas().fit()))

    def press(self, cv, pt, ev):
        cv.zoom_step(ev.button() == LB, ev.position())


class DropperTool(Tool):
    edits_pixels = False
    cid, glyph = 0xd030, "💧"
    tip = "Klik: voorgrondkleur kiezen, rechtsklik: achtergrondkleur kiezen"

    def options(self):
        return (combo(self.main, "sample_size", "Proefgrootte:", ["1 × 1", "3 × 3", "5 × 5", "7 × 7", "9 × 9", "11 × 11"])
                + check(self.main, "sample_merged", "Alle lagen gebruiken"))

    def pick(self, cv, pt, foreground):
        x, y = ipt(pt)
        d = cv.doc
        if not d.rect().contains(x, y):
            return
        img = cv.cache if self.o["sample_merged"] else d.layer().image
        r = self.o["sample_size"]
        if r == 0:
            c = img.pixelColor(x, y)
        else:
            a = ops.qimage_to_rgba(img.copy(QRect(x - r, y - r, 2 * r + 1, 2 * r + 1).intersected(d.rect())))
            m = a.reshape(-1, 4).mean(axis=0)
            c = QColor(int(m[0]), int(m[1]), int(m[2]))
        c.setAlpha(255)
        self.main.set_color(c, foreground)

    def press(self, cv, pt, ev):
        self.pick(cv, pt, ev.button() == LB)

    def move(self, cv, pt, ev):
        if ev.buttons() & (LB | RB):
            self.pick(cv, pt, bool(ev.buttons() & LB))


# ================================================================ verplaatsen
class LayerMover:
    """Verplaatst de laag, de geselecteerde pixels of alleen het selectiekader."""

    def __init__(self, cv, pt, what):
        d = cv.doc
        self.cv, self.start, self.what = cv, pt, what  # what: layer | pixels | marquee
        d.push_undo({"layer": "Verplaatsen", "pixels": "Selectie verplaatsen", "marquee": "Selectiekader verplaatsen"}[what])
        self.base = QImage(d.layer().image)
        act = d.layer()
        members = [l for l in d.subtree(act) if l.kind != "group"] if act.kind == "group" else [act]
        self.linked = [(l, QImage(l.image)) for l in d.layers
                       if l in members or (act.link_set and l.link_set == act.link_set and l.adjust is None
                                           and l.kind != "group")]
        from .textlayer import copy_text
        self.text_base = {id(l): copy_text(l.text) for l, _ in self.linked if l.text is not None}
        self.sel = QImage(d.sel) if d.sel is not None else None
        self.lines = list(d.sel_lines)
        self.last = (0, 0)
        if what == "pixels":
            self.piece = QImage(self.base)
            p = QPainter(self.piece)
            p.setCompositionMode(CM.CompositionMode_DestinationIn)
            p.drawImage(0, 0, self.sel)
            p.end()
            self.hole = QImage(self.base)
            p = QPainter(self.hole)
            p.setCompositionMode(CM.CompositionMode_DestinationOut)
            p.drawImage(0, 0, self.sel)
            p.end()
            if d.active == 0 and d.layer().name == "Achtergrond":  # gat vullen met achtergrondkleur, zoals PSP
                bgfill = new_image(d.w, d.h, cv.main.bg)
                p = QPainter(bgfill)
                p.setCompositionMode(CM.CompositionMode_DestinationIn)
                p.drawImage(0, 0, self.sel)
                p.end()
                p = QPainter(self.hole)
                p.drawImage(0, 0, bgfill)
                p.end()

    def move(self, pt):
        dx, dy = round(pt.x() - self.start.x()), round(pt.y() - self.start.y())
        if (dx, dy) == self.last:
            return
        self.last = (dx, dy)
        d = self.cv.doc
        if self.what in ("pixels", "marquee") and self.sel is not None:
            m = QImage(d.w, d.h, QImage.Format.Format_Alpha8)
            m.fill(QColor(0, 0, 0, 0))
            p = QPainter(m)
            p.drawImage(dx, dy, self.sel)
            p.end()
            d.sel = m
            d.sel_lines = [l.translated(dx, dy) for l in self.lines]
        if self.what == "layer":
            from .textlayer import copy_text, set_transform, transform
            for layer, base in self.linked:
                if id(layer) in self.text_base:  # tekst blijft tekst
                    t = copy_text(self.text_base[id(layer)])
                    set_transform(t, transform(t) * QTransform.fromTranslate(dx, dy))
                    layer.text = t
                    d.render_text(layer)
                    continue
                out = new_image(d.w, d.h)
                p = QPainter(out)
                p.drawImage(dx, dy, base)
                p.end()
                layer.image = out
            d.changed.emit(QRect())
        elif self.what == "pixels":
            out = QImage(self.hole)
            p = QPainter(out)
            p.drawImage(dx, dy, self.piece)
            p.end()
            d.layer().image = out
            d.changed.emit(QRect())
        else:
            self.cv.update()

    def finish(self):
        d = self.cv.doc
        if self.last == (0, 0):
            d.drop_last_undo()
        elif self.sel is not None and self.what != "layer":
            d.set_selection(d.sel)
        d.structureChanged.emit()


class MoveTool(Tool):
    context_menu = True
    edits_pixels = False
    cid, glyph = 0xd012, "✥"
    tip = "Sleep om de laag te verplaatsen. Rechts slepen: alleen het selectiekader verplaatsen"
    cursor = Qt.CursorShape.SizeAllCursor

    def __init__(self, main):
        super().__init__(main)
        self.mover = None

    def press(self, cv, pt, ev):
        what = "marquee" if ev.button() == RB and cv.doc.sel is not None else "layer"
        self.mover = LayerMover(cv, pt, what)

    def move(self, cv, pt, ev):
        if self.mover and ev.buttons() & (LB | RB):
            self.mover.move(pt)

    def release(self, cv, pt, ev):
        if self.mover:
            self.mover.finish()
            self.mover = None


_ROT_CURSOR = None


def rotate_cursor():
    global _ROT_CURSOR
    if _ROT_CURSOR is None:
        from PySide6.QtGui import QCursor, QPixmap
        pm = QPixmap(24, 24)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for col, w in ((QColor(255, 255, 255), 4), (QColor(0, 0, 0), 2)):
            p.setPen(QPen(col, w))
            p.drawArc(QRectF(4, 4, 16, 16), 30 * 16, 280 * 16)
            p.drawLine(QPointF(17, 3), QPointF(19, 8))
            p.drawLine(QPointF(19, 8), QPointF(14, 9))
        p.end()
        _ROT_CURSOR = QCursor(pm, 12, 12)
    return _ROT_CURSOR


class PickTool(Tool):
    context_menu = True
    edits_pixels = False
    cid, glyph = 0xd011, "➚"
    tip = "Selecteren: sleep de grepen om te schalen, de draaigreep om te roteren, binnen het kader om te verplaatsen. Shift: verhouding behouden"
    cursor = Qt.CursorShape.ArrowCursor
    HS = 5

    def __init__(self, main):
        super().__init__(main)
        self.box = None
        self.drag = None
        self.box_doc = None

    def _bbox(self, d):
        a = ops.qimage_to_rgba(d.layer().image)[..., 3] > 0
        r = ops.mask_bbox(a)
        return QRectF(r) if not r.isEmpty() else QRectF(d.rect())

    def _poly(self, cv):
        layer = cv.doc.layer()
        if (self.box_doc is not cv.doc or self.box is None or getattr(self, "box_layer", None) is not layer
                or (self.drag is None and self._stale)):
            self.box = self._bbox(cv.doc)
            self.box_doc = cv.doc
            self.box_layer = layer
            self.T = QTransform()
            self._stale = False
        return self.T.map(QPolygonF(self.box))

    _stale = True

    def _handles(self, cv):
        poly = self._poly(cv)
        pts = [poly[0], poly[1], poly[2], poly[3]]
        mids = [(pts[i] + pts[(i + 1) % 4]) / 2 for i in range(4)]
        center = (pts[0] + pts[2]) / 2
        right = mids[1]
        rot = right + (right - center) * 0.25
        return pts, mids, center, rot

    def _hit(self, cv, pt):
        pts, mids, center, rot = self._handles(cv)
        tol = 7 / cv.zoom
        if math.hypot(rot.x() - pt.x(), rot.y() - pt.y()) < tol:
            return ("rot", None)
        for i, q in enumerate(pts):
            if math.hypot(q.x() - pt.x(), q.y() - pt.y()) < tol:
                return ("corner", i)
        for i, q in enumerate(mids):
            if math.hypot(q.x() - pt.x(), q.y() - pt.y()) < tol:
                return ("side", i)
        if self._poly(cv).containsPoint(pt, Qt.FillRule.OddEvenFill):
            return ("move", None)
        return None

    def hover_cursor(self, cv, pt):
        hit = self._hit(cv, pt)
        if hit is None:
            return Qt.CursorShape.ArrowCursor
        kind, i = hit
        if kind == "rot":
            return rotate_cursor()
        if kind == "corner":
            return Qt.CursorShape.SizeFDiagCursor if i in (0, 2) else Qt.CursorShape.SizeBDiagCursor
        if kind == "side":
            return Qt.CursorShape.SizeVerCursor if i in (0, 2) else Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeAllCursor

    def press(self, cv, pt, ev):
        if ev.button() != LB:
            return
        d = cv.doc
        self._stale = True
        pts, mids, center, rot = self._handles(cv)
        tol = 7 / cv.zoom
        hit = None
        if math.hypot(rot.x() - pt.x(), rot.y() - pt.y()) < tol:
            hit = ("rot", None)
        for i, q in enumerate(pts):
            if math.hypot(q.x() - pt.x(), q.y() - pt.y()) < tol:
                hit = ("corner", i)
        for i, q in enumerate(mids):
            if hit is None and math.hypot(q.x() - pt.x(), q.y() - pt.y()) < tol:
                hit = ("side", i)
        if hit is None:
            hit = ("move", None)
        d.push_undo("Selecteren")
        from .textlayer import copy_text
        self.text_base = copy_text(d.layer().text)
        self.drag = hit
        self.start = pt
        self.base = QImage(d.layer().image)
        self.box0 = QRectF(self.box)
        self.center = center
        self.changed_any = False

    def move(self, cv, pt, ev):
        if self.drag is None or not (ev.buttons() & LB):
            return
        kind, i = self.drag
        b = self.box0
        dx, dy = pt.x() - self.start.x(), pt.y() - self.start.y()
        if kind == "move":
            T = QTransform.fromTranslate(dx, dy)
        elif kind == "rot":
            c = self.center
            a0 = math.atan2(self.start.y() - c.y(), self.start.x() - c.x())
            a1 = math.atan2(pt.y() - c.y(), pt.x() - c.x())
            ang = math.degrees(a1 - a0)
            if ev.modifiers() & SHIFT:
                ang = round(ang / 15) * 15
            T = QTransform().translate(c.x(), c.y()).rotate(ang).translate(-c.x(), -c.y())
            self.main.statusBar().showMessage(f"Hoek: {ang:.1f}°")
        else:
            l, t, r, bt = b.left(), b.top(), b.right(), b.bottom()
            if kind == "corner":
                if i == 0: l, t = l + dx, t + dy
                elif i == 1: r, t = r + dx, t + dy
                elif i == 2: r, bt = r + dx, bt + dy
                else: l, bt = l + dx, bt + dy
            else:
                if i == 0: t += dy
                elif i == 1: r += dx
                elif i == 2: bt += dy
                else: l += dx
            sx = (r - l) / max(1e-6, b.width())
            sy = (bt - t) / max(1e-6, b.height())
            if kind == "corner" and ev.modifiers() & SHIFT:
                s = max(abs(sx), abs(sy))
                sx, sy = math.copysign(s, sx), math.copysign(s, sy)
                if i in (0, 3): l = r - b.width() * sx
                else: r = l + b.width() * sx
                if i in (0, 1): t = bt - b.height() * sy
                else: bt = t + b.height() * sy
            T = QTransform().translate(l, t).scale(sx, sy).translate(-b.left(), -b.top())
            self.main.statusBar().showMessage(f"Schaal X: {sx * 100:.1f}%  Schaal Y: {sy * 100:.1f}%")
        self.T = T
        d = cv.doc
        if self.text_base is not None:  # tekstlaag: transformatie in de tekst opslaan
            from .textlayer import copy_text, set_transform, transform
            t = copy_text(self.text_base)
            set_transform(t, transform(t) * T)
            d.layer().text = t
            d.render_text(d.layer())
            self.changed_any = True
            d.changed.emit(QRect())
            return
        out = new_image(d.w, d.h)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setTransform(T)
        p.drawImage(0, 0, self.base)
        p.end()
        d.layer().image = out
        self.changed_any = True
        d.changed.emit(QRect())

    def release(self, cv, pt, ev):
        if self.drag is None:
            return
        self.drag = None
        if not self.changed_any:
            cv.doc.drop_last_undo()
        self._stale = True
        self.base = None
        cv.doc.structureChanged.emit()
        cv.update()

    def overlay(self, cv, p):
        if cv.doc is None:
            return
        pts, mids, center, rot = self._handles(cv)
        W = [cv.to_widget(q) for q in pts]
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.addPolygon(QPolygonF(W + [W[0]]))
        draw_dashed(p, path)
        rc, rr = cv.to_widget(mids[1]), cv.to_widget(rot)
        p.setPen(QPen(QColor(60, 60, 60), 1))
        p.drawLine(rc, rr)
        p.setBrush(QColor(255, 255, 255))
        for q in W + [cv.to_widget(m) for m in mids]:
            p.drawRect(QRectF(q.x() - self.HS / 2 - 1, q.y() - self.HS / 2 - 1, self.HS + 2, self.HS + 2))
        p.setBrush(QColor(140, 140, 140))
        p.drawEllipse(rr, 4, 4)

    def deactivate(self):
        self._stale = True


# ================================================================ selecties
def draw_dashed(p, path):
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255), 0))
    p.drawPath(path)
    p.setPen(QPen(QColor(0, 0, 0), 0, Qt.PenStyle.DashLine))
    p.drawPath(path)


def commit_shape(d, path, mode, feather, antialias, label="Selectie"):
    m = QImage(d.w, d.h, QImage.Format.Format_Alpha8)
    m.fill(QColor(0, 0, 0, 0))
    p = QPainter(m)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, antialias)
    p.fillPath(path, QColor(0, 0, 0, 255))
    p.end()
    d.push_undo(label)
    d.combine_selection(m, mode, feather)


class SelectionBase(Tool):
    context_menu = True
    edits_pixels = False
    """Gemeenschappelijk: binnen een bestaande selectie slepen verplaatst de pixels,
    rechts slepen verplaatst alleen het kader (zoals in PSP)."""
    MODES = ["Vervangen", "Toevoegen", "Verwijderen"]

    def __init__(self, main):
        super().__init__(main)
        self.mover = None

    def common_options(self):
        return (combo(self.main, "sel_mode", "Modus:", self.MODES)
                + spin(self.main, "feather", "Doezelen:", 0, 200)
                + check(self.main, "antialias", "Anti-alias"))

    def try_move(self, cv, pt, ev):
        d = cv.doc
        x, y = ipt(pt)
        if (d.sel is not None and not ev.modifiers() & (SHIFT | CTRL) and d.rect().contains(x, y)
                and d.sel.pixelColor(x, y).alpha() > 127):
            if ev.button() != RB and not self.main.ensure_raster():
                return True
            self.mover = LayerMover(cv, pt, "marquee" if ev.button() == RB else "pixels")
            return True
        return False

    def hover_cursor(self, cv, pt):
        d = cv.doc
        x, y = ipt(pt)
        if (d.sel is not None and d.rect().contains(x, y) and d.sel.pixelColor(x, y).alpha() > 127
                and not getattr(self, "pts", None)):
            mods = QApplication.keyboardModifiers()
            if not mods & (SHIFT | CTRL):
                return Qt.CursorShape.SizeAllCursor
        return None

    def move_drag(self, cv, pt, ev):
        if self.mover:
            self.mover.move(pt)
            return True
        return False

    def end_drag(self):
        if self.mover:
            self.mover.finish()
            self.mover = None
            return True
        return False


class SelectTool(SelectionBase):
    cid, glyph = 0xd021, "⬚"
    tip = "Sleep om te selecteren. Shift: toevoegen, Ctrl: verwijderen. Sleep binnen de selectie om te verplaatsen"
    SHAPES = ["Rechthoek", "Vierkant", "Afgeronde rechthoek", "Afgerond vierkant", "Ovaal", "Cirkel",
              "Driehoek", "Ster 1", "Ster 2", "Pijl rechts"]

    def __init__(self, main):
        super().__init__(main)
        self.a = self.b = None

    def options(self):
        return combo(self.main, "sel_shape", "Selectietype:", self.SHAPES) + self.common_options()

    def press(self, cv, pt, ev):
        if self.try_move(cv, pt, ev) or ev.button() != LB:
            return
        self.a = self.b = pt
        self.mode = sel_mode_from(ev, self.o["sel_mode"])

    def move(self, cv, pt, ev):
        if self.move_drag(cv, pt, ev):
            return
        if self.a is not None and ev.buttons() & LB:
            self.b = pt
            cv.update()

    def path(self):
        return shape_path(self.o["sel_shape"], self.a, self.b, square_types=(1, 3, 5))

    def release(self, cv, pt, ev):
        if self.end_drag() or self.a is None:
            return
        d = cv.doc
        r = QRectF(self.a, self.b).normalized()
        if r.width() < 1 or r.height() < 1:
            if self.mode == "replace" and d.sel is not None:
                d.push_undo("Niets selecteren")
                d.set_selection(None)
        else:
            commit_shape(d, self.path(), self.mode, self.o["feather"], self.o["antialias"])
        self.a = None
        cv.update()

    def overlay(self, cv, p):
        if self.a is not None:
            p.setTransform(cv.transform())
            draw_dashed(p, self.path())
            p.resetTransform()

    def key(self, cv, ev):
        if ev.key() == Qt.Key.Key_Escape and self.a is not None:
            self.a = None
            cv.update()
            return True
        return False


def star_path(cx, cy, rx, ry, points, inner, rot=-math.pi / 2):
    path = QPainterPath()
    n = points * 2
    for i in range(n):
        r = 1.0 if i % 2 == 0 else inner
        ang = rot + i * math.pi / points
        q = QPointF(cx + math.cos(ang) * rx * r, cy + math.sin(ang) * ry * r)
        path.moveTo(q) if i == 0 else path.lineTo(q)
    path.closeSubpath()
    return path


def shape_path(kind, a, b, square_types=()):
    if kind in square_types:
        s = max(abs(b.x() - a.x()), abs(b.y() - a.y()))
        b = QPointF(a.x() + math.copysign(s, b.x() - a.x()), a.y() + math.copysign(s, b.y() - a.y()))
    r = QRectF(a, b).normalized()
    path = QPainterPath()
    cx, cy = r.center().x(), r.center().y()
    if kind in (0, 1):
        path.addRect(QRectF(QPointF(round(r.left()), round(r.top())), QPointF(round(r.right()), round(r.bottom()))))
    elif kind in (2, 3):
        rad = min(r.width(), r.height()) * 0.2
        path.addRoundedRect(r, rad, rad)
    elif kind in (4, 5):
        path.addEllipse(r)
    elif kind == 6:
        path.addPolygon(QPolygonF([QPointF(cx, r.top()), r.bottomRight(), r.bottomLeft()]))
        path.closeSubpath()
    elif kind == 7:
        path = star_path(cx, cy, r.width() / 2, r.height() / 2, 5, 0.4)
    elif kind == 8:
        path = star_path(cx, cy, r.width() / 2, r.height() / 2, 8, 0.6)
    else:
        w, h = r.width(), r.height()
        pts = [(0, .3), (.6, .3), (.6, 0), (1, .5), (.6, 1), (.6, .7), (0, .7)]
        path.addPolygon(QPolygonF([QPointF(r.left() + x * w, r.top() + y * h) for x, y in pts]))
        path.closeSubpath()
    return path


class LassoTool(SelectionBase):
    cid, glyph = 0xd022, "➰"
    TYPES = ["Uit de vrije hand", "Punt tot punt", "Slimme rand", "Rand zoeken"]
    TIPS = ["Klik en teken om te selecteren.",
            "Klik punten aan; dubbelklik of rechtsklik om te sluiten.",
            "Klik punten rond een object; de lijn volgt de sterkste rand binnen het bereik. Dubbelklik of rechtsklik om te sluiten.",
            "Klik punten rond een object; de lijn zoekt de rand op. Dubbelklik of rechtsklik om te sluiten."]

    def __init__(self, main):
        super().__init__(main)
        self.pts = None      # vaste punten van de omtrek (doc coördinaten)
        self.preview = []    # gesnapt stuk van laatste punt naar de muis
        self.G = None

    @property
    def tip(self):
        return self.TIPS[self.o["lasso_type"]] + " Shift = selectie uitbreiden, Ctrl = selectie verkleinen"

    def options(self):
        m = self.main
        return (combo(m, "lasso_type", "Selectietype:", self.TYPES) + combo(m, "sel_mode", "Modus:", self.MODES)
                + spin(m, "feather", "Doezelen:", 0, 200) + spin(m, "lasso_range", "Bereik:", 1, 100)
                + spin(m, "lasso_smooth", "Vloeiend:", 0, 40) + check(m, "antialias", "Anti-alias")
                + check(m, "sample_merged", "Alle lagen gebruiken"))

    def _rng(self):
        return self.o["lasso_range"] * (2 if self.o["lasso_type"] == 3 else 1)

    def wants_context_menu(self, cv):
        return not self.pts

    def _anchor(self, pt):
        if self.o["lasso_type"] >= 2 and self.G is not None:
            x, y = ops.snap_point(self.G, pt.x(), pt.y(), self._rng())
            return QPointF(x, y)
        return pt

    def _segment(self, a, b):
        t = self.o["lasso_type"]
        if t >= 2 and self.G is not None:
            depth = 2 if t == 2 else 5
            return [QPointF(x, y) for x, y in ops.snap_path(self.G, (a.x(), a.y()), (b.x(), b.y()), self._rng(), depth)][1:]
        return [b]

    def press(self, cv, pt, ev):
        t = self.o["lasso_type"]
        if self.pts is None and self.try_move(cv, pt, ev):
            return
        if t == 0:
            if ev.button() == LB:
                self.pts = [pt]
                self.mode = sel_mode_from(ev, self.o["sel_mode"])
            return
        if ev.button() == RB and self.pts:
            self._commit(cv)
            return
        if ev.button() != LB:
            return
        if self.pts is None:
            self.pts = [pt]
            self.mode = sel_mode_from(ev, self.o["sel_mode"])
            if t >= 2:
                src = cv.cache if self.o["sample_merged"] else cv.doc.layer().image
                self.G = ops.edge_map(ops.qimage_to_rgba(src))
                self.pts = [self._anchor(pt)]
        else:
            self.pts += self._segment(self.pts[-1], self._anchor(pt))
        self.preview = []
        cv.update()

    def move(self, cv, pt, ev):
        if self.move_drag(cv, pt, ev):
            return
        if self.o["lasso_type"] == 0:
            if self.pts is not None and ev.buttons() & LB:
                self.pts.append(pt)
                cv.update()
        elif self.pts:
            self.preview = self._segment(self.pts[-1], self._anchor(pt))
            cv.update()

    def release(self, cv, pt, ev):
        if self.end_drag():
            return
        if self.o["lasso_type"] == 0 and self.pts is not None:
            self._commit(cv)

    def double_click(self, cv, pt, ev):
        if self.o["lasso_type"] > 0 and self.pts:
            self._commit(cv)

    def _commit(self, cv):
        if self.pts and len(self.pts) > 2:
            pts = list(self.pts)
            if self.o["lasso_type"] >= 2:
                pts += self._segment(pts[-1], pts[0])  # ook de sluitlijn snapt
            pts = [QPointF(x, y) for x, y in ops.smooth_points([(q.x(), q.y()) for q in pts], self.o["lasso_smooth"])]
            path = QPainterPath()
            path.addPolygon(QPolygonF(pts))
            path.closeSubpath()
            commit_shape(cv.doc, path, self.mode, self.o["feather"], self.o["antialias"])
        self.pts = None
        self.preview = []
        self.G = None
        cv.update()

    def key(self, cv, ev):
        if ev.key() == Qt.Key.Key_Escape and self.pts:
            self.pts = None
            self.preview = []
            cv.update()
            return True
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.pts:
            self._commit(cv)
            return True
        if ev.key() == Qt.Key.Key_Backspace and self.pts and len(self.pts) > 1:
            self.pts.pop()
            cv.update()
            return True
        return False

    def overlay(self, cv, p):
        if not self.pts:
            return
        pts = list(self.pts) + list(self.preview)
        if len(pts) > 1:
            p.setTransform(cv.transform())
            path = QPainterPath()
            path.addPolygon(QPolygonF(pts))
            draw_dashed(p, path)
            p.resetTransform()

    def deactivate(self):
        self.pts = None
        self.preview = []


class WandTool(SelectionBase):
    cid, glyph = 0xd023, "✨"
    tip = "Klik voor selectie op basis van kleur, helderheid of dekking. Shift = selectie uitbreiden, Ctrl = verkleinen"

    def options(self):
        m = self.main
        return (combo(m, "sel_mode", "Modus:", self.MODES) + combo(m, "match_mode", "Overeenkomstmodus:", ops.MATCH_MODES)
                + spin(m, "tolerance", "Tolerantie:", 0, 200) + check(m, "sample_merged", "Alle lagen gebruiken")
                + check(m, "contiguous", "Aaneengesloten") + spin(m, "feather", "Doezelen:", 0, 200)
                + check(m, "antialias", "Anti-alias") + combo(m, "aa_where", "", ["Buiten", "Binnen"]))

    def press(self, cv, pt, ev):
        if self.try_move(cv, pt, ev):
            return
        d = cv.doc
        x, y = ipt(pt)
        if ev.button() != LB or not d.rect().contains(x, y):
            return
        src = cv.cache if self.o["sample_merged"] else d.layer().image
        mask = ops.region_mask2(ops.qimage_to_rgba(src), x, y, self.o["tolerance"], self.o["contiguous"], self.o["match_mode"])
        m8 = (ops.antialias_mask(mask, ["outside", "inside"][self.o["aa_where"]]) if self.o["antialias"]
              else mask.astype(np.uint8) * 255)
        d.push_undo("Toverstaf")
        d.combine_selection(ops.mask_to_qimage(m8), sel_mode_from(ev, self.o["sel_mode"]), self.o["feather"])

    def move(self, cv, pt, ev):
        self.move_drag(cv, pt, ev)

    def release(self, cv, pt, ev):
        self.end_drag()


# ================================================================ penselen
class StrokeTool(Tool):
    """Basis voor alle penselen: stempels op gelijke afstand langs de muisbeweging."""
    wants_cursor_overlay = True
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, main):
        super().__init__(main)
        self.active = False
        self.last_pt = None

    def brush_options(self, opacity=True, blend=False):
        m = self.main
        w = (combo(m, "brush_shape", "Vorm:", ["Rond", "Vierkant"]) + spin(m, "size", "Grootte:", 1, 999)
             + spin(m, "hardness", "Hardheid:", 0, 100) + spin(m, "step", "Stap:", 1, 200)
             + spin(m, "density", "Dichtheid:", 1, 100) + spin(m, "thickness", "Dikte:", 1, 100)
             + spin(m, "rotation", "Rotatie:", 0, 359))
        if opacity:
            w += spin(m, "opacity", "Dekking:", 1, 100)
        if blend:
            w += combo(m, "blend", "Mengmodus:", [b[0] for b in TOOL_BLEND_MODES])
        return w

    def options(self):
        return self.brush_options()

    # -- stempel
    def make_stamp(self, color=QColor(255, 255, 255)):
        o = self.o
        size = o["size"]
        s = int(math.ceil(size)) + 2
        img = new_image(s, s)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(s / 2, s / 2)
        p.rotate(o["rotation"])
        p.scale(1, o["thickness"] / 100)
        r = size / 2
        hard = o["hardness"] / 100
        p.setPen(Qt.PenStyle.NoPen)
        if o["brush_shape"] == 1:
            p.fillRect(QRectF(-r, -r, size, size), color)
        elif hard >= 0.99 or size <= 2:
            p.setBrush(color)
            p.drawEllipse(QPointF(0, 0), max(r, 0.5), max(r, 0.5))
        else:
            g = QRadialGradient(QPointF(0, 0), r)
            c1 = QColor(color)
            c1.setAlpha(0)
            g.setColorAt(0, color)
            g.setColorAt(hard, color)
            g.setColorAt(1, c1)
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(0, 0), r, r)
        p.end()
        self.stamp = img
        self.stamp_size = s
        self.weights = ops.qimage_to_rgba(img)[..., 3].astype(np.float32) / 255

    def stamp_rect(self, c):
        s = self.stamp_size
        return QRect(int(round(c.x() - s / 2)), int(round(c.y() - s / 2)), s, s)

    def dab_weights(self, rect, full):
        """Gewichten (0..1) voor het deel van de stempel dat binnen het beeld valt."""
        w = self.weights[rect.y() - full.y(): rect.y() - full.y() + rect.height(),
                         rect.x() - full.x(): rect.x() - full.x() + rect.width()]
        if self.o["density"] < 100:
            w = w * (np.random.rand(*w.shape) < self.o["density"] / 100)
        return w

    # -- verloop van een streek
    def press(self, cv, pt, ev):
        if ev.button() not in (LB, RB):
            return
        self.right = ev.button() == RB
        self.cv = cv
        cv.doc.push_undo(self.name)
        self.active = True
        self.dirty = QRect()
        self.begin(cv, pt)
        start = self.last_pt if (ev.modifiers() & SHIFT and self.last_pt is not None) else pt
        self.prev = start
        self.carry = 0.0
        self.dab(cv, start)
        if start is not pt:
            self.line(cv, start, pt)
        self.flush(cv)

    def move(self, cv, pt, ev):
        if self.active and ev.buttons() & (LB | RB):
            self.line(cv, self.prev, pt)
            self.flush(cv)

    def release(self, cv, pt, ev):
        if not self.active:
            return
        self.active = False
        self.last_pt = self.prev
        self.end(cv)
        cv.doc.structureChanged.emit()

    def line(self, cv, a, b):
        spacing = max(0.5, self.o["size"] * self.o["step"] / 100)
        dx, dy = b.x() - a.x(), b.y() - a.y()
        dist = math.hypot(dx, dy)
        t = spacing - self.carry
        while t <= dist:
            self.dab(cv, QPointF(a.x() + dx * t / dist, a.y() + dy * t / dist))
            t += spacing
        self.carry = dist - (t - spacing)
        self.prev = b

    def flush(self, cv):
        if not self.dirty.isEmpty():
            cv.doc.changed.emit(self.dirty)
            self.dirty = QRect()

    def begin(self, cv, pt): pass
    def dab(self, cv, c): pass
    def end(self, cv): pass

    def overlay(self, cv, p):
        if cv.mouse_doc is None:
            return
        c = cv.to_widget(cv.mouse_doc)
        r = self.o["size"] * cv.zoom / 2
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.save()
        p.translate(c)
        p.rotate(self.o["rotation"])
        p.scale(1, self.o["thickness"] / 100)
        for col, rr in ((QColor(0, 0, 0, 160), r + 0.5), (QColor(255, 255, 255, 160), r - 0.5)):
            p.setPen(QPen(col, 0))
            if self.o["brush_shape"] == 1:
                p.drawRect(QRectF(-rr, -rr, 2 * rr, 2 * rr))
            else:
                p.drawEllipse(QPointF(0, 0), rr, rr)
        p.restore()


class PaintBrushTool(StrokeTool):
    cid, glyph = 0xd091, "🖌"
    tip = "Schilder met de voorgrondkleur (rechts: achtergrondkleur). Shift+klik: rechte lijn vanaf vorige punt"
    erase = False

    def options(self):
        return self.brush_options(blend=not self.erase)

    def begin(self, cv, pt):
        d = cv.doc
        color = QColor(self.main.bg if self.right else self.main.fg)
        self.make_stamp(color)
        self.base = QImage(d.layer().image)
        self.stroke = new_image(d.w, d.h)

    def dab(self, cv, c):
        full = self.stamp_rect(c)
        r = full.intersected(cv.doc.rect())
        if r.isEmpty():
            return
        p = QPainter(self.stroke)
        if self.o["density"] < 100:
            st = self.stamp.copy(r.translated(-full.x(), -full.y()))
            m = (np.random.rand(r.height(), r.width()) < self.o["density"] / 100).astype(np.uint8) * 255
            q = QPainter(st)
            q.setCompositionMode(CM.CompositionMode_DestinationIn)
            q.drawImage(0, 0, ops.mask_to_qimage(m))
            q.end()
            p.drawImage(r.topLeft(), st)
        else:
            p.drawImage(full.topLeft(), self.stamp)
        p.end()
        self.compose(cv, r)

    def compose(self, cv, r):
        d = cv.doc
        local = self.base.copy(r)
        if self.erase:
            p = QPainter(local)
            p.setCompositionMode(CM.CompositionMode_DestinationOut)
            p.setOpacity(self.o["opacity"] / 100)
            p.drawImage(QPointF(0, 0), self.stroke, QRectF(r))
            p.end()
        else:
            blend_onto(local, self.stroke, self.o["blend"], self.o["opacity"] / 100, r, r.topLeft())
        paint_layer(d.layer(), r, local, d.sel)
        self.dirty = self.dirty.united(r)

    def end(self, cv):
        self.base = self.stroke = None


class AirbrushTool(PaintBrushTool):
    cid, glyph = 0xd092, "💨"
    tip = "Spuit verf: hoe langer je op één plek blijft, hoe meer verf. Rechts: achtergrondkleur"

    def options(self):
        return self.brush_options(blend=True) + spin(self.main, "rate", "Snelheid:", 0, 50)

    def begin(self, cv, pt):
        color = QColor(self.main.bg if self.right else self.main.fg)
        self.make_stamp(color)
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        if self.o["rate"] > 0:
            self.timer.start(max(15, 600 // self.o["rate"]))

    def _tick(self):
        if self.active:
            self.dab(self.cv, self.prev)
            self.flush(self.cv)

    def dab(self, cv, c):
        d = cv.doc
        full = self.stamp_rect(c)
        r = full.intersected(d.rect())
        if r.isEmpty():
            return
        local = d.layer().image.copy(r)
        src = new_image(r.width(), r.height())
        p = QPainter(src)
        p.drawImage(QPointF(full.x() - r.x(), full.y() - r.y()), self.stamp)
        p.end()
        blend_onto(local, src, self.o["blend"], self.o["opacity"] / 100 * 0.35, None, r.topLeft())
        paint_layer(d.layer(), r, local, d.sel)
        self.dirty = self.dirty.united(r)

    def end(self, cv):
        self.timer.stop()


class EraserTool(PaintBrushTool):
    cid, glyph = 0xd0b0, "⌫"
    tip = "Wis pixels naar transparant"
    erase = True


# ---------------------------------------------------------------- pixelpenselen
class PixelBrush(StrokeTool):
    """Penseel dat per stempel pixels bewerkt met NumPy (retoucheren, klonen, wissers)."""
    keep_alpha = True

    def options(self):
        return self.brush_options()

    def begin(self, cv, pt):
        self.make_stamp()

    def dab(self, cv, c):
        d = cv.doc
        full = self.stamp_rect(c)
        r = full.intersected(d.rect())
        if r.isEmpty():
            return
        w = self.dab_weights(r, full) * (self.o["opacity"] / 100)
        if not w.any():
            return
        layer = d.layer()
        arr = ops.qimage_to_rgba(layer.image.copy(r))
        new = self.op(arr.astype(np.float32), r, full, c)
        if new is None:
            return
        out = arr + (new - arr) * w[..., None]
        if self.keep_alpha:
            out[..., 3] = arr[..., 3]
        paint_layer(layer, r, ops.rgba_to_qimage(np.clip(np.rint(out), 0, 255)), d.sel)
        self.dirty = self.dirty.united(r)

    def op(self, arr, r, full, c):
        return None


def _hsl_op(arr, fn):
    h, s, l = ops.rgb_to_hsl(arr[..., :3])
    h, s, l = fn(h, s, l)
    out = arr.copy()
    out[..., :3] = ops.hsl_to_rgb(h, np.clip(s, 0, 1), np.clip(l, 0, 1))
    return out


class LightenDarkenTool(PixelBrush):
    cid, glyph = 0xd0a1, "◐"
    tip = "Slepen: lichter maken, rechts slepen: donkerder maken"

    def op(self, a, *_):
        k = -0.08 if self.right else 0.08
        return _hsl_op(a, lambda h, s, l: (h, s, l + k))


class DodgeTool(PixelBrush):
    cid, glyph = 0xd0a2, "◯"
    tip = "Tegenhouden: lichtere details naar voren halen. Rechts: doordrukken"

    def op(self, a, *_):
        g = 1.12 if self.right else 0.88
        out = a.copy()
        out[..., :3] = 255 * (a[..., :3] / 255) ** g
        return out


class BurnTool(DodgeTool):
    cid, glyph = 0xd0a3, "●"
    tip = "Doordrukken: gebieden donkerder maken. Rechts: tegenhouden"

    def op(self, a, *_):
        self.right = not self.right
        try:
            return super().op(a)
        finally:
            self.right = not self.right


class SmudgeTool(PixelBrush):
    cid, glyph = 0xd0a4, "☝"
    tip = "Uitsmeren: neemt kleuren mee terwijl je sleept. Rechts: verspreiden zonder nieuwe kleur op te nemen"
    pickup = True

    def begin(self, cv, pt):
        super().begin(cv, pt)
        self.load = None

    def op(self, a, r, full, c):
        pick = self.pickup != self.right
        if self.load is None or self.load.shape != a.shape:
            self.load = a.copy()
            return None
        out = self.load.copy()
        if pick:
            self.load = self.load * 0.5 + a * 0.5
        return out

    def dab(self, cv, c):
        super().dab(cv, c)
        if self.load is not None and self.pickup != self.right:
            # neem de nieuwe pixels op voor de volgende stempel
            r = self.stamp_rect(c).intersected(cv.doc.rect())
            cur = ops.qimage_to_rgba(cv.doc.layer().image.copy(r)).astype(np.float32)
            if cur.shape == self.load.shape:
                self.load = self.load * 0.6 + cur * 0.4


class PushTool(SmudgeTool):
    cid, glyph = 0xd0a5, "👉"
    tip = "Verspreiden: duwt pixels zonder nieuwe kleuren op te nemen. Rechts: uitsmeren"
    pickup = False


class SoftenTool(PixelBrush):
    cid, glyph = 0xd0a6, "◌"
    tip = "Verzachten bij slepen, rechts slepen: verscherpen"
    sharpen = False

    def op(self, a, *_):
        blur = ops.box_blur(a, 1, passes=1)
        if self.sharpen != self.right:
            out = a + (a - blur) * 1.0
            out[..., 3] = a[..., 3]
            return np.clip(out, 0, 255)
        return blur


class SharpenTool(SoftenTool):
    cid, glyph = 0xd0a7, "◉"
    tip = "Verscherpen bij slepen, rechts slepen: verzachten"
    sharpen = True


class EmbossTool(PixelBrush):
    cid, glyph = 0xd0a8, "▦"
    tip = "Bosseleren: reliëfeffect waar je sleept"

    def op(self, a, *_):
        return ops.adj_emboss(a).astype(np.float32)


class SaturationTool(PixelBrush):
    cid, glyph = 0xd0a9, "🌈"
    tip = "Slepen: kleuren levendiger, rechts slepen: minder levendig"

    def op(self, a, *_):
        k = -0.1 if self.right else 0.1
        return _hsl_op(a, lambda h, s, l: (h, s + k, l))


class HueTool(PixelBrush):
    cid, glyph = 0xd0aa, "🎨"
    tip = "Slepen: kleurtoon omhoog, rechts slepen: kleurtoon omlaag"

    def op(self, a, *_):
        k = -0.02 if self.right else 0.02
        return _hsl_op(a, lambda h, s, l: (h + k, s, l))


class ChangeToTargetTool(PixelBrush):
    cid, glyph = 0xd0ab, "🎯"
    tip = "Naar doel overgaan: kleurt pixels naar de voorgrondkleur met behoud van detail (rechts: achtergrondkleur)"

    def options(self):
        return self.brush_options() + combo(self.main, "target_mode", "Modus:", ["Kleur", "Kleurtoon", "Verzadiging", "Lichtheid"])

    def op(self, a, *_):
        t = self.main.bg if self.right else self.main.fg
        th, ts, tl = t.hslHueF(), t.hslSaturationF(), t.lightnessF()
        th = max(th, 0)
        mode = self.o["target_mode"]
        k = 0.15

        def fn(h, s, l):
            if mode in (0, 1):
                dh = ((th - h + 0.5) % 1) - 0.5
                h = h + dh * k
            if mode in (0, 2):
                s = s + (ts - s) * k
            if mode == 3:
                l = l + (tl - l) * k
            return h, s, l
        return _hsl_op(a, fn)


class ColorReplacerTool(PixelBrush):
    cid, glyph = 0xd0ac, "🔁"
    tip = "Vervangt de achtergrondkleur door de voorgrondkleur waar je sleept (rechts: andersom)"

    def options(self):
        return self.brush_options() + spin(self.main, "tolerance", "Tolerantie:", 0, 200)

    def op(self, a, *_):
        src, dst = (self.main.fg, self.main.bg) if self.right else (self.main.bg, self.main.fg)
        s = np.array([src.red(), src.green(), src.blue()], np.float32)
        diff = np.abs(a[..., :3] - s).max(axis=-1)
        m = diff <= self.o["tolerance"] * 1.275
        out = a.copy()
        out[m, 0], out[m, 1], out[m, 2] = dst.red(), dst.green(), dst.blue()
        return out


class BackgroundEraserTool(PixelBrush):
    cid, glyph = 0xd0c0, "🧽"
    tip = "Wist alleen pixels die lijken op de kleur onder het midden van het penseel"
    keep_alpha = False

    def options(self):
        return (self.brush_options() + spin(self.main, "tolerance", "Tolerantie:", 0, 200)
                + combo(self.main, "bg_sampling", "Bemonstering:", ["Doorlopend", "Eenmaal"]))

    def begin(self, cv, pt):
        super().begin(cv, pt)
        self.sample = None

    def op(self, a, r, full, c):
        x, y = ipt(c)
        if not cv_contains(r, x, y):
            return None
        if self.sample is None or self.o["bg_sampling"] == 0:
            self.sample = a[y - r.y(), x - r.x(), :3].copy()
        diff = np.abs(a[..., :3] - self.sample).max(axis=-1)
        tol = max(1.0, self.o["tolerance"] * 1.275)
        sim = np.clip(1 - (diff - tol * 0.6) / (tol * 0.4 + 1e-6), 0, 1)
        out = a.copy()
        out[..., 3] = a[..., 3] * (1 - sim)
        return out


def cv_contains(r, x, y):
    return r.x() <= x < r.x() + r.width() and r.y() <= y < r.y() + r.height()


class CloneTool(PixelBrush):
    cid, glyph = 0xd081, "⎘"
    tip = "Rechtsklik: bron kiezen. Daarna slepen om de bron over te schilderen"
    keep_alpha = False

    def __init__(self, main):
        super().__init__(main)
        self.source = None
        self.offset = None

    def options(self):
        return (self.brush_options() + check(self.main, "clone_aligned", "Uitgelijnde modus")
                + check(self.main, "sample_merged", "Alle lagen gebruiken"))

    def press(self, cv, pt, ev):
        if ev.button() == RB:
            self.source = QPointF(pt)
            self.offset = None
            self.main.statusBar().showMessage("Kloonbron ingesteld.", 2500)
            cv.update()
            return
        if self.source is None:
            self.main.statusBar().showMessage("Kies eerst een bron met de rechtermuisknop.", 4000)
            return
        if self.offset is None or not self.o["clone_aligned"]:
            self.offset = QPointF(self.source.x() - pt.x(), self.source.y() - pt.y())
        super().press(cv, pt, ev)

    def begin(self, cv, pt):
        super().begin(cv, pt)
        self.right = False
        self.src_img = QImage(cv.cache if self.o["sample_merged"] else cv.doc.layer().image)

    def op(self, a, r, full, c):
        sr = r.translated(round(self.offset.x()), round(self.offset.y()))
        src = ops.qimage_to_rgba(self.src_img.copy(sr)).astype(np.float32)
        return src

    def overlay(self, cv, p):
        super().overlay(cv, p)
        if self.source is not None and cv.mouse_doc is not None:
            src = self.source
            if self.offset is not None and self.active:
                src = QPointF(cv.mouse_doc.x() + self.offset.x(), cv.mouse_doc.y() + self.offset.y())
            c = cv.to_widget(src)
            p.setPen(QPen(QColor(255, 255, 255), 1))
            p.drawLine(c + QPointF(-6, 0), c + QPointF(6, 0))
            p.drawLine(c + QPointF(0, -6), c + QPointF(0, 6))
            p.setPen(QPen(QColor(0, 0, 0), 1, Qt.PenStyle.DotLine))
            p.drawEllipse(c, 4, 4)


# ================================================================ vullen
class FillTool(Tool):
    cid, glyph = 0xd0d1, "🪣"
    tip = "Klik: vullen met voorgrondkleur, rechtsklik: met achtergrondkleur"

    def options(self):
        m = self.main
        # zelfde volgorde als PSP: Overeenkomstmodus, Tolerantie, Alle lagen gebruiken, Mengmodus, Dekking
        return (combo(m, "match_mode", "Overeenkomstmodus:", ops.MATCH_MODES)
                + spin(m, "tolerance", "Tolerantie:", 0, 200) + check(m, "sample_merged", "Alle lagen gebruiken")
                + combo(m, "blend", "Mengmodus:", [b[0] for b in TOOL_BLEND_MODES])
                + spin(m, "opacity", "Dekking:", 1, 100))

    contiguous_opt = False  # PSP vlakvulling vult altijd aaneengesloten

    def region(self, cv, pt):
        d = cv.doc
        x, y = ipt(pt)
        if not d.rect().contains(x, y):
            return None, None
        if d.sel is not None and d.sel.pixelColor(x, y).alpha() == 0:
            return None, None
        src = cv.cache if self.o["sample_merged"] else d.layer().image
        mask = ops.region_mask2(ops.qimage_to_rgba(src), x, y, self.o["tolerance"],
                                self.o["contiguous"] if self.contiguous_opt else True, self.o["match_mode"])
        m8 = mask.astype(np.uint8) * 255
        if d.sel is not None:
            m8 = np.minimum(m8, ops.qimage_to_mask(d.sel))
        r = ops.mask_bbox(m8 > 0)
        return (None, None) if r.isEmpty() else (m8, r)

    def press(self, cv, pt, ev):
        m8, r = self.region(cv, pt)
        if m8 is None:
            return
        d = cv.doc
        layer = d.layer()
        color = QColor(self.main.fg if ev.button() == LB else self.main.bg)
        local = layer.image.copy(r)
        fill = new_image(r.width(), r.height(), color)
        blend_onto(local, fill, self.o["blend"], self.o["opacity"] / 100, None, r.topLeft())
        d.push_undo("Vlakvulling")
        paint_layer(layer, r, local, ops.mask_to_qimage(m8))
        d.changed.emit(r)
        d.structureChanged.emit()


class ColorChangerTool(FillTool):
    cid, glyph = 0xd0d2, "🖍"
    tip = "Klik op een kleur om die te veranderen in de voorgrondkleur met behoud van schaduw (rechts: achtergrondkleur)"

    def options(self):
        m = self.main
        return (spin(m, "tolerance", "Tolerantie:", 0, 200) + check(m, "contiguous", "Aaneengesloten")
                + spin(m, "opacity", "Dekking:", 1, 100))

    contiguous_opt = True

    def press(self, cv, pt, ev):
        save = self.o["sample_merged"]
        self.o["sample_merged"] = False
        try:
            m8, r = self.region(cv, pt)
        finally:
            self.o["sample_merged"] = save
        if m8 is None:
            return
        d = cv.doc
        layer = d.layer()
        t = self.main.fg if ev.button() == LB else self.main.bg
        a = ops.qimage_to_rgba(layer.image.copy(r)).astype(np.float32)
        x, y = ipt(pt)
        ref = a[y - r.y(), x - r.x(), :3]
        _, _, l0 = ops.rgb_to_hsl(ref[None, None, :])
        th, ts, tl = max(0, t.hslHueF()), t.hslSaturationF(), t.lightnessF()
        h, s, l = ops.rgb_to_hsl(a[..., :3])
        l2 = np.clip(l + (tl - float(l0[0, 0])), 0, 1)
        out = a.copy()
        out[..., :3] = ops.hsl_to_rgb(np.full_like(l, th), np.full_like(l, ts), l2)
        res = a + (out - a) * (self.o["opacity"] / 100)
        res[..., 3] = a[..., 3]
        d.push_undo("Kleurwisselaar")
        paint_layer(layer, r, ops.rgba_to_qimage(np.clip(res, 0, 255)), ops.mask_to_qimage(m8))
        d.changed.emit(r)
        d.structureChanged.emit()


# ================================================================ foto
class RedEyeTool(Tool):
    cid, glyph = 0xd060, "👁"
    tip = "Klik op een rood oog om het te corrigeren"
    wants_cursor_overlay = True

    def options(self):
        return spin(self.main, "size", "Grootte:", 2, 500) + spin(self.main, "redeye_strength", "Sterkte:", 1, 100)

    def press(self, cv, pt, ev):
        d = cv.doc
        rad = self.o["size"] / 2
        r = QRectF(pt.x() - rad, pt.y() - rad, 2 * rad, 2 * rad).toAlignedRect().intersected(d.rect())
        if r.isEmpty():
            return
        layer = d.layer()
        a = ops.qimage_to_rgba(layer.image.copy(r)).astype(np.float32)
        yy, xx = np.mgrid[r.y():r.y() + r.height(), r.x():r.x() + r.width()]
        dist = np.hypot(xx + 0.5 - pt.x(), yy + 0.5 - pt.y()) / max(rad, 1)
        circle = np.clip((1 - dist) * 4, 0, 1)
        R, G, B = a[..., 0], a[..., 1], a[..., 2]
        redness = np.clip((R - np.maximum(G, B)) / (R + 1) * 2.5, 0, 1)
        k = circle * redness * self.o["redeye_strength"] / 100
        newR = (G + B) / 2 * 0.8
        out = a.copy()
        out[..., 0] = R + (newR - R) * k
        out[..., 1] = G * (1 - 0.2 * k)
        out[..., 2] = B * (1 - 0.2 * k)
        d.push_undo("Rode ogen")
        paint_layer(layer, r, ops.rgba_to_qimage(np.clip(out, 0, 255)), d.sel)
        d.changed.emit(r)
        d.structureChanged.emit()

    def overlay(self, cv, p):
        if cv.mouse_doc is not None:
            c = cv.to_widget(cv.mouse_doc)
            r = self.o["size"] * cv.zoom / 2
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 200), 0, Qt.PenStyle.DashLine))
            p.drawEllipse(c, r, r)


class StraightenTool(Tool):
    context_menu = True
    edits_pixels = False
    cid, glyph = 0xd051, "📐"
    tip = "Sleep een lijn langs een rand die recht moet staan. Dubbelklik, Enter of Toepassen om recht te zetten"

    def __init__(self, main):
        super().__init__(main)
        self.a = self.b = None
        self.drag = None

    def options(self):
        return (combo(self.main, "straighten_mode", "Modus:", ["Automatisch", "Horizontaal maken", "Verticaal maken"])
                + check(self.main, "straighten_crop", "Afbeelding bijsnijden")
                + button("Toepassen", lambda: self.apply(self.main.canvas())))

    def press(self, cv, pt, ev):
        if ev.button() != LB:
            return
        tol = 8 / cv.zoom
        for name in ("a", "b"):
            q = getattr(self, name)
            if q is not None and math.hypot(q.x() - pt.x(), q.y() - pt.y()) < tol:
                self.drag = name
                return
        self.a, self.b, self.drag = pt, pt, "b"

    def move(self, cv, pt, ev):
        if self.drag and ev.buttons() & LB:
            setattr(self, self.drag, pt)
            cv.update()

    def release(self, cv, pt, ev):
        self.drag = None

    def double_click(self, cv, pt, ev):
        self.apply(cv)

    def angle(self):
        dx, dy = self.b.x() - self.a.x(), self.b.y() - self.a.y()
        ang = math.degrees(math.atan2(dy, dx))
        mode = self.o["straighten_mode"]
        if mode == 0:
            mode = 1 if abs(dx) >= abs(dy) else 2
        if mode == 1:
            target = 0 if abs(ang) <= 90 else math.copysign(180, ang)
        else:
            target = math.copysign(90, ang)
        return target - ang

    def context_actions(self, cv):
        return [("Rechttrekken toepassen", lambda: self.apply(cv))] if self.a is not None else []

    def hover_cursor(self, cv, pt):
        for q in (self.a, self.b):
            if q is not None and math.hypot(q.x() - pt.x(), q.y() - pt.y()) < 8 / cv.zoom:
                return Qt.CursorShape.SizeAllCursor
        return None

    def apply(self, cv):
        if cv is None or self.a is None or self.a == self.b:
            return
        ang = self.angle()
        if abs(ang) > 0.01:
            cv.doc.rotate_free(ang, self.o["straighten_crop"], self.main.bg)
        self.a = self.b = None
        cv.update()

    def key(self, cv, ev):
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.apply(cv)
            return True
        if ev.key() == Qt.Key.Key_Escape:
            self.a = self.b = None
            cv.update()
            return True
        return False

    def overlay(self, cv, p):
        if self.a is None:
            return
        a, b = cv.to_widget(self.a), cv.to_widget(self.b)
        p.setPen(QPen(QColor(0, 0, 0), 3))
        p.drawLine(a, b)
        p.setPen(QPen(QColor(255, 255, 0), 1))
        p.drawLine(a, b)
        p.setBrush(QColor(255, 255, 255))
        p.setPen(QPen(QColor(0, 0, 0), 1))
        for q in (a, b):
            p.drawRect(QRectF(q.x() - 4, q.y() - 4, 8, 8))


class CropTool(Tool):
    context_menu = True
    edits_pixels = False
    cid, glyph = 0xd040, "⛶"
    tip = "Sleep een rechthoek; dubbelklik, Enter of Toepassen om bij te snijden. Esc annuleert"

    def __init__(self, main):
        super().__init__(main)
        self.r = None
        self.a = None

    def options(self):
        return button("Toepassen", lambda: self.apply(self.main.canvas())) + button("Wissen", self.clear)

    def context_actions(self, cv):
        if self.r is None:
            return []
        return [("Bijsnijden toepassen", lambda: self.apply(cv)), ("Bijsnijrechthoek wissen", self.clear)]

    def clear(self):
        self.r = None
        cv = self.main.canvas()
        if cv:
            cv.update()

    def press(self, cv, pt, ev):
        if ev.button() == LB:
            self.a = QPointF(round(pt.x()), round(pt.y()))
            self.r = None

    def move(self, cv, pt, ev):
        if self.a is not None and ev.buttons() & LB:
            b = QPointF(round(pt.x()), round(pt.y()))
            self.r = QRectF(self.a, b).normalized().toRect().intersected(cv.doc.rect())
            cv.update()
            self.main.statusBar().showMessage(f"Bijsnijden: {self.r.width()} × {self.r.height()} px")

    def release(self, cv, pt, ev):
        self.a = None

    def double_click(self, cv, pt, ev):
        self.apply(cv)

    def apply(self, cv):
        if cv is None or self.r is None or self.r.width() < 1 or self.r.height() < 1:
            return
        cv.doc.crop(self.r)
        self.r = None

    def key(self, cv, ev):
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.apply(cv)
            return True
        if ev.key() == Qt.Key.Key_Escape:
            self.clear()
            return True
        return False

    def overlay(self, cv, p):
        if self.r is None:
            return
        full = QRectF(cv.to_widget(QPointF(0, 0)), cv.to_widget(QPointF(cv.doc.w, cv.doc.h)))
        inner = QRectF(cv.to_widget(QPointF(self.r.topLeft())),
                       cv.to_widget(QPointF(self.r.x() + self.r.width(), self.r.y() + self.r.height())))
        path = QPainterPath()
        path.addRect(full)
        path.addRect(inner)
        p.fillPath(path, QColor(0, 0, 0, 120))
        rp = QPainterPath()
        rp.addRect(inner)
        draw_dashed(p, rp)

    def deactivate(self):
        self.r = None


# ================================================================ vormen
class ShapeBase(Tool):
    """Teken een vorm op de actieve laag. Rand: voorgrondkleur, vulling: achtergrondkleur (zoals PSP)."""
    tip = "Sleep om te tekenen. Rand: voorgrondkleur, vulling: achtergrondkleur. Shift: gelijke zijden"
    from_center = False

    def __init__(self, main):
        super().__init__(main)
        self.a = None

    def common(self):
        m = self.main
        return spin(m, "line_width", "Lijnbreedte:", 0, 200) + check(m, "antialias", "Anti-alias")

    def options(self):
        return self.common()

    def press(self, cv, pt, ev):
        if ev.button() != LB:
            return
        d = cv.doc
        d.push_undo(self.name)
        self.a = pt
        self.base = QImage(d.layer().image)
        self.prev_rect = QRect()

    def constrain(self, b, ev):
        if ev.modifiers() & SHIFT:
            s = max(abs(b.x() - self.a.x()), abs(b.y() - self.a.y()))
            return QPointF(self.a.x() + math.copysign(s, b.x() - self.a.x()), self.a.y() + math.copysign(s, b.y() - self.a.y()))
        return b

    def path(self, a, b):
        return QPainterPath()

    def move(self, cv, pt, ev):
        if self.a is None or not (ev.buttons() & LB):
            return
        b = self.constrain(pt, ev)
        path = self.path(self.a, b)
        d = cv.doc
        lw = self.o["line_width"]
        bound = path.boundingRect().adjusted(-lw - 2, -lw - 2, lw + 2, lw + 2).toAlignedRect()
        r = bound.united(self.prev_rect).intersected(d.rect())
        self.prev_rect = bound
        if r.isEmpty():
            return
        local = self.base.copy(r)
        p = QPainter(local)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, self.o["antialias"])
        p.translate(-r.x(), -r.y())
        if (not self.main.fg_none or not self.fillable) and lw > 0:
            pen = QPen(self.main.fg, lw)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            p.setPen(pen)
        else:
            p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.main.bg if not self.main.bg_none and self.fillable else Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()
        paint_layer(d.layer(), r, local, d.sel)
        d.changed.emit(r)

    fillable = True

    def release(self, cv, pt, ev):
        if self.a is None:
            return
        if self.prev_rect.isEmpty():
            cv.doc.drop_last_undo()
        self.a = None
        self.base = None
        cv.doc.structureChanged.emit()


class RectangleTool(ShapeBase):
    cid, glyph = 0xd102, "▭"

    def options(self):
        return spin(self.main, "radius", "Hoekradius:", 0, 500) + self.common()

    def path(self, a, b):
        p = QPainterPath()
        r = QRectF(a, b).normalized()
        rad = self.o["radius"]
        p.addRoundedRect(r, rad, rad) if rad else p.addRect(r)
        return p


class EllipseTool(ShapeBase):
    cid, glyph = 0xd103, "⬭"

    def path(self, a, b):
        p = QPainterPath()
        p.addEllipse(QRectF(a, b).normalized())
        return p


class SymmetricShapeTool(ShapeBase):
    cid, glyph = 0xd104, "✶"
    tip = "Sleep vanuit het midden. Rand: voorgrondkleur, vulling: achtergrondkleur"

    def options(self):
        m = self.main
        return (spin(m, "sym_sides", "Aantal zijden:", 3, 100) + check(m, "sym_star", "Ster")
                + spin(m, "sym_inner", "Straal binnen:", 1, 99) + self.common())

    def constrain(self, b, ev):
        return b

    def path(self, a, b):
        R = math.hypot(b.x() - a.x(), b.y() - a.y())
        rot = math.atan2(b.y() - a.y(), b.x() - a.x())
        n = self.o["sym_sides"]
        if self.o["sym_star"]:
            return star_path(a.x(), a.y(), R, R, n, self.o["sym_inner"] / 100, rot)
        p = QPainterPath()
        p.addPolygon(QPolygonF([QPointF(a.x() + R * math.cos(rot + i * 2 * math.pi / n),
                                        a.y() + R * math.sin(rot + i * 2 * math.pi / n)) for i in range(n)]))
        p.closeSubpath()
        return p


class PresetShapeTool(ShapeBase):
    cid, glyph = 0xd101, "💬"
    SHAPES = ["Pijl rechts", "Pijl links", "Pijl omhoog", "Pijl omlaag", "Ster", "Hart", "Tekstballon",
              "Gedachtewolk", "Bliksem", "Kruis", "Zeshoek", "Starburst"]

    def options(self):
        return combo(self.main, "preset", "Vorm:", self.SHAPES) + self.common()

    def path(self, a, b):
        r = QRectF(a, b).normalized()
        x, y, w, h = r.x(), r.y(), r.width(), r.height()

        def poly(pts):
            p = QPainterPath()
            p.addPolygon(QPolygonF([QPointF(x + px * w, y + py * h) for px, py in pts]))
            p.closeSubpath()
            return p
        k = self.o["preset"]
        arrow = [(0, .3), (.6, .3), (.6, 0), (1, .5), (.6, 1), (.6, .7), (0, .7)]
        if k == 0:
            return poly(arrow)
        if k == 1:
            return poly([(1 - px, py) for px, py in arrow])
        if k == 2:
            return poly([(py, 1 - px) for px, py in arrow])
        if k == 3:
            return poly([(py, px) for px, py in arrow])
        if k == 4:
            return star_path(r.center().x(), r.center().y(), w / 2, h / 2, 5, 0.4)
        if k == 5:
            p = QPainterPath(QPointF(x + w / 2, y + h))
            p.cubicTo(x - w * 0.1, y + h * 0.55, x + w * 0.05, y - h * 0.15, x + w / 2, y + h * 0.25)
            p.cubicTo(x + w * 0.95, y - h * 0.15, x + w * 1.1, y + h * 0.55, x + w / 2, y + h)
            return p
        if k == 6:
            p = QPainterPath()
            p.addRoundedRect(QRectF(x, y, w, h * 0.75), w * 0.12, h * 0.12)
            t = QPainterPath()
            t.addPolygon(QPolygonF([QPointF(x + w * .2, y + h * .7), QPointF(x + w * .4, y + h * .7), QPointF(x + w * .15, y + h)]))
            return p.united(t)
        if k == 7:
            p = QPainterPath()
            for cx, cy, rr in [(.3, .4, .22), (.5, .3, .25), (.7, .4, .22), (.5, .55, .25), (.35, .55, .18), (.65, .55, .18)]:
                p.addEllipse(QPointF(x + cx * w, y + cy * h * 0.85), rr * w, rr * h * 0.8)
            p = p.simplified()
            for cx, cy, rr in [(.2, .88, .06), (.1, .97, .035)]:
                p.addEllipse(QPointF(x + cx * w, y + cy * h), rr * w, rr * h)
            return p
        if k == 8:
            return poly([(.55, 0), (.15, .55), (.45, .55), (.3, 1), (.85, .4), (.55, .4), (.75, 0)])
        if k == 9:
            return poly([(.35, 0), (.65, 0), (.65, .35), (1, .35), (1, .65), (.65, .65), (.65, 1), (.35, 1),
                         (.35, .65), (0, .65), (0, .35), (.35, .35)])
        if k == 10:
            return poly([(.25, 0), (.75, 0), (1, .5), (.75, 1), (.25, 1), (0, .5)])
        return star_path(r.center().x(), r.center().y(), w / 2, h / 2, 16, 0.7)


class PenTool(ShapeBase):
    cid, glyph = 0xd110, "✒"
    tip = "Teken lijnen in de voorgrondkleur. Shift: hoeken in stappen van 45°"
    fillable = False

    def options(self):
        m = self.main
        return (combo(m, "pen_mode", "Modus:", ["Lijn", "Uit de vrije hand"])
                + spin(m, "line_width", "Breedte:", 1, 200) + check(m, "antialias", "Anti-alias"))

    def press(self, cv, pt, ev):
        super().press(cv, pt, ev)
        self.pts = [pt]

    def constrain(self, b, ev):
        if ev.modifiers() & SHIFT:
            ang = round(math.atan2(b.y() - self.a.y(), b.x() - self.a.x()) / (math.pi / 4)) * math.pi / 4
            ln = math.hypot(b.x() - self.a.x(), b.y() - self.a.y())
            return QPointF(self.a.x() + ln * math.cos(ang), self.a.y() + ln * math.sin(ang))
        return b

    def path(self, a, b):
        p = QPainterPath(a)
        if self.o["pen_mode"] == 1:
            self.pts.append(b)
            for q in self.pts[1:]:
                p.lineTo(q)
        else:
            p.lineTo(b)
        return p



# ================================================================ tekst
class TextTool(Tool):
    context_menu = True
    cid, glyph = 0xd0f0, "A"
    tip = ("Klik om tekst te maken, of klik op bestaande tekst om die te bewerken. "
           "Vulling: achtergrondkleur, rand: voorgrondkleur (zoals PSP)")
    cursor = Qt.CursorShape.IBeamCursor
    edits_pixels = False  # werkt zelf met tekstlagen

    def __init__(self, main):
        super().__init__(main)
        self.dlg = None
        self.layer = None

    def options(self):
        m = self.main
        f = QFontComboBox()
        f.setCurrentFont(QFont(m.opts["font"]))
        f.currentFontChanged.connect(lambda font: (m.opts.__setitem__("font", font.family()), self.refresh()))
        out = [QLabel("Lettertype:"), f]
        for part in (spin(m, "font_size", "Grootte:", 1, 2000), combo(m, "text_units", "Eenheden:", ["Punten", "Pixels"]),
                     check(m, "bold", "Vet"), check(m, "italic", "Cursief"), check(m, "underline", "Onderstreept"),
                     combo(m, "text_align", "Uitlijning:", ["Links", "Midden", "Rechts"]),
                     spin(m, "text_stroke", "Lijnbreedte:", 0, 100), spin(m, "leading", "Regelafstand:", -100, 300),
                     spin(m, "tracking", "Spatiëring:", -50, 200), check(m, "antialias", "Anti-alias")):
            for w in part:
                for sig in ("valueChanged", "toggled", "currentIndexChanged"):
                    if hasattr(w, sig):
                        getattr(w, sig).connect(lambda *_: self.refresh())
                        break
            out += part
        return out

    def hit(self, d, pt):
        """Bovenste zichtbare tekstlaag onder de muis (de actieve laag krijgt voorrang)."""
        from .textlayer import bounds
        cands = [d.layer()] + list(reversed(d.layers))
        for l in cands:
            if l.text is not None and l.visible:
                r = bounds(l.text, d.px_per_pt).adjusted(-4, -4, 4, 4)
                if r.contains(pt):
                    return l
        return None

    def hover_cursor(self, cv, pt):
        return Qt.CursorShape.IBeamCursor

    def _load_opts(self, t):
        o = self.o
        first = t["runs"][0][0] if t.get("runs") else t
        o["font"] = first.get("family", o["font"])
        o["font_size"] = max(1, round(first.get("size", o["font_size"])))
        o["text_units"] = 0 if first.get("units", "pt") == "pt" else 1
        o["bold"] = first.get("bold", first.get("weight", 400) >= 600)
        o["italic"] = first.get("italic", False)
        o["underline"] = first.get("underline", False)
        o["text_align"] = t.get("align", 0)
        o["text_stroke"] = int(round(t.get("stroke_width", 1))) if t.get("stroke") or (t.get("runs") and t["runs"][0][1]) else 0
        o["leading"] = int(t.get("leading", 0))
        o["tracking"] = int(first.get("tracking", 0))
        o["antialias"] = t.get("antialias", True)
        fill = t.get("fill") if not t.get("runs") else t["runs"][0][2]
        stroke = t.get("stroke") if not t.get("runs") else t["runs"][0][1]
        if fill is not None:
            self.main.bg = QColor(*fill)
        if stroke is not None:
            self.main.fg = QColor(*stroke)
        self.main.bg_none = fill is None
        self.main.fg_none = False  # geen rand = lijnbreedte 0 in de optiebalk
        self.main.materials.refresh()

    def press(self, cv, pt, ev):
        if ev.button() != LB or self.dlg is not None:
            return
        from .dialogs import TextEntryDialog
        from .textlayer import copy_text, new_text
        d = cv.doc
        self.cv = cv
        target = self.hit(d, pt)
        if target is not None:  # bestaande tekst bewerken
            d.active = d.layers.index(target)
            self.layer, self.new = target, False
            self.orig = copy_text(target.text)
            self._load_opts(target.text)
            self.main.select_tool(self)  # optiebalk met de waarden van deze tekst
            d.push_undo("Tekst bewerken")
            text = target.text["text"]
            self.anchor = (target.text["x"], target.text["y"])
        else:
            self.anchor = (pt.x(), pt.y())
            layer = Layer("Tekst", new_image(d.w, d.h))
            layer.text = new_text("", pt.x(), pt.y(), self.o, self.main.fg, self.main.bg,
                                  self.main.fg_none, self.main.bg_none)
            d.add_layer(layer, label="Tekst")
            self.layer, self.new = layer, True
            self.orig = None
            remember = self.main.settings.value("remember_text") == "true"
            text = self.main.settings.value("last_text", "") if remember else ""
        d.structureChanged.emit()
        self.dlg = TextEntryDialog(self.main, text)
        self.dlg.textChanged.connect(self.refresh)
        self.dlg.finished.connect(self._done)
        self.dlg.show()
        self.refresh()

    def refresh(self):
        if self.dlg is None or self.layer is None:
            return
        from .textlayer import new_text
        d = self.cv.doc
        old = self.layer.text
        t = new_text(self.dlg.text(), self.anchor[0], self.anchor[1], self.o, self.main.fg, self.main.bg,
                     self.main.fg_none, self.main.bg_none)
        if old is not None:
            t["matrix"] = old.get("matrix", t["matrix"])
        self.layer.text = t
        d.render_text(self.layer)
        d.changed.emit(QRect())
        self.cv.update()

    def overlay(self, cv, p):
        if self.dlg is None or self.layer is None or self.layer.text is None:
            return
        from .textlayer import bounds
        r = bounds(self.layer.text, cv.doc.px_per_pt)
        if r.isNull():
            return
        path = QPainterPath()
        path.addRect(QRectF(cv.to_widget(r.topLeft()), cv.to_widget(r.bottomRight())))
        draw_dashed(p, path)

    def deactivate(self):
        if self.dlg is not None:
            self.dlg.accept()

    def _done(self, result):
        d = self.cv.doc
        text = self.dlg.text()
        self.main.settings.setValue("remember_text", "true" if self.dlg.remember() else "false")
        if self.dlg.remember():
            self.main.settings.setValue("last_text", text)
        self.dlg = None
        layer, self.layer = self.layer, None
        if result and text.strip():
            layer.name = text.strip().split("\n")[0][:30]
            d.structureChanged.emit()
        elif self.new:  # niets ingevoerd: nieuwe laag weer weghalen
            d.undo()
            d.redo_stack.clear()
            d.historyChanged.emit()
        else:  # bewerken geannuleerd: oude tekst terug
            layer.text = self.orig
            d.render_text(layer)
            d.drop_last_undo()
            d.changed.emit(QRect())
            d.structureChanged.emit()
        self.cv.update()


# ================================================================ register
IMPLEMENTED = [PanTool, ZoomTool, PickTool, MoveTool, SelectTool, LassoTool, WandTool, DropperTool,
               CropTool, StraightenTool, RedEyeTool, CloneTool, PaintBrushTool, AirbrushTool,
               LightenDarkenTool, DodgeTool, BurnTool, SmudgeTool, PushTool, SoftenTool, SharpenTool,
               EmbossTool, SaturationTool, HueTool, ChangeToTargetTool, ColorReplacerTool, EraserTool,
               BackgroundEraserTool, FillTool, ColorChangerTool, TextTool, PresetShapeTool, RectangleTool,
               EllipseTool, SymmetricShapeTool, PenTool]

PLACEHOLDER_GLYPHS = {0xd052: "⏢", 0xd070: "💄", 0xd082: "〰", 0xd083: "⌧", 0xd0e0: "🌸",
                      0xd121: "🌀", 0xd122: "▦", 0xd131: "🖌", 0xd132: "✎", 0xd133: "✎", 0xd134: "✎",
                      0xd135: "✏", 0xd136: "🖊", 0xd137: "🔪", 0xd138: "☝", 0xd139: "⌫"}


def create_tools(main):
    tools = {cls.cid: cls(main) for cls in IMPLEMENTED}
    for cid, glyph in PLACEHOLDER_GLYPHS.items():
        tools[cid] = PlaceholderTool(main, cid, glyph)
    return tools
