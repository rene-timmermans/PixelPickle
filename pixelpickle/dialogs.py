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
    """Niet-modaal tekstinvoervenster met live voorbeeld (zoals 'Tekst invoeren' in PSP).
    De optiebalk bepaalt de opmaak van de hele tekst; met het werkbalkje in dit venster geef je geselecteerde
    woorden een eigen opmaak (vet, cursief, onderstreept, kleur, lettertype, grootte). Alleen wat afwijkt
    wordt per stuk bewaard (zie runs())."""
    textChanged = Signal()
    SIZE = 1  # eigen eigenschap in de tekstopmaak: grootte in de eenheden van de tekst

    def __init__(self, parent, text="", t=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QFontComboBox, QTextEdit, QToolBar
        from PySide6.QtGui import QAction
        self.setWindowTitle("Tekst invoeren")
        self.setModal(False)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Tekst invoeren"))
        tb = QToolBar()
        tb.setIconSize(tb.iconSize() * 0.8)
        self.edit = QTextEdit()
        self.edit.setAcceptRichText(False)  # plakken: alleen tekst
        self.edit.setTabChangesFocus(True)
        self.edit.document().setDefaultFont(self.edit.font())
        self.edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.edit.customContextMenuRequested.connect(self._context_menu)
        self.base_pt = self.edit.font().pointSizeF() if self.edit.font().pointSizeF() > 0 else 10.0

        def act(text, tip, fn, checkable=True, bold=False, italic=False, underline=False):
            a = QAction(text, self)
            a.setToolTip(tip)
            a.setCheckable(checkable)
            f = a.font()
            f.setBold(bold)
            f.setItalic(italic)
            f.setUnderline(underline)
            a.setFont(f)
            a.triggered.connect(fn)
            tb.addAction(a)
            return a
        self.a_bold = act("B", "Vet", lambda on: self._merge(bold=on), bold=True)
        self.a_italic = act("I", "Cursief", lambda on: self._merge(italic=on), italic=True)
        self.a_under = act("U", "Onderstreept", lambda on: self._merge(underline=on), underline=True)
        tb.addSeparator()
        self.a_color = act("●", "Kleur van de geselecteerde tekst", self._pick_color, checkable=False)
        tb.addSeparator()
        self.font_box = QFontComboBox()
        self.font_box.setToolTip("Lettertype van de geselecteerde tekst")
        self.font_box.setMaximumWidth(170)
        self.font_box.activated.connect(lambda *_: self._merge(family=self.font_box.currentFont().family()))
        tb.addWidget(self.font_box)
        self.size_box = QSpinBox()
        self.size_box.setRange(1, 2000)
        self.size_box.setToolTip("Grootte van de geselecteerde tekst")
        self.size_box.editingFinished.connect(lambda: self._merge(size=self.size_box.value()))
        tb.addWidget(self.size_box)
        tb.addSeparator()
        act("⌫", "Opmaak van de selectie wissen (terug naar de optiebalk)", self._clear_format, checkable=False)
        v.addWidget(tb)
        self.base = dict(t) if t else None
        self._fill_editor(text, t)
        self.edit.textChanged.connect(self.textChanged)
        self.edit.currentCharFormatChanged.connect(self._sync_buttons)
        self.edit.cursorPositionChanged.connect(self._sync_buttons)
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
        self.resize(520, 230)
        self._sync_buttons()

    def _context_menu(self, pos):
        """Zoals PSP: alleen knippen, kopiëren en plakken."""
        from PySide6.QtWidgets import QApplication, QMenu
        m = QMenu(self)
        sel = self.edit.textCursor().hasSelection()
        m.addAction("Knippen", self.edit.cut).setEnabled(sel)
        m.addAction("Kopiëren", self.edit.copy).setEnabled(sel)
        m.addAction("Plakken", self.edit.paste).setEnabled(bool(QApplication.clipboard().text()))
        m.exec(self.edit.mapToGlobal(pos))

    # ------------------------------------------------------------ opmaak in de editor
    def set_base(self, t):
        """De opmaak uit de optiebalk (wordt bij elke wijziging bijgewerkt)."""
        self.base = dict(t)
        self._sync_buttons()

    def _base(self, key, default=None):
        return (self.base or {}).get(key, default)

    def _merge(self, bold=None, italic=None, underline=None, color=None, family=None, size=None):
        from PySide6.QtGui import QFont, QTextCharFormat
        fmt = QTextCharFormat()
        if bold is not None:
            fmt.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
        if italic is not None:
            fmt.setFontItalic(italic)
        if underline is not None:
            fmt.setFontUnderline(underline)
        if color is not None:
            fmt.setForeground(color)
        if family is not None:
            fmt.setFontFamilies([family])
        if size is not None:
            fmt.setProperty(QTextCharFormat.Property.UserProperty + self.SIZE, float(size))
            base = max(1.0, float(self._base("size", 12)))
            fmt.setFontPointSize(max(6.0, min(40.0, self.base_pt * size / base)))  # alleen voor de weergave
        cur = self.edit.textCursor()
        if not cur.hasSelection():
            self.edit.mergeCurrentCharFormat(fmt)  # geldt voor wat je hierna typt
        else:
            cur.mergeCharFormat(fmt)
        self.edit.setFocus()
        self.textChanged.emit()

    def _pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        cur = self.edit.currentCharFormat()
        start = cur.foreground().color() if cur.hasProperty(cur.Property.ForegroundBrush) else \
            QColor(*(self._base("fill") or (0, 0, 0)))
        c = QColorDialog.getColor(start, self, "Kleur")
        if c.isValid():
            self._merge(color=c)

    def _clear_format(self):
        from PySide6.QtGui import QTextCharFormat
        cur = self.edit.textCursor()
        if cur.hasSelection():
            cur.setCharFormat(QTextCharFormat())
        else:
            self.edit.setCurrentCharFormat(QTextCharFormat())
        self.textChanged.emit()
        self._sync_buttons()

    def _sync_buttons(self, *_):
        from PySide6.QtGui import QFont, QTextCharFormat
        f = self.edit.currentCharFormat()
        P = QTextCharFormat.Property
        self.a_bold.setChecked(f.fontWeight() >= QFont.Weight.DemiBold if f.hasProperty(P.FontWeight) else bool(self._base("bold")))
        self.a_italic.setChecked(f.fontItalic() if f.hasProperty(P.FontItalic) else bool(self._base("italic")))
        self.a_under.setChecked(f.fontUnderline() if f.hasProperty(P.TextUnderlineStyle) else bool(self._base("underline")))
        fam = f.fontFamilies()[0] if f.hasProperty(P.FontFamilies) and f.fontFamilies() else self._base("family")
        if fam:
            self.font_box.blockSignals(True)
            self.font_box.setCurrentFont(QFont(fam))
            self.font_box.blockSignals(False)
        from PySide6.QtGui import QIcon, QPainter as _QP, QPixmap
        col = f.foreground().color() if f.hasProperty(P.ForegroundBrush) else QColor(*(self._base("fill") or (0, 0, 0)))
        pm = QPixmap(16, 16)
        pm.fill(QColor(0, 0, 0, 0))
        q = _QP(pm)
        q.setRenderHint(_QP.RenderHint.Antialiasing)
        q.setBrush(col)
        q.setPen(self.palette().mid().color())
        q.drawEllipse(2, 2, 12, 12)
        q.end()
        self.a_color.setIcon(QIcon(pm))
        size = f.property(P.UserProperty + self.SIZE) if f.hasProperty(P.UserProperty + self.SIZE) else self._base("size", 12)
        self.size_box.blockSignals(True)
        self.size_box.setValue(int(round(float(size or 12))))
        self.size_box.blockSignals(False)

    def _fill_editor(self, text, t):
        """Editor vullen: platte tekst, of de opmaakdelen van een bestaande tekst (afwijkingen van de basis)."""
        from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor
        runs = (t or {}).get("runs")
        if not runs:
            self.edit.setPlainText(text)
            return
        base = t if "family" in t else runs[0][0]
        cur = QTextCursor(self.edit.document())
        for style, stroke, fill, chunk in runs:
            fmt = QTextCharFormat()
            if style.get("family") and style.get("family") != base.get("family"):
                fmt.setFontFamilies([style["family"]])
            if style.get("size") and abs(float(style["size"]) - float(base.get("size", style["size"]))) > 1e-6:
                fmt.setProperty(QTextCharFormat.Property.UserProperty + self.SIZE, float(style["size"]))
                fmt.setFontPointSize(max(6.0, min(40.0, self.base_pt * float(style["size"]) / max(1.0, float(base.get("size", 12))))))
            b = style.get("bold", style.get("weight", 400) >= 600)
            if b != base.get("bold", base.get("weight", 400) >= 600):
                fmt.setFontWeight(QFont.Weight.Bold if b else QFont.Weight.Normal)
            if bool(style.get("italic")) != bool(base.get("italic")):
                fmt.setFontItalic(bool(style.get("italic")))
            if bool(style.get("underline")) != bool(base.get("underline")):
                fmt.setFontUnderline(bool(style.get("underline")))
            base_fill = t.get("fill") if "fill" in t else runs[0][2]
            if fill is not None and tuple(fill) != tuple(base_fill or ()):
                fmt.setForeground(QColor(*fill))
            cur.insertText(chunk.replace("\r\n", "\n").replace("\r", "\n"), fmt)

    # ------------------------------------------------------------ uitkomst
    def text(self):
        return self.edit.toPlainText()

    def runs(self, t):
        """Opmaakdelen voor tekstgegevens t (zie textlayer): [[stijl, rand, vulling, tekst], ...], of None
        als niets afwijkt van de optiebalk (dan geldt die voor de hele tekst)."""
        from PySide6.QtGui import QFont, QTextCharFormat
        P = QTextCharFormat.Property
        keys = ("family", "size", "units", "bold", "italic", "underline", "tracking", "stroke_width")
        out, any_override = [], False
        doc = self.edit.document()
        block = doc.begin()
        first = True
        while block.isValid():
            if not first:
                out.append(None)  # regeleinde
            first = False
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    f = frag.charFormat()
                    style = {k: t.get(k) for k in keys}
                    fill = t.get("fill")
                    if f.hasProperty(P.FontWeight):
                        style["bold"] = f.fontWeight() >= QFont.Weight.DemiBold
                    if f.hasProperty(P.FontItalic):
                        style["italic"] = f.fontItalic()
                    if f.hasProperty(P.TextUnderlineStyle):
                        style["underline"] = f.fontUnderline()
                    if f.hasProperty(P.FontFamilies) and f.fontFamilies():
                        style["family"] = f.fontFamilies()[0]
                    if f.hasProperty(P.UserProperty + self.SIZE):
                        style["size"] = float(f.property(P.UserProperty + self.SIZE))
                    if f.hasProperty(P.ForegroundBrush) and fill is not None:
                        c = f.foreground().color()
                        fill = (c.red(), c.green(), c.blue())
                    if any(style[k] != t.get(k) for k in keys) or (fill is not None and tuple(fill) != tuple(t.get("fill") or ())):
                        any_override = True
                    out.append([style, t.get("stroke"), list(fill) if fill is not None else None, frag.text()])
                it += 1
            block = block.next()
        if not any_override:
            return None
        runs = []
        for r in out:  # regeleinden aan het vorige deel toevoegen en gelijke delen samenvoegen
            if r is None:
                if runs:
                    runs[-1][3] += "\n"
                else:
                    runs.append([{k: t.get(k) for k in keys}, t.get("stroke"), t.get("fill"), "\n"])
                continue
            if runs and runs[-1][0] == r[0] and runs[-1][2] == r[2] and not runs[-1][3].endswith("\n"):
                runs[-1][3] += r[3]
            else:
                runs.append(r)
        return runs

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


CHECKER_SIZES = [4, 8, 16]  # halve tegel in pixels: klein, middel, groot
CHECKER_SCHEMES = [("Lichtgrijs", "#ffffff", "#cccccc"), ("Middengrijs", "#999999", "#666666"),
                   ("Donkergrijs", "#444444", "#2a2a2a"), ("Zwart-wit", "#ffffff", "#000000")]


def view_settings():
    """Weergave-instellingen uit de voorkeuren (ruitjespatroon achter transparantie en arcering bij bijsnijden)."""
    from PySide6.QtCore import QSettings
    st = QSettings("PixelPickle", "PixelPickle")
    return {"checker_size": int(st.value("checker_size", 1)), "checker_c1": st.value("checker_c1", "#ffffff"),
            "checker_c2": st.value("checker_c2", "#cccccc"), "shade": st.value("crop_shade", "true") == "true",
            "shade_color": st.value("crop_shade_color", "#000000"), "shade_opacity": int(st.value("crop_shade_opacity", 35)),
            "crop_bar": st.value("crop_bar", "true") == "true"}


def checker_brush(size_index, c1, c2):
    from PySide6.QtGui import QBrush, QPainter, QPixmap
    h = CHECKER_SIZES[max(0, min(2, size_index))]
    pm = QPixmap(2 * h, 2 * h)
    pm.fill(QColor(c1))
    p = QPainter(pm)
    p.fillRect(0, 0, h, h, QColor(c2))
    p.fillRect(h, h, h, h, QColor(c2))
    p.end()
    return QBrush(pm)


class _ColorButton(QWidget):
    changed = Signal()

    def __init__(self, color):
        from PySide6.QtWidgets import QPushButton
        super().__init__()
        self.color = QColor(color)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.btn = QPushButton()
        self.btn.setFixedSize(70, 26)
        self.btn.clicked.connect(self._pick)
        lay.addWidget(self.btn)
        self._paint()

    def _paint(self):
        from PySide6.QtGui import QIcon, QPixmap
        pm = QPixmap(52, 14)
        pm.fill(self.color)
        self.btn.setIcon(QIcon(pm))

    def set_color(self, c):
        self.color = QColor(c)
        self._paint()

    def _pick(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(self.color, self, "Kleur")
        if c.isValid():
            self.set_color(c)
            self.changed.emit()


class PreferencesDialog(QDialog):
    """Algemene programmavoorkeuren: taal, transparantie en arcering, en lettertypen (met de mogelijkheid de
    Microsoft-kernlettertypen te downloaden)."""

    def __init__(self, parent, current):
        from PySide6.QtWidgets import QGroupBox, QListWidget, QPushButton, QProgressBar, QStackedWidget
        from .i18n import LANGUAGES
        super().__init__(parent)
        self.setWindowTitle("Algemene programmavoorkeuren")
        outer = QVBoxLayout(self)
        body = QHBoxLayout()
        outer.addLayout(body, 1)
        self.pages = QListWidget()
        self.pages.setFixedWidth(190)
        self.stack = QStackedWidget()
        body.addWidget(self.pages)
        body.addWidget(self.stack, 1)
        vs = view_settings()

        # --- taal
        page = QWidget()
        f = QFormLayout(page)
        self.lang = QComboBox()
        self.codes = [c for c, _ in LANGUAGES]
        self.lang.addItems([name for _, name in LANGUAGES])
        self.lang.setProperty("pp_notr", True)  # taalnamen altijd in hun eigen taal
        self.lang.setCurrentIndex(self.codes.index(current) if current in self.codes else 0)
        f.addRow("Taal / Language:", self.lang)
        f.addRow(QLabel("De nieuwe taal wordt actief na het herstarten van PixelPickle."))
        self._add_page("Taal", page)

        # --- transparantie en arcering
        page = QWidget()
        v = QVBoxLayout(page)
        grid = QGroupBox("Ruitjespatroon achter transparante delen")
        gf = QFormLayout(grid)
        self.csize = QComboBox()
        self.csize.addItems(["Klein", "Middel", "Groot"])
        self.csize.setCurrentIndex(vs["checker_size"])
        self.scheme = QComboBox()
        self.scheme.addItems([n for n, _, _ in CHECKER_SCHEMES] + ["Eigen kleuren"])
        idx = next((k for k, (_, a, b) in enumerate(CHECKER_SCHEMES)
                    if (a, b) == (vs["checker_c1"], vs["checker_c2"])), len(CHECKER_SCHEMES))
        self.scheme.setCurrentIndex(idx)
        self.c1, self.c2 = _ColorButton(vs["checker_c1"]), _ColorButton(vs["checker_c2"])
        crow = QHBoxLayout()
        crow.addWidget(QLabel("Kleur 1:"))
        crow.addWidget(self.c1)
        crow.addWidget(QLabel("Kleur 2:"))
        crow.addWidget(self.c2)
        crow.addStretch()
        gf.addRow("Grootte:", self.csize)
        gf.addRow("Schema:", self.scheme)
        gf.addRow(crow)
        self.preview = QLabel()
        self.preview.setFixedSize(120, 80)
        gf.addRow("Voorbeeld:", self.preview)
        v.addWidget(grid)
        shade = QGroupBox("Arcering bij bijsnijden")
        sf = QFormLayout(shade)
        self.shade_on = QCheckBox("Gebied buiten het bijsnijkader arceren")
        self.shade_on.setChecked(vs["shade"])
        self.shade_col = _ColorButton(vs["shade_color"])
        self.shade_op = _spin(0, 100, vs["shade_opacity"], " %")
        self.crop_bar = QCheckBox("Zwevende werkbalk bij bijsnijden tonen")
        self.crop_bar.setChecked(vs["crop_bar"])
        sf.addRow(self.shade_on)
        sf.addRow("Kleur:", self.shade_col)
        sf.addRow("Dekking:", self.shade_op)
        sf.addRow(self.crop_bar)
        v.addWidget(shade)
        v.addStretch()
        self.csize.currentIndexChanged.connect(self._preview)
        self.scheme.currentIndexChanged.connect(self._scheme)
        self.c1.changed.connect(self._custom)
        self.c2.changed.connect(self._custom)
        self._add_page("Transparantie en arcering", page)

        # --- lettertypen
        page = QWidget()
        v = QVBoxLayout(page)
        from . import corefonts
        info = QLabel("De bekende Microsoft-lettertypen (Arial, Times New Roman, Courier New, Verdana, Georgia, "
                      "Trebuchet MS, Comic Sans MS, Impact, Webdings en Andale Mono) mogen niet met PixelPickle "
                      "worden meegeleverd. Je kunt de originele bestanden wel zelf bij de bron downloaden; "
                      "PixelPickle zet ze dan in je eigen lettertypemap, zonder beheerdersrechten.")
        info.setWordWrap(True)
        v.addWidget(info)
        self.font_state = QLabel()
        self.font_state.setWordWrap(True)
        v.addWidget(self.font_state)
        self.font_btn = QPushButton("Microsoft-kernlettertypen downloaden en installeren")
        self.font_btn.clicked.connect(self._install_fonts)
        v.addWidget(self.font_btn)
        self.font_bar = QProgressBar()
        self.font_bar.setRange(0, len(corefonts.FILES) + 1)
        self.font_bar.hide()
        v.addWidget(self.font_bar)
        lic = QLabel("Door te downloaden ga je akkoord met de licentie van Microsoft voor deze lettertypen "
                     "(gratis te gebruiken, niet te verkopen).")
        lic.setWordWrap(True)
        lic.setStyleSheet("color: gray;")
        v.addWidget(lic)
        v.addStretch()
        self._add_page("Lettertypen", page)
        self._font_state()

        self.pages.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.pages.setCurrentRow(0)
        outer.addWidget(_buttons(self))
        self._preview()
        self.resize(640, 420)

    def _add_page(self, title, widget):
        self.pages.addItem(title)
        self.stack.addWidget(widget)

    def _scheme(self, i):
        if i < len(CHECKER_SCHEMES):
            _, a, b = CHECKER_SCHEMES[i]
            self.c1.set_color(a)
            self.c2.set_color(b)
        self._preview()

    def _custom(self):
        self.scheme.blockSignals(True)
        self.scheme.setCurrentIndex(len(CHECKER_SCHEMES))
        self.scheme.blockSignals(False)
        self._preview()

    def _preview(self, *_):
        from PySide6.QtGui import QPainter, QPixmap
        pm = QPixmap(self.preview.size())
        p = QPainter(pm)
        p.fillRect(pm.rect(), checker_brush(self.csize.currentIndex(), self.c1.color, self.c2.color))
        p.end()
        self.preview.setPixmap(pm)

    def _font_state(self):
        from . import corefonts
        from .i18n import tr
        if corefonts.installed():
            self.font_state.setText(tr("De Microsoft-kernlettertypen zijn geïnstalleerd."))
            self.font_btn.setEnabled(False)
        elif corefonts.extractor() is None:
            self.font_state.setText(tr("Om de lettertypen uit te pakken is het programma cabextract (of 7z) nodig. "
                                       "Installeer dat eerst met je pakketbeheerder."))
            self.font_btn.setEnabled(False)
        else:
            self.font_state.setText(tr("De Microsoft-kernlettertypen zijn nog niet geïnstalleerd."))
            self.font_btn.setEnabled(True)

    def _install_fonts(self):
        from . import corefonts
        from .i18n import tr
        self.font_btn.setEnabled(False)
        self.font_bar.show()
        self.font_bar.setValue(0)
        self.font_state.setText(tr("Bezig met downloaden..."))
        self.installer = corefonts.Installer()
        self.installer.start()
        self._font_timer = QTimer(self)
        self._font_timer.timeout.connect(self._font_poll)
        self._font_timer.start(200)

    def _font_poll(self):
        from . import corefonts
        from .i18n import tr
        inst = self.installer
        self.font_bar.setValue(inst.step)
        if not inst.done:
            return
        self._font_timer.stop()
        self.font_bar.hide()
        if inst.error:
            msg = {"noextractor": "Om de lettertypen uit te pakken is het programma cabextract (of 7z) nodig.",
                   "empty": "Er zijn geen lettertypen gevonden in de gedownloade bestanden."}.get(
                inst.error, "Downloaden is niet gelukt (is er een internetverbinding?).")
            self.font_state.setText(tr(msg))
            self.font_btn.setEnabled(True)
            return
        n = corefonts.register(inst.result)
        self.font_state.setText(tr("{} lettertypebestanden geïnstalleerd; ze zijn meteen te gebruiken.").format(n))

    def language(self):
        return self.codes[self.lang.currentIndex()]

    def save_view_settings(self):
        from PySide6.QtCore import QSettings
        st = QSettings("PixelPickle", "PixelPickle")
        st.setValue("checker_size", self.csize.currentIndex())
        st.setValue("checker_c1", self.c1.color.name())
        st.setValue("checker_c2", self.c2.color.name())
        st.setValue("crop_shade", "true" if self.shade_on.isChecked() else "false")
        st.setValue("crop_shade_color", self.shade_col.color.name())
        st.setValue("crop_shade_opacity", self.shade_op.value())
        st.setValue("crop_bar", "true" if self.crop_bar.isChecked() else "false")


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


class AlphaChannelDialog(QDialog):
    """Alfakanalen: opslaan (naam kiezen; een bestaand kanaal kan overschreven worden), laden (kanaal
    kiezen met voorbeeld, omkeren en bij selecties de bewerking) of verwijderen."""

    def __init__(self, parent, title, doc, mode, default_name="", selection_ops=False):
        from PySide6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem
        super().__init__(parent)
        self.setWindowTitle(title)
        self.doc, self.mode = doc, mode
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        v.addLayout(top)
        left = QVBoxLayout()
        top.addLayout(left)
        left.addWidget(QLabel("Alfakanalen in deze afbeelding:" if doc.channels else "Deze afbeelding heeft nog geen alfakanalen."))
        self.list = QListWidget()
        self.list.setProperty("pp_notr", True)
        self.list.setMinimumWidth(220)
        for n in doc.channel_names():
            self.list.addItem(QListWidgetItem(n))
        if mode == "delete":
            self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        left.addWidget(self.list)
        self.preview = QLabel()
        self.preview.setFixedSize(160, 160)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background: #000; border: 1px solid palette(mid);")
        top.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)
        f = QFormLayout()
        v.addLayout(f)
        self.name = self.op = self.invert = self.all = None
        if mode == "save":
            self.name = QLineEdit(default_name)
            self.name.setProperty("pp_notr", True)
            f.addRow("Naam:", self.name)
            hint = QLabel("Kies een bestaand kanaal om het te overschrijven.")
            hint.setStyleSheet("color: gray;")
            f.addRow(hint)
            # alleen een bewuste klik neemt de naam over (de lijst kiest bij het tonen soms zelf een rij)
            self.list.itemClicked.connect(lambda it: self.name.setText(it.text()))
            self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        elif mode == "load":
            if selection_ops:
                self.op = QComboBox()
                self.op.addItems(["Vervangen", "Toevoegen", "Verwijderen"])
                f.addRow("Bewerking:", self.op)
            self.invert = QCheckBox("Omkeren")
            self.invert.toggled.connect(self._show_preview)
            f.addRow(self.invert)
        else:
            self.all = QCheckBox("Alle alfakanalen verwijderen")
            self.all.toggled.connect(lambda on: self.list.setEnabled(not on))
            f.addRow(self.all)
        self.list.currentRowChanged.connect(self._show_preview)
        if self.list.count() and mode != "save":
            self.list.setCurrentRow(self.list.count() - 1)
        bb = _buttons(self)
        self.ok = bb.button(QDialogButtonBox.StandardButton.Ok)
        v.addWidget(bb)
        self.list.itemSelectionChanged.connect(self._update_ok)
        if self.name is not None:
            self.name.textChanged.connect(self._update_ok)
        if self.all is not None:
            self.all.toggled.connect(self._update_ok)
        self._update_ok()
        self._show_preview()

    def _update_ok(self):
        if self.mode == "save":
            ok = bool(self.name.text().strip())
        elif self.mode == "delete":
            ok = bool(self.doc.channels) and (self.all.isChecked() or bool(self.list.selectedItems()))
        else:
            ok = self.list.currentRow() >= 0
        self.ok.setEnabled(ok)

    def _show_preview(self, *_):
        from PySide6.QtGui import QPixmap
        i = self.list.currentRow()
        if i < 0 or i >= len(self.doc.channels):
            self.preview.clear()
            return
        arr = self.doc.channel_mask(i)
        if self.invert is not None and self.invert.isChecked():
            arr = 255 - arr
        img = QImage(arr.data, arr.shape[1], arr.shape[0], arr.strides[0], QImage.Format.Format_Grayscale8).copy()
        self.preview.setPixmap(QPixmap.fromImage(img).scaled(156, 156, Qt.AspectRatioMode.KeepAspectRatio,
                                                             Qt.TransformationMode.SmoothTransformation))

    def values(self):
        if self.mode == "save":
            return self.name.text().strip()
        if self.mode == "delete":
            if self.all.isChecked():
                return list(range(len(self.doc.channels)))
            return sorted(self.list.row(it) for it in self.list.selectedItems())
        op = ["replace", "add", "sub"][self.op.currentIndex()] if self.op is not None else "replace"
        return self.list.currentRow(), op, self.invert.isChecked()


class Magnifier(QWidget):
    """Vergrootglas: zwevend venster met een uitvergroting van de afbeelding onder de muis (zoals PSP).
    Het muiswiel in het venster kiest de vergroting; een kruisje markeert het punt onder de muis."""
    closed = Signal()

    def __init__(self, main):
        super().__init__(main, Qt.WindowType.Tool)
        self.main = main
        self.setWindowTitle("Vergrootglas")
        self.resize(240, 240)
        self.zoom = 5
        self._last = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)

    def showEvent(self, e):
        self.timer.start(40)
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        self.closed.emit()
        super().hideEvent(e)

    def _canvas_under_mouse(self):
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication
        from .canvas import Canvas
        w = QApplication.widgetAt(QCursor.pos())
        while w is not None and not isinstance(w, Canvas):
            w = w.parentWidget()
        return w

    def _poll(self):
        from PySide6.QtGui import QCursor
        cv = self._canvas_under_mouse()
        if cv is None:
            return
        pt = cv.to_doc(cv.mapFromGlobal(QCursor.pos()).toPointF())
        key = (id(cv), round(pt.x(), 1), round(pt.y(), 1), cv.cache.cacheKey() if cv.cache is not None else 0, self.zoom)
        if key != self._last:
            self._last = key
            self._cv, self._pt = cv, pt
            self.update()

    def wheelEvent(self, e):
        self.zoom = max(2, min(16, self.zoom + (1 if e.angleDelta().y() > 0 else -1)))
        self._last = None
        self.setWindowTitle(f"{self.main_title()} {self.zoom}×")
        self.update()

    def main_title(self):
        from .i18n import tr
        return tr("Vergrootglas")

    def paintEvent(self, e):
        from PySide6.QtGui import QPainter, QPen
        from PySide6.QtCore import QRectF
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(112, 112, 112))
        cv = getattr(self, "_cv", None)
        if cv is not None and cv.cache is not None:
            z = self.zoom
            w, h = self.width() / z, self.height() / z
            src = QRectF(self._pt.x() - w / 2, self._pt.y() - h / 2, w, h)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            p.drawImage(QRectF(self.rect()), cv.cache, src)
            c = self.rect().center()
            p.setPen(QPen(QColor(255, 255, 255, 200), 1))
            p.drawLine(c.x() - 8, c.y(), c.x() + 8, c.y())
            p.drawLine(c.x(), c.y() - 8, c.x(), c.y() + 8)
        p.end()


