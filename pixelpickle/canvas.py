"""Canvas: shows a document with zoom, panning, selection frame and tool handling."""
from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

from .document import Document

ZOOM_MIN, ZOOM_MAX = 0.01, 64.0


class CanvasView(QWidget):
    """Canvas with scroll bars: they appear only when the image is larger than the window and follow
    panning and zooming; dragging a scroll bar moves the image."""

    def __init__(self, canvas):
        from PySide6.QtWidgets import QGridLayout, QScrollBar
        super().__init__()
        self.canvas = canvas
        g = QGridLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(0)
        self.hbar = QScrollBar(Qt.Orientation.Horizontal)
        self.vbar = QScrollBar(Qt.Orientation.Vertical)
        g.addWidget(canvas, 0, 0)
        g.addWidget(self.vbar, 0, 1)
        g.addWidget(self.hbar, 1, 0)
        self.hbar.hide()
        self.vbar.hide()
        self._busy = False
        self.hbar.valueChanged.connect(lambda v: self._scrolled("h", v))
        self.vbar.valueChanged.connect(lambda v: self._scrolled("v", v))
        canvas.viewChanged.connect(self.sync)

    def sync(self):
        """Update the scroll bars to the current zoom and canvas position."""
        if self._busy:
            return
        cv = self.canvas
        self._busy = True
        try:
            for bar, size, view, off in ((self.hbar, cv.doc.w * cv.zoom, cv.width(), cv.ox),
                                         (self.vbar, cv.doc.h * cv.zoom, cv.height(), cv.oy)):
                need = size > view + 1
                if need != bar.isVisible():
                    bar.setVisible(need)
                if need:
                    bar.setRange(0, int(size - view))
                    bar.setPageStep(int(view))
                    bar.setSingleStep(max(1, int(view / 20)))
                    bar.setValue(int(max(0, min(size - view, -off))))
        finally:
            self._busy = False

    def _scrolled(self, axis, v):
        if self._busy:
            return
        cv = self.canvas
        if axis == "h":
            cv.ox = -v
        else:
            cv.oy = -v
        cv._auto = False
        cv.update()


