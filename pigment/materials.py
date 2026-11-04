"""Materialen palet en het venster Materiaaleigenschappen (kleurenring, stalen, RGB/HSL)."""
import math

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QConicalGradient, QImage, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QSpinBox, QTabWidget, QToolButton, QVBoxLayout, QWidget)

BASIC = [
    "#ff0000", "#800000", "#a00000", "#c00000", "#ff4040", "#ff8080", "#000000",
    "#ffff00", "#808000", "#a0a000", "#c0c000", "#ffff40", "#ffff80", "#202020",
    "#00ff00", "#008000", "#00a000", "#00c000", "#40ff40", "#80ff80", "#404040",
    "#00ffff", "#008080", "#00a0a0", "#00c0c0", "#40ffff", "#80ffff", "#606060",
    "#0000ff", "#000080", "#0000a0", "#0000c0", "#4040ff", "#8080ff", "#808080",
    "#ff00ff", "#800080", "#a000a0", "#c000c0", "#ff40ff", "#ff80ff", "#a0a0a0",
    "#ff8000", "#804000", "#a05000", "#c06000", "#ffa040", "#ffc080", "#c0c0c0",
    "#ffffff", "#f0e0c0", "#e0c0a0", "#c08060", "#a06040", "#603020", "#e0e0e0",
]


class ColorWheel(QWidget):
    """Kleurtoonring met een vierkant voor verzadiging (horizontaal) en waarde (verticaal)."""
    changed = Signal(QColor)

    def __init__(self, color):
        super().__init__()
        self.setFixedSize(190, 190)
        self.h, self.s, self.v = max(0.0, color.hsvHueF()), color.hsvSaturationF(), color.valueF()
        self.drag = None

    def set_color(self, c):
        if c.hsvSaturationF() > 0 and c.valueF() > 0:
            self.h = max(0.0, c.hsvHueF())
        self.s, self.v = c.hsvSaturationF(), c.valueF()
        self.update()

    def color(self):
        return QColor.fromHsvF(self.h % 1.0, self.s, self.v)

    def _geom(self):
        c = QPointF(self.width() / 2, self.height() / 2)
        R = min(self.width(), self.height()) / 2 - 2
        ring = 18
        sq = (R - ring - 4) * math.sqrt(2)
        return c, R, ring, QRectF(c.x() - sq / 2, c.y() - sq / 2, sq, sq)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c, R, ring, sq = self._geom()
        g = QConicalGradient(c, 0)
        for i in range(13):
            g.setColorAt(i / 12, QColor.fromHsvF((i / 12) % 1.0, 1, 1))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(c, R, R)
        p.setBrush(self.palette().window())
        p.drawEllipse(c, R - ring, R - ring)
        hor = QLinearGradient(sq.topLeft(), sq.topRight())
        hor.setColorAt(0, QColor(255, 255, 255))
        hor.setColorAt(1, QColor.fromHsvF(self.h % 1.0, 1, 1))
        p.fillRect(sq, hor)
        ver = QLinearGradient(sq.topLeft(), sq.bottomLeft())
        ver.setColorAt(0, QColor(0, 0, 0, 0))
        ver.setColorAt(1, QColor(0, 0, 0, 255))
        p.fillRect(sq, ver)
        a = self.h * 2 * math.pi
        hp = QPointF(c.x() + math.cos(a) * (R - ring / 2), c.y() - math.sin(a) * (R - ring / 2))
        sp = QPointF(sq.left() + self.s * sq.width(), sq.top() + (1 - self.v) * sq.height())
        p.setBrush(Qt.BrushStyle.NoBrush)
        for q in (hp, sp):
            p.setPen(QPen(QColor(0, 0, 0), 2))
            p.drawEllipse(q, 5, 5)
            p.setPen(QPen(QColor(255, 255, 255), 1))
            p.drawEllipse(q, 5, 5)

    def mousePressEvent(self, e):
        c, R, ring, sq = self._geom()
        pos = e.position()
        self.drag = "sq" if sq.contains(pos) else ("ring" if math.hypot(pos.x() - c.x(), pos.y() - c.y()) > R - ring - 4 else None)
        self.mouseMoveEvent(e)

    def mouseMoveEvent(self, e):
        if not self.drag:
            return
        c, R, ring, sq = self._geom()
        pos = e.position()
        if self.drag == "ring":
            self.h = (math.atan2(-(pos.y() - c.y()), pos.x() - c.x()) / (2 * math.pi)) % 1.0
        else:
            self.s = min(1, max(0, (pos.x() - sq.left()) / sq.width()))
            self.v = min(1, max(0, 1 - (pos.y() - sq.top()) / sq.height()))
        self.update()
        self.changed.emit(self.color())

    def mouseReleaseEvent(self, e):
        self.drag = None