class VectorPropertiesDialog(QDialog):
    """Eigenschappen van vectorobjecten: naam, lijn en vulling (kleur of geen), breedte, lijnstijl,
    verbinding en anti-alias. Bij meer objecten tegelijk geldt de wijziging voor alle gekozen objecten."""
    STYLES = ["Effen", "Streepjes", "Puntjes", "Streep-punt", "Streep-punt-punt"]
    JOINS = ["Verstek", "Rond", "Schuin"]

    def __init__(self, parent, objs):
        from PySide6.QtWidgets import QLineEdit, QPushButton
        super().__init__(parent)
        self.setWindowTitle("Eigenschappen")
        self.objs = objs
        first = objs[0]
        f = QFormLayout(self)
        self.name = QLineEdit(first.get("name", "") if len(objs) == 1 else "")
        self.name.setProperty("pp_notr", True)
        self.name.setEnabled(len(objs) == 1)
        f.addRow("Naam:", self.name)
        self.colors = {}
        for key, label in (("stroke", "Lijn:"), ("fill", "Vulling:")):
            row = QHBoxLayout()
            btn = QPushButton()
            btn.setFixedWidth(70)
            none = QCheckBox("Geen")
            c = first.get(key)
            self.colors[key] = [QColor(*c[:3]) if c else QColor(0, 0, 0) if key == "stroke" else QColor(255, 255, 255),
                                btn, none]
            none.setChecked(c is None)
            btn.clicked.connect(lambda _=False, k=key: self._pick(k))
            none.toggled.connect(lambda on, b=btn: b.setEnabled(not on))
            btn.setEnabled(c is not None)
            row.addWidget(btn)
            row.addWidget(none)
            row.addStretch()
            f.addRow(label, row)
            self._paint(key)
        from PySide6.QtWidgets import QDoubleSpinBox
        self.width = QDoubleSpinBox()
        self.width.setRange(0, 500)
        self.width.setDecimals(1)
        self.width.setValue(float(first.get("width", 1)))
        f.addRow("Breedte:", self.width)
        self.style = QComboBox()
        self.style.addItems(self.STYLES)
        self.style.setCurrentIndex(int(first.get("style", 0)))
        f.addRow("Lijnstijl:", self.style)
        self.join = QComboBox()
        self.join.addItems(self.JOINS)
        self.join.setCurrentIndex(int(first.get("join", 0)))
        f.addRow("Verbinding:", self.join)
        self.aa = QCheckBox("Anti-alias")
        self.aa.setChecked(bool(first.get("aa", True)))
        f.addRow(self.aa)
        f.addRow(_buttons(self))

    def _paint(self, key):
        from PySide6.QtGui import QIcon, QPixmap
        col, btn, _ = self.colors[key]
        pm = QPixmap(50, 14)
        pm.fill(col)
        btn.setIcon(QIcon(pm))

    def _pick(self, key):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(self.colors[key][0], self, "Kleur")
        if c.isValid():
            self.colors[key][0] = c
            self._paint(key)

    def apply(self):
        for o in self.objs:
            if len(self.objs) == 1:
                name = self.name.text().strip()
                if name:
                    o["name"] = name
                else:
                    o.pop("name", None)
            for key in ("stroke", "fill"):
                col, _, none = self.colors[key]
                o[key] = None if none.isChecked() else [col.red(), col.green(), col.blue(), 255]
            o["width"] = float(self.width.value())
            o["style"] = self.style.currentIndex()
            o["join"] = self.join.currentIndex()
            o["aa"] = self.aa.isChecked()


