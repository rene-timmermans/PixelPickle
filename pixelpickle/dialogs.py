"""Dialoogvensters: nieuwe afbeelding, formaat, canvasgrootte en aanpassingen met voorbeeld."""
from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QSlider, QSpinBox, QVBoxLayout, QWidget)

from .document import apply_region
from . import imageops as ops


def _buttons(dlg):
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    bb.button(QDialogButtonBox.StandardButton.Ok).setText("OK")
    bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuleren")
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    return bb


def _spin(lo, hi, val, suffix=""):
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(val)
    s.setSuffix(suffix)
    return s


class NewImageDialog(QDialog):
    PRESETS = [("Aangepast", None), ("640 × 480", (640, 480)), ("800 × 600", (800, 600)),
               ("1024 × 768", (1024, 768)), ("1280 × 720 (HD)", (1280, 720)),
               ("1920 × 1080 (Full HD)", (1920, 1080)), ("3840 × 2160 (4K)", (3840, 2160)),
               ("A4 300 dpi", (2480, 3508)), ("10 × 15 cm 300 dpi", (1181, 1772))]

    def __init__(self, parent, fg, bg):
        super().__init__(parent)
        self.setWindowTitle("Nieuwe afbeelding")
        self.fg, self.bg = fg, bg
        f = QFormLayout(self)
        self.preset = QComboBox()
        self.preset.addItems([p[0] for p in self.PRESETS])
        self.preset.currentIndexChanged.connect(self._preset)
        f.addRow("Voorinstelling:", self.preset)
        self.w = _spin(1, 30000, 1024, " px")
        self.h = _spin(1, 30000, 768, " px")
        f.addRow("Breedte:", self.w)
        f.addRow("Hoogte:", self.h)
        self.bgc = QComboBox()
        self.bgc.addItems(["Wit", "Zwart", "Transparant", "Achtergrondkleur", "Voorgrondkleur"])
        f.addRow("Achtergrond:", self.bgc)
        f.addRow(_buttons(self))

    def _preset(self, i):
        v = self.PRESETS[i][1]
        if v:
            self.w.setValue(v[0])
            self.h.setValue(v[1])

    def result_values(self):
        c = [QColor(255, 255, 255), QColor(0, 0, 0), None, self.bg, self.fg][self.bgc.currentIndex()]
        return self.w.value(), self.h.value(), c


class ResizeDialog(QDialog):
    def __init__(self, parent, w, h):
        super().__init__(parent)
        self.setWindowTitle("Formaat wijzigen")
        self.ow, self.oh = w, h
        f = QFormLayout(self)
        self.pct = _spin(1, 2000, 100, " %")
        self.w = _spin(1, 30000, w, " px")
        self.h = _spin(1, 30000, h, " px")
        self.keep = QCheckBox("Hoogte-breedteverhouding behouden")
        self.keep.setChecked(True)
        self.mode = QComboBox()
        self.mode.addItems(["Vloeiend (bicubisch)", "Pixel herhalen"])
        f.addRow("Percentage:", self.pct)
        f.addRow("Breedte:", self.w)
        f.addRow("Hoogte:", self.h)
        f.addRow(self.keep)
        f.addRow("Methode:", self.mode)
        f.addRow(_buttons(self))
        self._lock = False
        self.pct.valueChanged.connect(self._from_pct)
        self.w.valueChanged.connect(lambda v: self._from_side(True))
        self.h.valueChanged.connect(lambda v: self._from_side(False))

    def _from_pct(self, v):
        if self._lock:
            return
        self._lock = True
        self.w.setValue(max(1, round(self.ow * v / 100)))
        self.h.setValue(max(1, round(self.oh * v / 100)))
        self._lock = False

    def _from_side(self, width):
        if self._lock or not self.keep.isChecked():
            return
        self._lock = True
        if width:
            self.h.setValue(max(1, round(self.w.value() * self.oh / self.ow)))
        else:
            self.w.setValue(max(1, round(self.h.value() * self.ow / self.oh)))
        self.pct.setValue(round(self.w.value() * 100 / self.ow))
        self._lock = False


