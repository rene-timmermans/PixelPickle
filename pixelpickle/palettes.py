"""Paletten: Materialen, Lagen en Geschiedenis."""
from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QImage, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QColorDialog, QComboBox, QHBoxLayout, QInputDialog, QLabel, QMenu,
                               QListWidget, QListWidgetItem, QSlider, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)

from . import icons
from .document import BLEND_MODES


# ---------------------------------------------------------------- materialen
class Spectrum(QWidget):
    picked = Signal(QColor, bool)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(160, 110)
        self.img = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("Links: voorgrondkleur, rechts: achtergrondkleur")

    def resizeEvent(self, e):
        w, h = self.width(), self.height()
        img = QImage(w, h, QImage.Format.Format_RGB32)
        img.fill(self.palette().window().color())  # ook de strook tussen kleurvlak en grijsbalk vullen
        p = QPainter(img)
        gw = w - 14
        g = QLinearGradient(0, 0, gw, 0)
        for i in range(7):
            g.setColorAt(i / 6, QColor.fromHsvF((i / 6) % 1.0, 1, 1))
        p.fillRect(0, 0, gw, h, g)
        v = QLinearGradient(0, 0, 0, h)
        v.setColorAt(0, QColor(255, 255, 255, 255))
        v.setColorAt(0.5, QColor(255, 255, 255, 0))
        v.setColorAt(0.5, QColor(0, 0, 0, 0))
        v.setColorAt(1, QColor(0, 0, 0, 255))
        p.fillRect(0, 0, gw, h, v)
        gray = QLinearGradient(0, 0, 0, h)
        gray.setColorAt(0, QColor(255, 255, 255))
        gray.setColorAt(1, QColor(0, 0, 0))
        p.fillRect(gw + 2, 0, 12, h, gray)
        p.end()
        self.img = img

    def paintEvent(self, e):
        if self.img:
            QPainter(self).drawImage(0, 0, self.img)

    def mousePressEvent(self, e):
        self.mouseMoveEvent(e)

    def mouseMoveEvent(self, e):
        if not self.img:
            return
        x = max(0, min(self.width() - 1, int(e.position().x())))
        y = max(0, min(self.height() - 1, int(e.position().y())))
        right = bool(e.buttons() & Qt.MouseButton.RightButton)
        self.picked.emit(self.img.pixelColor(x, y), not right)


class Swatches(QWidget):
    clickedFg = Signal()
    clickedBg = Signal()
    swap = Signal()

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.setFixedSize(84, 74)
        self.setToolTip("Klik om een kleur te kiezen. Pijltje of X: kleuren wisselen")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(30, 30, 30), 1))
        p.setBrush(self.main.bg)
        p.drawRect(30, 26, 44, 44)
        p.setBrush(self.main.fg)
        p.drawRect(4, 4, 44, 44)
        p.setPen(QPen(self.palette().text().color(), 1.5))
        p.drawLine(58, 6, 74, 6)
        p.drawLine(74, 6, 74, 20)
        p.drawLine(74, 20, 70, 15)
        p.drawLine(74, 20, 78, 15)
        p.end()

    def mousePressEvent(self, e):
        x, y = e.position().x(), e.position().y()
        if x > 54 and y < 24:
            self.swap.emit()
        elif QRect(4, 4, 44, 44).contains(int(x), int(y)):
            self.clickedFg.emit()
        elif QRect(30, 26, 44, 44).contains(int(x), int(y)):
            self.clickedBg.emit()