def ask_form(parent, title, fields, note=None):
    """Klein invulvenster. fields: [(sleutel, label, soort, ...)] met soort
    "int" (laag, hoog, standaard[, achtervoegsel]), "choice" (opties, standaard), "bool" (standaard) of
    "color" (standaard QColor). Geeft {sleutel: waarde} terug, of None bij Annuleren."""
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtWidgets import QColorDialog, QPushButton
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    f = QFormLayout(dlg)
    if note:
        lab = QLabel(note)
        lab.setWordWrap(True)
        lab.setMinimumWidth(300)
        f.addRow(lab)
    getters = {}
    for key, label, kind, *a in fields:
        if kind == "int":
            w = _spin(a[0], a[1], a[2], a[3] if len(a) > 3 else "")
            getters[key] = w.value
            f.addRow(label, w)
        elif kind == "choice":
            w = QComboBox()
            w.addItems(a[0])
            w.setCurrentIndex(a[1] if len(a) > 1 else 0)
            getters[key] = w.currentIndex
            f.addRow(label, w)
        elif kind == "bool":
            w = QCheckBox(label)
            w.setChecked(bool(a[0]) if a else False)
            getters[key] = w.isChecked
            f.addRow(w)
        elif kind == "color":
            box = {"c": QColor(a[0])}
            w = QPushButton()
            w.setFixedWidth(80)

            def paint(b=w, bx=box):
                pm = QPixmap(56, 14)
                pm.fill(bx["c"])
                b.setIcon(QIcon(pm))

            def pick(_=False, bx=box, p=paint):
                c = QColorDialog.getColor(bx["c"], dlg, "Kleur")
                if c.isValid():
                    bx["c"] = c
                    p()
            w.clicked.connect(pick)
            paint()
            getters[key] = (lambda bx=box: QColor(bx["c"]))
            f.addRow(label, w)
    f.addRow(_buttons(dlg))
    if not dlg.exec():
        return None
    return {k: g() for k, g in getters.items()}


