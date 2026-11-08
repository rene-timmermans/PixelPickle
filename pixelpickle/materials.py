"""Materialen palet en het venster Materiaaleigenschappen (kleurenring, stalen, RGB/HSL)."""
import math

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal
import numpy as np
from PySide6.QtGui import (QColor, QConicalGradient, QIcon, QImage, QLinearGradient, QPainter, QPen, QPixmap,
                           QPolygonF)
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QSpinBox, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from . import icons
from . import imageops as ops
from . import material as M

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
        self.image = None  # verloop of patroon in plaats van de kleur
        self.setFixedSize(size)

    def paintEvent(self, e):
        p = QPainter(self)
        if self.image is not None:
            p.drawImage(self.rect(), self.image)
        else:
            p.fillRect(self.rect(), self.color)
        p.setPen(QColor(90, 90, 90))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def mousePressEvent(self, e):
        self.clicked.emit()


KEY = Qt.ItemDataRole.UserRole + 2  # naam van een patroon (de getoonde tekst kan vertaald zijn)


class MaterialDialog(QDialog):
    def __init__(self, parent, color, title="Materiaaleigenschappen", mat=None, fg=None, bg=None,
                 documents=()):
        """mat: huidig materiaal (None = effen kleur); fg/bg: kleuren voor verlopen als
        Voorgrond-achtergrond; documents: [(naam, QImage)] open afbeeldingen, te gebruiken als patroon."""
        super().__init__(parent)
        self.setWindowTitle(title)
        self.prev = QColor(color)
        self.cur = QColor(color)
        self.prev_mat = mat
        self.fgc = QColor(fg if fg is not None else color)
        self.bgc = QColor(bg if bg is not None else QColor(255, 255, 255))
        self.grad = dict(mat) if mat and mat["kind"] == "gradient" else M.default_gradient()
        self.pat = dict(mat) if mat and mat["kind"] == "pattern" else M.default_pattern()
        self.documents = list(documents)
        self._busy = False
        outer = QHBoxLayout(self)
        self.tabs = tabs = QTabWidget()
        tabs.setMinimumWidth(440)
        page = QWidget()
        tabs.addTab(page, "● Kleur")
        tabs.addTab(self._gradient_page(), "◑ Verloop")
        tabs.addTab(self._pattern_page(), "✣ Patroon")
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
        if mat is not None:
            self.sw_prev.image = M.preview(mat, 80, 50, self.fgc, self.bgc)
        self.sw_prev.clicked.connect(self._back_to_prev)
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
        tabs.currentChanged.connect(self._update_current)
        tabs.setCurrentIndex({None: 0, "gradient": 1, "pattern": 2}[mat["kind"] if mat else None])
        self._update_current()

    # ------------------------------------------------------------ verloop
    def _gradient_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        self.glist = QListWidget()
        self.glist.setIconSize(QSize(96, 18))
        names = M.gradient_names()
        for name in names:
            it = QListWidgetItem(M.gradient_label(name))
            it.setData(Qt.ItemDataRole.UserRole, name)
            self.glist.addItem(it)
        self._gradient_icons()
        self.glist.setCurrentRow(names.index(self.grad["preset"]) if self.grad["preset"] in names else 0)
        self.glist.currentRowChanged.connect(self._grad_changed)
        v.addWidget(self.glist, 1)
        brow = QHBoxLayout()
        for text, fn in (("Nieuw...", self._grad_new), ("Bewerken...", self._grad_edit), ("Verwijderen", self._grad_delete)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            brow.addWidget(b)
            if text == "Verwijderen":
                self.gdel = b
        brow.addStretch()
        v.addLayout(brow)
        row = QHBoxLayout()
        row.addWidget(QLabel("Stijl:"))
        self.gstyle = QButtonGroup(self)
        for i, name in enumerate(M.STYLES):
            b = QToolButton()
            b.setCheckable(True)
            b.setToolTip(name)
            m = dict(self.grad, preset="Zwart-wit", style=i, angle=0 if i != 0 else 90, cx=50, cy=50,
                     repeats=0, invert=False)
            b.setIcon(QIcon(QPixmap.fromImage(M.preview(m, 24, 24, self.fgc, self.bgc))))
            b.setIconSize(QSize(24, 24))
            self.gstyle.addButton(b, i)
            row.addWidget(b)
        self.gstyle.button(self.grad["style"]).setChecked(True)
        self.gstyle.idClicked.connect(self._grad_changed)
        row.addStretch()
        v.addLayout(row)
        form = QGridLayout()
        self.gsp = {}
        for i, (k, lbl, lo, hi) in enumerate([("angle", "Hoek:", 0, 359), ("repeats", "Herhalingen:", 0, 99),
                                              ("cx", "Middelpunt horizontaal:", 0, 100),
                                              ("cy", "Middelpunt verticaal:", 0, 100)]):
            sp = QSpinBox()
            sp.setRange(lo, hi)
            sp.setValue(int(self.grad.get(k, 0)))
            if k in ("cx", "cy"):
                sp.setSuffix(" %")
            sp.valueChanged.connect(self._grad_changed)
            self.gsp[k] = sp
            form.addWidget(QLabel(lbl), i, 0)
            form.addWidget(sp, i, 1)
        self.ginv = QCheckBox("Omkeren")
        self.ginv.setChecked(bool(self.grad.get("invert")))
        self.ginv.toggled.connect(self._grad_changed)
        form.addWidget(self.ginv, 4, 0, 1, 2)
        v.addLayout(form)
        for k in ("cx", "cy"):  # middelpunt telt niet bij een lineair verloop
            self.gsp[k].setEnabled(self.grad["style"] != 0)
        return page

    def _grad_reload(self, select=None):
        names = M.gradient_names()
        self.glist.blockSignals(True)
        self.glist.clear()
        for name in names:
            it = QListWidgetItem(M.gradient_label(name))
            it.setData(Qt.ItemDataRole.UserRole, name)
            self.glist.addItem(it)
        self._gradient_icons()
        self.glist.blockSignals(False)
        key = select if select in names else self.grad["preset"]
        self.glist.setCurrentRow(names.index(key) if key in names else 0)
        self._grad_changed()

    def _grad_edit_dialog(self, name, stops):
        dlg = GradientEditor(self, name, stops, self.fgc, self.bgc)
        if dlg.exec():
            new_name, new_stops = dlg.result_gradient()
            save_user_gradient(new_name, new_stops)
            self._grad_reload(M.USER_PREFIX + new_name)

    def _grad_new(self):
        self._grad_edit_dialog(_free_name(), [(0.0, "fg:255"), (1.0, "bg:255")])

    def _grad_edit(self):
        it = self.glist.currentItem()
        if it is None:
            return
        key = it.data(Qt.ItemDataRole.UserRole)
        # een ingebouwd verloop (of een uit een eigen installatie) wordt als kopie bewerkt
        name = key[len(M.USER_PREFIX):] if key.startswith(M.USER_PREFIX) else _free_name(M.gradient_label(key))
        self._grad_edit_dialog(name, M.gradient_stops(key))

    def _grad_delete(self):
        it = self.glist.currentItem()
        if it is None or not it.data(Qt.ItemDataRole.UserRole).startswith(M.USER_PREFIX):
            return
        delete_user_gradient(it.data(Qt.ItemDataRole.UserRole)[len(M.USER_PREFIX):])
        self._grad_reload("Voorgrond-achtergrond")

    def _gradient_icons(self):
        for i in range(self.glist.count()):
            it = self.glist.item(i)
            m = M.default_gradient()
            m.update(preset=it.data(Qt.ItemDataRole.UserRole), angle=90)
            it.setIcon(QIcon(QPixmap.fromImage(M.preview(m, 96, 18, self.fgc, self.bgc))))

    def _grad_changed(self, *_):
        it = self.glist.currentItem()
        self.grad.update(preset=it.data(Qt.ItemDataRole.UserRole) if it else "Voorgrond-achtergrond",
                         style=max(self.gstyle.checkedId(), 0), invert=self.ginv.isChecked(),
                         **{k: sp.value() for k, sp in self.gsp.items()})
        if hasattr(self, "gdel"):
            self.gdel.setEnabled(bool(it) and it.data(Qt.ItemDataRole.UserRole).startswith(M.USER_PREFIX))
        centered = self.grad["style"] != 0
        self.gsp["cx"].setEnabled(centered)
        self.gsp["cy"].setEnabled(centered)
        self._update_current()

    # ------------------------------------------------------------ patroon
    def _pattern_page(self):
        page = QWidget()
        v = QVBoxLayout(page)
        self.plist = QListWidget()
        self.plist.setViewMode(QListWidget.ViewMode.IconMode)
        self.plist.setIconSize(QSize(48, 48))
        self.plist.setGridSize(QSize(100, 76))
        self.plist.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.plist.setMovement(QListWidget.Movement.Static)
        self.plist.setWordWrap(True)
        from .i18n import tr
        for name in M.PATTERNS:
            self._add_pattern(name, M.pattern_image(name), tr(name))
        for name, _ in M.psp_patterns():
            img = M.pattern_image(name)
            if img is not None:
                self._add_pattern(name, img, tr(name))
        for name, img in self.documents:
            self._add_pattern(name, img)
        keys = [self.plist.item(i).data(KEY) for i in range(self.plist.count())]
        if self.pat["name"] not in keys:
            self._add_pattern(self.pat["name"], self.pat["image"])
        for i in range(self.plist.count()):
            if self.plist.item(i).data(KEY) == self.pat["name"]:
                self.plist.setCurrentRow(i)
        self.plist.currentRowChanged.connect(self._pat_changed)
        v.addWidget(self.plist, 1)
        load = QPushButton("Uit bestand laden...")
        load.clicked.connect(self._pat_from_file)
        v.addWidget(load, 0, Qt.AlignmentFlag.AlignLeft)
        form = QGridLayout()
        self.psp = {}
        for i, (k, lbl, lo, hi, suf) in enumerate([("angle", "Hoek:", 0, 359, ""), ("scale", "Schaal:", 10, 250, " %")]):
            sp = QSpinBox()
            sp.setRange(lo, hi)
            sp.setSuffix(suf)
            sp.setValue(int(self.pat.get(k, 100 if k == "scale" else 0)))
            sp.valueChanged.connect(self._pat_changed)
            self.psp[k] = sp
            form.addWidget(QLabel(lbl), i, 0)
            form.addWidget(sp, i, 1)
        v.addLayout(form)
        return page

    def _add_pattern(self, name, img, label=None):
        thumb = img.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        it = QListWidgetItem(QIcon(QPixmap.fromImage(thumb)), label or name)
        it.setData(Qt.ItemDataRole.UserRole, img)
        it.setData(KEY, name)
        self.plist.addItem(it)
        return it

    def _pat_from_file(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Patroon laden", "",
                                            "Afbeeldingen (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)")
        if not fn:
            return
        img = QImage(fn)
        if img.isNull():
            return
        import os
        it = self._add_pattern(os.path.basename(fn), img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied))
        self.plist.setCurrentItem(it)

    def _pat_changed(self, *_):
        it = self.plist.currentItem()
        if it is not None:
            self.pat.update(name=it.data(KEY), image=it.data(Qt.ItemDataRole.UserRole))
        self.pat.update({k: sp.value() for k, sp in self.psp.items()})
        self._update_current()

    # ------------------------------------------------------------ algemeen
    def material(self):
        """Gekozen materiaal: None (effen kleur), een verloop of een patroon."""
        i = self.tabs.currentIndex()
        if i == 1:
            return dict(self.grad)
        if i == 2:
            return dict(self.pat)
        return None

    def _update_current(self, *_):
        if not hasattr(self, "sw_cur"):
            return
        m = self.material()
        self.sw_cur.image = M.preview(m, 80, 50, self.fgc, self.bgc) if m is not None else None
        self.sw_cur.update()

    def _back_to_prev(self):
        m = self.prev_mat
        if m is None:
            self.tabs.setCurrentIndex(0)
            self.set_color(self.prev)
        elif m["kind"] == "gradient":
            self.tabs.setCurrentIndex(1)
        else:
            self.tabs.setCurrentIndex(2)

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
        self._update_current()

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


