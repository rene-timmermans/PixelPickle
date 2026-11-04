"""Effectvenster in PSP stijl: Vóór/Na voorbeeld, Instellingen (voorinstellingen), Voorbeeld op afbeelding."""
import json

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QPushButton, QSlider,
                               QSpinBox, QToolButton, QVBoxLayout, QWidget)

from . import imageops as ops
from .document import apply_region
from .effects import Ctx, defaults

PREVIEW = QSize(230, 175)


def run_effect(eff, rgba, ctx, params):
    return eff.fn(rgba, ctx, **params)


def checker_pixmap(img: QImage, size=PREVIEW):
    pm = QPixmap(size)
    p = QPainter(pm)
    for y in range(0, size.height(), 8):
        for x in range(0, size.width(), 8):
            p.fillRect(x, y, 8, 8, QColor(255, 255, 255) if (x // 8 + y // 8) % 2 == 0 else QColor(204, 204, 204))
    if img is not None and not img.isNull():
        p.drawImage((size.width() - img.width()) // 2, (size.height() - img.height()) // 2, img)
    p.setPen(QColor(90, 90, 90))
    p.drawRect(0, 0, size.width() - 1, size.height() - 1)
    p.end()
    return pm


class CurveWidget(QWidget):
    changed = Signal()

    def __init__(self, points):
        super().__init__()
        self.setFixedSize(220, 220)
        self.pts = sorted([list(p) for p in points])
        self.drag = None

    def value(self):
        return [list(p) for p in self.pts]

    def set_value(self, pts):
        self.pts = sorted([list(p) for p in pts])
        self.update()

    def _to_w(self, p):
        return QPointF(10 + p[0] / 255 * 200, 210 - p[1] / 255 * 200)

    def _from_w(self, q):
        return [min(255, max(0, round((q.x() - 10) / 200 * 255))), min(255, max(0, round((210 - q.y()) / 200 * 255)))]

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(QRectF(10, 10, 200, 200), QColor(255, 255, 255))
        p.setPen(QPen(QColor(220, 220, 220), 1))
        for i in range(1, 4):
            p.drawLine(QPointF(10 + i * 50, 10), QPointF(10 + i * 50, 210))
            p.drawLine(QPointF(10, 10 + i * 50), QPointF(210, 10 + i * 50))
        xs = np.arange(256)
        ys = np.interp(xs, [q[0] for q in self.pts], [q[1] for q in self.pts])
        path = QPainterPath(self._to_w((0, ys[0])))
        for x in range(0, 256, 3):
            path.lineTo(self._to_w((x, ys[x])))
        p.setPen(QPen(QColor(0, 0, 0), 1.5))
        p.drawPath(path)
        p.setBrush(QColor(255, 255, 255))
        for q in self.pts:
            p.drawRect(QRectF(self._to_w(q) - QPointF(3, 3), QSize(6, 6)))

    def mousePressEvent(self, e):
        pos = e.position()
        for i, q in enumerate(self.pts):
            w = self._to_w(q)
            if abs(w.x() - pos.x()) < 6 and abs(w.y() - pos.y()) < 6:
                if e.button() == Qt.MouseButton.RightButton and 0 < i < len(self.pts) - 1:
                    del self.pts[i]
                    self.update()
                    self.changed.emit()
                    return
                self.drag = i
                return
        if e.button() == Qt.MouseButton.LeftButton:
            self.pts.append(self._from_w(pos))
            self.pts.sort()
            self.drag = self.pts.index(self._from_w(pos)) if self._from_w(pos) in self.pts else None
            self.update()
            self.changed.emit()

    def mouseMoveEvent(self, e):
        if self.drag is None:
            return
        v = self._from_w(e.position())
        i = self.drag
        lo = self.pts[i - 1][0] + 1 if i > 0 else 0
        hi = self.pts[i + 1][0] - 1 if i < len(self.pts) - 1 else 255
        if i == 0:
            v[0] = 0 if self.pts[0][0] == 0 else min(max(v[0], 0), hi)
        elif i == len(self.pts) - 1:
            v[0] = 255 if self.pts[-1][0] == 255 else max(min(v[0], 255), lo)
        else:
            v[0] = min(max(v[0], lo), hi)
        self.pts[i] = v
        self.update()
        self.changed.emit()

    def mouseReleaseEvent(self, e):
        self.drag = None


class ColorButton(QPushButton):
    changed = Signal()

    def __init__(self, rgb):
        super().__init__()
        self.rgb = tuple(rgb)
        self.setFixedWidth(60)
        self.clicked.connect(self._pick)
        self._paint()

    def _paint(self):
        self.setStyleSheet(f"background: rgb{self.rgb};")

    def _pick(self):
        c = QColorDialog.getColor(QColor(*self.rgb), self)
        if c.isValid():
            self.rgb = (c.red(), c.green(), c.blue())
            self._paint()
            self.changed.emit()


class EffectDialog(QDialog):
    """mode 'apply': past toe op de actieve laag. mode 'params': geeft alleen parameters terug (aanpassingslaag)."""

    def __init__(self, main, doc, eff, params=None, mode="apply"):
        super().__init__(main)
        self.main, self.doc, self.eff, self.mode = main, doc, eff, mode
        self.setWindowTitle(eff.name)
        self.ctx = Ctx(fg=main.fg.getRgb()[:3], bg=main.bg.getRgb()[:3])
        layer = doc.layer()
        self.layer = layer
        self.orig = QImage(layer.image)
        self.rect = doc.selection_bbox() if doc.sel is not None else doc.rect()
        if mode == "params":  # aanpassingslaag: voorbeeld op de samengestelde lagen eronder
            below = doc.layers[:doc.active] if layer.adjust else doc.layers[:doc.active + 1]
            src = doc.composite(None, below)
            self.rect = doc.rect()
        else:
            src = self.orig
        region = src.copy(self.rect)
        small = region.scaled(PREVIEW, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.prev_scale = small.width() / max(1, region.width())
        self.small_rgba = ops.qimage_to_rgba(small)
        self.small_img = small

        v = QVBoxLayout(self)
        head = QHBoxLayout()
        self.toggle = QToolButton(text="▼ Voorbeeld")
        self.toggle.setAutoRaise(True)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        head.addWidget(self.toggle)
        head.addStretch()
        self.on_image = QCheckBox("Voorbeeld op afbeelding")
        self.on_image.setEnabled(mode == "apply")
        head.addWidget(self.on_image)
        v.addLayout(head)
        self.pv = QWidget()
        pv = QHBoxLayout(self.pv)
        for title, attr in (("Vóór:", "before"), ("Na:", "after")):
            col = QVBoxLayout()
            col.addWidget(QLabel(title))
            lbl = QLabel()
            lbl.setFixedSize(PREVIEW)
            setattr(self, attr, lbl)
            col.addWidget(lbl)
            pv.addLayout(col)
        v.addWidget(self.pv)
        self.toggle.toggled.connect(lambda on: (self.pv.setVisible(on), self.toggle.setText(("▼" if on else "▶") + " Voorbeeld")))
        self.before.setPixmap(checker_pixmap(small))

        row = QHBoxLayout()
        row.addWidget(QLabel("Instellingen"))
        self.presets = QComboBox()
        self.presets.setMinimumWidth(170)
        self.presets.activated.connect(self._load_preset)
        row.addWidget(self.presets, 1)
        save = QToolButton(text="💾")
        save.setToolTip("Voorinstelling opslaan")
        save.clicked.connect(self._save_preset)
        row.addWidget(save)
        reset = QToolButton(text="↺")
        reset.setToolTip("Standaardwaarden herstellen")
        reset.clicked.connect(lambda: self.set_params(defaults(self.eff, self.ctx)))
        row.addWidget(reset)
        v.addLayout(row)

        box = QGroupBox()
        form = QFormLayout(box)
        self.widgets = {}
        for prm in eff.params:
            w = self._make_widget(prm)
            form.addRow(prm["label"] + ":" if prm["type"] != "bool" else "", w)
        v.addWidget(box)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuleren")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

        self.timer = QTimer(self, singleShot=True, interval=120)
        self.timer.timeout.connect(self.update_preview)
        self.img_timer = QTimer(self, singleShot=True, interval=450)
        self.img_timer.timeout.connect(self.update_on_image)
        self.on_image.toggled.connect(lambda _: self.img_timer.start())
        self._fill_presets()
        start = params or self._stored("last") or defaults(eff, self.ctx)
        self.set_params(start)
        self.update_preview()

    # ---------------------------------------------------------------- parameters
    def _make_widget(self, prm):
        t = prm["type"]
        if t == "int":
            wrap = QWidget()
            h = QHBoxLayout(wrap)
            h.setContentsMargins(0, 0, 0, 0)
            s = QSlider(Qt.Orientation.Horizontal)
            s.setRange(prm["lo"], prm["hi"])
            sp = QSpinBox()
            sp.setRange(prm["lo"], prm["hi"])
            s.valueChanged.connect(sp.setValue)
            sp.valueChanged.connect(s.setValue)
            sp.valueChanged.connect(self.changed)
            h.addWidget(s, 1)
            h.addWidget(sp)
            self.widgets[prm["key"]] = (t, sp)
            return wrap
        if t == "choice":
            c = QComboBox()
            c.addItems(prm["options"])
            c.currentIndexChanged.connect(self.changed)
            self.widgets[prm["key"]] = (t, c)
            return c
        if t == "bool":
            c = QCheckBox(prm["label"])
            c.toggled.connect(self.changed)
            self.widgets[prm["key"]] = (t, c)
            return c
        if t == "color":
            d = prm["default"]
            b = ColorButton(self.ctx.fg if d == "fg" else self.ctx.bg if d == "bg" else d)
            b.changed.connect(self.changed)
            self.widgets[prm["key"]] = (t, b)
            return b
        cw = CurveWidget(prm["default"])
        cw.changed.connect(self.changed)
        self.widgets[prm["key"]] = (t, cw)
        return cw

    def params(self):
        out = {}
        for k, (t, w) in self.widgets.items():
            out[k] = (w.value() if t in ("int", "curve") else w.currentIndex() if t == "choice"
                      else w.isChecked() if t == "bool" else tuple(w.rgb))
        return out

    def set_params(self, prm):
        self._loading = True
        for k, (t, w) in self.widgets.items():
            if k not in prm:
                continue
            v = prm[k]
            if t == "int":
                w.setValue(int(v))
            elif t == "choice":
                w.setCurrentIndex(int(v))
            elif t == "bool":
                w.setChecked(bool(v))
            elif t == "color":
                w.rgb = tuple(v)
                w._paint()
            else:
                w.set_value(v)
        self._loading = False
        self.changed()

    def changed(self, *_):
        if getattr(self, "_loading", False):
            return
        self.timer.start()
        if self.on_image.isChecked():
            self.img_timer.start()

    # ---------------------------------------------------------------- voorinstellingen
    def _key(self):
        return f"effect_presets/{self.eff.cid:04x}"

    def _all_presets(self):
        try:
            return json.loads(self.main.settings.value(self._key(), "{}"))
        except (TypeError, ValueError):
            return {}

    def _stored(self, name):
        return self._all_presets().get(name)

    def _fill_presets(self):
        self.presets.clear()
        self.presets.addItem("Standaardwaarden")
        if self._stored("last"):
            self.presets.addItem("Laatst gebruikt")
        for n in self._all_presets():
            if n != "last":
                self.presets.addItem(n)
        from . import presets as psp
        self._psp = {}
        for name, flat in self.main.psp_preset_list(self.eff.cid):
            prm = psp.usable(self.eff, flat)
            if prm is not None:
                label = f"{name}  (PSP)"
                self._psp[label] = prm
                self.presets.addItem(label)
        self.presets.setCurrentIndex(-1)

    def _load_preset(self, i):
        name = self.presets.itemText(i)
        if name == "Standaardwaarden":
            self.set_params(defaults(self.eff, self.ctx))
        elif name in getattr(self, "_psp", {}):
            prm = defaults(self.eff, self.ctx)
            prm.update(self._psp[name])
            self.set_params(prm)
        else:
            p = self._stored("last" if name == "Laatst gebruikt" else name)
            if p:
                self.set_params(p)

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "Voorinstelling opslaan", "Naam:")
        if ok and name.strip():
            allp = self._all_presets()
            allp[name.strip()] = self.params()
            self.main.settings.setValue(self._key(), json.dumps(allp))
            self._fill_presets()

    # ---------------------------------------------------------------- voorbeeld
    def update_preview(self):
        ctx = Ctx(self.ctx.fg, self.ctx.bg, self.prev_scale, self.ctx.seed)
        try:
            out = run_effect(self.eff, self.small_rgba, ctx, self.params())
            img = ops.rgba_to_qimage(out)
        except Exception as e:  # nooit het venster laten crashen
            print("effect fout:", e)
            img = self.small_img
        self.after.setPixmap(checker_pixmap(img))

    def result_image(self):
        region = self.orig.copy(self.rect)
        res = ops.rgba_to_qimage(run_effect(self.eff, ops.qimage_to_rgba(region), self.ctx, self.params()))
        out = QImage(self.orig)
        apply_region(out, self.rect, res, self.doc.sel)
        return out

    def update_on_image(self):
        if self.mode != "apply":
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.layer.image = self.result_image() if self.on_image.isChecked() else self.orig
        finally:
            QApplication.restoreOverrideCursor()
        self.doc.changed.emit(QRect())

    def _remember(self):
        allp = self._all_presets()
        allp["last"] = self.params()
        self.main.settings.setValue(self._key(), json.dumps(allp))

    def accept(self):
        self.timer.stop()
        self.img_timer.stop()
        self._remember()
        if self.mode == "apply":
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                out = self.result_image()
            finally:
                QApplication.restoreOverrideCursor()
            self.layer.image = self.orig
            self.doc.push_undo(self.eff.name)
            self.layer.image = out
            self.doc.changed.emit(QRect())
            self.doc.structureChanged.emit()
        super().accept()

    def reject(self):
        self.timer.stop()
        self.img_timer.stop()
        if self.mode == "apply" and self.layer.image is not self.orig:
            self.layer.image = self.orig
            self.doc.changed.emit(QRect())
        super().reject()


class EffectBrowser(QDialog):
    """Effecten zoeken: miniaturen van alle effecten op de huidige afbeelding."""

    def __init__(self, main, doc, menu_tree):
        super().__init__(main)
        from PySide6.QtWidgets import QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem, QSplitter
        self.main, self.doc = main, doc
        self.setWindowTitle("Effecten zoeken")
        self.resize(900, 600)
        src = doc.layer().image.scaled(110, 85, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.thumb_rgba = ops.qimage_to_rgba(src)
        self.scale = src.width() / max(1, doc.w)
        self.chosen = None
        v = QVBoxLayout(self)
        split = QSplitter()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.groups = {}
        for top in menu_tree:
            if top["text"].replace("&", "") not in ("Effecten", "Aanpassen"):
                continue
            root = QTreeWidgetItem([top["text"].replace("&", "")])
            self.tree.addTopLevelItem(root)
            self._walk(top["items"], root, [])
            root.setExpanded(True)
        split.addWidget(self.tree)
        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.grid.setIconSize(QSize(110, 85))
        self.grid.setGridSize(QSize(140, 125))
        self.grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.grid.setWordWrap(True)
        self.grid.itemDoubleClicked.connect(self._choose)
        split.addWidget(self.grid)
        split.setSizes([220, 680])
        v.addWidget(split)
        bb = QDialogButtonBox()
        bb.addButton("Toepassen...", QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton("Sluiten", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(lambda: self._choose(self.grid.currentItem()))
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.tree.currentItemChanged.connect(self._show)
        self.queue = []
        self.timer = QTimer(self, interval=0)
        self.timer.timeout.connect(self._next_thumb)
        self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _walk(self, items, parent, out):
        from PySide6.QtWidgets import QTreeWidgetItem
        cids = []
        for it in items:
            if not it:
                continue
            if it["items"]:
                node = QTreeWidgetItem([it["text"].replace("&", "")])
                parent.addChild(node)
                sub = self._walk(it["items"], node, out)
                node.setData(0, Qt.ItemDataRole.UserRole, sub)
                cids += sub
            elif it["id"] in self.main.effects:
                cids.append(it["id"])
        parent.setData(0, Qt.ItemDataRole.UserRole, cids)
        return cids

    def _show(self, item, _prev=None):
        from PySide6.QtWidgets import QListWidgetItem
        if item is None:
            return
        self.grid.clear()
        self.queue = []
        for cid in item.data(0, Qt.ItemDataRole.UserRole) or []:
            eff = self.main.effects[cid]
            li = QListWidgetItem(eff.name)
            li.setData(Qt.ItemDataRole.UserRole, cid)
            self.grid.addItem(li)
            self.queue.append(li)
        self.timer.start()

    def _next_thumb(self):
        from PySide6.QtGui import QIcon
        if not self.queue:
            self.timer.stop()
            return
        li = self.queue.pop(0)
        eff = self.main.effects[li.data(Qt.ItemDataRole.UserRole)]
        ctx = Ctx(self.main.fg.getRgb()[:3], self.main.bg.getRgb()[:3], self.scale)
        try:
            img = ops.rgba_to_qimage(eff.fn(self.thumb_rgba, ctx, **defaults(eff, ctx)))
        except Exception:
            img = ops.rgba_to_qimage(self.thumb_rgba)
        li.setIcon(QIcon(checker_pixmap(img, QSize(110, 85))))

    def _choose(self, item):
        if item is not None:
            self.chosen = item.data(Qt.ItemDataRole.UserRole)
            self.accept()