# ================================================================ Bestand: export en batch
class PngOptimizerDialog(QDialog):
    """PNG-optimalisatie: kleurtype (32 bits met transparantie, 24 bits, 8 bits palet), aantal kleuren en
    compressie, met de verwachte bestandsgrootte."""

    def __init__(self, parent, rgba):
        super().__init__(parent)
        self.setWindowTitle("PNG-optimalisatie")
        self.rgba = rgba
        f = QFormLayout(self)
        self.kind = QComboBox()
        self.kind.addItems(["32 bits (met transparantie)", "24 bits (zonder transparantie)", "8 bits (palet)"])
        self.colors = _spin(2, 256, 256)
        self.level = _spin(0, 9, 9)
        self.size = QLabel()
        self.size.setProperty("pp_notr", True)
        f.addRow("Kleurtype:", self.kind)
        f.addRow("Aantal kleuren:", self.colors)
        f.addRow("Compressie:", self.level)
        f.addRow("Bestandsgrootte:", self.size)
        f.addRow(_buttons(self))
        self.timer = QTimer(self, singleShot=True, interval=250)
        self.timer.timeout.connect(self._estimate)
        for w in (self.kind, self.colors, self.level):
            (w.currentIndexChanged if isinstance(w, QComboBox) else w.valueChanged).connect(lambda *_: self.timer.start())
        self.kind.currentIndexChanged.connect(lambda i: self.colors.setEnabled(i == 2))
        self.colors.setEnabled(False)
        self._estimate()

    def pil_image(self):
        from PIL import Image
        a = self.rgba
        k = self.kind.currentIndex()
        if k == 0:
            return Image.fromarray(a, "RGBA")
        if k == 1:
            return Image.fromarray(a[..., :3].copy(), "RGB")
        img = Image.fromarray(a, "RGBA")
        return img.quantize(colors=self.colors.value(), method=Image.Quantize.FASTOCTREE,
                            dither=Image.Dither.FLOYDSTEINBERG)

    def save(self, target):
        self.pil_image().save(target, "PNG", optimize=self.level.value() >= 9, compress_level=self.level.value())

    def _estimate(self):
        import io
        buf = io.BytesIO()
        self.save(buf)
        n = buf.tell()
        self.size.setText(f"{n / 1024:.1f} kB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.2f} MB")