class MaterialsPalette(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.spectrum = Spectrum()
        self.spectrum.picked.connect(main.set_color)
        lay.addWidget(self.spectrum, 1)
        row = QHBoxLayout()
        self.sw = Swatches(main)
        self.sw.clickedFg.connect(lambda: self.choose(True))
        self.sw.clickedBg.connect(lambda: self.choose(False))
        self.sw.swap.connect(main.swap_colors)
        row.addWidget(self.sw)
        info = QVBoxLayout()
        self.lbl = QLabel()
        self.lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info.addWidget(self.lbl)
        reset = QToolButton(text="Standaard (zwart/wit)")
        reset.clicked.connect(main.reset_colors)
        info.addWidget(reset)
        info.addStretch()
        row.addLayout(info)
        lay.addLayout(row)
        self.refresh()

    def choose(self, fg):
        cur = self.main.fg if fg else self.main.bg
        c = QColorDialog.getColor(cur, self, "Voorgrondkleur" if fg else "Achtergrondkleur")
        if c.isValid():
            self.main.set_color(c, fg)

    def refresh(self):
        f, b = self.main.fg, self.main.bg
        from .i18n import tr
        self.lbl.setText(tr("Voorgrond: {}\nAchtergrond: {}").format(f.name().upper(), b.name().upper()))
        self.sw.update()


# ---------------------------------------------------------------- lagen
def _checker_thumb(img, w=44, h=44):
    pm = QPixmap(w, h)
    p = QPainter(pm)
    for y in range(0, h, 6):
        for x in range(0, w, 6):
            p.fillRect(x, y, 6, 6, QColor(255, 255, 255) if (x // 6 + y // 6) % 2 == 0 else QColor(204, 204, 204))
    t = img.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    p.drawImage((w - t.width()) // 2, (h - t.height()) // 2, t)
    p.setPen(QColor(120, 120, 120))
    p.drawRect(0, 0, w - 1, h - 1)
    p.end()
    return pm


class LayerRow(QWidget):
    def __init__(self, palette, layer, depth=0):
        super().__init__()
        self.layer = layer
        h = QHBoxLayout(self)
        h.setContentsMargins(2 + depth * 18, 2, 2, 2)
        self.tog = None
        self.selected = False
        if layer.kind == "group":
            tog = self.tog = QToolButton()
            icons.set_button(tog, "chevron_right" if layer.collapsed else "chevron_down", 12)
            tog.setAutoRaise(True)
            tog.setFixedSize(16, 22)
            tog.setToolTip("Groep in- of uitklappen")
            tog.clicked.connect(lambda: palette.toggle_collapse(layer))
            h.addWidget(tog)
            h.addSpacing(8)  # ruimte tot het oogje, zodat je bij in- of uitklappen niet per ongeluk de groep verbergt
        self.eye = QToolButton()
        self.eye.setCheckable(True)
        self.eye.setChecked(layer.visible)
        self.eye.setAutoRaise(True)
        self.eye.setFixedSize(22, 22)
        self.eye.setToolTip("Zichtbaarheid aan/uit")
        # geen eigen knopvlak: het oogje staat direct op de rij, zodat het ook op de selectiebalk goed te zien is
        self.eye.setStyleSheet("QToolButton { border: none; background: transparent; border-radius: 3px; }"
                               "QToolButton:hover { background: rgba(127, 127, 127, 70); }")
        self._paint_icons()
        self.eye.toggled.connect(lambda v: self._paint_icons())
        self.eye.toggled.connect(lambda v: palette.set_visible(layer, v))
        h.addWidget(self.eye)
        kind = {"group": ("folder", "Lagengroep"), "mask": ("mask", "Maskerlaag (wit = tonen, zwart = verbergen)")}.get(layer.kind)
        if layer.adjust is not None:
            kind = ("adjust", "Aanpassingslaag (wit = effect, zwart = geen effect)")
        if layer.text is not None:
            kind = ("A", "Tekstlaag: klik met het tekstgereedschap op de tekst om te bewerken")
        elif layer.vector is not None:
            kind = ("✒", "Vectorlaag: lijnen en vormen blijven bewerkbaar met de Pen (modus Bewerken)")
        if kind:
            k = QLabel()
            k.setPixmap(icons.label_pixmap(kind[0], 16, icons.text_color()))
            k.setToolTip(kind[1])
            h.addWidget(k)
        self.thumb = QLabel()
        if layer.kind != "group":
            self.thumb.setPixmap(_checker_thumb(layer.image))
            h.addWidget(self.thumb)
        self.name = QLabel(layer.name)
        self.name.setProperty("pp_notr", True)  # laagnamen zijn gegevens, niet vertalen
        h.addWidget(self.name, 1)
        if layer.lock_alpha:
            lk = QLabel()
            lk.setPixmap(icons.label_pixmap("lock", 14, icons.text_color()))
            lk.setToolTip("Transparantie vergrendeld")
            h.addWidget(lk)
        if layer.link_set:
            ln = QLabel(str(layer.link_set))
            ln.setProperty("pp_notr", True)
            ic = QLabel()
            ic.setPixmap(icons.label_pixmap("link", 14, icons.text_color()))
            ic.setToolTip("Koppelingsset")
            h.addWidget(ic)
            h.addWidget(ln)
        if layer.highlight is not None:
            self.setAutoFillBackground(True)
            pal = self.palette()
            pal.setColor(self.backgroundRole(), layer.highlight)
            self.setPalette(pal)

    def set_selected(self, sel):
        if sel != self.selected:
            self.selected = sel
            self._paint_icons()

    def _paint_icons(self):
        """Oogje en uitklappijltje; op de geselecteerde rij in de tekstkleur van de selectie, anders vallen ze
        weg tegen de selectiebalk (die dezelfde accentkleur heeft als de iconen)."""
        from PySide6.QtWidgets import QApplication
        col = QApplication.palette().highlightedText().color() if self.selected else None
        icons.set_button(self.eye, "eye" if self.eye.isChecked() else "eye_off", 16, color=col)
        if self.tog is not None:
            icons.set_button(self.tog, "chevron_right" if self.layer.collapsed else "chevron_down", 12, color=col)

    def refresh_thumb(self):
        if self.layer.kind != "group":
            self.thumb.setPixmap(_checker_thumb(self.layer.image))


class LayersPalette(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.doc = None
        self._busy = False
        self._opacity_undo = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(3)

        bar = QHBoxLayout()
        new = QToolButton()
        icons.set_button(new, "layer_new", 18, "Nieuwe rasterlaag")
        new.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.new_menu = QMenu(new)
        self.new_menu.aboutToShow.connect(self._fill_new_menu)
        new.setMenu(self.new_menu)
        new.clicked.connect(lambda: self.doc and self.main._run(self.main.new_raster_layer))
        bar.addWidget(new)
        for glyph, tip, fn in [
            ("delete", "Laag verwijderen", lambda d: d.delete_layer()),
            ("gear", "Laageigenschappen", lambda d: self.main.layer_properties()),
            ("up", "Omhoog verplaatsen", lambda d: d.move_layer(1)),
            ("down", "Omlaag verplaatsen", lambda d: d.move_layer(-1)),
            ("merge_down", "Omlaag samenvoegen", lambda d: d.merge_down()),
        ]:
            b = QToolButton()
            icons.set_button(b, glyph, 18, tip)
            b.setAutoRaise(True)
            b.clicked.connect(lambda _=False, f=fn: self.doc and f(self.doc))
            bar.addWidget(b)
        bar.addStretch()
        lay.addLayout(bar)

        row = QHBoxLayout()
        from .tools import SliderSpinBox
        self.spin = SliderSpinBox()  # met schuifbalk onderaan, net als de invoervelden in de optiebalk
        self.spin.setRange(0, 100)
        self.spin.setToolTip("Dekking")
        self.spin.valueChanged.connect(self.on_opacity)
        op = QLabel()
        op.setPixmap(icons.label_pixmap("opacity", 16))
        op.setToolTip("Dekking")
        row.addWidget(op)
        row.addWidget(self.spin)
        self.mode = QComboBox()
        self.mode.addItems([m[0] for m in BLEND_MODES])
        self.mode.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.mode.setMinimumContentsLength(3)
        self.mode.setToolTip("Mengmodus")
        self.mode.currentIndexChanged.connect(self.on_mode)
        row.addWidget(self.mode, 1)
        self.lock = QToolButton()
        icons.set_button(self.lock, "lock", 16)
        self.lock.setCheckable(True)
        self.lock.setToolTip("Transparantie vergrendelen")
        self.lock.toggled.connect(self.on_lock)
        row.addWidget(self.lock)
        lay.addLayout(row)

        self.list = QListWidget()
        self.list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.currentRowChanged.connect(self.on_row)
        self.list.currentRowChanged.connect(lambda _: self._mark_selected())
        self.list.model().rowsMoved.connect(self.on_moved)
        self.list.itemDoubleClicked.connect(lambda it: self.main.layer_properties())
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.context_menu)
        lay.addWidget(self.list, 1)

        self.thumb_timer = QTimer(self, singleShot=True, interval=400)
        self.thumb_timer.timeout.connect(self.refresh_thumbs)
        self.set_doc(None)

    def _fill_new_menu(self):
        """Zelfde indeling als de knop 'Nieuwe laag' in PSP (zelfde acties als het menu Lagen)."""
        m = self.new_menu
        m.clear()
        acts = self.main.actions_by_id
        for cid in (0x8140, 0x8141, 0x8289, 0x8191):
            if cid in acts:
                m.addAction(acts[cid])
        for title, cids in (("Nieuwe maskerlaag", (0x8107, 0x8108, None, 0x8106, 0x80e9, None, 0x80e8)),
                            ("Nieuwe aanpassingslaag", (0x8144, 0x8147, 0x8145, 0x8143, 0x8146, 0x8148, 0x8142, 0x814a, 0x8149))):
            sub = m.addMenu(title)
            for cid in cids:
                if cid is None:
                    sub.addSeparator()
                elif cid in acts:
                    sub.addAction(acts[cid])

    def set_doc(self, doc):
        if self.doc is not None:
            for sig, slot in ((self.doc.structureChanged, self.refresh), (self.doc.changed, self._changed)):
                try:
                    sig.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        self.doc = doc
        if doc is not None:
            doc.structureChanged.connect(self.refresh)
            doc.changed.connect(self._changed)
        self.setEnabled(doc is not None)
        self.refresh()

    def _changed(self, _r):
        self.thumb_timer.start()

    def _hidden(self, l):
        p = l.group
        while p is not None:
            if p.collapsed:
                return True
            p = p.group
        return False

    def refresh(self):
        self._busy = True
        self.list.clear()
        d = self.doc
        if d is not None:
            cur = None
            for i in reversed(range(len(d.layers))):
                l = d.layers[i]
                if self._hidden(l):
                    continue
                it = QListWidgetItem()
                it.setData(Qt.ItemDataRole.UserRole, i)
                row = LayerRow(self, l, d.depth(l))
                it.setSizeHint(QSize(100, 50 if l.kind != "group" else 30))
                self.list.addItem(it)
                self.list.setItemWidget(it, row)
                if i == d.active:
                    cur = self.list.count() - 1
            if cur is not None:
                self.list.setCurrentRow(cur)
            self._mark_selected()
            l = d.layer()
            self.mode.setCurrentIndex(l.mode)
            self.spin.setValue(round(l.opacity * 100))
            self.lock.setChecked(l.lock_alpha)
        self._busy = False

    def _mark_selected(self):
        cur = self.list.currentRow()
        for i in range(self.list.count()):
            w = self.list.itemWidget(self.list.item(i))
            if isinstance(w, LayerRow):
                w.set_selected(i == cur)

    def toggle_collapse(self, g):
        g.collapsed = not g.collapsed
        if g.collapsed and self.doc.layer() in self.doc.subtree(g) and self.doc.layer() is not g:
            self.doc.active = self.doc.layers.index(g)
        self.refresh()

    def refresh_thumbs(self):
        for i in range(self.list.count()):
            w = self.list.itemWidget(self.list.item(i))
            if w is not None:
                w.refresh_thumb()

    def _index(self, row):
        return self.list.item(row).data(Qt.ItemDataRole.UserRole)

    def on_row(self, row):
        if self._busy or self.doc is None or row < 0:
            return
        self.doc.active = self._index(row)
        self._busy = True
        l = self.doc.layer()
        self.mode.setCurrentIndex(l.mode)
        self.spin.setValue(round(l.opacity * 100))
        self.lock.setChecked(l.lock_alpha)
        self._busy = False
        self.doc.titleChanged.emit()

    def on_moved(self, parent, start, end, dest, row):
        """Slepen in het lagenpalet. De laag komt direct onder de laag die er nu boven staat:
        onder een uitgeklapte groepskop wordt hij lid van die groep, anders van dezelfde groep als de buur."""
        if self._busy or self.doc is None:
            return
        d = self.doc
        new_row = row if row < start else row - 1
        moved = d.layers[self.list.item(new_row).data(Qt.ItemDataRole.UserRole)]
        above = d.layers[self.list.item(new_row - 1).data(Qt.ItemDataRole.UserRole)] if new_row > 0 else None
        subtree = d.subtree(moved)
        if above is not None and above in subtree:
            QTimer.singleShot(0, self.refresh)
            return
        d.push_undo("Laag verplaatsen")
        rest = [l for l in d.layers if l not in subtree]
        if above is None:  # helemaal bovenaan
            moved.group = None
            pos = len(rest)
        elif above.kind == "group" and not above.collapsed:
            moved.group = above
            pos = rest.index(above)
        else:
            moved.group = above.group
            pos = rest.index(d.subtree(above)[0])
        d.layers = rest[:pos] + subtree + rest[pos:]
        d.active = d.layers.index(moved)
        d.normalize()
        QTimer.singleShot(0, d.structureChanged.emit)
        d.changed.emit(QRect())

    def set_visible(self, layer, vis):
        if self._busy or self.doc is None or layer.visible == vis:
            return
        self.doc.push_undo("Zichtbaarheid")
        layer.visible = vis
        self.doc.changed.emit(QRect())
        self.refresh()

    def context_menu(self, pos):
        """Rechtsklik op een laag: die laag wordt actief en het volledige Lagen menu verschijnt (zoals PSP)."""
        it = self.list.itemAt(pos)
        if it is not None:
            self.list.setCurrentItem(it)
        lagen = self.main.top_menus.get("Lagen")
        m = QMenu(self)
        if self.doc is not None and (self.doc.layer().text is not None or self.doc.layer().vector is not None):
            m.addAction("Omzetten in rasterlaag", self.main.convert_to_raster)
            m.addSeparator()
        if lagen is not None:
            for a in lagen.actions():
                m.addAction(a)
        m.exec(self.list.mapToGlobal(pos))

    def on_mode(self, i):
        if self._busy or self.doc is None:
            return
        self.doc.push_undo("Mengmodus")
        self.doc.layer().mode = i
        self.doc.changed.emit(QRect())

    def on_lock(self, v):
        if self._busy or self.doc is None:
            return
        self.doc.push_undo("Transparantie vergrendelen")
        self.doc.layer().lock_alpha = v
        self.refresh()

    def on_opacity(self, v):
        if self._busy or self.doc is None:
            return
        if not self._opacity_undo:
            self.doc.push_undo("Dekking")
            self._opacity_undo = True
            QTimer.singleShot(1200, lambda: setattr(self, "_opacity_undo", False))
        self.doc.layer().opacity = v / 100
        self.doc.changed.emit(QRect())


# ---------------------------------------------------------------- geschiedenis
class HistoryPalette(QWidget):
    def __init__(self, main):
        super().__init__()
        self.doc = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.list = QListWidget()
        self.list.itemClicked.connect(self.jump)
        lay.addWidget(self.list)
        self.set_doc(None)

    def set_doc(self, doc):
        if self.doc is not None:
            try:
                self.doc.historyChanged.disconnect(self.refresh)
            except (RuntimeError, TypeError):
                pass
        self.doc = doc
        if doc is not None:
            doc.historyChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.list.clear()
        d = self.doc
        if d is None:
            return
        from .i18n import tr
        self.list.addItem(tr("Begin"))
        for label, _ in d.undo_stack:
            self.list.addItem(tr(label))
        for label, _ in reversed(d.redo_stack):
            it = QListWidgetItem(tr(label))
            it.setForeground(QBrush(QColor(150, 150, 150)))
            self.list.addItem(it)
        self.list.setCurrentRow(len(d.undo_stack))

    def jump(self, it):
        d = self.doc
        if d is None:
            return
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            d.jump_history(self.list.row(it))
        finally:
            QApplication.restoreOverrideCursor()


# ================================================================ Histogram, Overzicht, Penseelvariantie
class _CanvasWatcher(QWidget):
    """Basis voor paletten die het actieve beeld volgen: kijkt een paar keer per seconde of er iets
    veranderd is (alleen als het palet zichtbaar is)."""

    def __init__(self, main, interval=250):
        super().__init__()
        self.main = main
        self._key = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(interval)

    def _state(self, cv):
        return None

    def _poll(self):
        if not self.isVisible():
            return
        cv = self.main.canvas()
        key = (id(cv), self._state(cv)) if cv is not None else None
        if key != self._key:
            self._key = key
            self.refresh(cv)

    def refresh(self, cv):
        self.update()


class HistogramPalette(_CanvasWatcher):
    """Histogram van de afbeelding (alle zichtbare lagen): helderheid of een kleurkanaal, met gemiddelde en
    mediaan. Wordt bijgewerkt als de afbeelding verandert."""
    CHANNELS = ["Helderheid", "Rood", "Groen", "Blauw", "RGB"]

    def __init__(self, main):
        super().__init__(main, 400)
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        self.combo = QComboBox()
        self.combo.addItems(self.CHANNELS)
        self.combo.currentIndexChanged.connect(lambda *_: self.refresh(self.main.canvas()))
        v.addWidget(self.combo)
        self.view = QWidget()
        self.view.setMinimumHeight(110)
        self.view.paintEvent = self._paint_view
        v.addWidget(self.view, 1)
        self.info = QLabel()
        self.info.setProperty("pp_notr", True)
        v.addWidget(self.info)
        self.hist = None

    def _state(self, cv):
        return cv.cache.cacheKey() if cv is not None and cv.cache is not None else None

    def refresh(self, cv):
        import numpy as np
        from . import imageops as ops
        from .i18n import tr
        self.hist = None
        if cv is not None and cv.cache is not None:
            a = ops.qimage_to_rgba(cv.cache)
            step = max(1, int((a.shape[0] * a.shape[1] / 400000) ** 0.5))  # grote foto's: steekproef
            a = a[::step, ::step].reshape(-1, 4)
            a = a[a[:, 3] > 0]
            if len(a):
                y = (a[:, 0] * 0.299 + a[:, 1] * 0.587 + a[:, 2] * 0.114).astype(np.int32)
                self.hist = [np.bincount(y, minlength=256)] + [np.bincount(a[:, c], minlength=256) for c in range(3)]
                ch = self.combo.currentIndex()
                vals = y if ch in (0, 4) else a[:, ch - 1]
                self.info.setText(f"{tr('Gemiddelde')}: {vals.mean():.1f}   {tr('Mediaan')}: {int(np.median(vals))}")
        if self.hist is None:
            self.info.setText("")
        self.view.update()

    def _paint_view(self, e):
        p = QPainter(self.view)
        r = self.view.rect().adjusted(1, 1, -1, -1)
        p.fillRect(r, self.palette().base())
        if self.hist is not None:
            ch = self.combo.currentIndex()
            sets = [(self.hist[1], QColor(230, 60, 60, 150)), (self.hist[2], QColor(60, 190, 60, 150)),
                    (self.hist[3], QColor(60, 90, 230, 150))] if ch == 4 else \
                [(self.hist[ch], [self.palette().text().color(), QColor(220, 50, 50), QColor(40, 170, 40),
                                  QColor(50, 80, 220)][ch])]
            top = max(float(h[1:255].max()) for h, _ in sets) or 1.0  # uitersten niet laten overheersen
            for h, col in sets:
                p.setPen(Qt.PenStyle.NoPen)
                c = QColor(col)
                p.setBrush(c)
                for i in range(256):
                    x0 = r.left() + r.width() * i / 256
                    hh = min(1.0, h[i] / top) * r.height()
                    p.drawRect(QRectF(x0, r.bottom() - hh, max(1.0, r.width() / 256), hh))
        p.setPen(QPen(self.palette().mid().color()))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        p.end()


class OverviewPalette(_CanvasWatcher):
    """Overzicht: de hele afbeelding verkleind, met een kader om wat er in het venster te zien is. Klik of
    sleep in het overzicht om het beeld te verschuiven."""

    def __init__(self, main):
        super().__init__(main, 150)
        self.setMinimumSize(160, 120)
        self._drag = False

    def _state(self, cv):
        return (cv.cache.cacheKey() if cv.cache is not None else 0, round(cv.zoom, 4), round(cv.ox), round(cv.oy),
                cv.width(), cv.height())

    def _geom(self, cv):
        d = cv.doc
        s = min((self.width() - 8) / d.w, (self.height() - 24) / d.h)
        w, h = d.w * s, d.h * s
        return QRectF((self.width() - w) / 2, 4, w, h), s

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().window())
        cv = self.main.canvas()
        if cv is not None and cv.cache is not None:
            r, s = self._geom(cv)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.drawImage(r, cv.cache)
            # zichtbaar deel van het venster
            vx, vy = -cv.ox / cv.zoom, -cv.oy / cv.zoom
            vw, vh = cv.width() / cv.zoom, cv.height() / cv.zoom
            view = QRectF(r.x() + vx * s, r.y() + vy * s, vw * s, vh * s).intersected(r)
            p.setPen(QPen(QColor(230, 40, 40), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(view)
            p.setPen(self.palette().text().color())
            from .i18n import tr
            p.drawText(QRectF(0, self.height() - 18, self.width(), 16), Qt.AlignmentFlag.AlignCenter,
                       f"{tr('Zoom')}: {cv.zoom * 100:.0f}%")
        p.end()

    def _center_on(self, pos):
        cv = self.main.canvas()
        if cv is None:
            return
        r, s = self._geom(cv)
        x, y = (pos.x() - r.x()) / s, (pos.y() - r.y()) / s
        cv.ox = cv.width() / 2 - x * cv.zoom
        cv.oy = cv.height() / 2 - y * cv.zoom
        cv._auto = False
        cv.update()
        self.update()

    def mousePressEvent(self, e):
        self._drag = True
        self._center_on(e.position())

    def mouseMoveEvent(self, e):
        if self._drag:
            self._center_on(e.position())

    def mouseReleaseEvent(self, e):
        self._drag = False


class BrushVariancePalette(QWidget):
    """Penseelvariantie: willekeurige afwijking per stempel in grootte, dekking, rotatie en plaats (spreiding),
    voor een natuurlijker streek. Geldt voor het penseel, de airbrush en de wisser."""
    FIELDS = [("var_size", "Grootte"), ("var_opacity", "Dekking"), ("var_rotation", "Rotatie"),
              ("var_spread", "Spreiding")]

    def __init__(self, main):
        super().__init__()
        from PySide6.QtWidgets import QFormLayout, QSpinBox
        self.main = main
        f = QFormLayout(self)
        for key, label in self.FIELDS:
            main.opts.setdefault(key, 0)
            sp = QSpinBox()
            sp.setRange(0, 100)
            sp.setSuffix(" %")
            sp.setValue(int(main.opts[key]))
            sp.valueChanged.connect(lambda v, k=key: main.opts.__setitem__(k, v))
            f.addRow(label + ":", sp)
        reset = QLabel("0 % = geen variatie")
        reset.setStyleSheet("color: gray;")
        f.addRow(reset)
