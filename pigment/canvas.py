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
        if e.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            if self.doc.layer().text is not None and getattr(self.main.tool, "edits_pixels", True):
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
        if self._pan is not None:
            start, ox, oy = self._pan
            self._auto = False
            self.ox = ox + e.position().x() - start.x()
            self.oy = oy + e.position().y() - start.y()
            self.update()
            return
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

    def mouseReleaseEvent(self, e):
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

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self.space = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if not self.main.tool.key(self, e):
            super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self.space = False
            self.apply_cursor()
            return
        super().keyReleaseEvent(e)

    def apply_cursor(self):
        self.setCursor(self.main.tool.cursor)