class ImageMapDialog(QDialog):
    """Afbeelding met hyperlinks: sleep rechthoeken of cirkels over het voorbeeld, geef elk gebied een
    adres (URL), een alternatieve tekst en een doel, en bewaar een HTML-pagina met de afbeelding."""

    def __init__(self, parent, image):
        from PySide6.QtWidgets import QLineEdit, QListWidget, QPushButton
        super().__init__(parent)
        self.setWindowTitle("Afbeelding met hyperlinks")
        self.image = image
        self.areas = []  # [{"shape": "rect"|"circle", "r": QRect (afbeeldingscoördinaten), "url", "alt", "target"}]
        v = QHBoxLayout(self)
        self.view = _MapView(self)
        v.addWidget(self.view, 1)
        side = QVBoxLayout()
        v.addLayout(side)
        self.shape = QComboBox()
        self.shape.addItems(["Rechthoek", "Cirkel"])
        side.addWidget(QLabel("Vorm voor nieuwe gebieden:"))
        side.addWidget(self.shape)
        side.addWidget(QLabel("Gebieden:"))
        self.list = QListWidget()
        self.list.setProperty("pp_notr", True)
        self.list.currentRowChanged.connect(self._show)
        side.addWidget(self.list, 1)
        f = QFormLayout()
        self.url = QLineEdit()
        self.alt = QLineEdit()
        self.target = QComboBox()
        self.target.setEditable(True)
        self.target.addItems(["", "_blank", "_self", "_parent", "_top"])
        for w in (self.url, self.alt):
            w.setProperty("pp_notr", True)
            w.textChanged.connect(self._edit)
        self.target.currentTextChanged.connect(self._edit)
        f.addRow("URL:", self.url)
        f.addRow("Alternatieve tekst:", self.alt)
        f.addRow("Doel:", self.target)
        side.addLayout(f)
        rm = QPushButton("Gebied verwijderen")
        rm.clicked.connect(self._remove)
        side.addWidget(rm)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Save).setText("Opslaan...")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuleren")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        side.addWidget(bb)
        self.resize(900, 560)

    def add_area(self, shape, r):
        self.areas.append({"shape": shape, "r": r, "url": "", "alt": "", "target": ""})
        self.list.addItem(f"{len(self.areas)}. {shape}")
        self.list.setCurrentRow(len(self.areas) - 1)
        self.url.setFocus()

    def _show(self, i):
        if 0 <= i < len(self.areas):
            a = self.areas[i]
            for w, k in ((self.url, "url"), (self.alt, "alt")):
                w.blockSignals(True)
                w.setText(a[k])
                w.blockSignals(False)
            self.target.blockSignals(True)
            self.target.setCurrentText(a["target"])
            self.target.blockSignals(False)
        self.view.update()

    def _edit(self, *_):
        i = self.list.currentRow()
        if 0 <= i < len(self.areas):
            self.areas[i].update(url=self.url.text(), alt=self.alt.text(), target=self.target.currentText())
            self.list.item(i).setText(f"{i + 1}. {self.areas[i]['shape']}  {self.areas[i]['url']}")

    def _remove(self):
        i = self.list.currentRow()
        if 0 <= i < len(self.areas):
            del self.areas[i]
            self.list.takeItem(i)
            self.view.update()

    def html(self, image_name):
        import html as H
        parts = [f'<img src="{H.escape(image_name)}" width="{self.image.width()}" height="{self.image.height()}" '
                 f'usemap="#pixelpickle" alt="">', '<map name="pixelpickle">']
        for a in self.areas:
            r = a["r"]
            if a["shape"] == "circle":
                c = r.center()
                coords, shape = f"{c.x()},{c.y()},{max(r.width(), r.height()) // 2}", "circle"
            else:
                coords, shape = f"{r.left()},{r.top()},{r.right() + 1},{r.bottom() + 1}", "rect"
            tgt = f' target="{H.escape(a["target"])}"' if a["target"] else ""
            parts.append(f'  <area shape="{shape}" coords="{coords}" href="{H.escape(a["url"])}" '
                         f'alt="{H.escape(a["alt"])}"{tgt}>')
        parts.append("</map>")
        return "<!DOCTYPE html>\n<html>\n<head><meta charset=\"utf-8\"><title>" + H.escape(image_name) + \
            "</title></head>\n<body>\n" + "\n".join(parts) + "\n</body>\n</html>\n"