class Swatch(QWidget):
    clicked = Signal()

    def __init__(self, color, size=QSize(16, 16)):
        super().__init__()
        self.color = QColor(color)
        self.setFixedSize(size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), self.color)
        p.setPen(QColor(90, 90, 90))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def mousePressEvent(self, e):
        self.clicked.emit()


class MaterialDialog(QDialog):
    def __init__(self, parent, color, title="Materiaaleigenschappen"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.prev = QColor(color)
        self.cur = QColor(color)
        self._busy = False
        outer = QHBoxLayout(self)
        tabs = QTabWidget()
        page = QWidget()
        tabs.addTab(page, "● Kleur")
        for name in ("◑ Verloop", "✣ Patroon"):
            tabs.addTab(QWidget(), name)
            tabs.setTabEnabled(tabs.count() - 1, False)
        v = QVBoxLayout(page)
        self.wheel = ColorWheel(color)
        self.wheel.changed.connect(self._from_wheel)
        v.addWidget(self.wheel, 0, Qt.AlignmentFlag.AlignHCenter)
        grid = QGridLayout()
        grid.setSpacing(1)
        for i, hexc in enumerate(BASIC):
            sw = Swatch(hexc)
            sw.clicked.connect(lambda c=hexc: self.set_color(QColor(c)))
            grid.addWidget(sw, i // 7, i % 7)
        gw = QWidget()
        gw.setLayout(grid)
        v.addWidget(gw, 0, Qt.AlignmentFlag.AlignHCenter)
        form = QGridLayout()
        self.sp = {}
        for i, (k, lbl) in enumerate([("r", "R:"), ("g", "G:"), ("b", "B:")]):
            self.sp[k] = self._spin()
            form.addWidget(QLabel(lbl), i, 0)
            form.addWidget(self.sp[k], i, 1)
        for i, (k, lbl) in enumerate([("h", "H:"), ("s", "S:"), ("l", "L:")]):
            self.sp[k] = self._spin()
            form.addWidget(QLabel(lbl), i, 2)
            form.addWidget(self.sp[k], i, 3)
        self.html = QLineEdit()
        self.html.setMaxLength(7)
        self.html.editingFinished.connect(self._from_html)
        form.addWidget(QLabel("HTML:"), 3, 2)
        form.addWidget(self.html, 3, 3)
        v.addLayout(form)
        outer.addWidget(tabs)
        side = QVBoxLayout()
        side.addStretch()
        side.addWidget(QLabel("Huidig:"))
        self.sw_cur = Swatch(color, QSize(80, 50))
        side.addWidget(self.sw_cur)
        side.addWidget(QLabel("Vorige:"))
        self.sw_prev = Swatch(color, QSize(80, 50))
        self.sw_prev.clicked.connect(lambda: self.set_color(self.prev))
        side.addWidget(self.sw_prev)
        side.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuleren")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        side.addWidget(bb)
        outer.addLayout(side)
        for k in "rgb":
            self.sp[k].valueChanged.connect(self._from_rgb)
        for k in "hsl":
            self.sp[k].valueChanged.connect(self._from_hsl)
        self.set_color(color)

    def _spin(self):
        s = QSpinBox()
        s.setRange(0, 255)
        return s

    def set_color(self, c, skip=None):
        if self._busy:
            return
        self._busy = True
        self.cur = QColor(c)
        if skip != "wheel":
            self.wheel.set_color(c)
        if skip != "rgb":
            self.sp["r"].setValue(c.red()); self.sp["g"].setValue(c.green()); self.sp["b"].setValue(c.blue())
        if skip != "hsl":
            h = c.hslHue()
            self.sp["h"].setValue(round(max(h, 0) * 255 / 359)); self.sp["s"].setValue(c.hslSaturation()); self.sp["l"].setValue(c.lightness())
        self.html.setText(c.name())
        self.sw_cur.color = QColor(c)
        self.sw_cur.update()
        self._busy = False

    def _from_wheel(self, c):
        self.set_color(c, "wheel")

    def _from_rgb(self):
        self.set_color(QColor(self.sp["r"].value(), self.sp["g"].value(), self.sp["b"].value()), "rgb")

    def _from_hsl(self):
        self.set_color(QColor.fromHsl(round(self.sp["h"].value() * 359 / 255), self.sp["s"].value(), self.sp["l"].value()), "hsl")

    def _from_html(self):
        c = QColor(self.html.text())
        if c.isValid():
            self.set_color(c)

    def color(self):
        return QColor(self.cur)


class MaterialBox(QWidget):
    """Groot kleurvak met daaronder stijlknopjes en de transparant-schakelaar."""
    clicked = Signal()
    toggled_none = Signal(bool)

    def __init__(self, main, fg):
        super().__init__()
        self.main, self.fg = main, fg
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(1)
        self.box = Swatch(QColor(0, 0, 0), QSize(56, 42))
        self.box.clicked.connect(self.clicked)
        v.addWidget(self.box)
        row = QHBoxLayout()
        row.setSpacing(1)
        for g, tip, en in (("●", "Kleur", True), ("◑", "Verloop (volgt)", False), ("✣", "Patroon (volgt)", False)):
            b = QToolButton(text=g)
            b.setToolTip(tip)
            b.setEnabled(en)
            b.setCheckable(True)
            b.setChecked(g == "●")
            b.setFixedSize(18, 18)
            row.addWidget(b)
        self.none = QToolButton(text="⊘")
        self.none.setCheckable(True)
        self.none.setFixedSize(18, 18)
        self.none.setToolTip("Transparant: geen " + ("rand" if fg else "vulling"))
        self.none.toggled.connect(self.toggled_none)
        row.addWidget(self.none)
        v.addLayout(row)

    def refresh(self, color, none):
        self.box.color = QColor(color) if not none else QColor(255, 255, 255)
        self.box.update()
        self.none.blockSignals(True)
        self.none.setChecked(none)
        self.none.blockSignals(False)


class MaterialsPalette(QWidget):
    def __init__(self, main):
        super().__init__()
        from .palettes import Spectrum
        self.main = main
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.spectrum = Spectrum()
        self.spectrum.picked.connect(main.set_color)
        tabs.addTab(self.spectrum, "Regenboog")
        sw = QWidget()
        g = QGridLayout(sw)
        g.setSpacing(1)
        for i, hexc in enumerate(BASIC):
            s = Swatch(hexc, QSize(14, 14))
            s.clicked.connect(lambda c=hexc: main.set_color(QColor(c), True))
            s.setToolTip("Klik: voorgrondkleur")
            g.addWidget(s, i // 7, i % 7)
        tabs.addTab(sw, "Stalen")
        lay.addWidget(tabs, 1)
        right = QVBoxLayout()
        right.setSpacing(2)
        self.fgbox = MaterialBox(main, True)
        self.bgbox = MaterialBox(main, False)
        self.fgbox.clicked.connect(lambda: self.choose(True))
        self.bgbox.clicked.connect(lambda: self.choose(False))
        self.fgbox.toggled_none.connect(lambda v: main.set_none(True, v))
        self.bgbox.toggled_none.connect(lambda v: main.set_none(False, v))
        right.addWidget(QLabel("Voorgrond en rand"))
        right.addWidget(self.fgbox)
        swap = QToolButton(text="⇅")
        swap.setToolTip("Kleuren wisselen")
        swap.clicked.connect(main.swap_colors)
        right.addWidget(swap)
        right.addWidget(QLabel("Achtergrond en vulling"))
        right.addWidget(self.bgbox)
        self.all_tools = QCheckBox("Alle gereedschappen")
        self.all_tools.setChecked(True)
        right.addWidget(self.all_tools)
        right.addStretch()
        lay.addLayout(right)
        self.refresh()

    def choose(self, fg):
        cur = self.main.fg if fg else self.main.bg
        dlg = MaterialDialog(self, cur)
        if dlg.exec():
            self.main.set_color(dlg.color(), fg)
            self.main.set_none(fg, False)

    def refresh(self):
        self.fgbox.refresh(self.main.fg, self.main.fg_none)
        self.bgbox.refresh(self.main.bg, self.main.bg_none)
        self.fgbox.setToolTip(f"Voorgrond: {self.main.fg.name().upper()}")
        self.bgbox.setToolTip(f"Achtergrond: {self.main.bg.name().upper()}")