# ---------------------------------------------------------------- verloopbewerker
def load_user_gradients():
    """Eigen verlopen uit de instellingen inlezen (bij het starten)."""
    import json
    from PySide6.QtCore import QSettings
    try:
        M.set_user_gradients(json.loads(QSettings("PixelPickle", "PixelPickle").value("user_gradients", "{}") or "{}"))
    except (ValueError, TypeError):
        M.set_user_gradients({})


def _store_user_gradients():
    import json
    from PySide6.QtCore import QSettings
    QSettings("PixelPickle", "PixelPickle").setValue(
        "user_gradients", json.dumps({k: [[p, c] for p, c in v] for k, v in M.USER_GRADIENTS.items()}))


def save_user_gradient(name, stops):
    M.USER_GRADIENTS[name] = [(float(p), c) for p, c in sorted(stops, key=lambda s: s[0])]
    _store_user_gradients()


def delete_user_gradient(name):
    M.USER_GRADIENTS.pop(name, None)
    _store_user_gradients()


def _free_name(base=None):
    from .i18n import tr
    base = base or tr("Eigen verloop")
    if base not in M.USER_GRADIENTS:
        return base
    n = 2
    while f"{base} {n}" in M.USER_GRADIENTS:
        n += 1
    return f"{base} {n}"