class _MapView(QWidget):
    """Voorbeeld voor Afbeelding met hyperlinks: sleep om een gebied te maken."""

    def __init__(self, dlg):
        super().__init__()
        self.dlg = dlg
        self.drag = None
        self.setMinimumSize(400, 300)

    def _geom(self):
        img = self.dlg.image
        s = min(self.width() / img.width(), self.height() / img.height())
        return s, (self.width() - img.width() * s) / 2, (self.height() - img.height() * s) / 2

    def _to_img(self, pos):
        s, ox, oy = self._geom()
        img = self.dlg.image
        return (max(0, min(img.width() - 1, int((pos.x() - ox) / s))),
                max(0, min(img.height() - 1, int((pos.y() - oy) / s))))

    def paintEvent(self, e):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainter, QPen
        p = QPainter(self)
        s, ox, oy = self._geom()
        img = self.dlg.image
        p.drawImage(QRectF(ox, oy, img.width() * s, img.height() * s), img)
        cur = self.dlg.list.currentRow()
        for i, a in enumerate(self.dlg.areas + ([self.drag] if self.drag else [])):
            r = a["r"]
            rr = QRectF(ox + r.x() * s, oy + r.y() * s, r.width() * s, r.height() * s)
            p.setPen(QPen(QColor(255, 60, 60) if i == cur else QColor(40, 160, 255), 2))
            p.setBrush(QColor(40, 160, 255, 50))
            p.drawEllipse(rr) if a["shape"] == "circle" else p.drawRect(rr)
        p.end()

    def mousePressEvent(self, e):
        x, y = self._to_img(e.position())
        self.start = (x, y)
        self.drag = {"shape": "circle" if self.dlg.shape.currentIndex() == 1 else "rect", "r": QRect(x, y, 1, 1)}

    def mouseMoveEvent(self, e):
        if self.drag:
            x, y = self._to_img(e.position())
            self.drag["r"] = QRect(min(x, self.start[0]), min(y, self.start[1]),
                                   abs(x - self.start[0]) + 1, abs(y - self.start[1]) + 1)
            self.update()

    def mouseReleaseEvent(self, e):
        if self.drag:
            if self.drag["r"].width() > 3 and self.drag["r"].height() > 3:
                self.dlg.add_area(self.drag["shape"], self.drag["r"])
            self.drag = None
            self.update()