class Canvas(QWidget):
    viewChanged = Signal()  # zoom or position changed (for the scroll bars)

    def __init__(self, doc: Document, main):
        super().__init__()
        self.doc, self.main = doc, main
        self.zoom = 1.0
        self.ox = self.oy = 0.0
        self.cache = None
        self._auto = True  # keep fitted and centered until the user zooms or scrolls
        self._pan = None
        self.space = False
        self.mouse_doc = None
        self.apply_view_settings()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(120, 90)
        self.ant_offset = 0
        self.ants = QTimer(self)
        self.ants.setInterval(160)
        self.ants.timeout.connect(self._tick)
        # scroll automatically at the edge while selecting, dragging, cropping...
        self.autoscroll = QTimer(self)
        self.autoscroll.setInterval(30)
        self.autoscroll.timeout.connect(self._autoscroll_tick)
        self._as_buttons = Qt.MouseButton.NoButton
        self._as_mods = Qt.KeyboardModifier.NoModifier
        doc.changed.connect(self._on_changed)
        doc.sizeChanged.connect(self._on_size)
        doc.selectionChanged.connect(self._on_selection)
        # another active layer (layers palette) or layer structure: redraw right away, so that for example the
        # Select frame is placed around the new layer at once (the image itself does not need to be recomposed)
        doc.titleChanged.connect(self.update)
        doc.structureChanged.connect(self.update)
        self.recompose()

    # ------------------------------------------------------------ image
    def _mask_overlay(self, rect=None):
        """Red haze where the active mask hides (Layers > Overlay weergeven, i.e. show overlay)."""
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

    # ------------------------------------------------------------ coordinates
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
            # keep the same point in the center
            dx = (e.size().width() - e.oldSize().width()) / 2
            dy = (e.size().height() - e.oldSize().height()) / 2
            self.ox += dx
            self.oy += dy

    # ------------------------------------------------------------ drawing
    def apply_view_settings(self):
        """Checkerboard pattern and hatching according to the preferences."""
        from .dialogs import checker_brush, view_settings
        vs = view_settings()
        self.view = vs
        self.checker = checker_brush(vs["checker_size"], vs["checker_c1"], vs["checker_c2"])
        self.update()

    def _ruby(self):
        """Red layer for Edit Selection: the less is selected, the redder it gets (half transparent)."""
        lay = self.doc.seledit_layer() if hasattr(self.doc, "seledit_layer") else None
        if lay is None or not lay.visible:
            return None
        key = lay.image.cacheKey()
        if getattr(self, "_ruby_key", None) != key:
            import numpy as np
            from . import imageops as ops
            a = ops.qimage_to_rgba(lay.image).astype(np.float32)
            v = (a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114) * a[..., 3] / 255
            out = np.zeros(v.shape + (4,), np.uint8)
            out[..., 0] = 255
            out[..., 3] = np.clip((255 - v) * 0.5, 0, 255).astype(np.uint8)
            self._ruby_img, self._ruby_key = ops.rgba_to_qimage(out), key
        return self._ruby_img

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
            ruby = self._ruby()
            if ruby is not None:  # edit selection: unselected parts in red
                p.drawImage(vis, ruby, src)
        p.setPen(QPen(QColor(40, 40, 40), 1))
        p.drawRect(target.adjusted(-1, -1, 0, 0))

        from .viewaids import paint_grid, paint_guides, paint_rulers
        paint_grid(self, p, vis)
        paint_guides(self, p, vis)

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
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        paint_rulers(self, p)
        p.end()
        key = (round(self.zoom, 5), round(self.ox), round(self.oy), self.width(), self.height(), self.doc.w, self.doc.h)
        if key != getattr(self, "_view_key", None):
            self._view_key = key
            self.viewChanged.emit()

    # ------------------------------------------------------------ input
    def _panning_button(self, e):
        return (e.button() == Qt.MouseButton.MiddleButton
                or (e.button() == Qt.MouseButton.LeftButton and (self.space or self.main.tool.is_pan)))

    # ------------------------------------------------------------ rulers, guides and snapping
    RULER = 18  # width of the rulers in pixels

    def rulers_on(self):
        return bool(self.main.view_opts.get("rulers"))

    def tool_point(self, pos):
        """Document point for the tool, snapped to the grid or guides when that is enabled."""
        pt = self.to_doc(pos)
        if getattr(self.main.tool, "snaps", False):
            from .viewaids import snap
            pt = snap(self, pt)
        return pt

    def _guide_at(self, pos):
        """Guide whose handle on the ruler is under the mouse: ("h"|"v", index) or None."""
        if not self.rulers_on():
            return None
        g = self.doc.guides
        if pos.y() < self.RULER:
            for i, x in enumerate(g["v"]):
                if abs(self.ox + x * self.zoom - pos.x()) <= 5:
                    return ("v", i)
        if pos.x() < self.RULER:
            for i, y in enumerate(g["h"]):
                if abs(self.oy + y * self.zoom - pos.y()) <= 5:
                    return ("h", i)
        return None

    def _ruler_press(self, e):
        """Dragging from a ruler creates a guide; an existing handle drags that guide."""
        if not self.rulers_on() or e.button() != Qt.MouseButton.LeftButton:
            return False
        pos = e.position()
        hit = self._guide_at(pos)
        if hit is None:
            if pos.y() < self.RULER and pos.x() >= self.RULER:
                self.doc.guides["h"].append((pos.y() - self.oy) / self.zoom)
                hit = ("h", len(self.doc.guides["h"]) - 1)
            elif pos.x() < self.RULER and pos.y() >= self.RULER:
                self.doc.guides["v"].append((pos.x() - self.ox) / self.zoom)
                hit = ("v", len(self.doc.guides["v"]) - 1)
            else:
                return pos.x() < self.RULER and pos.y() < self.RULER  # corner: nothing
        self._guide_drag = hit
        self.main.view_opts["guides"] = True
        self.main.sync_view_checks()
        self.update()
        return True

    def _ruler_move(self, e):
        drag = getattr(self, "_guide_drag", None)
        if drag is None:
            return False
        kind, i = drag
        pt = self.to_doc(e.position())
        self.doc.guides[kind][i] = round(pt.y() if kind == "h" else pt.x())
        self.update()
        return True

    def _ruler_release(self, e):
        drag = getattr(self, "_guide_drag", None)
        if drag is None:
            return False
        kind, i = drag
        self._guide_drag = None
        pos = e.position()
        # dragged back into the ruler (or outside the image): remove the guide
        if (kind == "h" and (pos.y() < self.RULER or not 0 <= self.doc.guides["h"][i] <= self.doc.h)) or \
                (kind == "v" and (pos.x() < self.RULER or not 0 <= self.doc.guides["v"][i] <= self.doc.w)):
            del self.doc.guides[kind][i]
        self.update()
        return True

    def mousePressEvent(self, e):
        self.setFocus()
        if self._ruler_press(e):
            return
        if self._panning_button(e):
            self._pan = (e.position(), self.ox, self.oy)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if e.button() == Qt.MouseButton.RightButton and self.main.tool.wants_context_menu(self):
            # right click: first wait to see whether a drag follows (if so, just pass it on to the tool)
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
            self.main.tool.press(self, self.tool_point(e.position()), e)
        except Exception as ex:  # never let the program crash
            self.main.report_error(ex)

    def mouseMoveEvent(self, e):
        pt = self.to_doc(e.position())
        self.mouse_doc = pt
        if self._ruler_move(e):
            return
        if not e.buttons() and self._guide_at(e.position()) is not None:
            kind = self._guide_at(e.position())[0]
            self.setCursor(Qt.CursorShape.SplitVCursor if kind == "h" else Qt.CursorShape.SplitHCursor)
            return
        rc = getattr(self, "_rc", None)
        if rc is not None and not self._rc_drag:
            start, mods = rc
            if (e.position() - start).manhattanLength() < 5:
                return
            self._rc_drag = True  # it is a drag: pass the right click on to the tool after all
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
            self.main.tool.move(self, self.tool_point(e.position()), e)
            if not e.buttons() and not self.space:  # the mouse pointer shows what dragging will do
                c = self.main.tool.hover_cursor(self, pt)
                self.setCursor(c if c is not None else self.main.tool.cursor)
        except Exception as ex:
            self.main.report_error(ex)
        self.main.update_status(self, pt)
        if self.main.tool.wants_cursor_overlay:
            self.update()

    # ---------------------------------------------------------------- automatic scrolling
    EDGE = 40          # edge zone in pixels in which scrolling starts
    MAX_OUTSIDE = 200  # up to this far outside the canvas, working continues

    def _autoscroll_wanted(self):
        """Only during an operation: dragging with a mouse button, or a point-to-point selection in progress."""
        tool = self.main.tool
        if self._pan is not None or self.space or getattr(tool, "is_pan", False) or not getattr(tool, "autoscroll", True):
            return False
        if self._as_buttons & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton):
            return True
        return bool(getattr(tool, "pts", None))  # freehand selection (point to point, smart edge)

    def _edge_velocity(self, pos):
        """Scroll speed per tick: zero in the middle of the window, higher the further the mouse moves
        into the edge zone and beyond."""
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
        # do not scroll further than needed: the edge of the image may reach slightly past the center
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
        # the tool follows the mouse, so the selection line or frame moves along
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
        if self._ruler_release(e):
            return
        self._as_buttons = e.buttons()
        rc = getattr(self, "_rc", None)
        if rc is not None and e.button() == Qt.MouseButton.RightButton:
            self._rc = None
            if not self._rc_drag:
                if self.main.tool.right_click(self, self.to_doc(e.position())):
                    return  # the tool uses the right click itself (for example to clear a selection)
                self.main.show_canvas_menu(self, e.position())
                return
        if self._pan is not None:
            self._pan = None
            self.unsetCursor()
            self.apply_cursor()
            return
        try:
            self.main.tool.release(self, self.tool_point(e.position()), e)
        except Exception as ex:
            self.main.report_error(ex)

    def mouseDoubleClickEvent(self, e):
        self.main.tool.double_click(self, self.tool_point(e.position()), e)

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
        # Menu key or Shift+F10: always the menu, also for tools that use the right button themselves
        if e.reason() == e.Reason.Keyboard:
            pos = self.mapFromGlobal(self.cursor().pos())
            if not self.rect().contains(pos):
                pos = self.rect().center()
            self.main.show_canvas_menu(self, QPointF(pos))

    def _refresh_cursor(self):
        """Determine the cursor again (for example an eyedropper while Ctrl is held down)."""
        if self.space or self._pan is not None or self.mouse_doc is None:
            return
        c = self.main.tool.hover_cursor(self, self.mouse_doc)
        self.setCursor(c if c is not None else self.main.tool.cursor)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Control:
            self._refresh_cursor()
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
        """Step size after this many repeats: slow per pixel at first, then faster and faster (up to 8x)."""
        return 1 if repeats < 8 else min(8, 1 + (repeats - 8) // 6)

    def _nudge_key(self, e):
        """Arrow keys: move the selected pixels 1 pixel (Shift: 10), Ctrl: only the selection frame.
        With Move and no selection the whole layer moves. A series of nudges is one undo step."""
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
        if what == "pixels" and not self.main.ensure_raster():  # a whole text or vector layer stays what it is
            return True
        # acceleration: the longer the key is held down, the larger the steps
        self._nudge_repeat = getattr(self, "_nudge_repeat", 0) + 1 if e.isAutoRepeat() else 0
        n = (10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1) * self.nudge_speed(self._nudge_repeat)
        nz = getattr(self, "_nudge", None)
        # same series as long as nothing else has happened to the image in between
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
        if e.key() == Qt.Key.Key_Control:
            QTimer.singleShot(0, self._refresh_cursor)  # after release: restore the normal cursor
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self.space = False
            self.apply_cursor()
            return
        super().keyReleaseEvent(e)

    def apply_cursor(self):
        self.setCursor(self.main.tool.cursor)
