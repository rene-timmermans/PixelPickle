"""Gereedschappen, ingedeeld zoals de PSP XI gereedschapsbalk (zie psplayout.py)."""
import collections.abc
import math
import random

import numpy as np
from PySide6.QtCore import QLineF, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen,
                           QPolygonF, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFontComboBox, QInputDialog, QLabel,
                               QPushButton, QSpinBox, QToolButton, QWidget)

from . import imageops as ops
from .document import BG_NAMES, CM, TOOL_BLEND_MODES, Layer, apply_region, blend_onto, new_image, paint_layer
from .i18n import tr
from .psplayout import TOOL_NAMES

LB = Qt.MouseButton.LeftButton
RB = Qt.MouseButton.RightButton
SHIFT = Qt.KeyboardModifier.ShiftModifier
CTRL = Qt.KeyboardModifier.ControlModifier

DEFAULT_OPTS = dict(
    size=25, hardness=100, step=10, density=100, thickness=100, rotation=0, brush_shape=0,
    opacity=100, blend=0, rate=10, tolerance=20, contiguous=True, sample_merged=False,
    cc_tolerance=40, cc_softness=30, cc_contiguous=False,
    sel_shape=0, sel_mode=0, feather=0, antialias=True, lasso_type=0, line_width=3,
    shape_fill=True, shape_stroke=True, radius=0, sym_sides=5, sym_star=True, sym_inner=50,
    preset=0, pen_vector=True, shape_vector=True, pen_mode=1, pen_tracking=10, pen_connect=True, pen_nodes=True, pen_style=0, pen_join=0,
    pen_miter=15, font="Sans Serif", font_size=48, bold=False, italic=False,
    sample_size=0, clone_aligned=True, bg_sampling=0, straighten_mode=0, straighten_crop=False, persp_grid=5, persp_crop=False, scratch_width=10, scratch_ends=0, warp_mode=0, warp_strength=50, warp_edge=0,
    mesh_cols=6, mesh_rows=6, continuous=False,
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


class _SpinSlider(QWidget):
    """De strook onderaan een SliderSpinBox: tekent de balk en zet de waarde bij klikken en slepen.
    Ligt bovenop het tekstvak, zodat de muis altijd bij de balk aankomt."""
    BAR = 3

    def __init__(self, box):
        super().__init__(box)
        self.box = box
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self._sliding = False

    def _track(self):
        return QRect(0, self.height() - self.BAR, self.width(), self.BAR)

    def paintEvent(self, e):
        b = self._track()
        p = QPainter(self)
        pal = self.box.palette()
        groove = QColor(pal.mid().color())
        groove.setAlpha(110)
        p.fillRect(b, groove)
        fill = QColor(pal.highlight().color())
        if not self.box.isEnabled():
            fill.setAlpha(90)
        n = round(b.width() * self.box.fraction())
        rtl = self.box.layoutDirection() == Qt.LayoutDirection.RightToLeft
        p.fillRect(QRect(b.right() - n + 1 if rtl else b.left(), b.top(), n, b.height()), fill)
        p.end()

    def _set(self, x):
        if self.box.layoutDirection() == Qt.LayoutDirection.RightToLeft:
            x = self.width() - 1 - x
        self.box.set_fraction(max(0.0, min(1.0, x / max(1, self.width() - 1))))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.box.isEnabled():
            self._sliding = True
            self._set(e.position().x())

    def mouseMoveEvent(self, e):
        if self._sliding:
            self._set(e.position().x())

    def mouseReleaseEvent(self, e):
        self._sliding = False


class SliderSpinBox(QSpinBox):
    """Invoerveld met een dunne schuifbalk aan de onderkant: de balk toont de waarde binnen het bereik,
    en klikken of slepen op die strook zet de waarde meteen (handig voor grote veranderingen). Bij grote
    bereiken (zoals grootte 1 tot 999) loopt de balk kwadratisch, zodat kleine waarden ook goed te kiezen
    zijn. De balk valt binnen de rand van het veld, dus de hoogte blijft gelijk."""
    GRAB = 6  # hoogte van de strook onderaan

    def __init__(self, *a):
        super().__init__(*a)
        self.slider = _SpinSlider(self)
        self.valueChanged.connect(self.slider.update)

    def _curve(self):
        return 2.0 if self.maximum() - self.minimum() > 300 else 1.0

    def fraction(self):
        span = self.maximum() - self.minimum()
        t = (self.value() - self.minimum()) / span if span else 0
        return max(0.0, min(1.0, t)) ** (1 / self._curve())

    def set_fraction(self, t):
        self.setValue(round(self.minimum() + (self.maximum() - self.minimum()) * t ** self._curve()))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        from PySide6.QtWidgets import QStyle, QStyleOptionSpinBox
        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)
        up = self.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, opt, QStyle.SubControl.SC_SpinBoxUp, self)
        right = up.left() - 1 if up.isValid() and up.left() > self.width() // 2 else self.width() - 3
        if self.layoutDirection() == Qt.LayoutDirection.RightToLeft and up.isValid() and up.right() < self.width() // 2:
            left, right = up.right() + 2, self.width() - 3
        else:
            left = 3
        self.slider.setGeometry(left, self.height() - self.GRAB - 2, max(4, right - left), self.GRAB)
        self.slider.raise_()


def spin(main, key, label, lo, hi, suffix=""):
    _rec(key)
    w = SliderSpinBox()
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


_CURSORS = {}


def tool_cursor(glyph):
    """Cursor zoals in PSP: draadkruis (het midden is het klikpunt) met het gereedschapsicoon rechtsonder."""
    if glyph in _CURSORS:
        return _CURSORS[glyph]
    from PySide6.QtGui import QCursor, QPixmap
    # 1. het icoon apart tekenen: zwart lijnicoon in dezelfde stijl als de werkbalk (icons.py);
    #    alleen zonder tekening het teken zelf
    from . import icons
    icon = QImage(20, 20, QImage.Format.Format_ARGB32_Premultiplied)
    icon.fill(Qt.GlobalColor.transparent)
    q = QPainter(icon)
    if glyph in icons.ICONS:
        q.drawPixmap(1, 1, icons.render(glyph, 18, QColor(0, 0, 0)))
    else:
        f = QFont()
        f.setPixelSize(15)
        q.setFont(f)
        q.setPen(QColor(0, 0, 0))
        q.drawText(QRectF(0, 0, 20, 20), Qt.AlignmentFlag.AlignCenter, glyph)
    q.end()
    # 2. wit silhouet van het icoon, voor een rand die op elke ondergrond zichtbaar is
    halo = QImage(icon)
    q = QPainter(halo)
    q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    q.fillRect(halo.rect(), QColor(255, 255, 255))
    q.end()
    pm = QPixmap(34, 34)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    c = 8
    for col, w in ((QColor(255, 255, 255), 3), (QColor(0, 0, 0), 1)):
        p.setPen(QPen(col, w))
        p.drawLine(c, 0, c, c - 3)
        p.drawLine(c, c + 3, c, 2 * c)
        p.drawLine(0, c, c - 3, c)
        p.drawLine(c + 3, c, 2 * c, c)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        p.drawImage(13 + dx, 13 + dy, halo)
    p.drawImage(13, 13, icon)
    p.end()
    _CURSORS[glyph] = QCursor(pm, c, c)
    return _CURSORS[glyph]


class Tool:
    edits_pixels = True  # False voor gereedschappen die geen pixels van de laag wijzigen
    cid = 0
    glyph = "?"
    tip = ""

    @property
    def cursor(self):
        # standaard: draadkruis + eigen icoon; gereedschappen met een vaste Qt-cursor overschrijven dit
        return tool_cursor(self.glyph)
    is_pan = False
    wants_cursor_overlay = False
    available = True

    def __init__(self, main):
        self.main = main

    @property
    def name(self):
        from .i18n import tr
        return tr(TOOL_NAMES.get(self.cid, "?"))

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

    # Automatisch scrollen bij de rand tijdens slepen (uit voor gereedschappen waar dat hindert)
    autoscroll = False  # meeschuiven bij de rand: alleen waar het nodig is (puntsgewijs selecteren)

    # Rechtsklik zonder slepen opent het snelmenu bij gereedschappen die de rechterknop niet zelf gebruiken
    context_menu = False

    def wants_context_menu(self, cv):
        return self.context_menu

    def context_actions(self, cv):
        """Extra opdrachten bovenaan het snelmenu: [(tekst, functie)]."""
        return []

    def right_click(self, cv, pt):
        """Rechtsklik zonder slepen; True = afgehandeld (dan geen snelmenu)."""
        return False