class BatchDialog(QDialog):
    """Batchverwerking: een lijst bestanden in één keer omzetten naar een andere indeling, eventueel verkleind,
    naar een map naar keuze."""
    FORMATS = [("PNG", ".png"), ("JPEG", ".jpg"), ("WebP", ".webp"), ("TIFF", ".tif"), ("BMP", ".bmp"),
               ("GIF", ".gif"), ("OpenRaster (.ora)", ".ora")]

    def __init__(self, parent, files=()):
        from PySide6.QtWidgets import QLineEdit, QListWidget, QPushButton
        super().__init__(parent)
        self.setWindowTitle("Batchverwerking")
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Bestanden:"))
        self.list = QListWidget()
        self.list.setProperty("pp_notr", True)
        self.list.addItems(list(files))
        v.addWidget(self.list, 1)
        row = QHBoxLayout()
        add = QPushButton("Toevoegen...")
        add.clicked.connect(self._add)
        rm = QPushButton("Verwijderen")
        rm.clicked.connect(lambda: [self.list.takeItem(self.list.row(i)) for i in self.list.selectedItems()])
        self.list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        row.addWidget(add)
        row.addWidget(rm)
        row.addStretch()
        v.addLayout(row)
        f = QFormLayout()
        self.fmt = QComboBox()
        self.fmt.addItems([n for n, _ in self.FORMATS])
        self.quality = _spin(1, 100, 90)
        self.maxsize = _spin(0, 20000, 0, " px")
        self.outdir = QLineEdit()
        self.outdir.setProperty("pp_notr", True)
        self.outdir.setPlaceholderText("Zelfde map als het origineel")
        browse = QPushButton("Bladeren...")
        browse.clicked.connect(self._browse)
        orow = QHBoxLayout()
        orow.addWidget(self.outdir, 1)
        orow.addWidget(browse)
        f.addRow("Opslaan als:", self.fmt)
        f.addRow("Kwaliteit (JPEG/WebP):", self.quality)
        f.addRow("Langste zijde hoogstens (0 = niet verkleinen):", self.maxsize)
        f.addRow("Map:", orow)
        self.overwrite = QCheckBox("Bestaande bestanden overschrijven")
        f.addRow(self.overwrite)
        v.addLayout(f)
        bb = _buttons(self)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Starten")
        v.addWidget(bb)
        self.resize(560, 480)

    def _add(self):
        from PySide6.QtWidgets import QFileDialog
        from . import fileio
        paths, _ = QFileDialog.getOpenFileNames(self, "Bestanden toevoegen", "", fileio.OPEN_FILTER)
        self.list.addItems(paths)

    def _browse(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Map kiezen", self.outdir.text())
        if d:
            self.outdir.setText(d)

    def values(self):
        return dict(files=[self.list.item(i).text() for i in range(self.list.count())],
                    ext=self.FORMATS[self.fmt.currentIndex()][1], quality=self.quality.value(),
                    maxsize=self.maxsize.value(), outdir=self.outdir.text().strip(), overwrite=self.overwrite.isChecked())


class BatchRenameDialog(QDialog):
    """Namen in batch wijzigen: nieuwe namen uit vaste tekst, een volgnummer en de oude naam, met voorbeeld."""

    def __init__(self, parent):
        from PySide6.QtWidgets import QLineEdit, QListWidget, QPushButton
        super().__init__(parent)
        self.setWindowTitle("Namen in batch wijzigen")
        v = QVBoxLayout(self)
        row = QHBoxLayout()
        add = QPushButton("Bestanden toevoegen...")
        add.clicked.connect(self._add)
        row.addWidget(add)
        row.addStretch()
        v.addLayout(row)
        self.list = QListWidget()
        self.list.setProperty("pp_notr", True)
        v.addWidget(self.list, 1)
        f = QFormLayout()
        self.prefix = QLineEdit()
        self.suffix = QLineEdit()
        for w in (self.prefix, self.suffix):
            w.setProperty("pp_notr", True)
            w.textChanged.connect(self._preview)
        self.keep = QCheckBox("Oude naam behouden")
        self.keep.toggled.connect(self._preview)
        self.number = QCheckBox("Volgnummer")
        self.number.setChecked(True)
        self.number.toggled.connect(self._preview)
        self.start = _spin(0, 1000000, 1)
        self.digits = _spin(1, 8, 3)
        for w in (self.start, self.digits):
            w.valueChanged.connect(self._preview)
        f.addRow("Tekst vooraan:", self.prefix)
        f.addRow(self.keep)
        f.addRow(self.number)
        f.addRow("Beginnen bij:", self.start)
        f.addRow("Aantal cijfers:", self.digits)
        f.addRow("Tekst achteraan:", self.suffix)
        v.addLayout(f)
        bb = _buttons(self)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Hernoemen")
        v.addWidget(bb)
        self.files = []
        self.resize(560, 480)

    def _add(self):
        from PySide6.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(self, "Bestanden toevoegen", "")
        self.files += [p for p in paths if p not in self.files]
        self._preview()

    def new_names(self):
        import os
        out = []
        for k, path in enumerate(self.files):
            stem, ext = os.path.splitext(os.path.basename(path))
            name = self.prefix.text() + (stem if self.keep.isChecked() else "")
            if self.number.isChecked():
                name += str(self.start.value() + k).zfill(self.digits.value())
            name += self.suffix.text()
            out.append((path, os.path.join(os.path.dirname(path), (name or stem) + ext)))
        return out

    def _preview(self, *_):
        import os
        self.list.clear()
        for old, new in self.new_names():
            self.list.addItem(f"{os.path.basename(old)}  →  {os.path.basename(new)}")


class FileLocationsDialog(QDialog):
    """Bestandslocaties: de mappen voor eigen penselen, vormen, fotolijsten en patronen."""

    def __init__(self, parent):
        from PySide6.QtWidgets import QLineEdit, QPushButton
        from . import userdata
        super().__init__(parent)
        self.setWindowTitle("Bestandslocaties")
        f = QFormLayout(self)
        self.edits = {}
        for kind, label in (("brushes", "Penselen:"), ("shapes", "Vormen:"), ("frames", "Fotolijsten:"),
                            ("patterns", "Patronen:")):
            e = QLineEdit(userdata.folder(kind, create=False))
            e.setProperty("pp_notr", True)
            e.setMinimumWidth(340)
            b = QPushButton("Bladeren...")
            b.clicked.connect(lambda _=False, ed=e: self._browse(ed))
            row = QHBoxLayout()
            row.addWidget(e, 1)
            row.addWidget(b)
            f.addRow(label, row)
            self.edits[kind] = e
        reset = QPushButton("Standaardmappen")
        reset.clicked.connect(lambda: [e.setText(userdata.default_folder(k)) for k, e in self.edits.items()])
        f.addRow(reset)
        f.addRow(_buttons(self))

    def _browse(self, ed):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Map kiezen", ed.text())
        if d:
            ed.setText(d)

    def apply(self):
        from . import userdata
        for kind, e in self.edits.items():
            path = e.text().strip()
            userdata.set_folder(kind, "" if path == userdata.default_folder(kind) else path)