class GradientBar(QWidget):
    """Verloopbalk met kleurpunten eronder: klik een punt om het te kiezen, sleep om het te verschuiven,
    klik op een lege plek om een punt toe te voegen."""
    changed = Signal()
    selected = Signal(int)
    MARK = 9

    def __init__(self, stops, fg, bg):
        super().__init__()
        self.stops = [[float(p), c] for p, c in stops]
        self.fg, self.bg = fg, bg
        self.cur = 0
        self._drag = False
        self.setMinimumSize(360, 54)

    def _bar(self):
        return QRect(self.MARK, 4, self.width() - 2 * self.MARK, self.height() - self.MARK * 2 - 8)

    def _x(self, pos):
        b = self._bar()
        return b.left() + pos * b.width()

    def paintEvent(self, e):
        p = QPainter(self)
        b = self._bar()
        for y in range(b.top(), b.bottom() + 1, 6):
            for x in range(b.left(), b.right() + 1, 6):
                p.fillRect(x, y, 6, 6, QColor(204, 204, 204) if ((x - b.left()) // 6 + (y - b.top()) // 6) % 2 else QColor(255, 255, 255))
        lut = M.stops_lut(self.stops, self.fg, self.bg)
        idx = np.clip(np.round(np.linspace(0, 255, max(1, b.width()))).astype(int), 0, 255)
        row = np.clip(lut[idx], 0, 255).astype(np.uint8)
        p.drawImage(b.topLeft(), ops.rgba_to_qimage(np.ascontiguousarray(np.repeat(row[None], b.height(), axis=0))))
        p.setPen(QPen(self.palette().mid().color()))
        p.drawRect(b.adjusted(0, 0, -1, -1))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, (pos, spec) in enumerate(self.stops):
            x = self._x(pos)
            r, g, bb, _ = M._rgba(spec, self.fg, self.bg)
            tri = [QPointF(x, b.bottom() + 2), QPointF(x - self.MARK / 2 - 1, b.bottom() + self.MARK + 4),
                   QPointF(x + self.MARK / 2 + 1, b.bottom() + self.MARK + 4)]
            p.setBrush(QColor(r, g, bb))
            p.setPen(QPen(self.palette().highlight().color() if i == self.cur else self.palette().text().color(),
                          2.2 if i == self.cur else 1))
            p.drawPolygon(QPolygonF(tri))
        p.end()

    def _hit(self, x):
        best, bd = None, 1e9
        for i, (pos, _) in enumerate(self.stops):
            d = abs(self._x(pos) - x)
            if d < bd:
                best, bd = i, d
        return best if bd <= self.MARK else None

    def _pos(self, x):
        b = self._bar()
        return max(0.0, min(1.0, (x - b.left()) / max(1, b.width())))

    def mousePressEvent(self, e):
        x = e.position().x()
        i = self._hit(x)
        if i is None:  # nieuw punt met de kleur die het verloop daar al heeft
            pos = self._pos(x)
            lut = M.stops_lut(self.stops, self.fg, self.bg)
            r, g, b, a = (int(round(v)) for v in lut[int(round(pos * 255))])
            self.stops.append([pos, "#%02x%02x%02x%02x" % (r, g, b, a)])
            i = len(self.stops) - 1
            self.changed.emit()
        self.cur = i
        self._drag = True
        self.selected.emit(i)
        self.update()

    def mouseMoveEvent(self, e):
        if self._drag and 0 <= self.cur < len(self.stops):
            self.stops[self.cur][0] = self._pos(e.position().x())
            self.selected.emit(self.cur)
            self.changed.emit()
            self.update()

    def mouseReleaseEvent(self, e):
        self._drag = False


class GradientEditor(QDialog):
    """Verloopbewerker: kleurpunten met een eigen kleur of de voorgrond-/achtergrondkleur, dekking en positie."""

    SOURCES = ["Eigen kleur", "Voorgrondkleur", "Achtergrondkleur"]

    def __init__(self, parent, name, stops, fg, bg):
        from PySide6.QtWidgets import QComboBox, QFormLayout
        super().__init__(parent)
        self.setWindowTitle("Verloopbewerker")
        self.fg, self.bg = QColor(fg), QColor(bg)
        stops = list(stops) or [(0.0, "fg:255"), (1.0, "bg:255")]
        if len(stops) < 2:
            stops = [stops[0], (1.0, stops[0][1])]
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.name = QLineEdit(name)
        self.name.setProperty("pp_notr", True)
        f.addRow("Naam:", self.name)
        v.addLayout(f)
        self.bar = GradientBar(stops, self.fg, self.bg)
        v.addWidget(self.bar)
        hint = QLabel("Klik onder de balk op een lege plek om een kleurpunt toe te voegen; sleep een punt om het te verschuiven.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        v.addWidget(hint)
        g = QFormLayout()
        self.src = QComboBox()
        self.src.addItems(self.SOURCES)
        self.color_btn = QPushButton()
        self.color_btn.setFixedWidth(80)
        self.color_btn.clicked.connect(self._pick_color)
        self.alpha = QSpinBox()
        self.alpha.setRange(0, 100)
        self.alpha.setSuffix(" %")
        self.pos = QSpinBox()
        self.pos.setRange(0, 100)
        self.pos.setSuffix(" %")
        row = QHBoxLayout()
        row.addWidget(self.src)
        row.addWidget(self.color_btn)
        g.addRow("Kleur:", row)
        g.addRow("Dekking:", self.alpha)
        g.addRow("Positie:", self.pos)
        v.addLayout(g)
        brow = QHBoxLayout()
        self.del_btn = QPushButton("Kleurpunt verwijderen")
        self.del_btn.clicked.connect(self._delete_stop)
        rev = QPushButton("Omdraaien")
        rev.clicked.connect(self._reverse)
        brow.addWidget(self.del_btn)
        brow.addWidget(rev)
        brow.addStretch()
        v.addLayout(brow)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Opslaan")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuleren")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.ok = bb.button(QDialogButtonBox.StandardButton.Ok)
        v.addWidget(bb)
        self._busy = False
        self.bar.selected.connect(self._show_stop)
        self.bar.changed.connect(self._update_buttons)
        self.src.currentIndexChanged.connect(self._edit_stop)
        self.alpha.valueChanged.connect(self._edit_stop)
        self.pos.valueChanged.connect(self._edit_stop)
        self.name.textChanged.connect(self._update_buttons)
        self._show_stop(0)
        self.resize(440, 0)

    # een kleurpunt: (bron 0/1/2, QColor, dekking 0..255)
    def _parse(self, spec):
        r, g, b, a = M._rgba(spec, self.fg, self.bg)
        src = 1 if spec.startswith("fg") else 2 if spec.startswith("bg") else 0
        return src, QColor(r, g, b), a

    def _spec(self, src, color, a):
        if src == 1:
            return f"fg:{a}"
        if src == 2:
            return f"bg:{a}"
        return "#%02x%02x%02x%02x" % (color.red(), color.green(), color.blue(), a)

    def _show_stop(self, i):
        self._busy = True
        pos, spec = self.bar.stops[i]
        src, color, a = self._parse(spec)
        self._color = color
        self.src.setCurrentIndex(src)
        self.alpha.setValue(round(a / 2.55))
        self.pos.setValue(round(pos * 100))
        self._paint_color_btn()
        self._busy = False
        self._update_buttons()

    def _paint_color_btn(self):
        pm = QPixmap(60, 16)
        pm.fill(self._color)
        self.color_btn.setIcon(QIcon(pm))
        self.color_btn.setIconSize(QSize(60, 16))
        self.color_btn.setEnabled(self.src.currentIndex() == 0)

    def _edit_stop(self, *_):
        if self._busy:
            return
        i = self.bar.cur
        if self.src.currentIndex() != 0:
            self._color = QColor(self.fg if self.src.currentIndex() == 1 else self.bg)
        self.bar.stops[i] = [self.pos.value() / 100,
                             self._spec(self.src.currentIndex(), self._color, round(self.alpha.value() * 2.55))]
        self._paint_color_btn()
        self.bar.update()

    def _pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(self._color, self, "Kleur")
        if c.isValid():
            self._color = c
            self._edit_stop()

    def _delete_stop(self):
        if len(self.bar.stops) <= 2:
            return
        del self.bar.stops[self.bar.cur]
        self.bar.cur = min(self.bar.cur, len(self.bar.stops) - 1)
        self.bar.update()
        self._show_stop(self.bar.cur)

    def _reverse(self):
        self.bar.stops = [[1 - p, c] for p, c in self.bar.stops]
        self.bar.update()
        self._show_stop(self.bar.cur)

    def _update_buttons(self):
        self.del_btn.setEnabled(len(self.bar.stops) > 2)
        self.ok.setEnabled(bool(self.name.text().strip()))

    def result_gradient(self):
        return self.name.text().strip(), [(p, c) for p, c in sorted(self.bar.stops, key=lambda s: s[0])]


class MaterialBox(QWidget):
    """Groot kleurvak met daaronder stijlknopjes en de transparant-schakelaar."""
    clicked = Signal()
    toggled_none = Signal(bool)
    kind_chosen = Signal(int)  # 0 kleur, 1 verloop, 2 patroon

    def __init__(self, main, fg):
        super().__init__()
        self.main, self.fg = main, fg
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(1)
        # het kleurvak is precies zo breed als de vier knopjes eronder, die tegen elkaar aan staan
        self.box = Swatch(QColor(0, 0, 0), QSize(4 * self.BTN, 30))
        self.box.clicked.connect(self.clicked)
        v.addWidget(self.box)
        row = QHBoxLayout()
        row.setSpacing(0)
        row.setContentsMargins(0, 0, 0, 0)
        self.kinds = QButtonGroup(self)
        for i, (g, tip) in enumerate((("color", "Kleur"), ("gradient", "Verloop"), ("pattern", "Patroon"))):
            b = QToolButton()
            icons.set_button(b, g, 12, tip)
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.setFixedSize(self.BTN, self.BTN)
            self.kinds.addButton(b, i)
            row.addWidget(b)
        self.kinds.idClicked.connect(self.kind_chosen)
        self.none = QToolButton()
        icons.set_button(self.none, "none", 12)
        self.none.setCheckable(True)
        self.none.setFixedSize(self.BTN, self.BTN)
        self.none.setToolTip("Transparant: geen rand" if fg else "Transparant: geen vulling")
        self.none.toggled.connect(self.toggled_none)
        row.addWidget(self.none)
        v.addLayout(row)
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    BTN = 18  # grootte van de stijlknopjes

    def refresh(self, color, none, mat=None, fg=None, bg=None):
        self.box.color = QColor(color) if not none else QColor(255, 255, 255)
        self.box.image = None if (none or mat is None) else M.preview(mat, 4 * self.BTN, 30, fg, bg)
        self.box.update()
        self.kinds.button({None: 0, "gradient": 1, "pattern": 2}[mat["kind"] if mat else None]).setChecked(True)
        self.none.blockSignals(True)
        self.none.setChecked(none)
        self.none.blockSignals(False)


def _tab_icon(kind):
    """Icoontjes voor de tabbladen van het materialenpalet (zoals in PSP, zonder tekst)."""
    img = QImage(18, 18, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    if kind == "rainbow":
        g = QLinearGradient(1, 0, 17, 0)
        for i in range(7):
            g.setColorAt(i / 6, QColor.fromHsvF((i / 6) % 1.0, 1, 1))
        p.fillRect(1, 1, 16, 16, g)
        v = QLinearGradient(0, 1, 0, 17)
        v.setColorAt(0, QColor(255, 255, 255, 200))
        v.setColorAt(0.5, QColor(255, 255, 255, 0))
        v.setColorAt(1, QColor(0, 0, 0, 220))
        p.fillRect(1, 1, 16, 16, v)
    else:
        cols = ["#e02020", "#f0c000", "#20a040", "#2060e0", "#a040c0", "#f08020", "#20b0c0", "#606060", "#ffffff"]
        for k, c in enumerate(cols):
            p.fillRect(1 + (k % 3) * 6, 1 + (k // 3) * 6, 5, 5, QColor(c))
    p.setPen(QColor(90, 90, 90))
    p.drawRect(0, 0, 17, 17)
    p.end()
    return QIcon(QPixmap.fromImage(img))


class MaterialsPalette(QWidget):
    def __init__(self, main):
        super().__init__()
        from .palettes import Spectrum
        self.main = main
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(2)
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(lay)
        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.TabPosition.North)
        tabs.setIconSize(QSize(18, 18))
        self.spectrum = Spectrum()
        self.spectrum.setMinimumSize(140, 80)
        self.spectrum.picked.connect(main.set_color)
        tabs.addTab(self.spectrum, _tab_icon("rainbow"), "")
        tabs.setTabToolTip(0, "Regenboog")
        sw = QWidget()
        g = QGridLayout(sw)
        g.setSpacing(1)
        g.setContentsMargins(2, 2, 2, 2)
        for i, hexc in enumerate(BASIC):
            s = Swatch(hexc, QSize(12, 12))
            s.clicked.connect(lambda c=hexc: main.set_color(QColor(c), True))
            s.setToolTip("Klik: voorgrondkleur")
            g.addWidget(s, i // 7, i % 7)
        tabs.addTab(sw, _tab_icon("swatches"), "")
        tabs.setTabToolTip(1, "Stalen")
        lay.addWidget(tabs, 1)
        right = QGridLayout()
        right.setSpacing(2)
        self.fgbox = MaterialBox(main, True)
        self.bgbox = MaterialBox(main, False)
        self.fgbox.clicked.connect(lambda: self.choose(True))
        self.bgbox.clicked.connect(lambda: self.choose(False))
        self.fgbox.toggled_none.connect(lambda v: main.set_none(True, v))
        self.bgbox.toggled_none.connect(lambda v: main.set_none(False, v))
        self.fgbox.kind_chosen.connect(lambda k: main.set_material_kind(True, k))
        self.bgbox.kind_chosen.connect(lambda k: main.set_material_kind(False, k))
        right.addWidget(self.fgbox, 0, 0)
        swap = QToolButton()
        icons.set_button(swap, "swap", 14)
        swap.setToolTip("Kleuren wisselen")
        swap.setFixedSize(20, 20)
        swap.clicked.connect(main.swap_colors)
        right.addWidget(swap, 0, 1, 2, 1, Qt.AlignmentFlag.AlignVCenter)
        right.addWidget(self.bgbox, 1, 0)
        right.setRowStretch(2, 1)
        lay.addLayout(right)
        # het vinkje op een eigen regel onder het palet, zodat de kolom met de kleurvakken smal blijft
        self.all_tools = QCheckBox("Alle gereedschappen")
        self.all_tools.setChecked(True)
        outer.addWidget(self.all_tools)
        # niet hoger dan nodig, zodat Lagen en Geschiedenis de ruimte krijgen (zoals in PSP)
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.refresh()

    def choose(self, fg):
        m = self.main
        cur = m.fg if fg else m.bg
        dlg = MaterialDialog(self, cur, mat=m.material(fg), fg=m.fg, bg=m.bg, documents=m.pattern_sources())
        if dlg.exec():
            m.set_color(dlg.color(), fg)
            m.set_material(fg, dlg.material())
            m.set_none(fg, False)

    def refresh(self):
        m = self.main
        self.fgbox.refresh(m.fg, m.fg_none, m.fg_mat, m.fg, m.bg)
        self.bgbox.refresh(m.bg, m.bg_none, m.bg_mat, m.fg, m.bg)
        def what(c, mat):
            return {"gradient": "Verloop", "pattern": "Patroon"}[mat["kind"]] if mat else c.name().upper()
        self.fgbox.setToolTip(f"Voorgrond en rand: {what(m.fg, m.fg_mat)}")
        self.bgbox.setToolTip(f"Achtergrond en vulling: {what(m.bg, m.bg_mat)}")