class PlaceholderTool(Tool):
    available = False
    tip = "Dit gereedschap volgt in een volgende versie van PixelPickle."

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
        from .vectorlayer import copy_vector
        self.text_base = {id(l): copy_text(l.text) for l, _ in self.linked if l.text is not None}
        self.vector_base = {id(l): copy_vector(l.vector) for l, _ in self.linked if l.vector is not None}
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
            if d.active == 0 and d.layer().name in BG_NAMES:  # gat vullen met achtergrondkleur, zoals PSP
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
                if id(layer) in self.vector_base:  # vectoren blijven vectoren
                    from . import vectorlayer
                    v = vectorlayer.copy_vector(self.vector_base[id(layer)])
                    vectorlayer.transform(v, QTransform.fromTranslate(dx, dy))
                    layer.vector = v
                    d.render_vector(layer)
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
            # het verschoven kader is al bekend: niet opnieuw uit het masker berekenen (scheelt veel tijd
            # bij grote foto's, vooral bij pijltoetsen die snel achter elkaar komen)
            d.set_selection(d.sel, d.sel_lines)
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
    snaps = True  # punten uitlijnen op raster en hulplijnen (als dat aan staat)
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

    def _vector(self, d):
        return d.layer().vector is not None

    def _bbox(self, d):
        if self._vector(d):  # vectorlaag: het kader om de gekozen objecten
            from . import vectorlayer as V
            sel = d.vsel
            r = V.bounds([d.layer().vector[i] for i in sel]) if sel else QRectF()
            return r if not r.isEmpty() else None
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
        if self.box is None:
            return QPolygonF()
        return self.T.map(QPolygonF(self.box))

    _stale = True

    def _handles(self, cv):
        poly = self._poly(cv)
        if poly.size() < 4:
            return None
        pts = [poly[0], poly[1], poly[2], poly[3]]
        mids = [(pts[i] + pts[(i + 1) % 4]) / 2 for i in range(4)]
        center = (pts[0] + pts[2]) / 2
        right = mids[1]
        rot = right + (right - center) * 0.25
        return pts, mids, center, rot

    def _hit(self, cv, pt):
        h = self._handles(cv)
        if h is None:
            return None
        pts, mids, center, rot = h
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

    def _obj_at(self, d, pt, tol):
        from . import vectorlayer as V
        objs = d.layer().vector or []
        for i in range(len(objs) - 1, -1, -1):  # bovenste eerst
            if V.hit(objs[i], pt, tol):
                return i
        return None

    def hover_cursor(self, cv, pt):
        hit = self._hit(cv, pt)
        if hit is None and self._vector(cv.doc) and self._obj_at(cv.doc, pt, 4 / cv.zoom) is not None:
            return Qt.CursorShape.PointingHandCursor
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
        if self._vector(d):
            from . import vectorops as VO
            handle = self._hit(cv, pt)
            if handle is None or handle[0] == "move":
                i = self._obj_at(d, pt, 4 / cv.zoom)
                sel = d.vsel
                if i is None and handle is None:  # leeg vlak: kader slepen om objecten te kiezen
                    if not ev.modifiers() & SHIFT:
                        d.vsel = []
                    self.rubber = (QPointF(pt), QPointF(pt))
                    self.drag = ("rubber", None)
                    cv.update()
                    return
                if i is not None:
                    if ev.modifiers() & SHIFT:  # erbij of eraf
                        grp = VO.expand_groups(d.layer().vector, [i])
                        sel = [k for k in sel if k not in grp] if i in sel else sel + [k for k in grp if k not in sel]
                        d.vsel = sel
                        self._stale = True
                        cv.update()
                        return
                    if i not in sel:
                        d.vsel = VO.expand_groups(d.layer().vector, [i])
                self._stale = True
            if not d.vsel:
                cv.update()
                return
        h = self._handles(cv)
        if h is None:
            return
        pts, mids, center, rot = h
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
        from .vectorlayer import copy_vector
        self.text_base = copy_text(d.layer().text)
        self.vector_base = copy_vector(d.layer().vector)
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
        if kind == "rubber":
            self.rubber = (self.rubber[0], QPointF(pt))
            cv.update()
            return
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
        if getattr(self, "vector_base", None) is not None:  # vectorlaag: alleen de gekozen objecten
            from . import vectorlayer as V
            objs = V.copy_vector(self.vector_base)
            V.transform([objs[k] for k in d.vsel], T)
            d.layer().vector = objs
            d.render_vector(d.layer())
            self.changed_any = True
            d.changed.emit(QRect())
            return
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
        if self.drag[0] == "rubber":
            from . import vectorlayer as V, vectorops as VO
            r = QRectF(*self.rubber).normalized()
            d = cv.doc
            objs = d.layer().vector or []
            got = [k for k, o in enumerate(objs) if r.intersects(V.qpath(o).boundingRect())]
            d.vsel = VO.expand_groups(objs, d.vsel + [k for k in got if k not in d.vsel])
            self.drag, self.rubber = None, None
            self._stale = True
            cv.update()
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
        if getattr(self, "rubber", None):
            path = QPainterPath()
            path.addRect(QRectF(cv.to_widget(self.rubber[0]), cv.to_widget(self.rubber[1])).normalized())
            draw_dashed(p, path)
        h = self._handles(cv)
        if h is None:
            return
        pts, mids, center, rot = h
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

    # ---------------------------------------------------------------- vectorobjecten (snelmenu zoals PSP)
    clipboard = []  # gekopieerde vectorobjecten
    OBJECT_MENUS = [("&Uitlijnen", [0x8163, 0x815e, 0x8160, 0x815f, 0x8161, 0x8162, None, 0x8172, 0x816e, 0x8170]),
                    ("&Verdelen", [0x816c, 0x8164, 0x8166, 0x8165, 0x8168, 0x8167, 0x816f, 0x8171]),
                    ("Even groot &maken", [0x8169, 0x816a, 0x816b]),
                    ("Schi&kken", [0x8139, 0x813a, 0x813b, 0x813c])]

    def object_edit(self, name, cv):
        from . import vectorlayer as V
        d = cv.doc
        layer = d.layer()
        sel = d.vsel
        if name == "copy":
            PickTool.clipboard = V.copy_vector([layer.vector[i] for i in sel])
            return
        if name == "select_all":
            d.vsel = list(range(len(layer.vector)))
        elif name == "select_none":
            d.vsel = []
        elif name in ("cut", "delete"):
            if name == "cut":
                PickTool.clipboard = V.copy_vector([layer.vector[i] for i in sel])
            d.push_undo("Knippen" if name == "cut" else "Wissen")
            layer.vector = [o for i, o in enumerate(layer.vector) if i not in set(sel)]
            d.vsel = []
        elif name == "paste":
            if not PickTool.clipboard:
                return
            d.push_undo("Plakken")
            start = len(layer.vector)
            layer.vector.extend(V.copy_vector(PickTool.clipboard))
            d.vsel = list(range(start, len(layer.vector)))
        elif name == "rename":
            if len(sel) != 1:
                return
            obj = layer.vector[sel[0]]
            text, ok = QInputDialog.getText(self.main, tr("Naam wijzigen"), tr("Naam:"), text=obj.get("name", ""))
            if not ok:
                return
            d.push_undo("Naam wijzigen")
            if text.strip():
                obj["name"] = text.strip()
            else:
                obj.pop("name", None)
        elif name == "raster_selection":
            m = QImage(d.w, d.h, QImage.Format.Format_Alpha8)
            m.fill(QColor(0, 0, 0, 0))
            p = QPainter(m)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            for i in sel:
                o = layer.vector[i]
                path = V.qpath(o)
                if V.is_closed(o):
                    p.fillPath(path, QColor(0, 0, 0, 255))
                if o.get("stroke") is not None and o["width"] > 0:
                    p.strokePath(path, QPen(QColor(0, 0, 0, 255), o["width"]))
            p.end()
            d.push_undo("Rasterselectie maken")
            d.set_selection(m)
            return
        d.render_vector(layer)
        d.changed.emit(QRect())
        d.structureChanged.emit()
        self._stale = True
        cv.update()

    def build_context_menu(self, cv, m):
        """Snelmenu van vectorobjecten (zoals PSP), als er op een vectorlaag objecten gekozen zijn."""
        d = cv.doc
        if d.layer().vector is None or (not d.vsel and not PickTool.clipboard):
            return False
        n = len(d.vsel)
        run = lambda name: (lambda: self.main._run(lambda: self.object_edit(name, cv)))  # noqa: E731

        def add(text, name, ok=True):
            a = m.addAction(tr(text), run(name))
            a.setEnabled(bool(ok))
        add("Knippen", "cut", n)
        add("Kopiëren", "copy", n)
        add("Plakken", "paste", PickTool.clipboard)
        add("Wissen", "delete", n)
        m.addSeparator()
        add("Alles selecteren", "select_all", d.layer().vector)
        add("Niets selecteren", "select_none", n)
        m.addSeparator()
        add("Naam wijzigen...", "rename", n == 1)
        acts = self.main.actions_by_id
        if 0x81e6 in acts:
            m.addAction(acts[0x81e6])
        m.addSeparator()
        # dezelfde submenu's en opdrachten als het hoofdmenu Objecten (zelfde woorden en vertalingen)
        def submenu(title, ids):
            sub = m.addMenu(tr(title))
            for cid in ids:
                if cid is None:
                    sub.addSeparator()
                elif cid in acts:
                    sub.addAction(acts[cid])
        for title, ids in self.OBJECT_MENUS:
            submenu(title, ids)
        for cid in (0x8154, 0x8156, None, 0x813d, 0x1793):
            if cid is None:
                m.addSeparator()
            elif cid in acts:
                m.addAction(acts[cid])
        submenu("Tekst omzetten in &curven", [0x814c, 0x814d])
        m.addSeparator()
        add("Rasterselectie maken", "raster_selection", n)
        return True


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
    rechts slepen verplaatst alleen het kader."""
    MODES = ["Vervangen", "Toevoegen", "Verwijderen"]

    def __init__(self, main):
        super().__init__(main)
        self.mover = None

    def common_options(self):
        return (combo(self.main, "sel_mode", "Modus:", self.MODES)
                + spin(self.main, "feather", "Doezelen:", 0, 200)
                + check(self.main, "antialias", "Anti-alias"))

    def _replace_mode(self, mods):
        """Alleen in de modus Vervangen (zonder Shift/Ctrl) verplaatst slepen binnen de selectie de
        pixels; bij Toevoegen en Verwijderen begint een klik binnen de selectie gewoon een nieuwe vorm."""
        return not mods & (SHIFT | CTRL) and self.o.get("sel_mode", 0) == 0

    def right_click(self, cv, pt):
        """Zoals PSP: met een selectiegereedschap heft een rechtsklik de selectie op."""
        if cv.doc.sel is None:
            return False
        self.main.run_command(0x80e2)  # Niets selecteren
        return True

    def try_move(self, cv, pt, ev):
        d = cv.doc
        x, y = ipt(pt)
        if (d.sel is not None and self._replace_mode(ev.modifiers()) and d.rect().contains(x, y)
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
            if self._replace_mode(QApplication.keyboardModifiers()):
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
    snaps = True  # punten uitlijnen op raster en hulplijnen (als dat aan staat)
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
    snaps = True  # punten uitlijnen op raster en hulplijnen (als dat aan staat)
    cid, glyph = 0xd022, "➰"
    TYPES = ["Uit de vrije hand", "Punt tot punt", "Slimme rand", "Rand zoeken"]
    TIPS = ["Klik en teken om te selecteren.",
            "Klik punten aan; dubbelklik of rechtsklik om te sluiten.",
            "Klik punten rond een object; de lijn volgt de sterkste rand binnen het bereik. Dubbelklik of rechtsklik om te sluiten.",
            "Klik punten rond een object; de lijn zoekt de rand op. Dubbelklik of rechtsklik om te sluiten."]

    @property
    def autoscroll(self):
        # bij punt tot punt (en slimme rand / rand zoeken) loopt de omtrek vaak buiten beeld door
        return self.o["lasso_type"] > 0

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

    def __init__(self, main):
        super().__init__(main)
        self.active = False
        self.last_pt = None

    def brush_options(self, opacity=True, blend=False):
        m = self.main
        from . import userdata
        w = (combo(m, "brush_shape", "Vorm:", ["Rond", "Vierkant"] + userdata.brush_names()) + spin(m, "size", "Grootte:", 1, 999)
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
        tip = self._custom_tip(o["brush_shape"])
        if tip is not None:  # eigen penseel: de penseelpunt geschaald naar de grootte (verhouding blijft)
            th, tw = tip.shape
            k = size / max(th, tw)
            g = np.ascontiguousarray(np.clip(tip * 255, 0, 255).astype(np.uint8))
            mask = QImage(g.data, tw, th, g.strides[0], QImage.Format.Format_Alpha8).copy()
            col = QImage(tw, th, QImage.Format.Format_ARGB32_Premultiplied)
            col.fill(color)
            q = QPainter(col)
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            q.drawImage(0, 0, mask)
            q.end()
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(QRectF(-tw * k / 2, -th * k / 2, tw * k, th * k), col)
        elif o["brush_shape"] == 1:
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

    def _custom_tip(self, index):
        """Penseelpunt van een eigen penseel (vorm 2 en verder), of None."""
        if index < 2:
            return None
        from . import userdata
        names = userdata.brush_names()
        if index - 2 >= len(names):
            return None
        cache = self.__dict__.setdefault("_tips", {})
        if names[index - 2] not in cache:
            cache[names[index - 2]] = userdata.load_brush(names[index - 2])
        return cache[names[index - 2]]

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
        self._stroke_size = cv.doc.layer().image.size()
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
        if not self.active:
            return
        if cv is not getattr(self, "cv", None) or cv.doc.layer().image.size() != self._stroke_size:
            # andere afbeelding of laag van ander formaat (bijv. na wisselen of ongedaan maken): streek stoppen
            self.active = False
            self.end(cv)
            return
        if ev.buttons() & (LB | RB):
            self.line(cv, self.prev, pt)
            self.flush(cv)

    def release(self, cv, pt, ev):
        if not self.active:
            return
        self.active = False
        self.last_pt = self.prev
        self.end(cv)
        (self.cv or cv).doc.structureChanged.emit()

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
        self.mat_img = None if self.erase else self.material_layer(cv)

    def _variance(self):
        """Penseelvariantie (palet): (schaal, dekking, rotatie, verschuiving x, y) voor deze stempel, of None."""
        m = self.main.opts
        vs, vo, vr, vp = (m.get(k, 0) for k in ("var_size", "var_opacity", "var_rotation", "var_spread"))
        if not (vs or vo or vr or vp):
            return None
        import random
        size = self.o["size"]
        return (max(0.05, 1 - random.random() * vs / 100), 1 - random.random() * vo / 100,
                (random.random() * 2 - 1) * 180 * vr / 100,
                (random.random() * 2 - 1) * size * vp / 100, (random.random() * 2 - 1) * size * vp / 100)

    def dab(self, cv, c):
        var = self._variance() if self.o["density"] >= 100 else None
        if var is not None:  # stempel met willekeurige afwijking
            sc, op, rot, dx, dy = var
            cc = QPointF(c.x() + dx, c.y() + dy)
            s = self.stamp_size
            reach = int(s * 0.75) + 2  # gedraaid kan de stempel iets verder reiken
            r = QRect(int(cc.x()) - reach, int(cc.y()) - reach, 2 * reach, 2 * reach).intersected(cv.doc.rect())
            if r.isEmpty():
                return
            p = QPainter(self.stroke)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.translate(cc)
            p.rotate(rot)
            p.scale(sc, sc)
            p.setOpacity(op)
            p.drawImage(QPointF(-s / 2, -s / 2), self.stamp)
            p.end()
            self.compose(cv, r)
            return
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
        elif self.mat_img is not None:
            blend_onto(local, self.colored(self.stroke.copy(r), r), self.o["blend"], self.o["opacity"] / 100,
                       None, r.topLeft())
        else:
            blend_onto(local, self.stroke, self.o["blend"], self.o["opacity"] / 100, r, r.topLeft())
        paint_layer(d.layer(), r, local, d.sel)
        self.dirty = self.dirty.united(r)

    def end(self, cv):
        self.base = self.stroke = self.mat_img = None

    mat_img = None

    def material_layer(self, cv):
        """Verloop/patroon voor deze streek, over de selectie of anders de hele afbeelding."""
        d = cv.doc
        fg = not self.right
        if self.main.material(fg) is None:
            return None
        span = d.selection_bbox() if d.sel is not None else d.rect()
        return self.main.material_image(fg, d.rect(), span)

    def colored(self, alpha_img, r):
        """Het materiaal op plek r, met de dekking van alpha_img (zelfde grootte als r)."""
        out = self.mat_img.copy(r)
        p = QPainter(out)
        p.setCompositionMode(CM.CompositionMode_DestinationIn)
        p.drawImage(0, 0, alpha_img)
        p.end()
        return out


# ---------------------------------------------------------------- verwringen
class _WarpBase:
    """Gedeeld door Penseel Verwringen en Maasvormig verwringen: de laag zoals hij was (bron) en een
    verschuivingsveld; uitkomst(x) = bron(x + veld(x)). Zolang niemand anders de laag verandert,
    blijft dat bewaard, zodat je verder kunt werken of (bij het penseel) kunt gladstrijken."""

    def _warp_state(self, d):
        layer = d.layer()
        key = (id(d), id(layer), layer.image.cacheKey(), d.w, d.h)
        if getattr(self, "_wkey", None) != key:
            self.src = ops.qimage_to_rgba(layer.image)
            self.fx = np.zeros((d.h, d.w), np.float32)
            self.fy = np.zeros((d.h, d.w), np.float32)
            self._wkey = key
            self.on_new_source(d)
        return layer

    def on_new_source(self, d):
        pass

    def _render(self, d, r):
        """Gebied r opnieuw opbouwen uit de bron met het veld."""
        from .effects.common import remap
        layer = d.layer()
        yy, xx = np.mgrid[r.y():r.bottom() + 1, r.x():r.right() + 1].astype(np.float32)
        mx = xx + self.fx[r.y():r.bottom() + 1, r.x():r.right() + 1]
        my = yy + self.fy[r.y():r.bottom() + 1, r.x():r.right() + 1]
        edge = ["clamp", "fill", "wrap", "mirror"][self.o.get("warp_edge", 0)]
        out = remap(self.src, mx, my, edge=edge)
        paint_layer(layer, r, ops.rgba_to_qimage(out), d.sel)
        self._wkey = (id(d), id(layer), layer.image.cacheKey(), d.w, d.h)


class WarpBrushTool(_WarpBase, StrokeTool):
    """Penseel Verwringen: pixels duwen, opblazen, laten krimpen, draaien of terugzetten."""
    cid, glyph = 0xd121, "warp"
    MODES = ["Duwen", "Uitzetten", "Samentrekken", "Rechtsom draaien", "Linksom draaien", "Ruis", "Gladstrijken"]

    @property
    def tip(self):
        from .i18n import tr
        return tr("Penseel Verwringen ({}): sleep over de afbeelding. Gladstrijken zet verwrongen pixels terug").format(
            tr(self.MODES[self.o["warp_mode"]]))

    def options(self):
        m = self.main
        return (combo(m, "warp_mode", "Modus:", self.MODES) + spin(m, "size", "Grootte:", 1, 999)
                + spin(m, "hardness", "Hardheid:", 0, 100) + spin(m, "warp_strength", "Sterkte:", 1, 100)
                + combo(m, "warp_edge", "Randmodus:", ["Herhalen", "Transparant", "Tegelen", "Spiegelen"]))

    def begin(self, cv, pt):
        self._warp_state(cv.doc)
        self.make_stamp()
        self.weights = self.warp_weights(self.stamp_size, self.o["size"] / 2, self.o["hardness"])
        self.last_dab = QPointF(pt)

    @staticmethod
    def warp_weights(n, radius, hardness):
        """Werking per pixel (0..1): altijd vloeiend aflopend naar de rand, ook bij hardheid 100.
        Een harde rand zou de verschuiving abrupt laten stoppen en scheuren in het beeld geven.
        Hardheid bepaalt alleen hoe groot het volle midden is (tot 60% van de straal)."""
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) + 0.5 - n / 2
        dist = np.hypot(xx, yy) / max(radius, 0.5)
        inner = 0.6 * hardness / 100
        t = np.clip((dist - inner) / max(1 - inner, 1e-3), 0, 1)
        return (0.5 + 0.5 * np.cos(t * np.pi)).astype(np.float32) * (dist < 1)

    def dab(self, cv, c):
        d = cv.doc
        full = self.stamp_rect(c)
        r = full.intersected(d.rect())
        if r.isEmpty():
            return
        w = self.weights[r.y() - full.y(): r.y() - full.y() + r.height(),
                         r.x() - full.x(): r.x() - full.x() + r.width()]
        s = self.o["warp_strength"] / 100
        mode = self.o["warp_mode"]
        ys, xs = slice(r.y(), r.bottom() + 1), slice(r.x(), r.right() + 1)
        yy, xx = np.mgrid[r.y():r.bottom() + 1, r.x():r.right() + 1].astype(np.float32)
        ox, oy = xx + 0.5 - c.x(), yy + 0.5 - c.y()
        k = w * s
        if mode == 6:  # gladstrijken: terug naar het origineel
            self.fx[ys, xs] *= 1 - k * 0.5
            self.fy[ys, xs] *= 1 - k * 0.5
        else:
            if mode == 0:  # duwen: inhoud volgt de beweging
                vx, vy = c.x() - self.last_dab.x(), c.y() - self.last_dab.y()
                dx, dy = -vx * k, -vy * k
            elif mode in (1, 2):  # uitzetten / samentrekken
                f = -0.12 if mode == 1 else 0.12
                dx, dy = ox * k * f, oy * k * f
            elif mode in (3, 4):  # draaien
                f = 0.08 if mode == 3 else -0.08
                dx, dy = -oy * k * f, ox * k * f
            else:  # ruis
                amp = self.o["size"] * 0.05
                dx = (np.random.rand(*k.shape).astype(np.float32) - 0.5) * k * amp
                dy = (np.random.rand(*k.shape).astype(np.float32) - 0.5) * k * amp
            # samenstellen: deze stempel werkt op het al verwrongen beeld, dus het oude veld wordt op de
            # verschoven plek gelezen. Optellen zou bij veel stempels het beeld laten omvouwen (strepen).
            ofx = self._sample(self.fx, xx + dx, yy + dy)
            ofy = self._sample(self.fy, xx + dx, yy + dy)
            self.fx[ys, xs] = dx + ofx
            self.fy[ys, xs] = dy + ofy
        self.last_dab = QPointF(c)
        self._render(d, r)
        self.dirty = self.dirty.united(r)


    @staticmethod
    def _sample(f, x, y):
        """Bilineair aflezen van een veld op (fractionele) posities, met de rand herhaald."""
        h, w = f.shape
        x = np.clip(x, 0, w - 1)
        y = np.clip(y, 0, h - 1)
        x0 = np.minimum(np.floor(x).astype(np.int64), w - 2) if w > 1 else np.zeros(x.shape, np.int64)
        y0 = np.minimum(np.floor(y).astype(np.int64), h - 2) if h > 1 else np.zeros(y.shape, np.int64)
        tx, ty = x - x0, y - y0
        x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
        top = f[y0, x0] * (1 - tx) + f[y0, x1] * tx
        bot = f[y1, x0] * (1 - tx) + f[y1, x1] * tx
        return (top * (1 - ty) + bot * ty).astype(np.float32)


class MeshWarpTool(_WarpBase, Tool):
    """Maasvormig verwringen: een raster over de afbeelding; versleep de knooppunten en de afbeelding
    buigt mee. Shift + slepen verschuift de hele rij, Ctrl + slepen de hele kolom."""
    cid, glyph = 0xd122, "mesh"
    edits_pixels = True
    context_menu = True
    tip = ("Versleep de knooppunten van het raster; de afbeelding buigt mee. Shift: hele rij, Ctrl: hele kolom. "
           "Herstellen zet het raster terug")

    def __init__(self, main):
        super().__init__(main)
        self.nodes = None
        self.drag = None

    def options(self):
        m = self.main
        return (spin(m, "mesh_cols", "Kolommen:", 1, 50) + spin(m, "mesh_rows", "Rijen:", 1, 50)
                + button("Herstellen", lambda: self.reset(m.canvas()))
                + button("Toepassen", lambda: self.finish(m.canvas())))

    def _grid0(self, d):
        cols, rows = self.o["mesh_cols"], self.o["mesh_rows"]
        xs = np.linspace(0, d.w, cols + 2)
        ys = np.linspace(0, d.h, rows + 2)
        return np.stack(np.meshgrid(xs, ys), axis=-1).astype(np.float32)  # (rijen+2, kolommen+2, 2)

    def on_new_source(self, d):
        self.base = self._grid0(d)
        self.nodes = self.base.copy()

    def _ensure(self, cv):
        d = cv.doc
        self._warp_state(d)
        if self.nodes is None or self.nodes.shape != self._grid0(d).shape:
            self.on_new_source(d)

    def reset(self, cv):
        if cv is None:
            return
        self._ensure(cv)
        if np.any(self.nodes != self.base):
            cv.doc.push_undo("Maasvormig verwringen")
            self.nodes = self.base.copy()
            self._apply_mesh(cv.doc)
        cv.update()

    def finish(self, cv):
        """Het huidige resultaat wordt het nieuwe beginpunt (nieuw, recht raster)."""
        if cv is None:
            return
        self._wkey = None
        self._ensure(cv)
        cv.update()

    def _hit(self, cv, pt):
        tol = 7 / cv.zoom
        d = np.hypot(self.nodes[..., 0] - pt.x(), self.nodes[..., 1] - pt.y())
        i, j = np.unravel_index(np.argmin(d), d.shape)
        return (i, j) if d[i, j] <= tol else None

    def press(self, cv, pt, ev):
        if ev.button() != LB:
            return
        self._ensure(cv)
        hit = self._hit(cv, pt)
        if hit is None:
            return
        cv.doc.push_undo("Maasvormig verwringen")
        self.drag = (hit, QPointF(pt), self.nodes.copy(), ev.modifiers())

    def move(self, cv, pt, ev):
        if not self.drag or not (ev.buttons() & LB):
            return
        (i, j), start, n0, mods = self.drag
        dx, dy = pt.x() - start.x(), pt.y() - start.y()
        self.nodes = n0.copy()
        if mods & SHIFT:
            self.nodes[i, :, 0] += dx
            self.nodes[i, :, 1] += dy
        elif mods & CTRL:
            self.nodes[:, j, 0] += dx
            self.nodes[:, j, 1] += dy
        else:
            self.nodes[i, j] += (dx, dy)
        cv.update()

    def release(self, cv, pt, ev):
        if not self.drag:
            return
        self.drag = None
        self._apply_mesh(cv.doc)
        cv.update()

    def _apply_mesh(self, d):
        """Elke rastercel van zijn oorspronkelijke rechthoek naar zijn nieuwe vierhoek tekenen."""
        from PySide6.QtGui import QPainterPath, QPolygonF
        src = ops.rgba_to_qimage(self.src)
        out = new_image(d.w, d.h)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        # elke cel in deelcellen; hun hoeken worden bilineair over de cel verdeeld, zodat punten langs
        # een gedeelde rand voor beide cellen op dezelfde plek liggen en lijnen vloeiend doorlopen
        S = 8
        b, n = self.base, self.nodes
        R, C = n.shape[:2]

        def bil(q, u, v):
            return (q[0] * (1 - u) + q[1] * u) * (1 - v) + (q[3] * (1 - u) + q[2] * u) * v

        for i in range(R - 1):
            for j in range(C - 1):
                c0 = [b[i, j], b[i, j + 1], b[i + 1, j + 1], b[i + 1, j]]
                c1 = [n[i, j], n[i, j + 1], n[i + 1, j + 1], n[i + 1, j]]
                if all(np.allclose(a_, b_) for a_, b_ in zip(c0, c1)):
                    r = QRectF(QPointF(*map(float, c0[0])), QPointF(*map(float, c0[2])))
                    p.drawImage(r, src, r)  # ongewijzigde cel: rechtstreeks
                    continue
                for si in range(S):
                    for sj in range(S):
                        uv = [(sj / S, si / S), ((sj + 1) / S, si / S), ((sj + 1) / S, (si + 1) / S), (sj / S, (si + 1) / S)]
                        q0 = QPolygonF([QPointF(*map(float, bil(c0, u, v))) for u, v in uv])
                        q1 = QPolygonF([QPointF(*map(float, bil(c1, u, v))) for u, v in uv])
                        t = QTransform()
                        if not QTransform.quadToQuad(q0, q1, t):
                            continue
                        clip = QPainterPath()
                        clip.addPolygon(q1)
                        clip.closeSubpath()
                        p.save()
                        p.setClipPath(clip)
                        p.setTransform(t)
                        r = q0.boundingRect().adjusted(-1, -1, 1, 1)
                        p.drawImage(r, src, r)
                        p.restore()
        p.end()
        layer = d.layer()
        paint_layer(layer, d.rect(), out, d.sel)
        self._wkey = (id(d), id(layer), layer.image.cacheKey(), d.w, d.h)
        d.changed.emit(d.rect())
        d.structureChanged.emit()

    def double_click(self, cv, pt, ev):
        pass

    def context_actions(self, cv):
        return [("Raster herstellen", lambda: self.reset(cv)), ("Raster toepassen", lambda: self.finish(cv))]

    def hover_cursor(self, cv, pt):
        if self.nodes is not None and self._hit(cv, pt) is not None:
            return Qt.CursorShape.SizeAllCursor
        return None

    def overlay(self, cv, p):
        self._ensure(cv)
        n = self.nodes
        R, C = n.shape[:2]
        tw = lambda i, j: cv.to_widget(QPointF(float(n[i, j, 0]), float(n[i, j, 1])))
        for col, wd in ((QColor(0, 0, 0, 160), 2.5), (QColor(255, 255, 255, 220), 1)):
            p.setPen(QPen(col, wd))
            for i in range(R):
                p.drawPolyline(QPolygonF([tw(i, j) for j in range(C)]))
            for j in range(C):
                p.drawPolyline(QPolygonF([tw(i, j) for i in range(R)]))
        p.setPen(QPen(QColor(0, 0, 0), 1))
        p.setBrush(QColor(255, 255, 255))
        for i in range(R):
            for j in range(C):
                q = tw(i, j)
                p.drawRect(QRectF(q.x() - 3, q.y() - 3, 6, 6))

    def key(self, cv, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.reset(cv)
            return True
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finish(cv)
            return True
        return False

    def deactivate(self):
        self.drag = None


# ---------------------------------------------------------------- kunstmedia
class _AliasOpts(collections.abc.MutableMapping):
    """De gewone gereedschapsopties, maar met eigen sleutels voor een paar waarden (bijvoorbeeld een
    eigen grootte per kunstmedium, zodat een potlood niet de grootte van het penseel overneemt) en
    vaste waarden die bij het medium horen."""

    def __init__(self, base, alias, fixed):
        self.base, self.alias, self.fixed = base, alias, fixed

    def __getitem__(self, k):
        if k in self.fixed:
            return self.fixed[k]
        return self.base[self.alias.get(k, k)]

    def __setitem__(self, k, v):
        if k not in self.fixed:
            self.base[self.alias.get(k, k)] = v

    def __delitem__(self, k):
        del self.base[self.alias.get(k, k)]

    def __iter__(self):
        return iter(self.base)

    def __len__(self):
        return len(self.base)


_GRAIN = {}


def paper_grain(kind, n=256):
    """Naadloze papierkorrel (0..1) voor krijt, pastel, kleurkrijt en kleurpotlood."""
    if kind not in _GRAIN:
        from .material import _fbm, _smooth_noise
        rng = np.random.default_rng({"chalk": 1, "pastel": 2, "crayon": 3, "pencil": 4}[kind])
        fine = rng.random((n, n)).astype(np.float32)
        if kind == "chalk":
            g = _fbm(n, 11) * 0.45 + _smooth_noise(n, 64, 12) * 0.35 + fine * 0.2
        elif kind == "pastel":
            g = _fbm(n, 21) * 0.6 + _smooth_noise(n, 48, 22) * 0.3 + fine * 0.1
        elif kind == "crayon":
            # wasachtig: grove korrel die een beetje in één richting is uitgerekt
            g = _smooth_noise(n, 32, 31) * 0.5 + np.roll(_smooth_noise(n, 96, 32), 1, axis=1) * 0.3 + fine * 0.2
        else:  # potlood: fijne korrel met schuine arcering
            yy, xx = np.mgrid[0:n, 0:n]
            hatch = (np.sin((xx + yy) * 2 * math.pi / 4) + 1) / 2
            g = _smooth_noise(n, 128, 41) * 0.45 + hatch.astype(np.float32) * 0.25 + fine * 0.3
        g = (g - g.min()) / max(float(g.max() - g.min()), 1e-6)
        _GRAIN[kind] = g.astype(np.float32)
    return _GRAIN[kind]


class ArtMediaTool(PaintBrushTool):
    """Basis voor de kunstmedia: tekent op een gewone laag met een eigen streek."""
    grain = None          # soort papierkorrel, of None
    threshold = 0.5       # waar de korrel begint pigment aan te nemen (0..1)
    softness = 0.2        # zachtheid van die overgang
    flow = 0.6            # dekking per stempel
    hardness = 60
    default_size = 20
    step = 15

    @property
    def o(self):
        k = f"am{self.cid:04x}"
        m = self.main.opts
        m.setdefault(k + "_size", self.default_size)
        m.setdefault(k + "_opacity", 100)
        m.setdefault(k + "_grain", 60)
        return _AliasOpts(m, {"size": k + "_size", "opacity": k + "_opacity", "grain": k + "_grain"},
                          {"hardness": self.hardness, "step": self.step, "density": 100, "brush_shape": 0,
                           "thickness": 100, "rotation": 0, "blend": self.blend_mode})

    blend_mode = 0  # index in TOOL_BLEND_MODES (Markering: vermenigvuldigen)

    def options(self):
        k = f"am{self.cid:04x}"
        self.o  # standaardwaarden zetten
        w = spin(self.main, k + "_size", "Grootte:", 1, 500) + spin(self.main, k + "_opacity", "Dekking:", 1, 100)
        if self.grain:
            w += spin(self.main, k + "_grain", "Korrel:", 0, 100)
        return w + self.extra_options()

    def extra_options(self):
        return []

    def begin(self, cv, pt):
        self.color = QColor(self.main.bg if self.right else self.main.fg)
        self.make_stamp(self.color)
        d = cv.doc
        self.base = QImage(d.layer().image)
        self.stroke = new_image(d.w, d.h)
        self.mat_img = None
        self.grain_map = paper_grain(self.grain) if self.grain else None

    def line(self, cv, a, b):
        if math.hypot(b.x() - a.x(), b.y() - a.y()) > 0:
            self.direction = math.degrees(math.atan2(b.y() - a.y(), b.x() - a.x()))
        super().line(cv, a, b)

    direction = 0.0

    def dab_color(self, cv, r):
        return self.color

    def dab_alpha(self, r, full):
        """Dekking (0..1) van deze stempel per pixel."""
        w = self.weights[r.y() - full.y(): r.y() - full.y() + r.height(),
                         r.x() - full.x(): r.x() - full.x() + r.width()] * self.flow
        if self.grain_map is not None:
            g = self.grain_map
            n = g.shape[0]
            ys = np.arange(r.y(), r.y() + r.height()) % n
            xs = np.arange(r.x(), r.x() + r.width()) % n
            gr = g[np.ix_(ys, xs)]
            amount = self.o["grain"] / 100
            th = self.threshold * amount
            k = np.clip((gr - th) / max(self.softness, 1e-3) + 0.5, 0, 1)
            w = w * (k * amount + (1 - amount))
        return w

    def dab(self, cv, c):
        full = self.stamp_rect(c)
        r = full.intersected(cv.doc.rect())
        if r.isEmpty():
            return
        a = self.dab_alpha(r, full)
        if not a.any():
            return
        col = self.dab_color(cv, r)
        if not isinstance(col, np.ndarray):
            col = np.array([col.red(), col.green(), col.blue()], np.float32)
        # binnen één streek telt de sterkste stempel (geen opstapeling), zodat de korrel zichtbaar
        # blijft; een nieuwe streek over dezelfde plek maakt het voller
        cur = ops.qimage_to_rgba(self.stroke.copy(r)).astype(np.float32)
        old = cur[..., 3] / 255
        new = np.maximum(old, a)
        take = (a > old)[..., None]
        mix = self.color_mix
        rgb = np.where(take, cur[..., :3] * (1 - mix) + col * mix if mix < 1 else col, cur[..., :3])
        rgb = np.where((old <= 0)[..., None], col, rgb)
        out = np.dstack([rgb, new * 255])
        p = QPainter(self.stroke)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.drawImage(r.topLeft(), ops.rgba_to_qimage(np.clip(np.rint(out), 0, 255)))
        p.end()
        self.compose(cv, r)

    color_mix = 1.0  # hoe sterk een nieuwe stempel de kleur in de streek overneemt


class ChalkTool(ArtMediaTool):
    cid, glyph = 0xd132, "chalk"
    tip = "Krijt: korrelige, droge streek; meer drukken (vaker overgaan) geeft meer dekking"
    grain, threshold, softness, flow, hardness, default_size, step = "chalk", 0.5, 0.1, 0.92, 45, 30, 12


class PastelTool(ArtMediaTool):
    cid, glyph = 0xd133, "pastel"
    tip = "Pastel: zachte, dekkende streek met een fijne korrel"
    grain, threshold, softness, flow, hardness, default_size, step = "pastel", 0.3, 0.25, 0.95, 35, 30, 10


class CrayonTool(ArtMediaTool):
    cid, glyph = 0xd134, "crayon_wax"
    tip = "Kleurkrijt: wasachtige streek met grove korrel en onregelmatige randen"
    grain, threshold, softness, flow, hardness, default_size, step = "crayon", 0.5, 0.08, 0.9, 80, 18, 8

    def dab_color(self, cv, r):
        # was geeft net iets wisselende kleur
        j = (np.random.rand() - 0.5) * 18
        c = self.color
        return np.array([c.red() + j, c.green() + j, c.blue() + j], np.float32)


class ColoredPencilTool(ArtMediaTool):
    cid, glyph = 0xd135, "pencil"
    tip = "Kleurpotlood: fijne lijnen met papierkorrel en arcering"
    grain, threshold, softness, flow, hardness, default_size, step = "pencil", 0.45, 0.15, 0.8, 85, 4, 20


class OilBrushTool(ArtMediaTool):
    cid, glyph = 0xd131, "oil"
    tip = ("Olieverfpenseel: dikke verf met haarsporen die mengt met wat er al ligt; de verf raakt in de loop "
           "van een streek op")
    grain, flow, hardness, default_size, step = None, 0.9, 70, 30, 8
    color_mix = 0.6

    def extra_options(self):
        k = f"am{self.cid:04x}"
        self.main.opts.setdefault(k + "_load", 70)
        self.main.opts.setdefault(k + "_visc", 50)
        return (spin(self.main, k + "_load", "Lading:", 1, 100) + spin(self.main, k + "_visc", "Viscositeit:", 0, 100))

    def begin(self, cv, pt):
        super().begin(cv, pt)
        k = f"am{self.cid:04x}"
        self.paint = 1.0  # hoeveel verf er nog op het penseel zit
        self.load = self.main.opts.get(k + "_load", 70) / 100
        self.visc = self.main.opts.get(k + "_visc", 50) / 100
        self.carried = np.array([self.color.red(), self.color.green(), self.color.blue()], np.float32)
        # haren: een vast patroon van evenwijdige strepen, per stempel gedraaid in de streekrichting
        s = self.stamp_size
        rng = np.random.default_rng(7)
        rows = rng.random(s).astype(np.float32)
        self.bristles = (0.7 + 0.3 * np.clip(rows * 1.6 - 0.3, 0, 1))[:, None] * np.ones((1, s), np.float32)
        self._bcache = {}

    def dab_alpha(self, r, full):
        w = super().dab_alpha(r, full)
        sub = self._bristle_mask()[r.y() - full.y(): r.y() - full.y() + r.height(),
                                   r.x() - full.x(): r.x() - full.x() + r.width()]
        return w * sub * (0.55 + 0.45 * self.paint)

    def _bristle_mask(self):
        """Haarsporen (0..1) gedraaid langs de streekrichting, per 15 graden bewaard."""
        key = int(round(self.direction / 15)) % 24
        cache = self.__dict__.setdefault("_bcache", {})
        if key not in cache:
            s = self.stamp_size
            src = np.ascontiguousarray(np.clip(self.bristles * 255, 0, 255).astype(np.uint8))
            img = QImage(src.data, s, s, s, QImage.Format.Format_Grayscale8).copy()
            out = QImage(s, s, QImage.Format.Format_Grayscale8)
            out.fill(0)
            q = QPainter(out)
            q.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            q.translate(s / 2, s / 2)
            q.rotate(key * 15)
            q.scale(1.5, 1.5)  # groter draaien, zodat de hoeken ook haren hebben
            q.translate(-s / 2, -s / 2)
            q.drawImage(0, 0, img)
            q.end()
            arr = np.frombuffer(out.constBits(), np.uint8, count=out.bytesPerLine() * s)
            cache[key] = arr.reshape(s, out.bytesPerLine())[:, :s].astype(np.float32) / 255
        return cache[key]

    def dab_color(self, cv, r):
        # kleur onder het penseel opnemen (viscositeit) en de verf langzaam laten opraken (lading)
        under = ops.qimage_to_rgba(self.base.copy(r)).astype(np.float32)
        al = under[..., 3:4] / 255
        if al.sum() > 0:
            mean = (under[..., :3] * al).sum(axis=(0, 1)) / al.sum()
            pick = self.visc * 0.25 * (1 - self.paint * 0.5)
            self.carried = self.carried * (1 - pick) + mean * pick
        self.paint = max(0.0, self.paint - (1 - self.load) * 0.008)
        fresh = np.array([self.color.red(), self.color.green(), self.color.blue()], np.float32)
        return self.carried * (1 - self.paint) + fresh * self.paint


def _blend_index(name):
    return next(i for i, m in enumerate(TOOL_BLEND_MODES) if m[0] == name)


class MarkerTool(ArtMediaTool):
    """Markering (viltstift): doorschijnende inkt met een vrij harde rand. Binnen één streek bouwt de kleur
    niet op; waar een nieuwe streek over een oude gaat, wordt het donkerder (zoals echte stiftinkt)."""
    cid, glyph = 0xd136, "marker"
    tip = "Markering: doorschijnende stiftinkt; waar streken elkaar overlappen wordt de kleur donkerder"
    grain, flow, hardness, default_size, step = None, 0.55, 85, 14, 8
    blend_mode = _blend_index("Vermenigvuldigen")


class PaletteKnifeTool(OilBrushTool):
    """Paletmes: dikke verf met een plat mes. Het mes staat dwars op de streekrichting, laat ribbels
    achter en smeert de verf die er al ligt mee (net als het olieverfpenseel, maar platter en voller)."""
    cid, glyph = 0xd137, "knife"
    tip = "Paletmes: dikke verf met een plat mes; smeert de verf die er al ligt mee"
    grain, flow, hardness, default_size, step = None, 0.97, 95, 30, 5
    color_mix = 0.85

    def _bristle_mask(self):
        """Plat mes dwars op de streekrichting, met ribbels in de lengte van de streek."""
        key = int(round(self.direction / 15)) % 24
        cache = self.__dict__.setdefault("_bcache", {})
        if key not in cache:
            s = self.stamp_size
            yy, xx = np.mgrid[0:s, 0:s].astype(np.float32) + 0.5 - s / 2
            a = math.radians(key * 15)
            along = xx * math.cos(a) + yy * math.sin(a)       # langs de streek
            across = -xx * math.sin(a) + yy * math.cos(a)     # dwars op de streek (breedte van het mes)
            blade = np.clip(s * 0.16 - np.abs(along) + 0.5, 0, 1) * np.clip(s * 0.5 - np.abs(across), 0, 1)
            # ribbels in de verf: afwisselend iets lichter en donkerder (licht valt op de richels)
            ridges = 0.88 + 0.2 * np.sin(across * 2 * math.pi / max(3.0, s / 5)) ** 2
            cache[key] = (blade.astype(np.float32), ridges.astype(np.float32))
        return cache[key]

    def dab_alpha(self, r, full):
        # geen ronde penseelvorm: het mes zelf bepaalt de vorm; de verf is dekkend
        blade, ridges = self._bristle_mask()
        sl = (slice(r.y() - full.y(), r.y() - full.y() + r.height()), slice(r.x() - full.x(), r.x() - full.x() + r.width()))
        self._ridges = ridges[sl]
        return blade[sl] * self.flow * (0.85 + 0.15 * self.paint)

    def dab_color(self, cv, r):
        col = super().dab_color(cv, r)
        return np.clip(col[None, None, :] * self._ridges[..., None], 0, 255)

    def extra_options(self):
        # een mes draagt meer verf dan een penseel en neemt minder op van wat er ligt
        k = f"am{self.cid:04x}"
        self.main.opts.setdefault(k + "_load", 90)
        self.main.opts.setdefault(k + "_visc", 35)
        return super().extra_options()


class AirbrushTool(PaintBrushTool):
    cid, glyph = 0xd092, "💨"
    tip = "Spuit verf: hoe langer je op één plek blijft, hoe meer verf. Rechts: achtergrondkleur"

    def options(self):
        return self.brush_options(blend=True) + spin(self.main, "rate", "Snelheid:", 0, 50)

    def begin(self, cv, pt):
        color = QColor(self.main.bg if self.right else self.main.fg)
        self.make_stamp(color)
        self.mat_img = self.material_layer(cv)
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
        if self.mat_img is not None:
            src = self.colored(src, r)
        blend_onto(local, src, self.o["blend"], self.o["opacity"] / 100 * 0.35, None, r.topLeft())
        paint_layer(d.layer(), r, local, d.sel)
        self.dirty = self.dirty.united(r)

    def end(self, cv):
        self.timer.stop()
        self.mat_img = None


class EraserTool(PaintBrushTool):
    cid, glyph = 0xd0b0, "⌫"
    tip = "Wis pixels naar transparant"
    erase = True


class ScratchRemoverTool(Tool):
    """Krasjes verwijderen: sleep een smal kader over een kras, haar of stofje. Bij loslaten wordt het
    kader opgevuld met een vloeiende overgang tussen de pixels aan weerszijden van het kader."""
    cid, glyph = 0xd082, "〰"
    tip = "Sleep een kader over een kras of haar; bij loslaten wordt het opgevuld vanuit de pixels ernaast"

    def __init__(self, main):
        super().__init__(main)
        self.a = self.b = None

    def options(self):
        m = self.main
        return (spin(m, "scratch_width", "Breedte:", 2, 100)
                + combo(m, "scratch_ends", "Uiteinden:", ["Recht", "Puntig"]))

    def press(self, cv, pt, ev):
        if ev.button() == LB:
            self.a = self.b = QPointF(pt)
            cv.update()

    def move(self, cv, pt, ev):
        if self.a is not None and ev.buttons() & LB:
            self.b = QPointF(pt)
            cv.update()

    def release(self, cv, pt, ev):
        if self.a is None:
            return
        self.b = QPointF(pt)
        a, b = self.a, self.b
        self.a = self.b = None
        if math.hypot(b.x() - a.x(), b.y() - a.y()) >= 1:
            self.remove(cv.doc, a, b)
        cv.update()

    def _frame(self, a, b):
        """Vier hoekpunten van het kader (voor het tekenen)."""
        L = max(math.hypot(b.x() - a.x(), b.y() - a.y()), 1e-6)
        dx, dy = (b.x() - a.x()) / L, (b.y() - a.y()) / L
        nx, ny = -dy, dx
        h = self.o["scratch_width"] / 2
        if self.o["scratch_ends"] == 1:
            k = min(h, L / 2)
            return [a, QPointF(a.x() + dx * k + nx * h, a.y() + dy * k + ny * h),
                    QPointF(b.x() - dx * k + nx * h, b.y() - dy * k + ny * h), b,
                    QPointF(b.x() - dx * k - nx * h, b.y() - dy * k - ny * h),
                    QPointF(a.x() + dx * k - nx * h, a.y() + dy * k - ny * h)]
        return [QPointF(a.x() + nx * h, a.y() + ny * h), QPointF(b.x() + nx * h, b.y() + ny * h),
                QPointF(b.x() - nx * h, b.y() - ny * h), QPointF(a.x() - nx * h, a.y() - ny * h)]

    def remove(self, d, a, b):
        from .effects.common import remap
        layer = d.layer()
        if layer.kind == "group" or layer.adjust is not None:
            return
        W = self.o["scratch_width"]
        h = W / 2
        L = math.hypot(b.x() - a.x(), b.y() - a.y())
        dx, dy = (b.x() - a.x()) / L, (b.y() - a.y()) / L
        nx, ny = -dy, dx
        pad = int(h + 4)
        r = QRectF(a, b).normalized().adjusted(-pad, -pad, pad, pad).toAlignedRect().intersected(d.rect())
        if r.isEmpty():
            return
        full = ops.qimage_to_rgba(layer.image)
        yy, xx = np.mgrid[r.y():r.bottom() + 1, r.x():r.right() + 1].astype(np.float32)
        px, py = xx + 0.5 - a.x(), yy + 0.5 - a.y()
        u = px * dx + py * dy               # langs de kras
        v = px * nx + py * ny               # dwars op de kras
        half = np.full_like(u, h)
        if self.o["scratch_ends"] == 1:     # puntige uiteinden: kader loopt naar de punten toe smal
            half = h * np.clip(np.minimum(u, L - u) / max(min(h, L / 2), 1e-6), 0, 1)
        inside = np.clip(half - np.abs(v) + 0.5, 0, 1) * ((u >= -0.5) & (u <= L + 0.5))
        if not inside.any():
            return
        # monsters net buiten het kader aan weerszijden, op dezelfde plek langs de kras
        off = half + 1.5
        lx, ly = xx + (-off - v) * nx, yy + (-off - v) * ny
        rx, ry = xx + (off - v) * nx, yy + (off - v) * ny
        left = remap(full, lx, ly).astype(np.float32)
        right = remap(full, rx, ry).astype(np.float32)
        t = np.clip((v + off) / np.maximum(2 * off, 1e-6), 0, 1)[..., None]
        fillv = left * (1 - t) + right * t
        cur = full[r.y():r.bottom() + 1, r.x():r.right() + 1].astype(np.float32)
        out = cur + (fillv - cur) * inside[..., None]
        d.push_undo("Krasjes verwijderen")
        paint_layer(layer, r, ops.rgba_to_qimage(np.clip(np.rint(out), 0, 255)), d.sel)
        d.changed.emit(r)
        d.structureChanged.emit()

    def overlay(self, cv, p):
        if self.a is None or self.b is None or self.a == self.b:
            return
        pts = [cv.to_widget(q) for q in self._frame(self.a, self.b)]
        poly = QPolygonF(pts + [pts[0]])
        p.setBrush(Qt.BrushStyle.NoBrush)
        for col, wd in ((QColor(0, 0, 0), 3), (QColor(255, 255, 255), 1)):
            p.setPen(QPen(col, wd))
            p.drawPolyline(poly)

    def deactivate(self):
        self.a = self.b = None


# ---------------------------------------------------------------- pixelpenselen
class PixelBrush(StrokeTool):
    """Penseel dat per stempel pixels bewerkt met NumPy (retoucheren, klonen, wissers)."""
    keep_alpha = True

    def options(self):
        return self.brush_options()

    snapshot = False  # effect berekend op de laag van bij het begin van de streek (zie hieronder)
    pad = 0           # extra rand rond de stempel voor filters die buren nodig hebben

    def options(self):
        w = self.brush_options()
        if self.snapshot:
            w += check(self.main, "continuous", "Doorlopend")
        return w

    def begin(self, cv, pt):
        self.make_stamp()
        if self.snapshot:
            # zoals het origineel: zonder 'Doorlopend' werkt het effect één keer per streek; heen en weer
            # gaan stapelt het dan niet op (anders blazen filters als verscherpen zichzelf op)
            self.snap = ops.qimage_to_rgba(cv.doc.layer().image)
            self.wmax = np.zeros(self.snap.shape[:2], np.float32)

    def end(self, cv):
        self.snap = self.wmax = None

    snap = wmax = None

    def _filtered(self, src_img, r, full, c, d):
        """Effect op gebied r, berekend met een rand eromheen zodat filters aan de rand kloppen."""
        rp = r.adjusted(-self.pad, -self.pad, self.pad, self.pad).intersected(d.rect())
        if isinstance(src_img, np.ndarray):
            region = src_img[rp.y():rp.bottom() + 1, rp.x():rp.right() + 1].astype(np.float32)
        else:
            region = ops.qimage_to_rgba(src_img.copy(rp)).astype(np.float32)
        new = self.op(region, rp, full, c)
        if new is None:
            return None
        ox, oy = r.x() - rp.x(), r.y() - rp.y()
        return new[oy:oy + r.height(), ox:ox + r.width()]

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
        if self.snap is not None and self.snap.shape[:2] != (d.h, d.w):
            self.snap = self.wmax = None  # laag veranderde van formaat tijdens de streek
        if self.snapshot and not self.o.get("continuous", False) and self.snap is not None:
            base = self.snap[r.y():r.bottom() + 1, r.x():r.right() + 1].astype(np.float32)
            new = self._filtered(self.snap, r, full, c, d)
            if new is None:
                return
            wm = np.maximum(self.wmax[r.y():r.bottom() + 1, r.x():r.right() + 1], w)
            self.wmax[r.y():r.bottom() + 1, r.x():r.right() + 1] = wm
            out = base + (new - base) * wm[..., None]
            if self.keep_alpha:
                out[..., 3] = base[..., 3]
            paint_layer(layer, r, ops.rgba_to_qimage(np.clip(np.rint(out), 0, 255)), d.sel)
            self.dirty = self.dirty.united(r)
            return
        arr = ops.qimage_to_rgba(layer.image.copy(r))
        new = self._filtered(layer.image, r, full, c, d) if self.snapshot else self.op(arr.astype(np.float32), r, full, c)
        if new is None:
            return
        if self.snapshot:  # Doorlopend: bouwt geleidelijk op bij elke stempel
            w = w * 0.25
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
    snapshot = True
    cid, glyph = 0xd0a1, "◐"
    tip = "Slepen: lichter maken, rechts slepen: donkerder maken"

    def op(self, a, *_):
        k = -0.2 if self.right else 0.2  # per streek (zonder Doorlopend stapelt het niet op)
        return _hsl_op(a, lambda h, s, l: (h, s, l + k))


class DodgeTool(PixelBrush):
    snapshot = True
    cid, glyph = 0xd0a2, "◯"
    tip = "Tegenhouden: lichtere details naar voren halen. Rechts: doordrukken"

    def op(self, a, *_):
        g = 1.4 if self.right else 0.7
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
    snapshot = True
    pad = 3
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
    snapshot = True
    pad = 2

    def op(self, a, *_):
        # per kanaal (zoals het origineel): grijs reliëf met kleurranden waar de kanalen verschillen
        p = np.pad(a[..., :3], ((1, 1), (1, 1), (0, 0)), mode="edge")
        out = a.copy()
        out[..., :3] = np.clip(128 + (p[2:, 2:] - p[:-2, :-2]), 0, 255)
        return out


class SaturationTool(PixelBrush):
    snapshot = True
    cid, glyph = 0xd0a9, "🌈"
    tip = "Slepen: kleuren levendiger, rechts slepen: minder levendig"

    def op(self, a, *_):
        k = -0.3 if self.right else 0.3
        return _hsl_op(a, lambda h, s, l: (h, s + k, l))


class HueTool(PixelBrush):
    snapshot = True
    cid, glyph = 0xd0aa, "🎨"
    tip = "Slepen: kleurtoon omhoog, rechts slepen: kleurtoon omlaag"

    def op(self, a, *_):
        k = -0.06 if self.right else 0.06
        return _hsl_op(a, lambda h, s, l: (h + k, s, l))


class ChangeToTargetTool(PixelBrush):
    snapshot = True
    cid, glyph = 0xd0ab, "🎯"
    tip = "Naar doel overgaan: kleurt pixels naar de voorgrondkleur met behoud van detail (rechts: achtergrondkleur)"

    def options(self):
        return (self.brush_options() + combo(self.main, "target_mode", "Modus:", ["Kleur", "Kleurtoon", "Verzadiging", "Lichtheid"])
                + check(self.main, "continuous", "Doorlopend"))

    def op(self, a, *_):
        t = self.main.bg if self.right else self.main.fg
        th, ts, tl = t.hslHueF(), t.hslSaturationF(), t.lightnessF()
        th = max(th, 0)
        mode = self.o["target_mode"]
        k = 0.5

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
            if self.active:  # een lopende streek eerst netjes afsluiten
                self.active = False
                self.last_pt = self.prev
                self.end(cv)
                cv.doc.structureChanged.emit()
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
        if self.offset is None:
            return None
        sr = r.translated(round(self.offset.x()), round(self.offset.y()))
        src = ops.qimage_to_rgba(self.src_img.copy(sr)).astype(np.float32)
        return src

    def overlay(self, cv, p):
        super().overlay(cv, p)
        if self.source is None:
            return
        # bij de bron een cirkel ter grootte van het penseel die meeloopt, zodat je ziet wat er gekloond
        # gaat worden (en wat er 'aankomt'); bij uitgelijnd klonen ook al voor de volgende streek
        src = self.source
        follow = self.offset is not None and cv.mouse_doc is not None and (self.active or self.o["clone_aligned"])
        if follow:
            src = QPointF(cv.mouse_doc.x() + self.offset.x(), cv.mouse_doc.y() + self.offset.y())
        c = cv.to_widget(src)
        r = max(3.0, self.o["size"] * cv.zoom / 2)
        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.translate(c)
        p.rotate(self.o["rotation"])
        p.scale(1, self.o["thickness"] / 100)
        for col, style in ((QColor(0, 0, 0, 200), Qt.PenStyle.SolidLine), (QColor(255, 255, 255, 230), Qt.PenStyle.DashLine)):
            p.setPen(QPen(col, 1.2, style))
            if self.o["brush_shape"] == 1:
                p.drawRect(QRectF(-r, -r, 2 * r, 2 * r))
            else:
                p.drawEllipse(QPointF(0, 0), r, r)
        p.restore()
        # klein kruisje in het midden van de bron
        for col, w_ in ((QColor(0, 0, 0), 3), (QColor(255, 255, 255), 1)):
            p.setPen(QPen(col, w_))
            p.drawLine(c + QPointF(-5, 0), c + QPointF(5, 0))
            p.drawLine(c + QPointF(0, -5), c + QPointF(0, 5))


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
        fg = ev.button() == LB
        color = QColor(self.main.fg if fg else self.main.bg)
        local = layer.image.copy(r)
        # verloop/patroon: loopt over het gevulde gebied
        fill = self.main.material_image(fg, r) or new_image(r.width(), r.height(), color)
        blend_onto(local, fill, self.o["blend"], self.o["opacity"] / 100, None, r.topLeft())
        d.push_undo("Vlakvulling")
        paint_layer(layer, r, local, ops.mask_to_qimage(m8))
        d.changed.emit(r)
        d.structureChanged.emit()


class ColorChangerTool(FillTool):
    """Klik op een kleur: alle gelijkende kleuren in de laag (of de selectie) krijgen de voorgrondkleur, met
    behoud van licht en schaduw. Lichtheid telt bij het vergelijken maar half mee, zodat ook de
    schaduwkanten van hetzelfde voorwerp meegaan; Randzachtheid laat de verandering geleidelijk uitlopen."""
    cid, glyph = 0xd0d2, "🖍"
    tip = "Klik op een kleur om die overal in de laag te veranderen in de voorgrondkleur, met behoud van schaduw (rechts: achtergrondkleur)"

    def options(self):
        m = self.main
        return (spin(m, "cc_tolerance", "Tolerantie:", 0, 200) + spin(m, "cc_softness", "Randzachtheid:", 0, 100)
                + check(m, "cc_contiguous", "Aaneengesloten") + spin(m, "opacity", "Dekking:", 1, 100))

    @staticmethod
    def weights(a, ref, tol, soft):
        """Gewicht 0..1 per pixel: hoe sterk lijkt de kleur op ref. Er wordt vooral naar de kleurtint gekeken
        (rgb gedeeld door de som, los van de helderheid); lichtheid telt maar licht mee, zodat licht en schaduw
        van hetzelfde voorwerp samen veranderen."""
        def chroma(c):
            c = c[..., :3] + 10.0  # bijna zwart: tint niet laten verspringen door ruis
            return c / c.sum(axis=-1, keepdims=True)
        def luma(c):
            return c[..., 0] * 0.299 + c[..., 1] * 0.587 + c[..., 2] * 0.114
        dc = np.abs(chroma(a) - chroma(ref)).sum(axis=-1) * 255
        dist = dc + np.abs(luma(a) - luma(ref)) * 0.15
        t = tol * 0.4
        s = 1.0 + soft * 0.01 * max(t, 15.0)
        return np.clip(1 - (dist - t) / s, 0, 1).astype(np.float32)

    def press(self, cv, pt, ev):
        d = cv.doc
        x, y = ipt(pt)
        if not d.rect().contains(x, y) or (d.sel is not None and d.sel.pixelColor(x, y).alpha() == 0):
            return
        if not self.main.ensure_raster():
            return
        layer = d.layer()
        a = ops.qimage_to_rgba(layer.image).astype(np.float32)
        ref = a[y, x, :3].copy()
        w = self.weights(a, ref, self.o["cc_tolerance"], self.o["cc_softness"])
        if self.o["cc_contiguous"]:
            w = w * ops.connected(w > 0, x, y)
        if d.sel is not None:
            w = w * (ops.qimage_to_mask(d.sel).astype(np.float32) / 255)
        r = ops.mask_bbox(w > 0)
        if r.isEmpty():
            return
        sl = (slice(r.y(), r.y() + r.height()), slice(r.x(), r.x() + r.width()))
        a, w = a[sl], w[sl]
        t = self.main.fg if ev.button() == LB else self.main.bg
        _, _, l0 = ops.rgb_to_hsl(ref[None, None, :])
        th, ts, tl = max(0, t.hslHueF()), t.hslSaturationF(), t.lightnessF()
        _, _, l = ops.rgb_to_hsl(a[..., :3])
        l2 = np.clip(l + (tl - float(l0[0, 0])), 0, 1)
        out = a.copy()
        out[..., :3] = ops.hsl_to_rgb(np.full_like(l, th), np.full_like(l, ts), l2)
        k = (w * (self.o["opacity"] / 100))[..., None]
        res = a + (out - a) * k
        res[..., 3] = a[..., 3]
        d.push_undo("Kleurwisselaar")
        img = QImage(layer.image)
        p = QPainter(img)
        p.setCompositionMode(CM.CompositionMode_Source)
        p.drawImage(r.topLeft(), ops.rgba_to_qimage(np.clip(res, 0, 255)))
        p.end()
        layer.image = img
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


class MakeoverTool(PixelBrush):
    """Makeover: snelle portretretouche met vijf modi.
    Vlekken verwijderen: vult een puistje of vlekje op vanuit de huid eromheen.
    Tandenborstel: maakt tanden witter (alleen lichte, niet rode pixels, dus niet het tandvlees of de lippen).
    Oogdruppel: haalt rode adertjes uit het oogwit en maakt het iets helderder.
    Zonnebruin: geeft de huid een gebruinde tint met behoud van licht en schaduw.
    Slanker maken: klik midden op een persoon; de afbeelding wordt rond dat punt horizontaal iets smaller."""
    cid, glyph = 0xd070, "makeover"
    tip = "Makeover: vlekken verwijderen, tanden witter, oogwit helderder, zonnebruin of slanker maken"
    snapshot = True
    MODES = ["Vlekken verwijderen", "Tandenborstel", "Oogdruppel", "Zonnebruin", "Slanker maken"]

    @property
    def o(self):
        m = self.main.opts
        m.setdefault("mk_mode", 0)
        m.setdefault("mk_size", 20)
        m.setdefault("mk_strength", 50)
        return _AliasOpts(m, {"size": "mk_size", "opacity": "mk_strength"},
                          {"hardness": 50 if m["mk_mode"] else 70, "step": 15, "density": 100, "brush_shape": 0,
                           "thickness": 100, "rotation": 0, "continuous": False})

    def options(self):
        self.o
        m = self.main
        return (combo(m, "mk_mode", "Modus:", self.MODES) + spin(m, "mk_size", "Grootte:", 1, 500)
                + spin(m, "mk_strength", "Sterkte:", 1, 100))

    def press(self, cv, pt, ev):
        if self.o["mk_mode"] == 4:
            if ev.button() == LB:
                self.thinify(cv.doc, pt)
            return
        super().press(cv, pt, ev)

    def op(self, a, r, full, c):
        mode = self.o["mk_mode"]
        rgb = a[..., :3]
        if mode == 0:
            return self._blemish(a, r, c)
        h, s, l = ops.rgb_to_hsl(rgb)
        if mode in (1, 2):
            # rood = tint dicht bij rood/roze (lippen, tandvlees, adertjes), niet geel (tanden)
            hd = np.minimum(h, 1 - h) * 360
            redness = np.clip((30 - hd) / 15, 0, 1) * np.clip(s * 3, 0, 1)
            if mode == 1:  # tanden: licht en niet rood (lippen en tandvlees blijven)
                k = np.clip((l - 0.35) / 0.2, 0, 1) * (1 - redness)
                s2, l2 = s * (1 - 0.85 * k), np.clip(l + 0.12 * k * (1 - l) * 2, 0, 1)
            else:  # oogwit: rode adertjes weg en iets helderder, de iris (donker) blijft
                k = np.clip((l - 0.3) / 0.25, 0, 1)
                s2, l2 = s * (1 - 0.8 * k * np.maximum(redness, 0.4)), np.clip(l + 0.06 * k, 0, 1)
            out = a.copy()
            out[..., :3] = ops.hsl_to_rgb(h, s2, l2)
            return out
        # zonnebruin: warme bruine tint, lichtheid iets lager, schaduw blijft
        tan_h, tan_s = 25 / 360, 0.45
        out = a.copy()
        out[..., :3] = ops.hsl_to_rgb(np.full_like(h, tan_h), np.maximum(s, tan_s) * 0.9 + s * 0.1,
                                      np.clip(l * 0.88, 0, 1))
        return out

    def _blemish(self, a, r, c):
        """Elke pixel in de cirkel krijgt de mix van twee tegenoverliggende punten op de rand eromheen,
        gewogen naar de afstand: zo verdwijnt het vlekje en lopen de huidtinten vloeiend door."""
        from .effects.common import remap
        R = max(self.o["size"] / 2, 1.5)
        snap = self.snap if self.snap is not None else a
        yy, xx = np.mgrid[r.y():r.y() + r.height(), r.x():r.x() + r.width()].astype(np.float32) + 0.5
        dx, dy = xx - c.x(), yy - c.y()
        rho = np.hypot(dx, dy)
        ux, uy = dx / np.maximum(rho, 1e-6), dy / np.maximum(rho, 1e-6)
        ring = R * 1.15 + 1
        A = remap(snap, c.x() + ux * ring - 0.5, c.y() + uy * ring - 0.5).astype(np.float32)
        B = remap(snap, c.x() - ux * ring - 0.5, c.y() - uy * ring - 0.5).astype(np.float32)
        t = np.clip((ring - rho) / (2 * ring), 0, 1)[..., None]  # dicht bij A: meer A
        fillc = A * (1 - t) + B * t
        out = a.copy()
        out[..., :3] = fillc[..., :3]
        return out

    def thinify(self, d, pt):
        """Horizontaal samendrukken rond het aangeklikte punt; de randen van de afbeelding blijven staan."""
        from .effects.common import remap
        layer = d.layer()
        if layer.kind == "group" or layer.adjust is not None or not self.main.ensure_raster():
            return
        a = ops.qimage_to_rgba(layer.image)
        h, w = a.shape[:2]
        cx = pt.x()
        k = self.o["mk_strength"] / 100 * 0.12   # hoogstens 12% smaller in het midden
        xs = np.arange(w, dtype=np.float32) + 0.5
        # doelpositie -> bronpositie: in het midden verder weg kijken (samendrukken), naar de randen toe
        # vloeiend terug naar 0, zodat de randen van het beeld op hun plek blijven
        span = np.where(xs < cx, max(cx, 1.0), max(w - cx, 1.0))
        u = (xs - cx) / span                       # -1 .. 1
        src = cx + (xs - cx) * (1 + k * (1 - np.abs(u)) ** 2 * 2)
        src = np.clip(src - 0.5, 0, w - 1)
        mx = np.broadcast_to(src[None, :], (h, w))
        my = np.broadcast_to(np.arange(h, dtype=np.float32)[:, None], (h, w))
        out = remap(a, mx, my)
        d.push_undo(self.name)
        paint_layer(layer, d.rect(), ops.rgba_to_qimage(np.clip(np.rint(out), 0, 255)), d.sel)
        d.changed.emit(d.rect())
        d.structureChanged.emit()

    def overlay(self, cv, p):
        if self.o["mk_mode"] == 4:
            if cv.mouse_doc is not None:
                x = cv.to_widget(cv.mouse_doc).x()
                p.setPen(QPen(QColor(255, 255, 255, 200), 0, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(x, 0), QPointF(x, cv.height()))
            return
        super().overlay(cv, p)


class ObjectRemoverTool(Tool):
    """Object verwijderen: trek een lijn om het object (modus Selecteren), verschuif daarna het bronkader
    naar een plek met passende achtergrond (modus Bron) en klik op Toepassen of druk op Enter. Het
    object wordt vervangen door de bron; kleur en helderheid worden aan de omgeving aangepast, zodat
    er geen zichtbare naad ontstaat."""
    cid, glyph = 0xd083, "object_remover"
    tip = "Trek een lijn om het object, verschuif het bronkader naar passende achtergrond en klik op Toepassen"
    wants_cursor_overlay = True

    def __init__(self, main):
        super().__init__(main)
        self.poly = []      # omtrek van het object (documentcoördinaten)
        self.src = None     # bronkader (QRectF)
        self.drag = None    # ("lasso",) | ("move", start, rect) | ("size", hoek, rect)
        self.cv = None

    def options(self):
        m = self.main
        m.opts.setdefault("or_mode", 0)
        m.opts.setdefault("or_blend", 10)
        return (combo(m, "or_mode", "Modus:", ["Object selecteren", "Bron"]) + spin(m, "or_blend", "Overgang:", 0, 50)
                + button("Toepassen", self.apply))

    def _corner(self, cv, pt):
        if self.src is None:
            return None
        tol = 6 / cv.zoom
        r = self.src
        for name, q in (("tl", r.topLeft()), ("tr", r.topRight()), ("bl", r.bottomLeft()), ("br", r.bottomRight())):
            if abs(q.x() - pt.x()) <= tol and abs(q.y() - pt.y()) <= tol:
                return name
        return None

    def press(self, cv, pt, ev):
        if ev.button() != LB:
            return
        self.cv = cv
        if self.o["or_mode"] == 1 and self.src is not None:
            corner = self._corner(cv, pt)
            if corner:
                self.drag = ("size", corner, QRectF(self.src))
            elif self.src.contains(pt):
                self.drag = ("move", QPointF(pt), QRectF(self.src))
            return
        self.poly = [QPointF(pt)]
        self.src = None
        self.drag = ("lasso",)
        cv.update()

    def move(self, cv, pt, ev):
        if not self.drag or not (ev.buttons() & LB):
            return
        if self.drag[0] == "lasso":
            if not self.poly or QLineF(self.poly[-1], pt).length() >= 1.5 / max(cv.zoom, 0.01):
                self.poly.append(QPointF(pt))
        elif self.drag[0] == "move":
            _, start, r0 = self.drag
            self.src = r0.translated(pt.x() - start.x(), pt.y() - start.y())
        else:
            _, corner, r0 = self.drag
            r = QRectF(r0)
            if "l" in corner:
                r.setLeft(min(pt.x(), r.right() - 4))
            else:
                r.setRight(max(pt.x(), r.left() + 4))
            if "t" in corner:
                r.setTop(min(pt.y(), r.bottom() - 4))
            else:
                r.setBottom(max(pt.y(), r.top() + 4))
            self.src = r
        cv.update()

    def release(self, cv, pt, ev):
        if not self.drag:
            return
        kind = self.drag[0]
        self.drag = None
        if kind == "lasso":
            if len(self.poly) < 3 or QPolygonF(self.poly).boundingRect().width() * \
                    QPolygonF(self.poly).boundingRect().height() < 4:
                self.poly = []
            else:
                self.src = self._default_source(cv.doc)
                self.main.opts["or_mode"] = 1
                self.main._build_options(self)  # optiebalk bijwerken (modus Bron)
        cv.update()

    def _default_source(self, d):
        """Bronkader even groot als het object, ernaast (links, rechts, boven of onder: wat binnen het beeld
        valt en het dichtst bij ligt)."""
        b = QPolygonF(self.poly).boundingRect()
        gap = 2 * (int(self.o["or_blend"]) + 3) + 4  # de overgangsrand van de bron mag het object niet raken
        for dx, dy in ((-(b.width() + gap), 0), (b.width() + gap, 0), (0, -(b.height() + gap)), (0, b.height() + gap)):
            r = b.translated(dx, dy)
            if QRectF(d.rect()).contains(r):
                return r
        return b.translated(-(b.width() + gap), 0)

    def key(self, cv, ev):
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.poly and self.src is not None:
            self.apply()
            return True
        if ev.key() == Qt.Key.Key_Escape and (self.poly or self.src is not None):
            self.poly, self.src = [], None
            cv.update()
            return True
        return False

    def apply(self, cv=None):
        if not hasattr(cv, "doc"):  # vanaf de knop (die geeft een bool mee) of zonder canvas
            cv = self.cv or self.main.canvas()
        if cv is None or len(self.poly) < 3 or self.src is None:
            return
        d = cv.doc
        layer = d.layer()
        if layer.kind == "group" or layer.adjust is not None or not self.main.ensure_raster():
            return
        layer = d.layer()
        feather = int(self.o["or_blend"])
        poly = QPolygonF(self.poly)
        tb = poly.boundingRect()
        pad = feather + 3
        T = tb.toAlignedRect().adjusted(-pad, -pad, pad, pad)  # doelgebied met rand
        Tc = T.intersected(d.rect())
        if Tc.isEmpty():
            return
        # masker van het object (zacht aflopend over 'Overgang' pixels naar buiten)
        m = QImage(Tc.width(), Tc.height(), QImage.Format.Format_Alpha8)
        m.fill(QColor(0, 0, 0, 0))
        p = QPainter(m)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(-Tc.x(), -Tc.y())
        p.setPen(QPen(QColor(0, 0, 0, 255), 2))
        p.setBrush(QColor(0, 0, 0, 255))
        p.drawPolygon(poly)
        p.end()
        core = ops.qimage_to_mask(m).astype(np.float32) / 255
        if feather > 0:
            grown = ops.box_blur(core, max(1, feather // 2), passes=2)
            mask = np.clip(np.maximum(core, grown * 2), 0, 1)
        else:
            mask = core
        # bron: het bronkader geschaald naar het objectkader, met dezelfde rand eromheen
        from .effects.common import remap
        full = ops.qimage_to_rgba(layer.image)
        sx = self.src.width() / max(tb.width(), 1e-6)
        sy = self.src.height() / max(tb.height(), 1e-6)
        yy, xx = np.mgrid[Tc.y():Tc.y() + Tc.height(), Tc.x():Tc.x() + Tc.width()].astype(np.float32) + 0.5
        mx = self.src.x() + (xx - tb.x()) * sx - 0.5
        my = self.src.y() + (yy - tb.y()) * sy - 0.5
        S = remap(full, mx, my).astype(np.float32)
        cur = full[Tc.y():Tc.y() + Tc.height(), Tc.x():Tc.x() + Tc.width()].astype(np.float32)
        # kleuraanpassing: het verschil tussen omgeving en bron op een ring net buiten het masker,
        # vloeiend naar binnen doorgetrokken (genormaliseerde vervaging)
        outer = ops.box_blur((mask > 0.01).astype(np.float32), 2, passes=1)
        ring = ((outer > 0.01) & (mask <= 0.01)).astype(np.float32)
        if ring.sum() >= 4:
            dim = max(tb.width(), tb.height())
            delta = (cur[..., :3] - S[..., :3]) * ring[..., None]

            def spread(rad):
                wsum = ops.box_blur(ring, rad, passes=3)
                return np.dstack([ops.box_blur(delta[..., c], rad, passes=3) for c in range(3)]) / \
                    (wsum[..., None] + 1e-6), wsum

            # grof (reikt tot in het midden) en fijn (volgt de rand nauwkeurig), vloeiend samengevoegd
            coarse, _ = spread(max(2, int(dim / 2)))
            fine, wf = spread(max(2, int(dim / 10)))
            k = np.clip(wf * 6, 0, 1)[..., None]
            S[..., :3] += coarse * (1 - k) + fine * k
        out = cur + (S - cur) * mask[..., None]
        out[..., 3] = np.maximum(cur[..., 3], S[..., 3] * mask)
        d.push_undo(self.name)
        paint_layer(layer, Tc, ops.rgba_to_qimage(np.clip(np.rint(out), 0, 255)), d.sel)
        self.poly, self.src = [], None
        self.main.opts["or_mode"] = 0
        self.main._build_options(self)
        d.changed.emit(Tc)
        d.structureChanged.emit()
        cv.update()

    def overlay(self, cv, p):
        p.setBrush(Qt.BrushStyle.NoBrush)
        if len(self.poly) >= 2:
            pts = [cv.to_widget(q) for q in self.poly]
            poly = QPolygonF(pts + ([pts[0]] if self.drag is None else []))
            for col, wd, st in ((QColor(0, 0, 0), 3, Qt.PenStyle.SolidLine), (QColor(255, 255, 255), 1, Qt.PenStyle.DashLine)):
                p.setPen(QPen(col, wd, st))
                p.drawPolyline(poly)
        if self.src is not None:
            r = QRectF(cv.to_widget(self.src.topLeft()), cv.to_widget(self.src.bottomRight()))
            for col, wd in ((QColor(0, 0, 0), 3), (QColor(80, 200, 255), 1)):
                p.setPen(QPen(col, wd))
                p.drawRect(r)
            p.setBrush(QColor(80, 200, 255))
            p.setPen(QPen(QColor(0, 0, 0), 1))
            for q in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
                p.drawRect(QRectF(q.x() - 3.5, q.y() - 3.5, 7, 7))

    def hover_cursor(self, cv, pt):
        if self.o.get("or_mode") == 1 and self.src is not None:
            c = self._corner(cv, pt)
            if c in ("tl", "br"):
                return Qt.CursorShape.SizeFDiagCursor
            if c in ("tr", "bl"):
                return Qt.CursorShape.SizeBDiagCursor
            if self.src.contains(pt):
                return Qt.CursorShape.SizeAllCursor
        return None

    def deactivate(self):
        self.drag = None


class StraightenTool(Tool):
    snaps = True  # punten uitlijnen op raster en hulplijnen (als dat aan staat)
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


class PerspectiveTool(Tool):
    snaps = True  # punten uitlijnen op raster en hulplijnen (als dat aan staat)
    """Perspectiefcorrectie: sleep de vier hoeken van het kader langs de randen van iets dat recht
    hoort te zijn (een gebouw, een schuin gefotografeerd document); toepassen trekt het recht."""
    context_menu = True
    edits_pixels = False
    cid, glyph = 0xd052, "⏢"
    tip = ("Sleep de hoeken van het kader langs randen die recht moeten zijn. Dubbelklik in het kader, "
           "Enter of Toepassen om recht te trekken; Esc zet het kader terug")
    HANDLE = 5

    def __init__(self, main):
        super().__init__(main)
        self.quad = None   # [linksboven, rechtsboven, rechtsonder, linksonder] in documentcoördinaten
        self.doc = None
        self.drag = None   # ("corner", i) of ("move", start, quad0)

    def options(self):
        m = self.main
        return (spin(m, "persp_grid", "Rasterlijnen:", 0, 30)
                + check(m, "persp_crop", "Afbeelding bijsnijden")
                + button("Toepassen", lambda: self.apply(m.canvas()))
                + button("Herstellen", lambda: self.reset(m.canvas())))

    def _ensure(self, cv):
        if self.quad is None or self.doc is not cv.doc:
            self.reset(cv, update=False)

    def reset(self, cv, update=True):
        if cv is None:
            return
        d = cv.doc
        mx, my = d.w * 0.15, d.h * 0.15
        self.quad = [QPointF(mx, my), QPointF(d.w - mx, my), QPointF(d.w - mx, d.h - my), QPointF(mx, d.h - my)]
        self.doc = d
        if update:
            cv.update()

    def _corner(self, cv, pt):
        tol = (self.HANDLE + 4) / cv.zoom
        for i, q in enumerate(self.quad):
            if abs(q.x() - pt.x()) <= tol and abs(q.y() - pt.y()) <= tol:
                return i
        return None

    def _inside(self, pt):
        return QPolygonF(self.quad).containsPoint(pt, Qt.FillRule.OddEvenFill)

    def press(self, cv, pt, ev):
        if ev.button() != LB:
            return
        self._ensure(cv)
        i = self._corner(cv, pt)
        if i is not None:
            self.drag = ("corner", i)
        elif self._inside(pt):
            self.drag = ("move", QPointF(pt), [QPointF(q) for q in self.quad])

    def move(self, cv, pt, ev):
        if not self.drag or not (ev.buttons() & LB):
            return
        if self.drag[0] == "corner":
            self.quad[self.drag[1]] = QPointF(pt)
        else:
            _, start, q0 = self.drag
            d = pt - start
            self.quad = [q + d for q in q0]
        cv.update()

    def release(self, cv, pt, ev):
        self.drag = None

    def double_click(self, cv, pt, ev):
        self._ensure(cv)
        if self._inside(pt):
            self.apply(cv)

    def hover_cursor(self, cv, pt):
        self._ensure(cv)
        if self._corner(cv, pt) is not None:
            return Qt.CursorShape.CrossCursor
        if self._inside(pt):
            return Qt.CursorShape.SizeAllCursor
        return None

    def context_actions(self, cv):
        return [("Perspectiefcorrectie toepassen", lambda: self.apply(cv)),
                ("Kader herstellen", lambda: self.reset(cv))]

    def apply(self, cv):
        if cv is None:
            return
        self._ensure(cv)
        if cv.doc.perspective(self.quad, self.o["persp_crop"], self.main.bg):
            self.reset(cv)
            cv.update()

    def key(self, cv, ev):
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.apply(cv)
            return True
        if ev.key() == Qt.Key.Key_Escape:
            self.reset(cv)
            return True
        return False

    def overlay(self, cv, p):
        self._ensure(cv)
        pts = [cv.to_widget(q) for q in self.quad]
        poly = QPolygonF(pts + [pts[0]])
        p.setBrush(Qt.BrushStyle.NoBrush)
        # raster: lijnen tussen overeenkomstige punten op tegenoverliggende zijden
        n = self.o["persp_grid"]
        lerp = lambda a, b, t: QPointF(a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t)
        lines = []
        for k in range(1, n + 1):
            t = k / (n + 1)
            lines.append((lerp(pts[0], pts[1], t), lerp(pts[3], pts[2], t)))
            lines.append((lerp(pts[0], pts[3], t), lerp(pts[1], pts[2], t)))
        for col, w in ((QColor(0, 0, 0, 150), 2.5), (QColor(255, 255, 255, 200), 1)):
            p.setPen(QPen(col, w))
            for a, b in lines:
                p.drawLine(a, b)
        for col, w in ((QColor(0, 0, 0), 3), (QColor(255, 255, 0), 1.2)):
            p.setPen(QPen(col, w))
            p.drawPolyline(poly)
        p.setPen(QPen(QColor(0, 0, 0), 1))
        p.setBrush(QColor(255, 255, 255))
        h = self.HANDLE
        for q in pts:
            p.drawRect(QRectF(q.x() - h, q.y() - h, 2 * h, 2 * h))

    def deactivate(self):
        self.drag = None


class CropTool(Tool):
    snaps = True  # punten uitlijnen op raster en hulplijnen (als dat aan staat)
    """Bijsnijden zoals PSP: kader met grepen op hoeken en zijden, zwevend balkje (toepassen, kantelen,
    verhouding), optiebalk met maten en uitlijnen. Dubbelklik in het kader snijdt bij."""
    context_menu = True
    edits_pixels = False
    cid, glyph = 0xd040, "⛶"
    tip = ("Sleep een rechthoek; versleep de grepen om de grootte aan te passen en binnen het kader om het "
           "te verplaatsen. Dubbelklik in het kader, Enter of ✓ om bij te snijden. Esc annuleert")
    HANDLE = 4
    RATIOS = [("Vrije vorm", None), ("1 × 1", 1.0), ("4 × 3", 4 / 3), ("3 × 2", 3 / 2), ("16 × 9", 16 / 9),
              ("5 × 4", 5 / 4), ("7 × 5", 7 / 5), ("A4 (1 × 1,41)", 1 / 1.4142)]

    def __init__(self, main):
        super().__init__(main)
        self.r = None
        self.drag = None
        self.spins = {}
        self.ratio = None   # breedte / hoogte, of None (vrije vorm)
        self.bars = {}      # zwevend balkje per werkvlak

    # ---------------------------------------------------------------- optiebalk
    def options(self):
        out = []
        self.spins = {}
        for key, label in (("w", "Breedte:"), ("h", "Hoogte:"), ("l", "Links:"), ("t", "Boven:"),
                           ("r", "Rechts:"), ("b", "Onder:")):
            sp = QSpinBox()
            sp.setRange(0, 100000)
            sp.setKeyboardTracking(False)
            sp.valueChanged.connect(lambda _v, k=key: self._from_spins(k))
            self.spins[key] = sp
            out += [QLabel(label), sp]
        self.keep = QCheckBox("Verhouding behouden")
        self.keep.setChecked(self.ratio is not None)
        self.keep.toggled.connect(self._keep_toggled)
        out.append(self.keep)
        out.append(QLabel("Bijsnijkader uitlijnen op:"))
        for glyph, tip, mode in (("⬚", "Huidige afbeelding", "image"), ("▣", "Dekkende delen van de laag", "layer"),
                                 ("◼", "Dekkende delen van alle lagen", "merged")):
            b = QToolButton(text=glyph)
            b.setToolTip(tip)
            b.clicked.connect(lambda _=False, m=mode: self.snap(m))
            out.append(b)
        self._to_spins()
        return out

    def _keep_toggled(self, on):
        if on and self.r is not None and self.ratio is None:
            self.ratio = self.r.width() / max(1, self.r.height())
        elif not on:
            self.ratio = None
        self._sync_bar_combo()

    def _to_spins(self):
        if not self.spins:
            return
        for sp in self.spins.values():
            sp.blockSignals(True)
        r = self.r or QRect()
        vals = dict(w=r.width(), h=r.height(), l=r.x(), t=r.y(), r=r.x() + r.width(), b=r.y() + r.height())
        for k, v in vals.items():
            self.spins[k].setValue(v)
        for sp in self.spins.values():
            sp.blockSignals(False)

    def _from_spins(self, key):
        cv = self.main.canvas()
        if cv is None:
            return
        v = {k: sp.value() for k, sp in self.spins.items()}
        if key in ("w", "h"):
            w, h = v["w"], v["h"]
            if self.ratio:
                if key == "w":
                    h = round(w / self.ratio)
                else:
                    w = round(h * self.ratio)
            r = QRect(v["l"], v["t"], max(1, w), max(1, h))
        else:
            r = QRect(QPoint(v["l"], v["t"]), QPoint(max(v["l"] + 1, v["r"]) - 1, max(v["t"] + 1, v["b"]) - 1))
        self.r = r.intersected(cv.doc.rect())
        self._to_spins()
        cv.update()

    def snap(self, mode):
        cv = self.main.canvas()
        if cv is None:
            return
        d = cv.doc
        if mode == "image":
            r = d.rect()
        else:
            img = d.layer().image if mode == "layer" else cv.cache
            r = ops.mask_bbox(ops.qimage_to_rgba(img)[..., 3] > 0)
            if r.isEmpty():
                return
        self.ratio = None
        self.r = r
        self._to_spins()
        self._sync_bar_combo()
        cv.update()

    def context_actions(self, cv):
        if self.r is None:
            return []
        return [("Bijsnijden toepassen", lambda: self.apply(cv)), ("Bijsnijrechthoek wissen", self.clear)]

    def clear(self):
        self.r = None
        self._to_spins()
        cv = self.main.canvas()
        if cv:
            cv.update()
        self._hide_bars()

    # ---------------------------------------------------------------- zwevend balkje onder het kader
    def _bar(self, cv):
        bar = self.bars.get(id(cv))
        if bar is None:
            from PySide6.QtWidgets import QFrame, QHBoxLayout
            bar = QFrame(cv)
            bar.setFrameShape(QFrame.Shape.StyledPanel)
            bar.setAutoFillBackground(True)
            h = QHBoxLayout(bar)
            h.setContentsMargins(3, 2, 3, 2)
            h.setSpacing(3)
            ok = QToolButton(text="✓")
            ok.setToolTip("Toepassen")
            ok.setStyleSheet("color: #2e9e3e; font-weight: bold;")
            ok.clicked.connect(lambda: self.apply(cv))
            turn = QToolButton(text="⇄")
            turn.setToolTip("Bijsnijkader kantelen (liggend / staand)")
            turn.clicked.connect(lambda: self.rotate_frame(cv))
            combo = QComboBox()
            combo.addItems([n for n, _ in self.RATIOS])
            combo.setToolTip("Verhouding")
            combo.activated.connect(lambda i: self.set_ratio(cv, self.RATIOS[i][1]))
            for wdg in (ok, turn, combo):
                h.addWidget(wdg)
            bar.combo = combo
            bar.adjustSize()
            self.bars[id(cv)] = bar
            bar.destroyed.connect(lambda *_a, k=id(cv): self.bars.pop(k, None))
        return bar

    def _sync_bar_combo(self):
        for bar in self.bars.values():
            idx = 0
            for i, (_, rt) in enumerate(self.RATIOS):
                if rt and self.ratio and (abs(rt - self.ratio) < 1e-3 or abs(1 / rt - self.ratio) < 1e-3):
                    idx = i
            bar.combo.setCurrentIndex(idx)
        if hasattr(self, "keep") and self.keep is not None:
            try:
                self.keep.blockSignals(True)
                self.keep.setChecked(self.ratio is not None)
                self.keep.blockSignals(False)
            except RuntimeError:
                pass

    def _place_bar(self, cv):
        bar = self._bar(cv)
        show = (getattr(cv, "view", None) or {}).get("crop_bar", True)  # voorkeuren: zwevende werkbalk tonen
        if not show or self.r is None or self.drag is not None and self.drag[0] == "new":
            bar.hide()
            return
        hs = self._handles(cv)
        x, y = int(hs[3].x()) + 10, int(hs[3].y()) + 6
        if y + bar.height() > cv.height():
            y = int(hs[0].y()) - bar.height() - 6
        x = max(2, min(cv.width() - bar.width() - 2, x))
        y = max(2, min(cv.height() - bar.height() - 2, y))
        if bar.pos() != QPoint(x, y):
            bar.move(x, y)
        if not bar.isVisible():
            bar.show()

    def _hide_bars(self):
        for bar in list(self.bars.values()):
            try:
                bar.hide()
            except RuntimeError:
                pass

    def set_ratio(self, cv, ratio):
        """Vaste verhouding kiezen; het kader past zich aan rond het midden, binnen de afbeelding."""
        if ratio is not None and self.r is not None and self.r.height() > self.r.width():
            ratio = 1 / ratio  # het kader staat: verhouding staand houden
        self.ratio = ratio
        if ratio and self.r is not None:
            c = QRectF(self.r).center()
            w, h = self.r.width(), self.r.height()
            if w / h > ratio:
                w = h * ratio
            else:
                h = w / ratio
            self.r = QRectF(c.x() - w / 2, c.y() - h / 2, w, h).toRect().intersected(cv.doc.rect())
        self._to_spins()
        self._sync_bar_combo()
        cv.update()

    def rotate_frame(self, cv):
        """Kader kantelen rond het midden (breedte en hoogte wisselen)."""
        if self.r is None:
            return
        c = QRectF(self.r).center()
        w, h = self.r.height(), self.r.width()
        d = cv.doc
        if w > d.w or h > d.h:  # past niet: evenredig verkleinen
            f = min(d.w / w, d.h / h)
            w, h = w * f, h * f
        x = min(max(c.x() - w / 2, 0), d.w - w)
        y = min(max(c.y() - h / 2, 0), d.h - h)
        self.r = QRectF(x, y, w, h).toRect()
        if self.ratio:
            self.ratio = 1 / self.ratio
        self._to_spins()
        cv.update()

    # ---------------------------------------------------------------- grepen
    def _handles(self, cv):
        """0-3 hoeken (LB, RB, RO, LO), 4-7 zijden (boven, rechts, onder, links), in schermcoördinaten."""
        r = self.r
        tl = cv.to_widget(QPointF(r.x(), r.y()))
        br = cv.to_widget(QPointF(r.x() + r.width(), r.y() + r.height()))
        cx, cy = (tl.x() + br.x()) / 2, (tl.y() + br.y()) / 2
        return [QPointF(tl.x(), tl.y()), QPointF(br.x(), tl.y()), QPointF(br.x(), br.y()), QPointF(tl.x(), br.y()),
                QPointF(cx, tl.y()), QPointF(br.x(), cy), QPointF(cx, br.y()), QPointF(tl.x(), cy)]

    def _hit(self, cv, pt):
        if self.r is None:
            return None
        w = cv.to_widget(pt)
        for i, h in enumerate(self._handles(cv)):
            if abs(h.x() - w.x()) <= self.HANDLE + 3 and abs(h.y() - w.y()) <= self.HANDLE + 3:
                return ("handle", i)
        if QRectF(self.r).contains(pt):
            return ("inside", None)
        return None

    def hover_cursor(self, cv, pt):
        hit = self._hit(cv, pt)
        if hit is None:
            return None
        if hit[0] == "inside":
            return Qt.CursorShape.SizeAllCursor
        return [Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeBDiagCursor, Qt.CursorShape.SizeFDiagCursor,
                Qt.CursorShape.SizeBDiagCursor, Qt.CursorShape.SizeVerCursor, Qt.CursorShape.SizeHorCursor,
                Qt.CursorShape.SizeVerCursor, Qt.CursorShape.SizeHorCursor][hit[1]]

    # ---------------------------------------------------------------- muis
    def press(self, cv, pt, ev):
        if ev.button() != LB:
            return
        hit = self._hit(cv, pt)
        p = QPointF(round(pt.x()), round(pt.y()))
        if hit and hit[0] == "handle":
            self.drag = ("handle", hit[1], QRect(self.r))
        elif hit and hit[0] == "inside":
            self.drag = ("move", p, QRect(self.r))
        else:
            self.drag = ("new", p)
            self.r = None
        self._place_bar(cv)

    @staticmethod
    def _corner_ratio(ax, ay, px, py, ratio):
        """Rechthoek van ankerpunt (ax, ay) naar (px, py) met vaste verhouding."""
        w, h = abs(px - ax), abs(py - ay)
        if h == 0 or w / max(h, 1e-6) > ratio:
            h = w / ratio
        else:
            w = h * ratio
        x1 = ax + (w if px >= ax else -w)
        y1 = ay + (h if py >= ay else -h)
        return QRectF(QPointF(ax, ay), QPointF(x1, y1)).normalized()

    def move(self, cv, pt, ev):
        if self.drag is None or not ev.buttons() & LB:
            return
        d = cv.doc
        p = QPointF(min(max(round(pt.x()), 0), d.w), min(max(round(pt.y()), 0), d.h))
        kind = self.drag[0]
        if kind == "new":
            a = self.drag[1]
            rf = self._corner_ratio(a.x(), a.y(), p.x(), p.y(), self.ratio) if self.ratio else QRectF(a, p).normalized()
            self.r = rf.toRect().intersected(d.rect())
        elif kind == "move":
            r0 = self.drag[2]
            dx = int(p.x() - self.drag[1].x())
            dy = int(p.y() - self.drag[1].y())
            dx = max(-r0.x(), min(d.w - (r0.x() + r0.width()), dx))
            dy = max(-r0.y(), min(d.h - (r0.y() + r0.height()), dy))
            self.r = r0.translated(dx, dy)
        else:
            i, r0 = self.drag[1], self.drag[2]
            x0, y0, x1, y1 = r0.x(), r0.y(), r0.x() + r0.width(), r0.y() + r0.height()
            if self.ratio and i < 4:  # hoek met vaste verhouding: tegenoverliggende hoek blijft staan
                ax, ay = [(x1, y1), (x0, y1), (x0, y0), (x1, y0)][i]
                self.r = self._corner_ratio(ax, ay, p.x(), p.y(), self.ratio).toRect().intersected(d.rect())
            elif self.ratio:  # zijde met vaste verhouding: de andere maat groeit mee rond het midden
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                if i in (4, 6):
                    h = abs((y1 if i == 4 else y0) - p.y())
                    w = h * self.ratio
                    top = p.y() if i == 4 else y0
                    self.r = QRectF(cx - w / 2, min(top, top + h), w, h).toRect().intersected(d.rect())
                else:
                    w = abs((x1 if i == 7 else x0) - p.x())
                    h = w / self.ratio
                    left = p.x() if i == 7 else x0
                    self.r = QRectF(left, cy - h / 2, w, h).toRect().intersected(d.rect())
            else:
                px, py = int(p.x()), int(p.y())
                if i in (0, 3, 7):
                    x0 = px
                if i in (1, 2, 5):
                    x1 = px
                if i in (0, 1, 4):
                    y0 = py
                if i in (2, 3, 6):
                    y1 = py
                self.r = QRect(min(x0, x1), min(y0, y1), max(1, abs(x1 - x0)), max(1, abs(y1 - y0)))
        self._to_spins()
        cv.update()
        if self.r is not None:
            self.main.statusBar().showMessage(f"Bijsnijden: {self.r.width()} × {self.r.height()} px")

    def release(self, cv, pt, ev):
        if self.drag and self.drag[0] == "new" and (self.r is None or self.r.width() < 2 or self.r.height() < 2):
            self.r = None
        self.drag = None
        self._to_spins()
        self._place_bar(cv)
        cv.update()

    def double_click(self, cv, pt, ev):
        if self.r is not None and QRectF(self.r).contains(pt):  # dubbelklik in het kader, zoals PSP
            self.apply(cv)

    def apply(self, cv):
        if cv is None or self.r is None or self.r.width() < 1 or self.r.height() < 1:
            return
        cv.doc.crop(self.r)
        self.r = None
        self._to_spins()
        self._hide_bars()

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
            self._hide_bars()
            return
        full = QRectF(cv.to_widget(QPointF(0, 0)), cv.to_widget(QPointF(cv.doc.w, cv.doc.h)))
        hs = self._handles(cv)
        inner = QRectF(hs[0], hs[2])
        vs = getattr(cv, "view", None) or {}
        if vs.get("shade", True):  # buiten het kader gearceerd (kleur en dekking uit de voorkeuren)
            path = QPainterPath()
            path.addRect(full)
            path.addRect(inner)
            c = QColor(vs.get("shade_color", "#000000"))
            c.setAlpha(round(255 * vs.get("shade_opacity", 35) / 100))
            p.fillPath(path, c)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 160), 3))
        p.drawRect(inner)
        p.setPen(QPen(QColor(235, 235, 235), 1))
        p.drawRect(inner)
        k = self.HANDLE
        for h in hs:  # holle vierkantjes, zoals PSP
            sq = QRectF(h.x() - k, h.y() - k, 2 * k, 2 * k)
            p.setPen(QPen(QColor(0, 0, 0, 180), 3))
            p.drawRect(sq)
            p.setPen(QPen(QColor(240, 240, 240), 1))
            p.drawRect(sq)
        if self.drag is None:
            self._place_bar(cv)

    def deactivate(self):
        self.r = None
        self.drag = None
        self._hide_bars()


# ================================================================ vormen
class ShapeBase(Tool):
    snaps = True  # punten uitlijnen op raster en hulplijnen (als dat aan staat)
    """Teken een vorm op de actieve laag. Rand: voorgrondkleur, vulling: achtergrondkleur (zoals PSP)."""
    tip = "Sleep om te tekenen. Rand: voorgrondkleur, vulling: achtergrondkleur. Shift: gelijke zijden"
    from_center = False

    def __init__(self, main):
        super().__init__(main)
        self.a = None

    vector_ok = True

    def common(self):
        m = self.main
        return (spin(m, "line_width", "Lijnbreedte:", 0, 200) + check(m, "antialias", "Anti-alias")
                + check(m, "shape_vector", "Op vector maken"))

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
        span = path.boundingRect().toAlignedRect()  # verloop loopt over de vorm
        if (not self.main.fg_none or not self.fillable) and lw > 0:
            pen = QPen(self.main.material_brush(True, span) or QBrush(self.main.fg), lw)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            p.setPen(pen)
        else:
            p.setPen(Qt.PenStyle.NoPen)
        if not self.main.bg_none and self.fillable:
            p.setBrush(self.main.material_brush(False, span) or QBrush(self.main.bg))
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.end()
        paint_layer(d.layer(), r, local, d.sel)
        d.changed.emit(r)
        self.last_path = path

    fillable = True
    last_path = None

    def release(self, cv, pt, ev):
        if self.a is None:
            return
        d = cv.doc
        if self.prev_rect.isEmpty():
            d.drop_last_undo()
        elif self.last_path is not None and (d.layer().vector is not None or self.o["shape_vector"]):
            # als bewerkbaar vectorobject: de voorbeeldpixels weghalen en een object maken
            from . import vectorlayer as V
            d.layer().image = self.base
            layer = d.layer() if d.layer().vector is not None else d.new_vector_layer(undo=False)
            lw = self.o["line_width"]
            stroke = V.color_list(self.main.fg, (self.main.fg_none and self.fillable) or lw <= 0)
            fill = V.color_list(self.main.bg, self.main.bg_none or not self.fillable)
            for nodes, closed in V.path_to_nodes(self.last_path):
                layer.vector.append(V.make_object(nodes, closed, stroke, fill, lw, 0, 0, 15, self.o["antialias"]))
            d.render_vector(layer)
            d.changed.emit(QRect())
        self.a = None
        self.base = None
        self.last_path = None
        d.structureChanged.emit()


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
        from . import userdata
        return combo(self.main, "preset", "Vorm:", self.SHAPES + userdata.shape_names()) + self.common()

    def path(self, a, b):
        r = QRectF(a, b).normalized()
        x, y, w, h = r.x(), r.y(), r.width(), r.height()
        if self.o["preset"] >= len(self.SHAPES):  # eigen vorm (Bestand > Exporteren > Vorm)
            from . import userdata
            names = userdata.shape_names()
            k = self.o["preset"] - len(self.SHAPES)
            p = userdata.shape_path(names[k], x, y, w, h) if k < len(names) else None
            if p is not None:
                return p

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


class PenTool(Tool):
    snaps = True  # punten uitlijnen op raster en hulplijnen (als dat aan staat)
    """Pen: lijnen, polylijnen, Bézier-krommen (punt tot punt) en vrije lijnen. De lijn blijft
    bewerkbaar (knooppunten en handvatten verslepen) tot Toepassen; dan wordt hij op de laag getekend.
    Rand: voorgrondmateriaal; gesloten paden worden gevuld met het achtergrondmateriaal."""
    cid, glyph = 0xd110, "✒"
    context_menu = True  # rechtsklik: het snelmenu van de Pen (de rechterknop tekent niet)
    vector_ok = True  # mag op een vectorlaag werken zonder die eerst om te zetten
    MODES = ["Bewerken", "Lijnen en polylijnen", "Punt tot punt (Bézier-krommen)", "Uit de vrije hand"]
    STYLES = ["Effen", "Streepjes", "Puntjes", "Streep-punt", "Streep-punt-punt"]
    JOINS = ["Verstek", "Rond", "Schuin"]
    TIPS = ["Versleep knooppunten en handvatten; Ctrl + slepen vanaf een knooppunt maakt er een kromme van. "
            "Delete verwijdert het gekozen knooppunt.",
            "Klik of sleep voor rechte lijnen; Shift: stappen van 45°.",
            "Bézier-krommen: klik voor een hoekpunt, houd ingedrukt en sleep voor een kromme. Klik op het eerste punt om te sluiten.",
            "Teken met ingedrukte muisknop; Tracking bepaalt hoe glad de lijn wordt."]
    HANDLE = 4

    def __init__(self, main):
        super().__init__(main)
        self.paths = []      # [{"nodes": [[punt, in, uit], ...], "closed": bool}]
        self.cur = None      # pad waaraan nu getekend wordt
        self.doc = None
        self.drag = None
        self.sel = None      # (pad, knooppunt) gekozen in Bewerken (het laatst aangeklikte)
        self.nsel = set()    # alle geselecteerde knooppunten {(pad, knooppunt)}
        self.free = None
        self.rubber = None
        self.target = None   # vectorlaag waar opgepakte objecten vandaan kwamen
        self.picked = None   # (laag, originele objecten) om met Esc terug te zetten

    @property
    def tip(self):
        from .i18n import tr
        return tr(self.TIPS[self.o["pen_mode"]]) + " " + tr("Enter of Toepassen: op de laag zetten; Esc: weggooien")

    def options(self):
        m = self.main
        return (button("✓ Toepassen", lambda: self.apply()) + combo(m, "pen_mode", "Modus:", self.MODES)
                + spin(m, "pen_tracking", "Tracking:", 0, 50)
                + check(m, "pen_connect", "Segmenten verbinden") + check(m, "pen_nodes", "Knooppunten tonen")
                + check(m, "pen_vector", "Op vector maken")
                + combo(m, "pen_style", "Lijnstijl:", self.STYLES) + spin(m, "line_width", "Breedte:", 0, 200)
                + check(m, "antialias", "Anti-alias") + combo(m, "pen_join", "Verbinding:", self.JOINS)
                + spin(m, "pen_miter", "Verstek:", 1, 50))

    # ---------------------------------------------------------------- pad
    def _start(self, pt):
        self.cur = {"nodes": [[QPointF(pt), None, None]], "closed": False, "types": {}}
        self.paths.append(self.cur)

    def qpath(self, sub):
        n = sub["nodes"]
        path = QPainterPath(n[0][0])
        segs = list(zip(n, n[1:])) + ([(n[-1], n[0])] if sub["closed"] and len(n) > 2 else [])
        for a, b in segs:
            c1 = a[2] if a[2] is not None else a[0]
            c2 = b[1] if b[1] is not None else b[0]
            if a[2] is None and b[1] is None:
                path.lineTo(b[0])
            else:
                path.cubicTo(c1, c2, b[0])
        if sub["closed"] and len(n) > 2:
            path.closeSubpath()
        return path

    def _pen(self, span):
        o = self.o
        lw = o["line_width"]
        if lw <= 0 or self.main.fg_none:
            return QPen(Qt.PenStyle.NoPen)
        br = self.main.material_brush(True, span) or QBrush(self.main.fg)
        pen = QPen(br, lw)
        pen.setStyle([Qt.PenStyle.SolidLine, Qt.PenStyle.DashLine, Qt.PenStyle.DotLine, Qt.PenStyle.DashDotLine,
                      Qt.PenStyle.DashDotDotLine][o["pen_style"]])
        pen.setJoinStyle([Qt.PenJoinStyle.MiterJoin, Qt.PenJoinStyle.RoundJoin, Qt.PenJoinStyle.BevelJoin][o["pen_join"]])
        pen.setMiterLimit(o["pen_miter"])
        pen.setCapStyle(Qt.PenCapStyle.RoundCap if o["pen_join"] == 1 else Qt.PenCapStyle.FlatCap)
        return pen

    def _paint_paths(self, p):
        if getattr(self, "compound", False) and len(self.paths) > 1:  # samengesteld: gaten blijven open
            path = QPainterPath()
            path.setFillRule(Qt.FillRule.OddEvenFill)
            for sub in self.paths:
                if len(sub["nodes"]) >= 2:
                    path.addPath(self.qpath(sub))
            span = path.boundingRect().toAlignedRect()
            fill = any(sub["closed"] for sub in self.paths) and not self.main.bg_none
            p.setBrush((self.main.material_brush(False, span) or QBrush(self.main.bg)) if fill else Qt.BrushStyle.NoBrush)
            p.setPen(self._pen(span))
            p.drawPath(path)
            return
        for sub in self.paths:
            if len(sub["nodes"]) < 2:
                continue
            path = self.qpath(sub)
            span = path.boundingRect().toAlignedRect()
            fill = sub["closed"] and not self.main.bg_none
            p.setBrush((self.main.material_brush(False, span) or QBrush(self.main.bg)) if fill else Qt.BrushStyle.NoBrush)
            p.setPen(self._pen(span))
            p.drawPath(path)

    def apply(self, cv=None):
        """Het pad toepassen: op een vectorlaag als bewerkbaar object, anders als pixels op de laag."""
        from . import vectorlayer as V
        d = self.doc
        drawn = [s_ for s_ in self.paths if len(s_["nodes"]) >= 2]
        target, picked = self.target, self.picked
        compound, keep = getattr(self, "compound", False), dict(getattr(self, "keep_props", {}))
        self.compound, self.keep_props = False, {}
        self.paths, self.cur, self.sel, self.drag, self.free, self.rubber = [], None, None, None, None, None
        self.nsel = set()
        self.target = self.picked = None
        cv = self.main.canvas()
        if d is None:
            return
        if not drawn and picked is None:
            if cv:
                cv.update()
            return
        layer = target if target is not None and target in d.layers else d.layer()
        if layer.kind == "group" or layer.adjust is not None:
            if cv:
                cv.update()
            return
        if picked is None:  # bij opgepakte objecten is ongedaan maken al vastgelegd
            d.push_undo(self.name)
        if layer.vector is None and self.o["pen_vector"]:
            layer = d.new_vector_layer(undo=False)
        if layer.vector is not None:
            o = self.o
            lw = o["line_width"]
            objs = [V.make_object(
                sub_["nodes"], sub_["closed"], V.color_list(self.main.fg, self.main.fg_none or lw <= 0),
                V.color_list(self.main.bg, self.main.bg_none), lw, o["pen_style"], o["pen_join"],
                o["pen_miter"], o["antialias"]) for sub_ in drawn]
            if compound and len(objs) > 1:  # weer één samengesteld object
                first = objs[0]
                first["more"] = [{"nodes": ob["nodes"], "closed": ob["closed"]} for ob in objs[1:]]
                objs = [first]
            for ob in objs:
                ob.update(keep)
            layer.vector.extend(objs)
            d.render_vector(layer)
        else:
            self.paths = drawn
            p = QPainter(layer.image)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, self.o["antialias"])
            if d.sel is not None:  # alleen binnen de selectie
                tmp = new_image(d.w, d.h)
                q = QPainter(tmp)
                q.setRenderHint(QPainter.RenderHint.Antialiasing, self.o["antialias"])
                self._paint_paths(q)
                q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                q.drawImage(0, 0, QImage(d.sel))
                q.end()
                p.drawImage(0, 0, tmp)
            else:
                self._paint_paths(p)
            p.end()
            self.paths = []
        d.changed.emit(QRect())
        d.structureChanged.emit()
        if cv:
            cv.update()

    def commit_pending(self):
        if self.paths or self.picked is not None:
            self.apply()

    def pick_up(self, cv, pt):
        """Bewerken: een bestaand object op de actieve vectorlaag oppakken om het opnieuw te bewerken."""
        from . import vectorlayer as V
        d = cv.doc
        layer = d.layer()
        if layer.vector is None or self.paths:
            return False
        tol = 4 / cv.zoom
        for i in range(len(layer.vector) - 1, -1, -1):  # bovenste object eerst
            obj = layer.vector[i]
            if V.hit(obj, pt, tol):
                d.push_undo("Vector bewerken")
                self.picked = (layer, [V.copy_vector(obj)])
                del layer.vector[i]
                d.render_vector(layer)
                d.changed.emit(QRect())
                self.target = layer
                self.paths = [{"nodes": [[V._pt(q[0]), V._pt(q[1]), V._pt(q[2])] for q in nodes],
                               "closed": closed, "types": {}} for nodes, closed in V.contours(obj)]
                self.nsel = set()
                # samengesteld object (meerdere contouren) blijft bij toepassen één object; naam en groep blijven
                self.compound = len(self.paths) > 1
                self.keep_props = {k: obj[k] for k in ("name", "group") if k in obj}
                self.cur = None
                # kleuren en lijninstellingen van het object overnemen, zodat ze aan te passen zijn
                m = self.main
                if obj.get("stroke") is not None:
                    m.set_color(QColor(*obj["stroke"]), True)
                m.set_none(True, obj.get("stroke") is None)
                if obj.get("fill") is not None:
                    m.set_color(QColor(*obj["fill"]), False)
                m.set_none(False, obj.get("fill") is None)
                m.opts.update(line_width=int(round(obj["width"])), pen_style=obj.get("style", 0),
                              pen_join=obj.get("join", 0), pen_miter=int(obj.get("miter", 15)),
                              antialias=obj.get("aa", True))
                if hasattr(m, "_build_options"):
                    m._build_options(self)  # optiebalk bijwerken (zonder het gereedschap opnieuw te kiezen)
                return True
        return False

    def restore_picked(self):
        """Esc na oppakken: het object ongewijzigd terugzetten."""
        layer, objs = self.picked
        layer.vector.extend(objs)
        self.doc.render_vector(layer)
        self.doc.changed.emit(QRect())
        self.picked = self.target = None

    def _ensure_doc(self, cv):
        if self.doc is not cv.doc:
            if self.paths or self.picked is not None:
                self.apply()
            self.doc = cv.doc

    # ---------------------------------------------------------------- muis
    def _hit(self, cv, pt):
        """Knooppunt of handvat onder de muis: (pad, knooppunt, 0 punt / 1 in / 2 uit)."""
        tol = (self.HANDLE + 3) / cv.zoom
        for pi, sub in enumerate(self.paths):
            for ni, node in enumerate(sub["nodes"]):
                for k in (1, 2, 0):
                    q = node[k]
                    if q is not None and abs(q.x() - pt.x()) <= tol and abs(q.y() - pt.y()) <= tol:
                        return pi, ni, k
        return None

    def constrain(self, a, b, ev):
        if ev.modifiers() & SHIFT:
            ang = round(math.atan2(b.y() - a.y(), b.x() - a.x()) / (math.pi / 4)) * math.pi / 4
            ln = math.hypot(b.x() - a.x(), b.y() - a.y())
            return QPointF(a.x() + ln * math.cos(ang), a.y() + ln * math.sin(ang))
        return b

    def press(self, cv, pt, ev):
        if ev.button() != LB:
            return
        self._ensure_doc(cv)
        mode = self.o["pen_mode"]
        hit = self._hit(cv, pt)
        if mode == 0 and hit is None and not self.paths and self.pick_up(cv, pt):
            cv.update()
            return
        if mode == 0 or (hit is not None and hit[2] != 0):
            if hit is not None:
                key = (hit[0], hit[1])
                if hit[2] == 0 and ev.modifiers() & SHIFT:  # Shift: knooppunt erbij of eraf
                    self.nsel ^= {key}
                    self.sel = key if key in self.nsel else None
                    cv.update()
                    return
                if key not in self.nsel:
                    self.nsel = {key}
                self.sel = key
                if hit[2] == 0 and ev.modifiers() & CTRL:
                    # Ctrl + slepen vanaf een knooppunt: handvatten eruit trekken (hoekpunt wordt kromme)
                    node = self.paths[hit[0]]["nodes"][hit[1]]
                    node[1] = node[2] = QPointF(node[0])
                    self.paths[hit[0]].setdefault("types", {})[hit[1]] = "sym"
                    self.drag = ("edit", (hit[0], hit[1], 2), QPointF(pt))
                else:
                    self.drag = ("edit", hit, QPointF(pt))
            elif mode == 0 and self.paths:
                # kader slepen om knooppunten te selecteren (Shift: erbij)
                if not ev.modifiers() & SHIFT:
                    self.sel, self.nsel = None, set()
                self.drag = ("rubber", QPointF(pt), QPointF(pt))
            else:
                self.sel, self.nsel = None, set()
            cv.update()
            return
        if mode == 2 and self.cur is not None and hit is not None and self.paths[hit[0]] is self.cur \
                and hit[1] == 0 and len(self.cur["nodes"]) > 2:
            self.cur["closed"] = True  # klik op het eerste punt: pad sluiten
            self.cur = None
            cv.update()
            return
        connect = self.o["pen_connect"] and self.cur is not None and not self.cur["closed"]
        if mode == 1:
            if not connect:
                self._start(pt)
            start = self.cur["nodes"][-1][0]
            self.rubber = (start, QPointF(pt))
            self.drag = ("line", start)
        elif mode == 2:
            if not connect:
                self._start(pt)
            else:
                self.cur["nodes"].append([QPointF(pt), None, None])
            self.drag = ("curve", len(self.cur["nodes"]) - 1)
        else:
            self.free = [QPointF(pt)]
            self.drag = ("free",)
        cv.update()

    def move(self, cv, pt, ev):
        if not self.drag or not (ev.buttons() & LB):
            return
        kind = self.drag[0]
        if kind == "edit":
            (pi, ni, k), start = self.drag[1], self.drag[2]
            node = self.paths[pi]["nodes"][ni]
            d = pt - start
            if k == 0:  # knooppunt (en de andere geselecteerde) met handvatten mee verplaatsen
                for qi, qn in (self.nsel if (pi, ni) in self.nsel else {(pi, ni)}):
                    nd = self.paths[qi]["nodes"][qn]
                    for j in range(3):
                        if nd[j] is not None:
                            nd[j] = nd[j] + d
            else:  # handvat: het andere handvat volgt volgens het knooppunttype
                from . import penops
                penops.drag_handle(self.paths[pi], ni, k, node[k] + d)
            self.drag = ("edit", (pi, ni, k), QPointF(pt))
        elif kind == "rubber":
            self.drag = ("rubber", self.drag[1], QPointF(pt))
        elif kind == "line":
            self.rubber = (self.drag[1], self.constrain(self.drag[1], pt, ev))
        elif kind == "curve":
            node = self.cur["nodes"][self.drag[1]]
            node[2] = QPointF(pt)
            node[1] = node[0] * 2 - pt
        elif kind == "free":
            self.free.append(QPointF(pt))
        cv.update()

    def release(self, cv, pt, ev):
        if not self.drag:
            return
        kind = self.drag[0]
        if kind == "rubber":
            r = QRectF(self.drag[1], self.drag[2]).normalized()
            self.nsel |= {(pi, ni) for pi, sub in enumerate(self.paths) for ni, n in enumerate(sub["nodes"])
                          if r.contains(n[0])}
            self.sel = next(iter(self.nsel), None)
            self.drag = None
            cv.update()
            return
        if kind == "line":
            a, b = self.rubber
            if math.hypot(b.x() - a.x(), b.y() - a.y()) >= 1:
                self.cur["nodes"].append([QPointF(b), None, None])
            elif len(self.cur["nodes"]) == 1 and not self.o["pen_connect"]:
                pass  # alleen geklikt: beginpunt; volgende klik maakt de lijn
            self.rubber = None
        elif kind == "curve":
            node = self.cur["nodes"][self.drag[1]]
            if node[2] is not None and math.hypot(node[2].x() - node[0].x(), node[2].y() - node[0].y()) < 2:
                node[1] = node[2] = None  # alleen geklikt: hoekpunt
        elif kind == "free" and self.free and len(self.free) > 1:
            pts = self._simplify(self.free, max(0.5, self.o["pen_tracking"] / 4))
            if self.o["pen_connect"] and self.cur is not None and not self.cur["closed"]:
                self.cur["nodes"] += [[q, None, None] for q in pts]
            else:
                self.cur = {"nodes": [[q, None, None] for q in pts], "closed": False}
                self.paths.append(self.cur)
            self.free = None
        self.drag = None
        cv.update()

    @staticmethod
    def _simplify(pts, tol):
        """Ramer-Douglas-Peucker: minder punten, zelfde vorm (Tracking)."""
        if len(pts) < 3:
            return list(pts)
        a, b = pts[0], pts[-1]
        dx, dy = b.x() - a.x(), b.y() - a.y()
        ln = math.hypot(dx, dy) or 1e-9
        best, idx = -1.0, 0
        for i in range(1, len(pts) - 1):
            q = pts[i]
            dist = abs(dy * q.x() - dx * q.y() + b.x() * a.y() - b.y() * a.x()) / ln
            if dist > best:
                best, idx = dist, i
        if best <= tol:
            return [a, b]
        left = PenTool._simplify(pts[:idx + 1], tol)
        return left[:-1] + PenTool._simplify(pts[idx:], tol)

    def double_click(self, cv, pt, ev):
        # lijn afsluiten: de volgende klik begint een nieuw pad
        if self.o["pen_mode"] == 2 and self.cur is not None and len(self.cur["nodes"]) > 1:
            last = self.cur["nodes"][-1]
            prev = self.cur["nodes"][-2]
            if math.hypot(last[0].x() - prev[0].x(), last[0].y() - prev[0].y()) < 2:
                self.cur["nodes"].pop()  # dubbelklik voegde een extra punt toe
        self.cur = None
        cv.update()

    def key(self, cv, ev):
        k = ev.key()
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.apply()
            return True
        if k == Qt.Key.Key_Escape and (self.paths or self.picked is not None):
            self.paths, self.cur, self.sel, self.nsel = [], None, None, set()
            if self.picked is not None:
                self.restore_picked()
            cv.update()
            return True
        if k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and not self.nsel and self.picked is not None:
            # opgepakt object zonder gekozen knooppunt: het hele object verwijderen
            layer = self.picked[0]
            self.paths, self.cur, self.picked, self.target = [], None, None, None
            self.doc.render_vector(layer)
            self.doc.changed.emit(QRect())
            self.doc.structureChanged.emit()
            cv.update()
            return True
        if k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.nsel:
            self.delete_nodes()
            cv.update()
            return True
        return False

    # ---------------------------------------------------------------- snelmenu (zoals PSP)
    def delete_nodes(self):
        """Geselecteerde knooppunten verwijderen; een pad met minder dan twee punten verdwijnt."""
        for pi in sorted({p for p, _ in self.nsel}, reverse=True):
            sub = self.paths[pi]
            for ni in sorted((n for p, n in self.nsel if p == pi), reverse=True):
                del sub["nodes"][ni]
            sub["types"] = {}
            if len(sub["nodes"]) < 2:
                self.paths.pop(pi)
        if self.cur is not None and self.cur not in self.paths:
            self.cur = None
        self.sel, self.nsel = None, set()

    def _sel_paths(self):
        """Paden met geselecteerde knooppunten (of alle paden als er niets geselecteerd is)."""
        return sorted({p for p, _ in self.nsel}) or list(range(len(self.paths)))

    def _all_nodes(self):
        return {(pi, ni) for pi, sub in enumerate(self.paths) for ni in range(len(sub["nodes"]))}

    def _structure(self, new_paths):
        """Na samenvoegen/onderbreken/verbinden: nieuwe paden, selectie leeg."""
        if new_paths is None:
            self.main.statusBar().showMessage(tr("Kies twee eindpunten van open paden."), 4000)
            return
        self.paths = new_paths
        self.cur = None
        self.sel, self.nsel = None, set()

    def pen_command(self, name, cv=None):
        from . import penops as O
        sel = sorted(self.nsel)
        if name == "cut":
            self.pen_command("copy")
            keep = set(self._sel_paths())
            self.paths = [p for i, p in enumerate(self.paths) if i not in keep]
            self.sel, self.nsel, self.cur = None, set(), None
        elif name == "copy":
            PenTool.clipboard = O.clone_paths([self.paths[i] for i in self._sel_paths()])
        elif name == "paste":
            if PenTool.clipboard:
                self.paths, new = O.duplicate(self.paths + O.clone_paths(PenTool.clipboard), [], QPointF(0, 0))
                start = len(self.paths) - len(PenTool.clipboard)
                self.nsel = {(pi, ni) for pi in range(start, len(self.paths)) for ni in range(len(self.paths[pi]["nodes"]))}
        elif name == "delete":
            self.delete_nodes()
        elif name == "select_all":
            self.nsel = self._all_nodes()
        elif name == "select_none":
            self.nsel, self.sel = set(), None
        elif name == "invert":
            self.nsel = self._all_nodes() - self.nsel
        elif name in ("join", "merge"):
            if len(sel) == 2:
                self._structure((O.join if name == "join" else O.merge)(self.paths, sel[0], sel[1]))
            else:
                self._structure(None)
        elif name == "break":
            for pi, ni in sorted(sel, reverse=True):
                self.paths = O.break_at(self.paths, pi, ni)
            self.sel, self.nsel, self.cur = None, set(), None
        elif name == "close":
            for pi in self._sel_paths():
                if len(self.paths[pi]["nodes"]) > 2:
                    self.paths[pi]["closed"] = True
        elif name == "reverse_contour":
            for pi in self._sel_paths():
                O.reverse_contour(self.paths[pi])
            self.nsel = set()
        elif name == "reverse_path":
            for p in self.paths:
                O.reverse_contour(p)
            self.paths.reverse()
            self.nsel = set()
        elif name in ("duplicate", "duplicate_offset"):
            off = QPointF(10, 10) if name == "duplicate_offset" else QPointF(0, 0)
            self.paths, new = O.duplicate(self.paths, self._sel_paths(), off)
            self.nsel = {(pi, ni) for pi in new for ni in range(len(self.paths[pi]["nodes"]))}
        elif name in O.TYPES:
            for pi, ni in sel:
                O.set_type(self.paths[pi], ni, name)
        elif name in ("to_line", "line_before", "line_after", "curve_before", "curve_after"):
            for pi, ni in sel:
                getattr(O, name)(self.paths[pi], ni)
        elif name in ("flip", "mirror", "contract", "expand"):
            O.transform_nodes(self.paths, sel, O.transforms()[name])
        elif name in ("rotate", "skew_x", "skew_y"):
            label = {"rotate": "Hoek (graden):", "skew_x": "Schuintrekken X (graden):",
                     "skew_y": "Schuintrekken Y (graden):"}[name]
            val, ok = QInputDialog.getDouble(self.main, tr({"rotate": "Roteren", "skew_x": "Schuintrekken X",
                                                            "skew_y": "Schuintrekken Y"}[name]), tr(label),
                                             15.0, -360.0, 360.0, 1)
            if ok:
                t = O.rotate(val) if name == "rotate" else O.skew(val, 0) if name == "skew_x" else O.skew(0, val)
                O.transform_nodes(self.paths, sel, t)
        self.sel = self.sel if self.sel in self.nsel else next(iter(self.nsel), None)
        (cv or self.main.canvas()).update()

    clipboard = []  # gekopieerde paden (gedeeld tussen afbeeldingen)

    def command_state(self):
        """Welke knooppuntopdrachten nu kunnen: {naam: bool}."""
        has, n = bool(self.paths), len(self.nsel)
        st = {k: has for k in ("cut", "copy", "select_all", "invert", "close", "reverse_contour", "reverse_path",
                               "duplicate_offset", "duplicate")}
        st.update(paste=bool(PenTool.clipboard), delete=n > 0, select_none=n > 0, join=n == 2, merge=n == 2,
                  **{k: n > 0 for k in ("break", "asym", "sym", "cusp", "smooth", "to_line", "line_before",
                                        "line_after", "curve_before", "curve_after")},
                  **{k: n > 1 for k in ("flip", "mirror", "rotate", "skew_x", "skew_y", "contract", "expand")})
        return st

    # snelmenu: dezelfde opdrachten als Objecten > Bewerken, Tekenpunttype en Geselecteerde tekenpunten
    # transformeren (zelfde woorden en vertalingen)
    MENU = [("Be&werken", [0x1770, 0x1771, 0x1772, 0x1773, None, 0x1774, 0x1775, 0x1776, None, 0x1777, 0x1778,
                           0x1779, 0x177a, 0x177b, 0x177c, None, 0x177d, 0x177e]),
            ("&Tekenpunttype", [0x177f, 0x1780, 0x1781, 0x1782, None, 0x1783, 0x1784, 0x1785, None, 0x1786, 0x1787]),
            ("&Geselecteerde tekenpunten transformeren", [0x1788, 0x1789, 0x178a, 0x178b, 0x178c, None, 0x178d,
                                                          0x178e])]

    def build_context_menu(self, cv, m):
        """Snelmenu van de Pen zoals in PSP. Alleen als er lijnen zijn (of iets gekopieerd is); anders het
        gewone menu van de afbeelding."""
        if not self.paths and not PenTool.clipboard:
            return False
        self.main.update_node_actions()
        acts = self.main.actions_by_id
        for title, ids in self.MENU:
            sub = m.addMenu(tr(title))
            for cid in ids:
                if cid is None:
                    sub.addSeparator()
                elif cid in acts:
                    sub.addAction(acts[cid])
        m.addSeparator()
        m.addAction(tr("Pad toepassen"), lambda: self.main._run(self.apply)).setEnabled(bool(self.paths))
        return True

    def make_smooth(self, pi, ni):
        """Knooppunt vloeiend maken: handvatten in de richting van de buren (een derde van de afstand)."""
        sub = self.paths[pi]
        n = sub["nodes"]
        node = n[ni]
        prev = n[ni - 1] if ni > 0 or sub["closed"] else None
        nxt = n[(ni + 1) % len(n)] if ni < len(n) - 1 or sub["closed"] else None
        a = prev[0] if prev is not None else node[0]
        b = nxt[0] if nxt is not None else node[0]
        dx, dy = b.x() - a.x(), b.y() - a.y()
        ln = math.hypot(dx, dy) or 1.0
        ux, uy = dx / ln, dy / ln
        lin = math.hypot(node[0].x() - a.x(), node[0].y() - a.y()) / 3 or ln / 6
        lout = math.hypot(b.x() - node[0].x(), b.y() - node[0].y()) / 3 or ln / 6
        node[1] = QPointF(node[0].x() - ux * lin, node[0].y() - uy * lin)
        node[2] = QPointF(node[0].x() + ux * lout, node[0].y() + uy * lout)

    def make_corner(self, pi, ni):
        node = self.paths[pi]["nodes"][ni]
        node[1] = node[2] = None

    def context_actions(self, cv):
        acts = [("Pad toepassen", self.apply)] if self.paths else []
        if self.sel is not None:
            pi, ni = self.sel
            sub = self.paths[pi]
            acts.append(("Vloeiend knooppunt", lambda: (self.make_smooth(pi, ni), cv.update())))
            acts.append(("Hoekpunt", lambda: (self.make_corner(pi, ni), cv.update())))
            acts.append(("Pad openen" if sub["closed"] else "Pad sluiten",
                         lambda: (sub.__setitem__("closed", not sub["closed"]), cv.update())))
        return acts

    def hover_cursor(self, cv, pt):
        if self._hit(cv, pt) is not None:
            return Qt.CursorShape.SizeAllCursor
        layer = cv.doc.layer()
        if self.o["pen_mode"] == 0 and not self.paths and layer.vector:
            from . import vectorlayer as V
            if any(V.hit(o, pt, 4 / cv.zoom) for o in layer.vector):
                return Qt.CursorShape.PointingHandCursor  # klikken pakt dit object op
        return None

    def overlay(self, cv, p):
        if cv.doc is not self.doc and self.doc is not None:
            return
        p.save()
        p.setTransform(cv.transform())
        p.setRenderHint(QPainter.RenderHint.Antialiasing, self.o["antialias"])
        self._paint_paths(p)  # voorbeeld zoals het op de laag komt
        p.restore()
        if self.rubber:
            a, b = (cv.to_widget(q) for q in self.rubber)
            pen = self._pen(QRect())
            if pen.style() != Qt.PenStyle.NoPen:
                pen.setWidthF(pen.widthF() * cv.zoom)
            p.setPen(pen)
            p.drawLine(a, b)
        if self.free and len(self.free) > 1:
            p.setPen(QPen(QColor(0, 0, 0), 1))
            p.drawPolyline(QPolygonF([cv.to_widget(q) for q in self.free]))
        if self.drag and self.drag[0] == "rubber":
            r = QRectF(cv.to_widget(self.drag[1]), cv.to_widget(self.drag[2])).normalized()
            path = QPainterPath()
            path.addRect(r)
            draw_dashed(p, path)
        if not self.o["pen_nodes"]:
            return
        h = self.HANDLE
        for pi, sub in enumerate(self.paths):
            for ni, (pt_, cin, cout) in enumerate(sub["nodes"]):
                c = cv.to_widget(pt_)
                for hnd in (cin, cout):
                    if hnd is not None:
                        q = cv.to_widget(hnd)
                        p.setPen(QPen(QColor(90, 140, 255), 1))
                        p.drawLine(c, q)
                        p.setBrush(QColor(90, 140, 255))
                        p.drawEllipse(q, 3, 3)
                chosen = (pi, ni) in self.nsel
                p.setPen(QPen(QColor(0, 0, 0), 1))
                p.setBrush(QColor(255, 80, 80) if chosen else (QColor(80, 220, 120) if ni == 0 else QColor(255, 255, 255)))
                p.drawRect(QRectF(c.x() - h, c.y() - h, 2 * h, 2 * h))

    def deactivate(self):
        # zoals het origineel: bij het wisselen van gereedschap wordt de lijn toegepast
        if self.paths or self.picked is not None:
            self.apply()
        self.drag = None


# ================================================================ tekst
class TextTool(Tool):
    snaps = True  # punten uitlijnen op raster en hulplijnen (als dat aan staat)
    context_menu = True
    cid, glyph = 0xd0f0, "A"
    tip = ("Klik om tekst te maken, of klik op bestaande tekst om die te bewerken. "
           "Vulling: achtergrondkleur, rand: voorgrondkleur")
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
        first = t if ("family" in t or not t.get("runs")) else t["runs"][0][0]  # eigen tekst: basis staat in t
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
        fill = t.get("fill") if ("fill" in t or not t.get("runs")) else t["runs"][0][2]
        stroke = t.get("stroke") if ("stroke" in t or not t.get("runs")) else t["runs"][0][1]
        if fill is not None:
            self.main.bg = QColor(*fill)
        if stroke is not None:
            self.main.fg = QColor(*stroke)
        self.main.bg_none = fill is None
        self.main.fg_none = False  # geen rand = lijnbreedte 0 in de optiebalk
        from .textlayer import mat_dict
        if t.get("mat_fg") and (t.get("fill_mat") or t.get("stroke_mat")):
            self.main.fg, self.main.bg = QColor(*t["mat_fg"]), QColor(*t["mat_bg"])
        self.main.fg_mat = mat_dict(t.get("stroke_mat"))
        self.main.bg_mat = mat_dict(t.get("fill_mat"))
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
                                  self.main.fg_none, self.main.bg_none, self.main.material(True), self.main.material(False))
            d.add_layer(layer, label="Tekst")
            self.layer, self.new = layer, True
            self.orig = None
            remember = self.main.settings.value("remember_text") == "true"
            text = self.main.settings.value("last_text", "") if remember else ""
        d.structureChanged.emit()
        self.dlg = TextEntryDialog(self.main, text, None if self.new else self.orig)
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
                     self.main.fg_none, self.main.bg_none, self.main.material(True), self.main.material(False))
        if old is not None:
            t["matrix"] = old.get("matrix", t["matrix"])
            for k in ("on_path", "path_offset"):  # tekst op een pad blijft op het pad
                if k in old:
                    t[k] = old[k]
        self.dlg.set_base(t)
        runs = self.dlg.runs(t)  # woorden met een eigen opmaak
        if runs:
            t["runs"] = runs
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
               CropTool, StraightenTool, PerspectiveTool, RedEyeTool, MakeoverTool, CloneTool, ScratchRemoverTool,
               ObjectRemoverTool, PaintBrushTool, AirbrushTool, OilBrushTool, MarkerTool, PaletteKnifeTool, ChalkTool, PastelTool, CrayonTool, ColoredPencilTool, WarpBrushTool, MeshWarpTool,
               LightenDarkenTool, DodgeTool, BurnTool, SmudgeTool, PushTool, SoftenTool, SharpenTool,
               EmbossTool, SaturationTool, HueTool, ChangeToTargetTool, ColorReplacerTool, EraserTool,
               BackgroundEraserTool, FillTool, ColorChangerTool, TextTool, PresetShapeTool, RectangleTool,
               EllipseTool, SymmetricShapeTool, PenTool]

PLACEHOLDER_GLYPHS = {0xd0e0: "🌸", 0xd138: "☝", 0xd139: "⌫"}


def create_tools(main):
    tools = {cls.cid: cls(main) for cls in IMPLEMENTED}
    for cid, glyph in PLACEHOLDER_GLYPHS.items():
        tools[cid] = PlaceholderTool(main, cid, glyph)
    return tools
