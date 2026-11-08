"""Werkvlak: toont een document met zoom, schuiven, selectierand en gereedschap."""
from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

from .document import Document

ZOOM_MIN, ZOOM_MAX = 0.01, 64.0


def _checker():
    pm = QPixmap(16, 16)
    pm.fill(QColor(255, 255, 255))
    p = QPainter(pm)
    p.fillRect(0, 0, 8, 8, QColor(204, 204, 204))
    p.fillRect(8, 8, 8, 8, QColor(204, 204, 204))
    p.end()
    return QBrush(pm)


class Canvas(QWidget):
    def __init__(self, doc: Document, main):
        super().__init__()
        self.doc, self.main = doc, main
        self.zoom = 1.0
        self.ox = self.oy = 0.0
        self.cache = None
        self._auto = True  # passend en gecentreerd houden tot de gebruiker zelf zoomt of schuift
        self._pan = None
        self.space = False
        self.mouse_doc = None
        self.checker = _checker()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(120, 90)
        self.ant_offset = 0
        self.ants = QTimer(self)
        self.ants.setInterval(160)
        self.ants.timeout.connect(self._tick)
        # automatisch scrollen bij de rand tijdens selecteren, slepen, bijsnijden...
        self.autoscroll = QTimer(self)
        self.autoscroll.setInterval(30)
        self.autoscroll.timeout.connect(self._autoscroll_tick)
        self._as_buttons = Qt.MouseButton.NoButton
        self._as_mods = Qt.KeyboardModifier.NoModifier
        doc.changed.connect(self._on_changed)
        doc.sizeChanged.connect(self._on_size)
        doc.selectionChanged.connect(self._on_selection)
        self.recompose()

    # ------------------------------------------------------------ beeld
    def _mask_overlay(self, rect=None):
        """Rode waas waar het actieve masker verbergt (Lagen > Overlay weergeven)."""
        d = self.doc
        l = d.layer()
        if not getattr(self.main, "mask_overlay", False) or (l.kind != "mask" and l.adjust is None):
            self.overlay_img = None
            return
        from . import imageops as ops
        import numpy as np
        if getattr(self, "overlay_img", None) is None or self.overlay_img.size() != QSize(d.w, d.h):
            self.overlay_img = QImage(d.w, d.h, QImage.Format.Format_ARGB32_Premultiplied)
            rect = None
        r = d.rect() if rect is None or rect.isEmpty() else rect.intersected(d.rect())
        m = ops.qimage_to_rgba(l.image.copy(r)).astype(np.float32)
        lum = (m[..., 0] * 0.299 + m[..., 1] * 0.587 + m[..., 2] * 0.114) * m[..., 3] / 255
        a = ((255 - lum) * 0.5).astype(np.uint8)
        red = np.dstack([np.full_like(a, 255), np.zeros_like(a), np.zeros_like(a), a])
        p = QPainter(self.overlay_img)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.drawImage(r.topLeft(), ops.rgba_to_qimage(red))
        p.end()

    def recompose(self, rect=None):
        self._mask_overlay(rect)
        d = self.doc
        if self.cache is None or self.cache.size() != QSize(d.w, d.h) or rect is None or rect.isEmpty():
            self.cache = d.composite()
            return
        r = rect.intersected(d.rect())
        if r.isEmpty():
            return
        part = d.composite(r)
        p = QPainter(self.cache)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.drawImage(r.topLeft(), part)
        p.end()

    def _on_changed(self, rect):
        self.recompose(rect)
        self.update()

    def _on_size(self):
        self.recompose()
        self.fit()

    def _on_selection(self):
        if self.doc.sel is not None:
            self.ants.start()
        else:
            self.ants.stop()
        self.update()

    def _tick(self):
        self.ant_offset = (self.ant_offset + 1) % 8
        self.update()

    # ------------------------------------------------------------ coördinaten
    def to_doc(self, pos) -> QPointF:
        return QPointF((pos.x() - self.ox) / self.zoom, (pos.y() - self.oy) / self.zoom)

    def to_widget(self, pt) -> QPointF:
        return QPointF(pt.x() * self.zoom + self.ox, pt.y() * self.zoom + self.oy)

    def transform(self) -> QTransform:
        return QTransform(self.zoom, 0, 0, self.zoom, self.ox, self.oy)

    def set_zoom(self, z, anchor=None):
        self._auto = False
        z = max(ZOOM_MIN, min(ZOOM_MAX, z))
        if anchor is None:
            anchor = QPointF(self.width() / 2, self.height() / 2)
        dp = self.to_doc(anchor)
        self.zoom = z
        self.ox = anchor.x() - dp.x() * z
        self.oy = anchor.y() - dp.y() * z
        self.update()
        self.main.update_status(self)

    def zoom_step(self, inward, anchor=None):
        self.set_zoom(self.zoom * (1.25 if inward else 0.8), anchor)

    def fit(self):
        d = self.doc
        if self.width() < 10:
            return
        z = min((self.width() - 20) / d.w, (self.height() - 20) / d.h, 1.0)
        self.zoom = max(ZOOM_MIN, z)
        self._auto = True
        self.center()

    def actual_size(self):
        self.zoom = 1.0
        self.center()
        self._auto = False

    def center(self):
        self.ox = (self.width() - self.doc.w * self.zoom) / 2
        self.oy = (self.height() - self.doc.h * self.zoom) / 2
        self.update()
        self.main.update_status(self)

    def resizeEvent(self, e):
        if self._auto:
            self.fit()
        else:
            # houd hetzelfde punt in het midden
            dx = (e.size().width() - e.oldSize().width()) / 2
            dy = (e.size().height() - e.oldSize().height()) / 2
            self.ox += dx
            self.oy += dy

    # ------------------------------------------------------------ tekenen
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(98, 98, 98))
        d, z = self.doc, self.zoom
        target = QRectF(self.ox, self.oy, d.w * z, d.h * z)
        vis = target.intersected(QRectF(self.rect()))
        if not vis.isEmpty():
            p.setBrushOrigin(QPointF(self.ox, self.oy))
            p.fillRect(vis, self.checker)
            src = QRectF((vis.x() - self.ox) / z, (vis.y() - self.oy) / z, vis.width() / z, vis.height() / z)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, z < 1)
            p.drawImage(vis, self.cache, src)
            if getattr(self, "overlay_img", None) is not None:
                p.drawImage(vis, self.overlay_img, src)
        p.setPen(QPen(QColor(40, 40, 40), 1))
        p.drawRect(target.adjusted(-1, -1, 0, 0))

        if getattr(self, "show_grid", False) and z >= 0.25:
            p.save()
            p.setClipRect(vis)
            p.setPen(QPen(QColor(120, 120, 255, 140), 0))
            step = 50
            x = 0
            while x <= d.w:
                wx = self.ox + x * z
                p.drawLine(QPointF(wx, vis.top()), QPointF(wx, vis.bottom()))
                x += step
            y = 0
            while y <= d.h:
                wy = self.oy + y * z
                p.drawLine(QPointF(vis.left(), wy), QPointF(vis.right(), wy))
                y += step
            p.restore()

        if d.sel is not None and d.sel_lines and not getattr(self, "hide_marquee", False):
            p.save()
            p.setTransform(self.transform())
            pen = QPen(QColor(255, 255, 255), 0)
            p.setPen(pen)
            p.drawLines(d.sel_lines)
            pen = QPen(QColor(0, 0, 0), 0, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([4, 4])
            pen.setDashOffset(self.ant_offset)
            p.setPen(pen)
            p.drawLines(d.sel_lines)
            p.restore()

        tool = self.main.tool
        if tool is not None:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            tool.overlay(self, p)
        p.end()

    # ------------------------------------------------------------ invoer
    def _panning_button(self, e):
        return (e.button() == Qt.MouseButton.MiddleButton
                or (e.button() == Qt.MouseButton.LeftButton and (self.space or self.main.tool.is_pan)))

    def mousePressEvent(self, e):
        self.setFocus()
        if self._panning_button(e):
            self._pan = (e.position(), self.ox, self.oy)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if e.button() == Qt.MouseButton.RightButton and self.main.tool.wants_context_menu(self):
            # rechtsklik: eerst afwachten of er gesleept wordt (dan gewoon doorgeven aan het gereedschap)
            self._rc = (e.position(), e.modifiers())
            self._rc_drag = False
            return
        if e.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self._forward_press(e)

    def _forward_press(self, e):
        lay = self.doc.layer()
        live = lay.text is not None or (lay.vector is not None and not getattr(self.main.tool, "vector_ok", False))
        if live and getattr(self.main.tool, "edits_pixels", True):
            if not self.main.ensure_raster():
                return
        if self.doc.layer().kind == "group" and getattr(self.main.tool, "edits_pixels", True):
            self.main.statusBar().showMessage("Dit is een lagengroep. Kies een laag in de groep om op te werken.", 4000)
            return
        try:
            self.main.tool.press(self, self.to_doc(e.position()), e)
        except Exception as ex:  # nooit het programma laten crashen
            self.main.report_error(ex)

    def mouseMoveEvent(self, e):
        pt = self.to_doc(e.position())
        self.mouse_doc = pt
        rc = getattr(self, "_rc", None)
        if rc is not None and not self._rc_drag:
            start, mods = rc
            if (e.position() - start).manhattanLength() < 5:
                return
            self._rc_drag = True  # het is slepen: alsnog de rechtsklik doorgeven aan het gereedschap
            from PySide6.QtGui import QMouseEvent
            from PySide6.QtCore import QEvent
            self._forward_press(QMouseEvent(QEvent.Type.MouseButtonPress, start, self.mapToGlobal(start),
                                            Qt.MouseButton.RightButton, Qt.MouseButton.RightButton, mods))
        if self._pan is not None:
            start, ox, oy = self._pan
            self._auto = False
            self.ox = ox + e.position().x() - start.x()
            self.oy = oy + e.position().y() - start.y()
            self.update()
            return
        self._as_buttons, self._as_mods = e.buttons(), e.modifiers()
        if self._autoscroll_wanted() and self._edge_velocity(e.position()) != (0.0, 0.0):
            if not self.autoscroll.isActive():
                self.autoscroll.start()
        try:
            self.main.tool.move(self, pt, e)
            if not e.buttons() and not self.space:  # muisaanwijzer laat zien wat slepen zal doen
                c = self.main.tool.hover_cursor(self, pt)
                self.setCursor(c if c is not None else self.main.tool.cursor)
        except Exception as ex:
            self.main.report_error(ex)
        self.main.update_status(self, pt)
        if self.main.tool.wants_cursor_overlay:
            self.update()

    # ---------------------------------------------------------------- automatisch scrollen
    EDGE = 40          # randzone in pixels waarin het scrollen begint
    MAX_OUTSIDE = 200  # tot zo ver buiten het werkvlak blijft het werken

    def _autoscroll_wanted(self):
        """Alleen tijdens een bewerking: slepen met een muisknop, of een punt-tot-punt selectie in uitvoering."""
        tool = self.main.tool
        if self._pan is not None or self.space or getattr(tool, "is_pan", False) or not getattr(tool, "autoscroll", True):
            return False
        if self._as_buttons & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton):
            return True
        return bool(getattr(tool, "pts", None))  # Selectie uit vrije hand (punt tot punt, slimme rand)

    def _edge_velocity(self, pos):
        """Scrollsnelheid per tik: nul midden in het venster, groter naarmate de muis verder
        in de randzone en daarbuiten komt."""
        def axis(v, size):
            if v < self.EDGE:
                d = self.EDGE - v
            elif v > size - self.EDGE:
                d = -(v - (size - self.EDGE))
            else:
                return 0.0
            if abs(d) > self.EDGE + self.MAX_OUTSIDE:
                return 0.0
            return (1 if d > 0 else -1) * min(60.0, 1.5 + (abs(d) / 6) ** 1.5)
        return axis(pos.x(), self.width()), axis(pos.y(), self.height())

    def _autoscroll_tick(self):
        from PySide6.QtGui import QCursor, QMouseEvent
        from PySide6.QtCore import QEvent
        if not self._autoscroll_wanted() or not self.isVisible():
            self.autoscroll.stop()
            return
        pos = QPointF(self.mapFromGlobal(QCursor.pos()))
        vx, vy = self._edge_velocity(pos)
        # niet verder scrollen dan nodig: de rand van de afbeelding mag tot iets voorbij het midden komen
        w, h = self.doc.w * self.zoom, self.doc.h * self.zoom
        if vx > 0 and self.ox >= self.width() / 2:
            vx = 0
        if vx < 0 and self.ox + w <= self.width() / 2:
            vx = 0
        if vy > 0 and self.oy >= self.height() / 2:
            vy = 0
        if vy < 0 and self.oy + h <= self.height() / 2:
            vy = 0
        if vx == 0 and vy == 0:
            self.autoscroll.stop()
            return
        self._auto = False
        self.ox += vx
        self.oy += vy
        # het gereedschap volgt de muis, zodat selectielijn of kader meeloopt
        pt = self.to_doc(pos)
        self.mouse_doc = pt
        ev = QMouseEvent(QEvent.Type.MouseMove, pos, QCursor.pos().toPointF(), Qt.MouseButton.NoButton,
                         self._as_buttons, self._as_mods)
        try:
            self.main.tool.move(self, pt, ev)
        except Exception as ex:
            self.autoscroll.stop()
            self.main.report_error(ex)
        self.update()

    def mouseReleaseEvent(self, e):
        self._as_buttons = e.buttons()
        rc = getattr(self, "_rc", None)
        if rc is not None and e.button() == Qt.MouseButton.RightButton:
            self._rc = None
            if not self._rc_drag:
                self.main.show_canvas_menu(self, e.position())
                return
        if self._pan is not None:
            self._pan = None
            self.unsetCursor()
            self.apply_cursor()
            return
        try:
            self.main.tool.release(self, self.to_doc(e.position()), e)
        except Exception as ex:
            self.main.report_error(ex)

    def mouseDoubleClickEvent(self, e):
        self.main.tool.double_click(self, self.to_doc(e.position()), e)

    def leaveEvent(self, e):
        self.mouse_doc = None
        self.update()

    def wheelEvent(self, e):
        dy = e.angleDelta().y()
        self._auto = False
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.ox += dy / 2
            self.update()
        elif e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.oy += dy / 2
            self.update()
        elif dy:
            self.zoom_step(dy > 0, e.position())

    def contextMenuEvent(self, e):
        # Menu-toets of Shift+F10: altijd het menu, ook bij gereedschappen die rechts zelf gebruiken
        if e.reason() == e.Reason.Keyboard:
            pos = self.mapFromGlobal(self.cursor().pos())
            if not self.rect().contains(pos):
                pos = self.rect().center()
            self.main.show_canvas_menu(self, QPointF(pos))

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self.space = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if self.main.tool.key(self, e):
            return
        if self._nudge_key(e):
            return
        super().keyPressEvent(e)

    ARROWS = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}

    @staticmethod
    def nudge_speed(repeats):
        """Stapgrootte na zoveel herhalingen: eerst rustig per pixel, daarna steeds sneller (tot 8x)."""
        return 1 if repeats < 8 else min(8, 1 + (repeats - 8) // 6)

    def _nudge_key(self, e):
        """Pijltoetsen: geselecteerde pixels 1 pixel verschuiven (Shift: 10), Ctrl: alleen het selectiekader.
        Met Verplaatsen en zonder selectie schuift de hele laag. Een reeks duwtjes is één stap ongedaan maken."""
        step = self.ARROWS.get(e.key())
        if step is None:
            return False
        from .tools import LayerMover, MoveTool, SelectionBase
        tool, d = self.main.tool, self.doc
        if isinstance(tool, SelectionBase):
            if d.sel is None:
                return False
            what = "marquee" if e.modifiers() & Qt.KeyboardModifier.ControlModifier else "pixels"
        elif isinstance(tool, MoveTool):
            what = "layer" if d.sel is None else ("marquee" if e.modifiers() & Qt.KeyboardModifier.ControlModifier else "pixels")
        else:
            return False
        if what == "pixels" and not self.main.ensure_raster():  # een hele tekst- of vectorlaag blijft wat hij is
            return True
        # versnelling: hoe langer de toets ingedrukt blijft, hoe grotere stappen
        self._nudge_repeat = getattr(self, "_nudge_repeat", 0) + 1 if e.isAutoRepeat() else 0
        n = (10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1) * self.nudge_speed(self._nudge_repeat)
        nz = getattr(self, "_nudge", None)
        # dezelfde reeks zolang er tussendoor niets anders met de afbeelding is gebeurd
        if nz is None or nz["what"] != what or nz["layer"] is not d.layer() or nz["undo"] != len(d.undo_stack) \
                or nz["sel"] is not d.sel:
            nz = {"mover": LayerMover(self, QPointF(0, 0), what), "what": what, "layer": d.layer(), "dx": 0, "dy": 0}
        nz["dx"] += step[0] * n
        nz["dy"] += step[1] * n
        nz["mover"].move(QPointF(nz["dx"], nz["dy"]))
        nz["mover"].finish()
        nz["undo"] = len(d.undo_stack)
        nz["sel"] = d.sel
        self._nudge = nz
        d.changed.emit(QRect())
        self.update()
        return True

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self.space = False
            self.apply_cursor()
            return
        super().keyReleaseEvent(e)

    def apply_cursor(self):
        self.setCursor(self.main.tool.cursor)