class CanvasSizeDialog(QDialog):
    ANCHORS = ["Linksboven", "Boven", "Rechtsboven", "Links", "Midden", "Rechts",
               "Linksonder", "Onder", "Rechtsonder"]

    def __init__(self, parent, w, h):
        super().__init__(parent)
        self.setWindowTitle("Canvasgrootte")
        self.ow, self.oh = w, h
        f = QFormLayout(self)
        self.w = _spin(1, 30000, w, " px")
        self.h = _spin(1, 30000, h, " px")
        self.anchor = QComboBox()
        self.anchor.addItems(self.ANCHORS)
        self.anchor.setCurrentIndex(4)
        f.addRow("Nieuwe breedte:", self.w)
        f.addRow("Nieuwe hoogte:", self.h)
        f.addRow("Plaatsing:", self.anchor)
        f.addRow(QLabel("Nieuw gebied krijgt de achtergrondkleur (achtergrondlaag)."))
        f.addRow(_buttons(self))

    def offsets(self):
        a = self.anchor.currentIndex()
        dx, dy = self.w.value() - self.ow, self.h.value() - self.oh
        return [0, dx // 2, dx][a % 3], [0, dy // 2, dy][a // 3]


class AdjustDialog(QDialog):
    """Generiek venster met schuifregelaars en live voorbeeld op de actieve laag."""

    def __init__(self, main, doc, title, fn, params):
        super().__init__(main)
        self.setWindowTitle(title)
        self.doc, self.fn, self.title = doc, fn, title
        self.layer = doc.layer()
        self.orig = QImage(self.layer.image)
        self.sliders = {}
        v = QVBoxLayout(self)
        f = QFormLayout()
        for key, label, lo, hi, val in params:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(lo, hi)
            s.setValue(val)
            sp = _spin(lo, hi, val)
            s.valueChanged.connect(sp.setValue)
            sp.valueChanged.connect(s.setValue)
            s.valueChanged.connect(self.schedule)
            h.addWidget(s, 1)
            h.addWidget(sp)
            f.addRow(label, row)
            self.sliders[key] = s
        v.addLayout(f)
        self.preview = QCheckBox("Voorbeeld op afbeelding")
        self.preview.setChecked(True)
        self.preview.toggled.connect(self.schedule)
        v.addWidget(self.preview)
        v.addWidget(_buttons(self))
        self.timer = QTimer(self, singleShot=True, interval=120)
        self.timer.timeout.connect(self.update_preview)
        self.schedule()

    def values(self):
        return {k: s.value() for k, s in self.sliders.items()}

    def schedule(self):
        self.timer.start()

    def _result(self):
        d = self.doc
        r = d.selection_bbox() if d.sel is not None else d.rect()
        out = QImage(self.orig)
        if r.isEmpty():
            return out, r
        vals = self.values()
        res = ops.rgba_to_qimage(self.fn(ops.qimage_to_rgba(self.orig.copy(r)), **vals))
        apply_region(out, r, res, d.sel)
        return out, r

    def update_preview(self):
        if self.preview.isChecked():
            self.layer.image, _ = self._result()
        else:
            self.layer.image = self.orig
        self.doc.changed.emit(QRect())

    def accept(self):
        self.timer.stop()
        out, _ = self._result()
        self.layer.image = self.orig
        self.doc.push_undo(self.title)
        self.layer.image = out
        self.doc.changed.emit(QRect())
        self.doc.structureChanged.emit()
        super().accept()

    def reject(self):
        self.timer.stop()
        self.layer.image = self.orig
        self.doc.changed.emit(QRect())
        super().reject()


class FreeRotateDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Vrij roteren")
        f = QFormLayout(self)
        self.dir = QComboBox()
        self.dir.addItems(["Rechtsom", "Linksom"])
        self.deg = QComboBox()
        self.deg.addItems(["90", "180", "270", "Vrij"])
        self.free = _spin(-360, 360, 15, "°")
        f.addRow("Richting:", self.dir)
        f.addRow("Graden:", self.deg)
        f.addRow("Vrij:", self.free)
        f.addRow(_buttons(self))

    def angle(self):
        i = self.deg.currentIndex()
        a = [90, 180, 270, self.free.value()][i]
        return a if self.dir.currentIndex() == 0 else -a


class BordersDialog(QDialog):
    def __init__(self, parent, color):
        super().__init__(parent)
        from PySide6.QtWidgets import QColorDialog, QPushButton
        self.setWindowTitle("Randen toevoegen")
        self.color = QColor(color)
        f = QFormLayout(self)
        self.sym = QCheckBox("Symmetrisch")
        self.sym.setChecked(True)
        self.s = [_spin(0, 5000, 10, " px") for _ in range(4)]
        f.addRow(self.sym)
        for lbl, sp in zip(["Boven:", "Onder:", "Links:", "Rechts:"], self.s):
            f.addRow(lbl, sp)
            sp.valueChanged.connect(self._sync)
        self.cbtn = QPushButton()
        self.cbtn.clicked.connect(lambda: self._pick(QColorDialog))
        self._paint()
        f.addRow("Kleur:", self.cbtn)
        f.addRow(QLabel("Een afbeelding met lagen wordt eerst samengevoegd."))
        f.addRow(_buttons(self))
        self._busy = False

    def _sync(self, v):
        if self.sym.isChecked() and not getattr(self, "_busy", False):
            self._busy = True
            for sp in self.s:
                sp.setValue(v)
            self._busy = False

    def _pick(self, QColorDialog):
        c = QColorDialog.getColor(self.color, self, "Randkleur")
        if c.isValid():
            self.color = c
            self._paint()

    def _paint(self):
        self.cbtn.setStyleSheet(f"background:{self.color.name()}; min-width:60px;")

    def values(self):
        t, b, l, r = (sp.value() for sp in self.s)
        return l, t, r, b


class RangeSlider(QWidget):
    """Mengbereik: kleurbalk met een dekkingsgrafiek en vier sleepbare driehoekjes (a <= b <= c <= d).
    Onder a en boven d is de laag onzichtbaar, tussen b en c volledig zichtbaar."""
    changed = Signal()
    PAD = 7

    def __init__(self):
        super().__init__()
        from PySide6.QtWidgets import QSizePolicy
        self.v = list((0, 0, 255, 255))
        self.color = QColor(255, 255, 255)
        self.drag = None
        self.setMinimumSize(260, 46)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def set_values(self, v):
        self.v = [int(x) for x in v]
        self.update()

    def set_color(self, c):
        self.color = QColor(c)
        self.update()

    def _x(self, val):
        return self.PAD + val / 255 * (self.width() - 2 * self.PAD)

    def _val(self, x):
        return round(max(0, min(255, (x - self.PAD) / max(1, self.width() - 2 * self.PAD) * 255)))

    def paintEvent(self, e):
        from PySide6.QtCore import QPointF, QRectF
        from PySide6.QtGui import QLinearGradient, QPainter, QPen, QPolygonF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        bar = QRectF(self.PAD, 4, w - 2 * self.PAD, 18)
        g = QLinearGradient(bar.left(), 0, bar.right(), 0)
        g.setColorAt(0, QColor(0, 0, 0))
        g.setColorAt(1, self.color)
        p.fillRect(bar, g)
        # dekkingsgrafiek over de balk
        a, b, c, d = (self._x(x) for x in self.v)
        top, bot = bar.top() + 2, bar.bottom() - 1
        poly = QPolygonF([QPointF(bar.left(), bot), QPointF(a, bot), QPointF(b, top), QPointF(c, top),
                          QPointF(d, bot), QPointF(bar.right(), bot)])
        for col, wd in ((QColor(0, 0, 0, 160), 3), (QColor(255, 255, 255), 1.2)):
            p.setPen(QPen(col, wd))
            p.drawPolyline(poly)
        p.setPen(QPen(self.palette().mid().color(), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(bar)
        # driehoekjes: binnenste twee gevuld, buitenste twee open
        hl = self.palette().highlight().color()
        for k, x in enumerate((a, b, c, d)):
            tri = QPolygonF([QPointF(x, bar.bottom() + 2), QPointF(x - 6, bar.bottom() + 12),
                             QPointF(x + 6, bar.bottom() + 12)])
            p.setPen(QPen(self.palette().windowText().color(), 1))
            p.setBrush(hl if k in (1, 2) else self.palette().base().color())
            p.drawPolygon(tri)
        p.end()

    def mousePressEvent(self, e):
        x = e.position().x()
        d = [abs(self._x(v) - x) for v in self.v]
        k = min(range(4), key=lambda i: (d[i], -i if x > self._x(self.v[i]) else i))
        self.drag = k
        self.mouseMoveEvent(e)

    def mouseMoveEvent(self, e):
        if self.drag is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        k = self.drag
        lo = self.v[k - 1] if k > 0 else 0
        hi = self.v[k + 1] if k < 3 else 255
        nv = max(lo, min(hi, self._val(e.position().x())))
        if nv != self.v[k]:
            self.v[k] = nv
            self.update()
            self.changed.emit()

    def mouseReleaseEvent(self, e):
        self.drag = None


class BlendRangesPage(QWidget):
    """Tabblad Mengbereiken van Laageigenschappen."""
    changed = Signal()
    COLORS = {"Grijs": QColor(255, 255, 255), "Rood": QColor(255, 0, 0), "Groen": QColor(0, 255, 0),
              "Blauw": QColor(0, 0, 255)}

    def __init__(self, ranges):
        super().__init__()
        from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QPushButton, QVBoxLayout
        from .document import BLEND_CHANNELS, FULL_RANGE
        self.channels = BLEND_CHANNELS
        self.full = FULL_RANGE
        self.ranges = {ch: (list(FULL_RANGE), list(FULL_RANGE)) for ch in BLEND_CHANNELS}
        for ch, (a, b) in (ranges or {}).items():
            if ch in self.ranges:
                self.ranges[ch] = (list(a), list(b))
        self._busy = False
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Mengkanaal:"))
        self.channel = QComboBox()
        self.channel.addItems(BLEND_CHANNELS)
        self.channel.currentIndexChanged.connect(self._show)
        top.addWidget(self.channel)
        top.addStretch()
        reset = QPushButton("Standaard")
        reset.setToolTip("Dit kanaal terugzetten: laag overal zichtbaar")
        reset.clicked.connect(self._reset)
        top.addWidget(reset)
        v.addLayout(top)
        self.sliders, self.spins = [], []
        for title in ("Deze laag:", "Onderliggende laag:"):
            v.addWidget(QLabel(title))
            sl = RangeSlider()
            sl.changed.connect(self._from_slider)
            v.addWidget(sl)
            row = QGridLayout()
            sp = []
            for k in range(4):
                b = _spin(0, 255, 0)
                b.valueChanged.connect(self._from_spin)
                row.addWidget(b, 0, k)
                sp.append(b)
            v.addLayout(row)
            self.sliders.append(sl)
            self.spins.append(sp)
        tip = QLabel("Tussen de twee gevulde driehoekjes is de laag volledig zichtbaar; buiten de open "
                     "driehoekjes onzichtbaar, met een zachte overgang daartussen. 'Onderliggende laag' "
                     "kijkt naar de pixels onder deze laag.")
        tip.setWordWrap(True)
        v.addWidget(tip)
        v.addStretch()
        self._show()

    def _show(self, *_):
        ch = self.channels[self.channel.currentIndex()]
        self._busy = True
        for i in range(2):
            vals = self.ranges[ch][i]
            self.sliders[i].set_values(vals)
            self.sliders[i].set_color(self.COLORS[ch])
            for k in range(4):
                self.spins[i][k].setValue(vals[k])
        self._busy = False

    def _store(self, i, vals):
        ch = self.channels[self.channel.currentIndex()]
        pair = list(self.ranges[ch])
        pair[i] = list(vals)
        self.ranges[ch] = tuple(pair)
        self.changed.emit()

    def _from_slider(self):
        if self._busy:
            return
        for i in range(2):
            vals = self.sliders[i].v
            self._busy = True
            for k in range(4):
                self.spins[i][k].setValue(vals[k])
            self._busy = False
            self._store(i, vals)

    def _from_spin(self):
        if self._busy:
            return
        for i in range(2):
            vals = [sp.value() for sp in self.spins[i]]
            for k in range(1, 4):  # volgorde bewaken
                vals[k] = max(vals[k], vals[k - 1])
            self._busy = True
            for k in range(4):
                self.spins[i][k].setValue(vals[k])
            self.sliders[i].set_values(vals)
            self._busy = False
            self._store(i, vals)

    def _reset(self):
        ch = self.channels[self.channel.currentIndex()]
        self.ranges[ch] = (list(self.full), list(self.full))
        self._show()
        self.changed.emit()

    def value(self):
        """Mengbereiken voor de laag, of None als alles op standaard staat."""
        from .document import ranges_active
        r = {ch: (tuple(a), tuple(b)) for ch, (a, b) in self.ranges.items()}
        return r if ranges_active(r) else None


class LayerPropertiesDialog(QDialog):
    """Laageigenschappen zoals PSP: tabbladen Algemeen / Mengbereiken, met voorbeeld op afbeelding."""

    def __init__(self, parent, layer, doc=None, title="Laageigenschappen"):
        super().__init__(parent)
        from PySide6.QtWidgets import QLineEdit, QTabWidget, QWidget, QGridLayout, QPushButton, QColorDialog
        from .document import BLEND_MODES
        self.setWindowTitle(title)
        self.layer, self.doc = layer, doc
        from .document import copy_ranges
        self.orig = (layer.name, layer.opacity, layer.mode, layer.visible, layer.lock_alpha, layer.link_set,
                     layer.highlight, copy_ranges(layer.blend_ranges))
        v = QVBoxLayout(self)
        head = QHBoxLayout()
        head.addStretch()
        self.preview = QCheckBox("Voorbeeld op afbeelding")
        self.preview.setChecked(doc is not None)
        self.preview.setEnabled(doc is not None)
        head.addWidget(self.preview)
        v.addLayout(head)
        tabs = QTabWidget()
        gen = QWidget()
        g = QGridLayout(gen)
        self.name = QLineEdit(layer.name)
        self.mode = QComboBox()
        self.mode.addItems([m[0] for m in BLEND_MODES])
        self.mode.setCurrentIndex(layer.mode)
        self.op = _spin(0, 100, round(layer.opacity * 100))
        self.link = _spin(0, 99, layer.link_set)
        self.vis = QCheckBox("Laag is &zichtbaar")
        self.vis.setChecked(layer.visible)
        self.lock = QCheckBox("&Transparantie vergrendelen")
        self.lock.setChecked(layer.lock_alpha)
        grp = QCheckBox("Groep is gekoppeld")
        grp.setEnabled(False)
        self.hl = QCheckBox("Markeren in &lagenpalet:")
        self.hl.setChecked(layer.highlight is not None)
        self.hl_color = QColor(layer.highlight) if layer.highlight is not None else QColor(255, 220, 120)
        self.hl_btn = QPushButton()
        self.hl_btn.setFixedWidth(56)
        self.hl_btn.clicked.connect(lambda: self._pick(QColorDialog))
        self._paint()
        def lbl(text, buddy):
            l = QLabel(text)
            l.setBuddy(buddy)  # Alt+letter springt naar het veld, zoals in PSP
            return l
        g.addWidget(lbl("&Naam:", self.name), 0, 0)
        g.addWidget(self.name, 0, 1, 1, 3)
        g.addWidget(lbl("&Mengen:", self.mode), 1, 0)
        g.addWidget(self.mode, 1, 1)
        g.addWidget(lbl("&Dekking:", self.op), 2, 0)
        g.addWidget(self.op, 2, 1)
        g.addWidget(self.vis, 2, 2)
        g.addWidget(self.lock, 3, 2)
        g.addWidget(lbl("&Koppelingsset:", self.link), 3, 0)
        g.addWidget(self.link, 3, 1)
        g.addWidget(grp, 4, 2)
        hrow = QHBoxLayout()
        hrow.addWidget(self.hl)
        hrow.addWidget(self.hl_btn)
        hrow.addStretch()
        g.addLayout(hrow, 5, 0, 1, 4)
        tabs.addTab(gen, "Algemeen")
        self.ranges = BlendRangesPage(layer.blend_ranges)
        self.ranges.changed.connect(self._live)
        tabs.addTab(self.ranges, "Mengbereiken")
        if layer.kind == "mask":  # een maskerlaag mengt niet
            tabs.setTabEnabled(1, False)
        v.addWidget(tabs)
        v.addWidget(_buttons(self))
        for w in (self.op, self.link):
            w.valueChanged.connect(self._live)
        self.mode.currentIndexChanged.connect(self._live)
        for w in (self.vis, self.lock, self.hl, self.preview):
            w.toggled.connect(self._live)

    def _pick(self, QColorDialog):
        c = QColorDialog.getColor(self.hl_color, self, "Markeerkleur")
        if c.isValid():
            self.hl_color = c
            self.hl.setChecked(True)
            self._paint()

    def _paint(self):
        self.hl_btn.setStyleSheet(f"background:{self.hl_color.name()};")

    def values(self):
        return dict(name=self.name.text() or "Laag", opacity=self.op.value() / 100, mode=self.mode.currentIndex(),
                    visible=self.vis.isChecked(), lock_alpha=self.lock.isChecked(), link_set=self.link.value(),
                    highlight=QColor(self.hl_color) if self.hl.isChecked() else None,
                    blend_ranges=self.ranges.value())

    def _set(self, vals):
        for k, val in vals.items():
            setattr(self.layer, k, val)

    def _live(self, *_):
        if self.doc is None:
            return
        if self.preview.isChecked():
            vals = self.values()
            vals.pop("name")
            self._set(vals)
        else:
            self._restore()
        self.doc.changed.emit(QRect())

    def _restore(self):
        n, o, m, vis, lock, link, hl, br = self.orig
        self._set(dict(name=n, opacity=o, mode=m, visible=vis, lock_alpha=lock, link_set=link, highlight=hl,
                       blend_ranges=br))

    def accept(self):
        if self.doc is not None:
            self._restore()
        super().accept()

    def reject(self):
        if self.doc is not None:
            self._restore()
            self.doc.changed.emit(QRect())
        super().reject()


class TextEntryDialog(QDialog):
    """Niet-modaal tekstinvoervenster met live voorbeeld (zoals 'Tekst invoeren' in PSP)."""
    textChanged = Signal()

    def __init__(self, parent, text=""):
        super().__init__(parent)
        from PySide6.QtWidgets import QPlainTextEdit
        self.setWindowTitle("Tekst invoeren")
        self.setModal(False)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Tekst invoeren"))
        self.edit = QPlainTextEdit(text)
        self.edit.textChanged.connect(self.textChanged)
        v.addWidget(self.edit)
        h = QHBoxLayout()
        self.rem = QCheckBox("Tekst onthouden")
        h.addWidget(self.rem)
        h.addStretch()
        bb = QDialogButtonBox()
        bb.addButton("Toepassen", QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton("Annuleren", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        h.addWidget(bb)
        v.addLayout(h)
        self.resize(380, 170)

    def text(self):
        return self.edit.toPlainText()

    def remember(self):
        return self.rem.isChecked()


class GifExportDialog(QDialog):
    """GIF-optimalisatie: transparantie, gedeeltelijke transparantie, kleuren, met voorbeeld."""

    def __init__(self, main, doc):
        super().__init__(main)
        from PySide6.QtWidgets import QButtonGroup, QGroupBox, QPushButton, QRadioButton, QColorDialog
        from . import fileio
        import numpy as np
        self.np, self.fileio = np, fileio
        self.setWindowTitle("GIF-optimalisatie")
        self.rgba = ops.qimage_to_rgba(doc.flattened())
        self.sel = ops.qimage_to_mask(doc.sel) if doc.sel is not None else None
        self.match = QColor(main.bg)
        self.blend = QColor(255, 255, 255)
        outer = QHBoxLayout(self)
        left = QVBoxLayout()

        g = QGroupBox("Transparantie")
        v = QVBoxLayout(g)
        self.tgroup = QButtonGroup(self)
        opts = ["Geen", "Bestaande transparantie van afbeelding of laag", "Gebieden binnen de huidige selectie",
                "Gebieden buiten de huidige selectie", "Gebieden die overeenkomen met deze kleur:"]
        for i, t in enumerate(opts):
            rb = QRadioButton(t)
            rb.setEnabled(i < 2 or i == 4 or self.sel is not None)
            self.tgroup.addButton(rb, i)
            v.addWidget(rb)
        has_alpha = self.rgba[..., 3].min() < 255
        self.tgroup.button(1 if has_alpha else 0).setChecked(True)
        row = QHBoxLayout()
        self.mbtn = QPushButton()
        self.mbtn.clicked.connect(lambda: self._pick("match", QColorDialog))
        row.addWidget(self.mbtn)
        row.addWidget(QLabel("Tolerantie:"))
        self.mtol = _spin(0, 200, 0)
        row.addWidget(self.mtol)
        v.addLayout(row)
        left.addWidget(g)

        g = QGroupBox("Gedeeltelijke transparantie")
        v = QVBoxLayout(g)
        self.pgroup = QButtonGroup(self)
        rb1 = QRadioButton("Drempel: pixels minder dan dit percentage dekkend worden transparant")
        rb2 = QRadioButton("Overvloeien met kleur:")
        self.pgroup.addButton(rb1, 0)
        self.pgroup.addButton(rb2, 1)
        rb1.setChecked(True)
        v.addWidget(rb1)
        self.thr = _spin(1, 100, 50, " %")
        v.addWidget(self.thr)
        row = QHBoxLayout()
        row.addWidget(rb2)
        self.bbtn = QPushButton()
        self.bbtn.clicked.connect(lambda: self._pick("blend", QColorDialog))
        row.addWidget(self.bbtn)
        v.addLayout(row)
        left.addWidget(g)

        g = QGroupBox("Kleuren")
        f = QFormLayout(g)
        self.colors = _spin(2, 256, 256)
        self.dither = QCheckBox("Dithering (Floyd-Steinberg)")
        self.dither.setChecked(True)
        self.interlace = QCheckBox("Interliniëren")
        f.addRow("Aantal kleuren:", self.colors)
        f.addRow(self.dither)
        f.addRow(self.interlace)
        left.addWidget(g)
        left.addWidget(_buttons(self))
        outer.addLayout(left)

        right = QVBoxLayout()
        right.addWidget(QLabel("Voorbeeld:"))
        self.preview = QLabel()
        self.preview.setFixedSize(260, 260)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.preview)
        self.info = QLabel()
        right.addWidget(self.info)
        right.addStretch()
        outer.addLayout(right)
        self._paint_btns()
        self.timer = QTimer(self, singleShot=True, interval=200)
        self.timer.timeout.connect(self.update_preview)
        for w in (self.mtol, self.thr, self.colors):
            w.valueChanged.connect(self.timer.start)
        for w in (self.dither,):
            w.toggled.connect(self.timer.start)
        self.tgroup.idClicked.connect(lambda _: self.timer.start())
        self.pgroup.idClicked.connect(lambda _: self.timer.start())
        self.update_preview()

    def _pick(self, which, QColorDialog):
        c = QColorDialog.getColor(getattr(self, which), self)
        if c.isValid():
            setattr(self, which, c)
            self._paint_btns()
            self.timer.start()

    def _paint_btns(self):
        self.mbtn.setStyleSheet(f"background:{self.match.name()}; min-width:40px;")
        self.bbtn.setStyleSheet(f"background:{self.blend.name()}; min-width:40px;")

    def result(self):
        rgb = lambda c: (c.red(), c.green(), c.blue())  # noqa: E731
        return self.fileio.gif_image(self.rgba, self.sel, self.tgroup.checkedId(), rgb(self.match), self.mtol.value(),
                                     self.pgroup.checkedId(), round(self.thr.value() * 2.55), rgb(self.blend),
                                     self.colors.value(), self.dither.isChecked())

    def update_preview(self):
        from PySide6.QtGui import QPixmap
        q = self.result()
        rgba = self.np.array(q.convert("RGBA"))
        img = ops.rgba_to_qimage(rgba).scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
        pm = QPixmap(img.size())
        from PySide6.QtGui import QPainter
        p = QPainter(pm)
        for y in range(0, pm.height(), 8):
            for x in range(0, pm.width(), 8):
                p.fillRect(x, y, 8, 8, QColor(255, 255, 255) if (x // 8 + y // 8) % 2 == 0 else QColor(204, 204, 204))
        p.drawImage(0, 0, img)
        p.end()
        self.preview.setPixmap(pm)
        n = len(q.getcolors(256) or [])
        from .i18n import tr
        self.info.setText(tr("Kleuren gebruikt: {}").format(n) + (tr("\nmet transparantie") if "transparency" in q.info else ""))


class JpegExportDialog(QDialog):
    def __init__(self, parent, quality=90):
        super().__init__(parent)
        self.setWindowTitle("JPEG-optimalisatie")
        f = QFormLayout(self)
        self.q = _spin(1, 100, quality)
        self.prog = QCheckBox("Progressief")
        self.sub = QComboBox()
        self.sub.addItems(["4:4:4 (geen)", "4:2:2", "4:2:0 (standaard)"])
        self.sub.setCurrentIndex(2)
        f.addRow("Kwaliteit:", self.q)
        f.addRow("Chroma-subsampling:", self.sub)
        f.addRow(self.prog)
        f.addRow(_buttons(self))


class MaskFromImageDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Masker uit afbeelding")
        f = QFormLayout(self)
        self.src = QComboBox()
        self.src.addItems(["Bronluminantie", "Brondekking (transparantie van de laag)"])
        self.inv = QCheckBox("Maskergegevens omkeren")
        f.addRow("Masker maken van:", self.src)
        f.addRow(self.inv)
        f.addRow(_buttons(self))

    def values(self):
        return ["luminance", "alpha"][self.src.currentIndex()], self.inv.isChecked()


class PreferencesDialog(QDialog):
    """Algemene programmavoorkeuren (voorlopig: taal)."""

    def __init__(self, parent, current):
        super().__init__(parent)
        from .i18n import LANGUAGES
        self.setWindowTitle("Algemene programmavoorkeuren")
        f = QFormLayout(self)
        self.lang = QComboBox()
        self.codes = [c for c, _ in LANGUAGES]
        self.lang.addItems([name for _, name in LANGUAGES])
        self.lang.setProperty("pp_notr", True)  # taalnamen altijd in hun eigen taal
        self.lang.setCurrentIndex(self.codes.index(current) if current in self.codes else 0)
        f.addRow("Taal / Language:", self.lang)
        f.addRow(QLabel("De nieuwe taal wordt actief na het herstarten van PixelPickle."))
        f.addRow(_buttons(self))

    def language(self):
        return self.codes[self.lang.currentIndex()]


class AutosaveDialog(QDialog):
    """Instellingen voor automatisch opslaan."""

    def __init__(self, parent, enabled, minutes):
        super().__init__(parent)
        self.setWindowTitle("Instellingen voor automatisch opslaan")
        f = QFormLayout(self)
        self.enabled = QCheckBox("Automatisch opslaan inschakelen")
        self.enabled.setChecked(enabled)
        f.addRow(self.enabled)
        self.minutes = _spin(1, 999, minutes)
        self.minutes.setEnabled(enabled)
        self.enabled.toggled.connect(self.minutes.setEnabled)
        f.addRow("Minuten:", self.minutes)
        info = QLabel("Gewijzigde afbeeldingen worden bewaard in een herstelmap, niet over uw eigen "
                      "bestanden heen. Sluit PixelPickle onverwacht af, dan kunt u ze bij de volgende "
                      "start terughalen.")
        info.setWordWrap(True)
        info.setMinimumWidth(320)
        f.addRow(info)
        f.addRow(_buttons(self))


def text_window(parent, title, html, size=(720, 640)):
    """Venster met opgemaakte tekst, schuifbalk en aanpasbare grootte (handleiding, sneltoetsen)."""
    from PySide6.QtWidgets import QTextBrowser, QVBoxLayout
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setSizeGripEnabled(True)
    v = QVBoxLayout(dlg)
    tb = QTextBrowser()
    tb.setOpenExternalLinks(True)
    tb.setHtml(html)
    v.addWidget(tb)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    bb.accepted.connect(dlg.accept)
    v.addWidget(bb)
    dlg.resize(*size)
    return dlg


class AboutDialog(QDialog):
    """Info over PixelPickle: versie, makers, licentie en gebruikte onderdelen."""

    def __init__(self, parent, icon):
        super().__init__(parent)
        import platform
        import numpy
        import PIL
        import PySide6
        from PySide6.QtCore import qVersion
        from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout
        from . import __version__
        from .i18n import tr
        self.setWindowTitle("Over PixelPickle")
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        pic = QLabel()
        pic.setPixmap(icon.pixmap(96, 96))
        pic.setAlignment(Qt.AlignmentFlag.AlignTop)
        top.addWidget(pic)
        url = "https://github.com/rene-timmermans/pixelpickle"
        txt = QLabel(
            f"<h2 style='margin:0'>PixelPickle {__version__}</h2>"
            f"<p>{tr('Een eenvoudig te gebruiken fotobewerker die meteen vertrouwd aanvoelt.')}</p>"
            f"<p><b>{tr('Gemaakt door')}</b><br>René Timmermans<br>{tr('met Claude (Anthropic)')}</p>"
            f"<p><b>{tr('Licentie')}</b><br>{tr('Vrije software onder de GNU General Public License, versie 3 of later.')}</p>"
            f"<p><b>{tr('Website')}</b><br><a href='{url}'>{url}</a></p>"
            f"<p style='color:gray'>{tr('Gebouwd met')} Python {platform.python_version()}, Qt {qVersion()}, "
            f"PySide6 {PySide6.__version__}, NumPy {numpy.__version__}, Pillow {PIL.__version__}</p>")
        txt.setProperty("pp_notr", True)
        txt.setWordWrap(True)
        txt.setOpenExternalLinks(True)
        txt.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        txt.setMinimumWidth(420)
        top.addWidget(txt, 1)
        v.addLayout(top)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.accepted.connect(self.accept)
        v.addWidget(bb)
