"""Document model: layers, selection and history (undo)."""
import numpy as np
from PySide6.QtCore import QObject, QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QTransform

from . import imageops as ops

FMT = ops.FMT
CM = QPainter.CompositionMode

# Blend modes in the same order as in Paint Shop Pro XI (compatible with the blend modes in .pspimage files).
# (Dutch name, Qt mode or None = NumPy, OpenRaster name)
BLEND_MODES = [
    ("Normaal", CM.CompositionMode_SourceOver, "svg:src-over"),
    ("Donkerder", CM.CompositionMode_Darken, "svg:darken"),
    ("Lichter", CM.CompositionMode_Lighten, "svg:lighten"),
    ("Kleurtoon", None, "svg:hue"),
    ("Kleurtoon (oud)", None, "pixelpickle:hue-legacy"),
    ("Verzadiging", None, "svg:saturation"),
    ("Verzadiging (oud)", None, "pixelpickle:saturation-legacy"),
    ("Kleur", None, "svg:color"),
    ("Kleur (oud)", None, "pixelpickle:color-legacy"),
    ("Luminantie", None, "svg:luminosity"),
    ("Luminantie (oud)", None, "pixelpickle:luminosity-legacy"),
    ("Vermenigvuldigen", CM.CompositionMode_Multiply, "svg:multiply"),
    ("Scherm", CM.CompositionMode_Screen, "svg:screen"),
    ("Oplossen", None, "pixelpickle:dissolve"),
    ("Bedekken", CM.CompositionMode_Overlay, "svg:overlay"),
    ("Hard licht", CM.CompositionMode_HardLight, "svg:hard-light"),
    ("Zacht licht", CM.CompositionMode_SoftLight, "svg:soft-light"),
    ("Verschil", CM.CompositionMode_Difference, "svg:difference"),
    ("Tegenhouden", CM.CompositionMode_ColorDodge, "svg:color-dodge"),
    ("Doordrukken", CM.CompositionMode_ColorBurn, "svg:color-burn"),
    ("Uitsluiting", CM.CompositionMode_Exclusion, "svg:exclusion"),
]
# Tools have one extra: paint only where the layer is transparent
TOOL_BLEND_MODES = BLEND_MODES + [("Achter tekenen", CM.CompositionMode_DestinationOver, None)]

_DISSOLVE = {}


def _dissolve_noise(h, w, x0=0, y0=0):
    key = (h + y0, w + x0)
    n = _DISSOLVE.get("n")
    if n is None or n.shape[0] < key[0] or n.shape[1] < key[1]:
        n = np.random.default_rng(1234).random((max(key[0], 1024), max(key[1], 1024)), dtype=np.float32)
        _DISSOLVE["n"] = n
    return n[y0:y0 + h, x0:x0 + w]


def _lum(c):
    return c[..., 0] * 0.3 + c[..., 1] * 0.59 + c[..., 2] * 0.11


def _clip_color(c):
    l = _lum(c)[..., None]
    n = c.min(axis=-1, keepdims=True)
    x = c.max(axis=-1, keepdims=True)
    c = np.where(n < 0, l + (c - l) * l / np.maximum(l - n, 1e-6), c)
    c = np.where(x > 1, l + (c - l) * (1 - l) / np.maximum(x - l, 1e-6), c)
    return c


def _set_lum(c, l):
    return _clip_color(c + (l - _lum(c))[..., None])


def _sat(c):
    return c.max(axis=-1) - c.min(axis=-1)


def _set_sat(c, s):
    mx = c.max(axis=-1, keepdims=True)
    mn = c.min(axis=-1, keepdims=True)
    rng = mx - mn
    return np.where(rng > 1e-6, (c - mn) * s[..., None] / np.maximum(rng, 1e-6), 0.0)


def _blend_fn(key, cb, cs):
    """Non-separable blend functions. cb = backdrop layer, cs = source layer, values 0..1."""
    if key.endswith("-legacy"):  # classic method (compatible with older .pspimage files): replace HSL components
        hb, sb, lb = ops.rgb_to_hsl(cb * 255)
        hs, ss, ls = ops.rgb_to_hsl(cs * 255)
        if "hue" in key:
            return ops.hsl_to_rgb(hs, sb, lb) / 255
        if "saturation" in key:
            return ops.hsl_to_rgb(hb, ss, lb) / 255
        if "color" in key:
            return ops.hsl_to_rgb(hs, ss, lb) / 255
        return ops.hsl_to_rgb(hb, sb, ls) / 255
    if key == "svg:hue":
        return _set_lum(_set_sat(cs, _sat(cb)), _lum(cb))
    if key == "svg:saturation":
        return _set_lum(_set_sat(cb, _sat(cs)), _lum(cb))
    if key == "svg:color":
        return _set_lum(cs, _lum(cb))
    if key == "svg:luminosity":
        return _set_lum(cb, _lum(cs))
    return cs


def blend_onto(dst: QImage, src: QImage, mode: int, opacity=1.0, src_rect: QRect | None = None,
               origin=QPoint(0, 0), modes=TOOL_BLEND_MODES) -> QImage:
    """Blend src (or the part src_rect of it) over dst; returns the result (dst is modified).
    origin: position of dst in document coordinates (for 'Oplossen' (Dissolve))."""
    name, qt_mode, key = modes[mode]
    if src_rect is None:
        src_rect = QRect(0, 0, dst.width(), dst.height())
    if qt_mode is not None:
        p = QPainter(dst)
        p.setOpacity(opacity)
        p.setCompositionMode(qt_mode)
        p.drawImage(QPoint(0, 0), src, src_rect)
        p.end()
        return dst
    b = ops.qimage_to_rgba(dst).astype(np.float32) / 255
    s = ops.qimage_to_rgba(src.copy(src_rect)).astype(np.float32) / 255
    ab, as_ = b[..., 3], s[..., 3] * opacity
    cb, cs = b[..., :3], s[..., :3]
    if key == "pixelpickle:dissolve":
        noise = _dissolve_noise(as_.shape[0], as_.shape[1], origin.x(), origin.y())
        as_ = (noise < as_).astype(np.float32)
        B = cs
    else:
        B = _blend_fn(key, cb, cs)
    ao = as_ + ab * (1 - as_)
    co = (as_[..., None] * (1 - ab[..., None]) * cs + as_[..., None] * ab[..., None] * B
          + (1 - as_[..., None]) * ab[..., None] * cb) / np.maximum(ao[..., None], 1e-6)
    out = np.dstack([np.clip(co, 0, 1), ao]) * 255
    res = ops.rgba_to_qimage(np.rint(out))
    p = QPainter(dst)
    p.setCompositionMode(CM.CompositionMode_Source)
    p.drawImage(0, 0, res)
    p.end()
    return dst


UNDO_LIMIT = 60
BG_NAMES = {"Achtergrond", "Background"}  # the background layer, regardless of the language


def bg_name():
    from .i18n import tr
    return tr("Achtergrond")


def raster_name(n):
    from .i18n import tr
    return tr("Raster {}").format(n)


def new_image(w, h, color=None) -> QImage:
    img = QImage(w, h, FMT)
    img.fill(color if color is not None else Qt.GlobalColor.transparent)
    return img


def apply_region(dst: QImage, rect: QRect, new_local: QImage, mask: QImage | None):
    """Put new_local (size of rect) into dst at rect, only inside the mask."""
    if rect.isEmpty():
        return
    if mask is None:
        p = QPainter(dst)
        p.setCompositionMode(CM.CompositionMode_Source)
        p.drawImage(rect.topLeft(), new_local)
        p.end()
        return
    m = mask.copy(rect)
    s = QImage(new_local)
    p = QPainter(s)
    p.setCompositionMode(CM.CompositionMode_DestinationIn)
    p.drawImage(0, 0, m)
    p.end()
    d = dst.copy(rect)
    p = QPainter(d)
    p.setCompositionMode(CM.CompositionMode_DestinationOut)
    p.drawImage(0, 0, m)
    p.setCompositionMode(CM.CompositionMode_Plus)
    p.drawImage(0, 0, s)
    p.end()
    p = QPainter(dst)
    p.setCompositionMode(CM.CompositionMode_Source)
    p.drawImage(rect.topLeft(), d)
    p.end()


def paint_layer(layer, rect: QRect, new_local: QImage, mask: QImage | None):
    """Write pixels to a layer; respects 'transparantie vergrendelen' (lock transparency)."""
    if rect.isEmpty():
        return
    if getattr(layer, "lock_alpha", False):
        tmp = layer.image.copy(rect)
        p = QPainter(tmp)
        p.setCompositionMode(CM.CompositionMode_SourceAtop)
        p.drawImage(0, 0, new_local)
        p.end()
        new_local = tmp
    apply_region(layer.image, rect, new_local, mask)


class Layer:
    def __init__(self, name, image, opacity=1.0, visible=True, mode=0, lock_alpha=False):
        self.name = name
        self.image = image
        self.opacity = opacity
        self.visible = visible
        self.mode = mode
        self.lock_alpha = lock_alpha
        self.adjust = None      # adjustment layer: (effect cid, parameters); image is then the mask
        self.link_set = 0       # link set: layers with the same number move together
        self.highlight = None   # highlight color in the layers palette (QColor) or None
        self.kind = "raster"    # "raster", "group" (layer group) or "mask" (mask layer)
        self.group = None       # the group (header layer) this layer is in, or None
        self.collapsed = False  # group collapsed in the layers palette
        self.text = None        # editable text (see textlayer.py); image is then the rendering
        self.blend_ranges = None  # blend ranges: {channel: (this layer, underlying)}, see BLEND_CHANNELS
        self.vector = None      # vector layer: [object, ...] (see vectorlayer.py); image is then the rendering
        self.role = None        # "floating" (floating selection) or "seledit" (edit selection), otherwise None

    def clone(self):
        # QImage copy shares pixels until written to (copy on write)
        l = Layer(self.name, QImage(self.image), self.opacity, self.visible, self.mode, self.lock_alpha)
        l.adjust = (self.adjust[0], dict(self.adjust[1])) if self.adjust else None
        l.link_set = self.link_set
        l.highlight = QColor(self.highlight) if self.highlight is not None else None
        l.kind, l.collapsed, l.group = self.kind, self.collapsed, self.group
        from .textlayer import copy_text
        l.text = copy_text(self.text)
        l.blend_ranges = copy_ranges(self.blend_ranges)
        from .vectorlayer import copy_vector
        l.vector = copy_vector(self.vector)
        l.role = self.role
        return l


def clone_layers(layers):
    """Clone a layer list and make the group references point to the new copies."""
    clones = [l.clone() for l in layers]
    m = {id(o): c for o, c in zip(layers, clones)}
    for c in clones:
        c.group = m.get(id(c.group)) if c.group is not None else None
    return clones


# ---------------------------------------------------------------- blend ranges
# Two ranges per channel (this layer and the underlying layers), each four points a <= b <= c <= d (0..255):
# below a and above d the layer is invisible, between b and c fully visible, with a soft transition in
# between. All ranges are multiplied together.
BLEND_CHANNELS = ["Grijs", "Rood", "Groen", "Blauw"]
FULL_RANGE = (0, 0, 255, 255)


def copy_ranges(r):
    return None if r is None else {k: (tuple(a), tuple(b)) for k, (a, b) in r.items()}


def ranges_active(r):
    return bool(r) and any(tuple(a) != FULL_RANGE or tuple(b) != FULL_RANGE for a, b in r.values())


def _channel_values(rgb, ch):
    if ch == "Grijs":
        return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    return rgb[..., {"Rood": 0, "Groen": 1, "Blauw": 2}[ch]]


def range_weight(v, rng):
    """Visibility 0..1 for values v (0..255) according to range (a, b, c, d)."""
    a, b, c, d = (float(x) for x in rng)
    w = np.ones_like(v, dtype=np.float32)
    if a > 0 or b > 0:
        w = np.where(v < a, 0.0, w)
        w = np.where((v >= a) & (v < b), (v - a) / max(b - a, 1e-6), w)
    if c < 255 or d < 255:
        w = np.where(v > d, 0.0, w)
        w = np.where((v > c) & (v <= d), (d - v) / max(d - c, 1e-6), w)
    return w.astype(np.float32)


def apply_blend_ranges(src: QImage, under: QImage, ranges) -> QImage:
    """Make layer pixels (src) less opaque where they, or the underlying pixels (under, same
    size), fall outside the blend ranges."""
    if not ranges_active(ranges):
        return src
    s = ops.qimage_to_rgba(src).astype(np.float32)
    u = ops.qimage_to_rgba(under).astype(np.float32)
    w = np.ones(s.shape[:2], np.float32)
    for ch, (mine, below) in ranges.items():
        if tuple(mine) != FULL_RANGE:
            w *= range_weight(_channel_values(s[..., :3], ch), mine)
        if tuple(below) != FULL_RANGE:
            w *= range_weight(_channel_values(u[..., :3], ch), below)
    s[..., 3] *= w
    return ops.rgba_to_qimage(np.clip(np.rint(s), 0, 255))


def apply_mask(out: QImage, layer, r: QRect) -> QImage:
    """Mask layer: white shows, black hides what lies below it (within the same group)."""
    base = ops.qimage_to_rgba(out).astype(np.float32)
    m = ops.qimage_to_rgba(layer.image.copy(r)).astype(np.float32)
    lum = (m[..., 0] * 0.299 + m[..., 1] * 0.587 + m[..., 2] * 0.114) / 255 * (m[..., 3] / 255)
    k = 1 - layer.opacity * (1 - lum)
    base[..., 3] *= k
    return ops.rgba_to_qimage(np.clip(np.rint(base), 0, 255))


def apply_adjustment(out: QImage, layer, r: QRect) -> QImage:
    """Apply an adjustment layer's effect to what lies below it, through the layer's mask."""
    from .effects import REGISTRY, Ctx, load_all
    if not REGISTRY:
        load_all()
    cid, params = layer.adjust
    eff = REGISTRY.get(cid)
    if eff is None:
        return out
    base = ops.qimage_to_rgba(out).astype(np.float32)
    adj = eff.fn(base.astype(np.uint8), Ctx(), **params).astype(np.float32)
    m = ops.qimage_to_rgba(layer.image.copy(r)).astype(np.float32)
    mask = (m[..., 0] * 0.299 + m[..., 1] * 0.587 + m[..., 2] * 0.114) / 255 * (m[..., 3] / 255) * layer.opacity
    res = base + (adj - base) * mask[..., None]
    res[..., 3] = base[..., 3]
    return ops.rgba_to_qimage(np.clip(np.rint(res), 0, 255))


class Document(QObject):
    changed = Signal(QRect)        # image area changed (empty = all)
    structureChanged = Signal()    # layer list or properties
    selectionChanged = Signal()
    sizeChanged = Signal()
    historyChanged = Signal()
    titleChanged = Signal()

    _counter = 0

    def __init__(self, w, h, background: QColor | None = QColor(255, 255, 255)):
        super().__init__()
        self.w, self.h = w, h
        if background is not None:
            self.layers = [Layer(bg_name(), new_image(w, h, background))]
        else:
            self.layers = [Layer(raster_name(1), new_image(w, h))]
        self.active = 0
        self.sel: QImage | None = None
        self.sel_lines = []
        self.path = None
        Document._counter += 1
        from .i18n import tr
        self.untitled = tr("Afbeelding{}").format(Document._counter)
        self._modified = False
        self.undo_stack = []
        self.redo_stack = []
        self.raster_counter = 1
        self.px_per_pt = 1.0  # text in points: 72 dpi (derived from the resolution for .pspimage files)
        # alpha channels: saved selections and masks [(name, QImage)], same size as the canvas; the value
        # is in the alpha, so they rotate, scale and crop along with the same operations as layers
        self.channels = []
        self._vsel = ([], None)
        self.guides = {"h": [], "v": []}  # guide lines (document coordinates), dragged out of the rulers
        # selected vector objects (indices) and the layer they belong to

    # ------------------------------------------------------------ general
    def rect(self):
        return QRect(0, 0, self.w, self.h)

    def title(self):
        import os
        name = os.path.basename(self.path) if self.path else self.untitled
        return name + (" *" if self._modified else "")

    @property
    def modified(self):
        return self._modified

    def set_modified(self, v=True):
        if v != self._modified:
            self._modified = v
            self.titleChanged.emit()

    def layer(self) -> Layer:
        return self.layers[self.active]

    def next_raster_name(self):
        self.raster_counter += 1
        return raster_name(self.raster_counter)

    # ------------------------------------------------------------ history
    def snapshot(self):
        return dict(w=self.w, h=self.h, layers=clone_layers(self.layers),
                    active=self.active, sel=QImage(self.sel) if self.sel is not None else None,
                    sel_lines=list(self.sel_lines), channels=list(self.channels))

    def restore(self, s):
        size_changed = (s["w"], s["h"]) != (self.w, self.h)
        self.w, self.h = s["w"], s["h"]
        self.layers = clone_layers(s["layers"])
        self.active = min(s["active"], len(self.layers) - 1)
        self.sel = s["sel"]
        self.sel_lines = s["sel_lines"]
        self.channels = list(s.get("channels", []))
        if size_changed:
            self.sizeChanged.emit()
        self.structureChanged.emit()
        self.changed.emit(QRect())
        self.selectionChanged.emit()

    def push_undo(self, label):
        self.undo_stack.append((label, self.snapshot()))
        if len(self.undo_stack) > UNDO_LIMIT:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.set_modified(True)
        self.historyChanged.emit()

    def drop_last_undo(self):
        if self.undo_stack:
            self.undo_stack.pop()
            self.historyChanged.emit()

    def undo(self):
        if not self.undo_stack:
            return
        label, s = self.undo_stack.pop()
        self.redo_stack.append((label, self.snapshot()))
        self.restore(s)
        self.set_modified(True)
        self.historyChanged.emit()

    def jump_history(self, k):
        """Go to step k of the history (k = number of steps on the undo stack), in one go:
        only the final state is restored and everything is updated once, instead of after every step."""
        n = len(self.undo_stack)
        if k == n or k < 0 or k > n + len(self.redo_stack):
            return
        cur = self.snapshot()
        if k < n:  # undo: every intermediate state goes on the redo stack
            for _ in range(n - k):
                label, s = self.undo_stack.pop()
                self.redo_stack.append((label, cur))
                cur = s
        else:  # redo
            for _ in range(k - n):
                label, s = self.redo_stack.pop()
                self.undo_stack.append((label, cur))
                cur = s
        self.restore(cur)
        self.set_modified(True)
        self.historyChanged.emit()

    def redo(self):
        if not self.redo_stack:
            return
        label, s = self.redo_stack.pop()
        self.undo_stack.append((label, self.snapshot()))
        self.restore(s)
        self.set_modified(True)
        self.historyChanged.emit()

    # ------------------------------------------------------------ compositing
    def children(self, g, layers=None):
        """Direct children of group g (None = top level), from bottom to top."""
        L = self.layers if layers is None else layers
        ids = {id(x) for x in L}
        return [l for l in L if l.group is g or (g is None and l.group is not None and id(l.group) not in ids)]

    def subtree(self, l):
        """The layer itself plus (for a group) everything in it, in list order."""
        out = []
        for x in self.layers:
            p = x
            while p is not None:
                if p is l:
                    out.append(x)
                    break
                p = p.group
        return out

    def depth(self, l):
        d, p = 0, l.group
        while p is not None:
            d, p = d + 1, p.group
        return d

    def normalize(self):
        """Make sure the content of each group sits directly below the group header."""
        act = self.layers[self.active] if self.layers else None
        out = []

        def emit(g):
            for l in self.children(g):
                if l.kind == "group":
                    emit(l)
                out.append(l)
        emit(None)
        self.layers = out
        self.active = out.index(act) if act in out else max(0, len(out) - 1)

    def composite(self, rect: QRect | None = None, layers=None) -> QImage:
        r = self.rect() if rect is None or rect.isEmpty() else rect
        L = self.layers if layers is None else layers

        def comp(items):
            out = new_image(r.width(), r.height())
            for l in items:
                if not l.visible or l.opacity <= 0 or l.role == "seledit":  # edit selection: only as a red layer
                    continue
                if l.kind == "group":
                    buf = comp(self.children(l, L))
                    if ranges_active(l.blend_ranges):
                        buf = apply_blend_ranges(buf, out, l.blend_ranges)
                    blend_onto(out, buf, l.mode, l.opacity, None, r.topLeft())
                elif l.kind == "mask":
                    out = apply_mask(out, l, r)
                elif l.adjust is not None:
                    out = apply_adjustment(out, l, r)
                elif ranges_active(l.blend_ranges):
                    part = apply_blend_ranges(l.image.copy(r), out, l.blend_ranges)
                    blend_onto(out, part, l.mode, l.opacity, None, r.topLeft())
                else:
                    blend_onto(out, l.image, l.mode, l.opacity, r, r.topLeft())
            return out
        return comp(self.children(None, L))

    def flattened(self, background=None) -> QImage:
        img = self.composite()
        if background is not None:
            out = new_image(self.w, self.h, background)
            p = QPainter(out)
            p.drawImage(0, 0, img)
            p.end()
            return out
        return img

    # ------------------------------------------------------------ selection
    def set_selection(self, mask: QImage | None, lines=None):
        if mask is not None:
            arr = ops.qimage_to_mask(mask)
            if not arr.any():
                mask = None
            elif lines is None:
                lines = ops.mask_edges(arr)
        self.sel = mask
        self.sel_lines = lines if mask is not None else []
        self.selectionChanged.emit()

    def combine_selection(self, shape: QImage, mode="replace", feather=0):
        if feather > 0:
            arr = ops.qimage_to_mask(shape).astype(np.float32)
            arr = ops.box_blur(arr, int(feather))
            shape = ops.mask_to_qimage(np.clip(arr, 0, 255))
        if mode == "replace" or self.sel is None:
            if mode == "sub":
                return
            self.set_selection(shape)
            return
        m = QImage(self.sel)
        p = QPainter(m)
        p.setCompositionMode(CM.CompositionMode_SourceOver if mode == "add"
                             else CM.CompositionMode_DestinationOut)
        p.drawImage(0, 0, shape)
        p.end()
        self.set_selection(m)

    def selection_bbox(self) -> QRect:
        if self.sel is None:
            return self.rect()
        return ops.mask_bbox(ops.qimage_to_mask(self.sel) > 0)

    def select_all(self):
        m = QImage(self.w, self.h, QImage.Format.Format_Alpha8)
        m.fill(QColor(0, 0, 0, 255))
        self.set_selection(m)

    def invert_selection(self):
        if self.sel is None:
            return
        arr = 255 - ops.qimage_to_mask(self.sel)
        self.set_selection(ops.mask_to_qimage(arr))

    # ------------------------------------------------------------ layers
    def add_layer(self, layer=None, index=None, label="Nieuwe rasterlaag"):
        self.push_undo(label)
        if layer is None:
            layer = Layer(self.next_raster_name(), new_image(self.w, self.h))
        act = self.layer()
        if index is None:
            # new layer above the active one, in the same group (inside a group if the header is active)
            layer.group = act if act.kind == "group" else act.group
            idx = self.active if act.kind == "group" else self.active + 1
        else:
            idx = index
        self.layers.insert(idx, layer)
        self.active = idx
        self.normalize()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def duplicate_layer(self):
        src = self.subtree(self.layer())
        clones = clone_layers(src)
        m = {id(o): c for o, c in zip(src, clones)}
        top = clones[-1]
        top.group = self.layer().group
        for o, c in zip(src, clones):
            if o.group is not None and id(o.group) in m:
                c.group = m[id(o.group)]
        top.name = "Kopie van " + top.name
        self.push_undo("Laag dupliceren")
        i = self.active + 1
        for c in clones:
            self.layers.insert(i, c)
            i += 1
        self.active = self.layers.index(top)
        self.normalize()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def delete_layer(self):
        gone = self.subtree(self.layer())
        if not any(l.kind == "raster" for l in self.layers if l not in gone):
            return  # at least one regular layer must always remain
        self.push_undo("Laag verwijderen")
        first = self.layers.index(gone[0])
        self.layers = [l for l in self.layers if l not in gone]
        self.active = max(0, min(first, len(self.layers)) - 1) if first > 0 else 0
        self.normalize()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def move_layer(self, delta, label="Laag verplaatsen"):
        """Move the active layer (with content, for a group) among the layers of the same level.
        delta may be larger than 1; it is clamped to the top or bottom."""
        act = self.layer()
        sib = self.children(act.group)
        i = sib.index(act)
        j = max(0, min(len(sib) - 1, i + delta))
        if j == i:
            return
        self.push_undo(label)
        sib.insert(j, sib.pop(i))
        rank = {id(l): k for k, l in enumerate(sib)}
        # reorder by putting the siblings back in their new order
        order = []
        for l in self.layers:
            if id(l) in rank:
                continue
            order.append(l)
        pos = min(self.layers.index(s_) for s_ in sib)
        for l in sib:
            order.insert(pos, l)
            pos += 1
        self.layers = order
        self.active = self.layers.index(act)
        self.normalize()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def merge_down(self):
        act = self.layer()
        sib = self.children(act.group)
        i = sib.index(act)
        if i == 0 or act.kind == "group" or sib[i - 1].kind == "group":
            return
        up, low = act, sib[i - 1]
        if low.adjust is not None or low.kind == "mask":
            return
        self.push_undo("Omlaag samenvoegen")
        img = QImage(low.image)
        if up.visible:
            if up.adjust is not None:
                img = apply_adjustment(img, up, self.rect())
            elif up.kind == "mask":
                img = apply_mask(img, up, self.rect())
            else:
                blend_onto(img, apply_blend_ranges(up.image, img, up.blend_ranges), up.mode, up.opacity)
        low.image = img
        self.layers.remove(up)
        self.active = self.layers.index(low)
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def ancestors(self, l):
        """The groups that layer l is in (directly or indirectly)."""
        out, g = [], l.group
        while g is not None:
            out.append(g)
            g = g.group
        return out

    def layer_view(self, how):
        """Layers > View: which layers are visible.
        current: only the active layer (with the groups around it and, for a group, everything in it);
        all / none: all layers on or off; invert: every layer inverted (groups stay on, so that
        inverted layers in them can be seen); link_show / link_hide: show or hide the link set of the
        active layer (without a link set: only the active layer)."""
        act = self.layer()
        if how == "current":
            keep = set(map(id, self.subtree(act) + self.ancestors(act)))
            new = {id(l): id(l) in keep for l in self.layers}
        elif how in ("all", "none"):
            new = {id(l): how == "all" for l in self.layers}
        elif how == "invert":
            new = {id(l): True if l.kind == "group" else not l.visible for l in self.layers}
        else:
            members = [l for l in self.layers if act.link_set and l.link_set == act.link_set] or [act]
            vis = how == "link_show"
            new = {id(l): l.visible for l in self.layers}
            for l in members:
                new[id(l)] = vis
                if vis:  # showing: also turn on the groups around it
                    for g in self.ancestors(l):
                        new[id(g)] = True
        if all(l.visible == new[id(l)] for l in self.layers):
            return False
        self.push_undo({"current": "Alleen huidige laag", "all": "Alle lagen", "none": "Geen lagen",
                        "invert": "Zichtbaarheid omkeren", "link_show": "Koppelingset weergeven",
                        "link_hide": "Koppelingset verbergen"}[how])
        for l in self.layers:
            l.visible = new[id(l)]
        self.changed.emit(QRect())
        self.structureChanged.emit()
        return True

    def merge_visible(self):
        vis = [l for l in self.layers if l.visible and l.kind != "group"]
        if len(vis) < 2:
            return
        self.push_undo("Zichtbare samenvoegen")
        merged = Layer("Samengevoegd", self.composite())
        keep = [l for l in self.layers if not l.visible]
        self.layers = keep + [merged]
        for l in self.layers:
            if l.group is not None and l.group not in self.layers:
                l.group = None
        self.active = len(self.layers) - 1
        self.normalize()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def flatten(self, background=QColor(255, 255, 255)):
        self.push_undo("Alle lagen samenvoegen")
        self.layers = [Layer(bg_name(), self.flattened(background))]
        self.active = 0
        self.structureChanged.emit()
        self.changed.emit(QRect())

    # ------------------------------------------------------------ groups and masks
    def _wrap_in_group(self, layer, name):
        g = Layer(name, new_image(self.w, self.h))
        g.kind = "group"
        g.group = layer.group
        layer.group = g
        self.layers.insert(self.layers.index(layer) + 1, g)
        return g

    def new_group(self):
        act = self.layer()
        self.push_undo("Nieuwe lagengroep")
        if act.name in BG_NAMES and act.group is None and self.layers.index(act) == 0:
            act.name = self.next_raster_name()
        g = self._wrap_in_group(act, f"Groep - {act.name}")
        self.active = self.layers.index(g)
        self.normalize()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def ungroup(self):
        act = self.layer()
        g = act if act.kind == "group" else act.group
        if g is None:
            return
        self.push_undo("Groepering van lagen opheffen")
        for l in self.children(g):
            l.group = g.group
        self.layers.remove(g)
        self.active = min(self.active, len(self.layers) - 1)
        self.normalize()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def merge_group(self):
        act = self.layer()
        g = act if act.kind == "group" else act.group
        if g is None:
            return
        self.push_undo("Groep samenvoegen")
        members = self.subtree(g)
        img = self.composite(None, members)
        merged = Layer(g.name, img)
        merged.group = g.group
        idx = self.layers.index(g)
        self.layers[idx] = merged
        self.layers = [l for l in self.layers if l not in members or l is merged]
        self.active = self.layers.index(merged)
        self.normalize()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def move_into_group(self):
        """Layers > Arrange > Put in group: in the group directly above or below the layer."""
        act = self.layer()
        sib = self.children(act.group)
        i = sib.index(act)
        target = next((x for x in (sib[i + 1] if i + 1 < len(sib) else None, sib[i - 1] if i > 0 else None)
                       if x is not None and x.kind == "group"), None)
        if target is None:
            return
        self.push_undo("In groep zetten")
        act.group = target
        self.normalize()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def move_out_of_group(self):
        act = self.layer()
        if act.group is None:
            return
        self.push_undo("Uit groep verwijderen")
        g = act.group
        act.group = g.group
        self.layers.remove(act)
        self.layers.insert(self.layers.index(g) + 1, act)
        self.active = self.layers.index(act)
        self.normalize()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def mask_image(self, source, invert=False):
        """Make a grayscale mask: show_all, hide_all, show_sel, hide_sel, luminance, alpha."""
        if source in ("show_all", "hide_all"):
            return new_image(self.w, self.h, QColor(255, 255, 255) if source == "show_all" else QColor(0, 0, 0))
        if source in ("show_sel", "hide_sel"):
            m = ops.qimage_to_mask(self.sel) if self.sel is not None else np.zeros((self.h, self.w), np.uint8)
            v = m if source == "show_sel" else 255 - m
        else:
            a = ops.qimage_to_rgba(self.composite(None, [l for l in self.layers if l.kind == "raster" and l.adjust is None])
                                   if source == "luminance" else self.layer().image)
            v = (a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114) if source == "luminance" else a[..., 3]
            v = v.astype(np.uint8)
        if invert:
            v = 255 - v
        g = np.dstack([v, v, v, np.full_like(v, 255)])
        return ops.rgba_to_qimage(g)

    def add_mask(self, source, invert=False):
        act = self.layer()
        if act.kind == "mask":
            return
        self.push_undo("Nieuwe maskerlaag")
        if act.kind == "group":
            target_group = act
        else:
            if act.name in BG_NAMES and act.group is None and self.layers.index(act) == 0:
                act.name = self.next_raster_name()
            target_group = self._wrap_in_group(act, f"Groep - {act.name}")
        mask = Layer("Masker - " + (act.name if act.kind != "group" else act.name.replace("Groep - ", "")),
                     self.mask_image(source, invert))
        mask.kind = "mask"
        mask.group = target_group
        self.layers.insert(self.layers.index(target_group), mask)
        self.normalize()
        self.active = self.layers.index(mask)
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def invert_mask(self):
        l = self.layer()
        if l.kind != "mask" and l.adjust is None:
            return
        self.push_undo("Masker/aanpassing omkeren")
        a = ops.qimage_to_rgba(l.image)
        a[..., :3] = 255 - a[..., :3]
        l.image = ops.rgba_to_qimage(a)
        self.structureChanged.emit()
        self.changed.emit(QRect())

    # ------------------------------------------------------------ selected vector objects
    @property
    def vsel(self):
        """Indices of the selected objects on the active vector layer (in selection order)."""
        sel, layer = self._vsel
        lay = self.layer()
        if layer is not lay or lay.vector is None:
            return []
        return [i for i in sel if 0 <= i < len(lay.vector)]

    @vsel.setter
    def vsel(self, sel):
        self._vsel = (list(sel), self.layer())
        self.selectionChanged.emit()

    # ------------------------------------------------------------ floating selection
    def floating_layer(self):
        return next((l for l in self.layers if l.role == "floating"), None)

    def float_selection(self, fill_bg: QColor | None = None):
        """Floating: the selected pixels go to a layer of their own above the active layer; on the layer itself
        a hole remains (filled with the background color on the background layer)."""
        src = self.layer()
        if self.sel is None or src.kind != "raster" or src.adjust is not None or self.floating_layer() is not None:
            return False
        self.push_undo("Zwevend")
        piece = QImage(src.image)
        p = QPainter(piece)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p.drawImage(0, 0, self.sel)
        p.end()
        hole = QImage(src.image)
        p = QPainter(hole)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        p.drawImage(0, 0, self.sel)
        if fill_bg is not None and self.layers.index(src) == 0 and src.name in BG_NAMES:
            bg = new_image(self.w, self.h, fill_bg)
            q = QPainter(bg)
            q.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            q.drawImage(0, 0, self.sel)
            q.end()
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOver)
            p.drawImage(0, 0, bg)
        p.end()
        src.image = hole
        from .i18n import tr
        fl = Layer(tr("Zwevende selectie"), piece)
        fl.role = "floating"
        fl.group = src.group
        self.layers.insert(self.layers.index(src) + 1, fl)
        self.active = self.layers.index(fl)
        self.structureChanged.emit()
        self.changed.emit(QRect())
        return True

    def defloat_selection(self):
        """Not floating: the floating selection becomes part of the layer below it again."""
        fl = self.floating_layer()
        if fl is None:
            return False
        i = self.layers.index(fl)
        below = next((l for l in reversed(self.layers[:i]) if l.kind == "raster" and l.adjust is None
                      and l.group is fl.group), None)
        self.push_undo("Niet-zwevend")
        if below is None:  # no layer below: the floating layer becomes a regular layer
            fl.role = None
        else:
            img = QImage(below.image)
            p = QPainter(img)
            p.setOpacity(fl.opacity)
            p.drawImage(0, 0, fl.image)
            p.end()
            below.image = img
            self.layers.remove(fl)
            self.active = self.layers.index(below)
        self.structureChanged.emit()
        self.changed.emit(QRect())
        return True

    # ------------------------------------------------------------ edit selection
    def seledit_layer(self):
        return next((l for l in self.layers if l.role == "seledit"), None)

    def toggle_selection_edit(self):
        """Edit selection: the selection becomes a gray layer (white = selected) that you update with the
        brushes, paint bucket and other tools; unselected areas are shown in red.
        Choosing it again turns it back into a selection."""
        from .i18n import tr
        lay = self.seledit_layer()
        if lay is None:
            self.push_undo("Selectie bewerken")
            arr = ops.qimage_to_mask(self.sel) if self.sel is not None else np.zeros((self.h, self.w), np.uint8)
            a = np.dstack([arr, arr, arr, np.full_like(arr, 255)])
            lay = Layer(tr("Selectie bewerken"), ops.rgba_to_qimage(a))
            lay.role = "seledit"
            self.layers.append(lay)
            self.active = len(self.layers) - 1
            self.set_selection(None)
        else:
            self.push_undo("Selectie bewerken")
            a = ops.qimage_to_rgba(lay.image).astype(np.float32)
            v = (a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114) * a[..., 3] / 255
            i = self.layers.index(lay)
            self.layers.remove(lay)
            self.active = max(0, min(i - 1, len(self.layers) - 1))
            self.set_selection(ops.mask_to_qimage(np.clip(v, 0, 255).astype(np.uint8)))
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def selection_from_vectors(self, layer=None, indices=None):
        """Selection from vector objects (the selected objects, or all on the vector layer): fill and line."""
        from . import vectorlayer as V
        layer = layer or self.layer()
        if layer.vector is None:
            return False
        objs = [layer.vector[i] for i in indices] if indices else list(layer.vector)
        if not objs:
            return False
        m = QImage(self.w, self.h, QImage.Format.Format_Alpha8)
        m.fill(QColor(0, 0, 0, 0))
        p = QPainter(m)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for o in objs:
            path = V.qpath(o)
            if V.is_closed(o):
                p.fillPath(path, QColor(0, 0, 0, 255))
            if o.get("stroke") is not None and o["width"] > 0:
                p.strokePath(path, QPen(QColor(0, 0, 0, 255), o["width"]))
        p.end()
        self.push_undo("Vanuit vectorobject")
        self.set_selection(m)
        return True

    def apply_selection_array(self, arr, label):
        """New selection from a mask (0..255) with one undo step."""
        self.push_undo(label)
        self.set_selection(ops.mask_to_qimage(np.ascontiguousarray(np.clip(arr, 0, 255).astype(np.uint8))))

    # ------------------------------------------------------------ alpha channels
    @staticmethod
    def _channel_image(arr):
        """Grayscale (uint8, 0..255) as a channel image: white with the value as alpha."""
        a = np.zeros(arr.shape + (4,), np.uint8)
        a[..., :3] = 255
        a[..., 3] = arr
        return ops.rgba_to_qimage(a)

    def channel_mask(self, i) -> np.ndarray:
        return ops.qimage_to_rgba(self.channels[i][1])[..., 3].copy()

    def channel_names(self):
        return [n for n, _ in self.channels]

    def store_channel(self, name, arr, label):
        """Save a channel; an existing channel with the same name is overwritten."""
        self.push_undo(label)
        img = self._channel_image(np.ascontiguousarray(arr, dtype=np.uint8))
        names = self.channel_names()
        if name in names:
            self.channels[names.index(name)] = (name, img)
        else:
            self.channels.append((name, img))
        self.structureChanged.emit()

    def delete_channels(self, indices):
        if not indices:
            return
        self.push_undo("Alfakanaal verwijderen")
        self.channels = [c for i, c in enumerate(self.channels) if i not in set(indices)]
        self.structureChanged.emit()

    def mask_values(self, l=None) -> np.ndarray:
        """Values (0..255) of a mask layer: brightness times opacity."""
        l = l or self.layer()
        a = ops.qimage_to_rgba(l.image).astype(np.float32)
        return np.clip((a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114) * a[..., 3] / 255, 0, 255
                       ).astype(np.uint8)

    def selection_from_channel(self, i, mode="replace", invert=False):
        arr = self.channel_mask(i)
        if invert:
            arr = 255 - arr
        self.push_undo("Selectie laden uit alfakanaal")
        self.combine_selection(ops.mask_to_qimage(arr), mode)

    def mask_from_channel(self, i, invert=False):
        """New mask layer on the active layer, with the channel as content (white = visible)."""
        if self.layer().kind == "mask":
            return False
        arr = self.channel_mask(i)
        if invert:
            arr = 255 - arr
        self.add_mask("show_all")
        self.undo_stack[-1] = ("Masker laden uit alfakanaal", self.undo_stack[-1][1])
        a = np.zeros(arr.shape + (4,), np.uint8)
        a[..., 0] = a[..., 1] = a[..., 2] = arr
        a[..., 3] = 255
        self.layer().image = ops.rgba_to_qimage(a)
        self.structureChanged.emit()
        self.changed.emit(QRect())
        return True

    def selection_from_mask(self):
        l = self.layer()
        if l.kind != "mask" and l.adjust is None:
            return
        v = self.mask_values(l)
        self.push_undo("Selectie vanuit masker")
        self.set_selection(ops.mask_to_qimage(v))

    # ------------------------------------------------------------ geometry
    def render_text(self, layer):
        from .textlayer import render
        layer.image = render(layer.text, self.w, self.h, self.px_per_pt)

    def render_vector(self, layer):
        from .vectorlayer import render
        layer.image = render(layer.vector or [], self.w, self.h)

    def new_vector_layer(self, name=None, undo=True):
        """New, empty vector layer above the active layer (in the same group)."""
        from .i18n import tr
        n = sum(1 for l in self.layers if l.vector is not None) + 1
        lay = Layer(name or tr("Vector {}").format(n), new_image(self.w, self.h))
        lay.vector = []
        if undo:
            self.add_layer(lay, label="Nieuwe vectorlaag")
        else:
            act = self.layer()
            lay.group = act if act.kind == "group" else act.group
            idx = self.active if act.kind == "group" else self.active + 1
            self.layers.insert(idx, lay)
            self.active = idx
            self.normalize()
            self.structureChanged.emit()
        return lay

    def _move_text(self, tmap: QTransform, layers=None):
        """Move text and vector layers along with a geometric operation, so that they stay editable."""
        from .textlayer import set_transform, transform
        from . import vectorlayer
        for l in (layers if layers is not None else self.layers):
            if l.text is not None:
                set_transform(l.text, transform(l.text) * tmap)
                self.render_text(l)
            elif l.vector is not None:
                vectorlayer.transform(l.vector, tmap)
                self.render_vector(l)

    def _transform_all(self, fn, sel_fn, w, h, label, tmap=None):
        self.push_undo(label)
        for l in self.layers:
            l.image = fn(l.image)
        self.channels = [(n, fn(im)) for n, im in self.channels]
        self.w, self.h = w, h
        if tmap is not None:
            self._move_text(tmap)
        if self.sel is not None and sel_fn is not None:
            self.set_selection(ops.mask_to_qimage(sel_fn(ops.qimage_to_mask(self.sel))))
        else:
            self.set_selection(None)
        self.sizeChanged.emit()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def resize_image(self, w, h, smooth=True):
        mode = Qt.TransformationMode.SmoothTransformation if smooth else Qt.TransformationMode.FastTransformation
        self._transform_all(lambda im: im.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, mode),
                            None, w, h, "Formaat wijzigen", QTransform.fromScale(w / self.w, h / self.h))

    def canvas_size(self, w, h, ox, oy, fill: QColor):
        def fn_for(layer_is_bg):
            def fn(im):
                out = new_image(w, h, fill if layer_is_bg else None)
                p = QPainter(out)
                p.drawImage(ox, oy, im)
                p.end()
                return out
            return fn
        self.push_undo("Canvasgrootte")
        for i, l in enumerate(self.layers):
            l.image = fn_for(i == 0 and l.name in BG_NAMES)(l.image)
        self.channels = [(n, fn_for(False)(im)) for n, im in self.channels]
        self.w, self.h = w, h
        self._move_text(QTransform.fromTranslate(ox, oy))
        self.set_selection(None)
        self.sizeChanged.emit()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def crop(self, r: QRect):
        r = r.intersected(self.rect())
        if r.isEmpty():
            return
        self._transform_all(lambda im: im.copy(r), None, r.width(), r.height(), "Bijsnijden",
                            QTransform.fromTranslate(-r.x(), -r.y()))

    def rotate(self, degrees):
        t = QTransform().rotate(degrees)
        k = {90: -1, -90: 1, 180: 2}[degrees]
        w, h = (self.h, self.w) if degrees in (90, -90) else (self.w, self.h)
        self._transform_all(lambda im: im.transformed(t), lambda a: np.rot90(a, k), w, h, "Roteren",
                            QImage.trueMatrix(t, self.w, self.h))

    def mirror_layer(self, horizontal=True):
        if self.sel is not None and self.layer().text is None and self.layer().vector is None \
                and self.layer().kind != "group":
            return self._mirror_selection(horizontal)
        # without a selection: around the center of the layer content (a lone shape stays in place);
        # for a full layer that is simply the center of the image. A layer group flips as a whole
        # around the center of the content of all layers in it.
        layer = self.layer()
        targets = [l for l in self.subtree(layer) if l.kind != "group"] if layer.kind == "group" else [layer]
        box = QRectF()
        for l in targets:
            if l.text is not None:
                from .textlayer import bounds
                b = bounds(l.text, self.px_per_pt)
            elif l.vector is not None:
                from .vectorlayer import bounds as vbounds
                b = vbounds(l.vector)
            elif l.adjust is None and l.kind == "raster":
                b = QRectF(ops.mask_bbox(ops.qimage_to_rgba(l.image)[..., 3] > 0))
            else:
                continue
            if not b.isEmpty():
                box = box.united(b)
        if box.isEmpty():
            box = QRectF(self.rect())
        self.push_undo("Spiegelen" if horizontal else "Omdraaien")
        c = box.center()
        m = QTransform(-1, 0, 0, 1, 2 * c.x(), 0) if horizontal else QTransform(1, 0, 0, -1, 0, 2 * c.y())
        for l in targets:
            if l.text is not None or l.vector is not None:
                self._move_text(m, [l])
                continue
            out = new_image(self.w, self.h)
            p = QPainter(out)
            p.setTransform(m)
            p.drawImage(0, 0, l.image)
            p.end()
            l.image = out
        self.changed.emit(QRect())
        self.structureChanged.emit()

    def _mirror_selection(self, horizontal):
        """Mirror/flip with a selection: the selected pixels flip in place, within the frame of the
        selection, and the selection frame flips along."""
        r = self.selection_bbox()
        if r.isEmpty():
            return
        self.push_undo("Spiegelen" if horizontal else "Omdraaien")
        layer = self.layer()
        src = layer.image
        piece = QImage(src)
        p = QPainter(piece)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p.drawImage(0, 0, self.sel)
        p.end()
        out = QImage(src)
        p = QPainter(out)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        p.drawImage(0, 0, self.sel)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        flip = (lambda im: im.flipped(Qt.Orientation.Horizontal if horizontal else Qt.Orientation.Vertical)) \
            if hasattr(QImage, "flipped") else (lambda im: im.mirrored(horizontal, not horizontal))
        p.drawImage(r.topLeft(), flip(piece.copy(r)))
        p.end()
        layer.image = out
        m = QImage(self.w, self.h, QImage.Format.Format_Alpha8)
        m.fill(QColor(0, 0, 0, 0))
        p = QPainter(m)
        p.drawImage(r.topLeft(), flip(self.sel.copy(r)))
        p.end()
        t = QTransform(-1, 0, 0, 1, 2 * r.x() + r.width(), 0) if horizontal \
            else QTransform(1, 0, 0, -1, 0, 2 * r.y() + r.height())
        self.set_selection(m, [t.map(l) for l in self.sel_lines])
        self.changed.emit(r)
        self.structureChanged.emit()

    # ------------------------------------------------------------ pixel filters
    def effect_targets(self):
        """Layers an adjustment or effect works on: the active layer, or for a layer group every raster layer
        in it (text, vector and adjustment layers in the group are skipped)."""
        act = self.layer()
        if act.kind != "group":
            return [act]
        return [l for l in self.subtree(act) if l.kind == "raster" and l.adjust is None and l.text is None
                and l.vector is None and l.role is None]

    def apply_to_layer(self, fn, label, base: QImage | None = None, push=True):
        """Apply fn(rgba)->rgba to the active layer (or every raster layer of an active group), within the selection."""
        targets = [self.layer()] if base is not None else self.effect_targets()
        r = self.selection_bbox() if self.sel is not None else self.rect()
        if r.isEmpty() or not targets:
            return
        outs = []
        for layer in targets:
            src = base if base is not None else layer.image
            result = ops.rgba_to_qimage(fn(ops.qimage_to_rgba(src.copy(r))))
            out = QImage(src)
            apply_region(out, r, result, self.sel)
            outs.append(out)
        if push:
            self.push_undo(label)
        for layer, out in zip(targets, outs):
            layer.image = out
        self.changed.emit(r)
        self.structureChanged.emit()

    # ------------------------------------------------------------ extensions
    def rotate_free(self, degrees, crop=False, fill: QColor | None = None):
        import math
        t = QTransform().rotate(degrees)
        tmap = QImage.trueMatrix(t, self.w, self.h)
        mode = Qt.TransformationMode.SmoothTransformation
        self.push_undo("Vrij roteren")
        for i, l in enumerate(self.layers):
            out = l.image.transformed(t, mode)
            if fill is not None and i == 0 and l.name in BG_NAMES:
                bg = new_image(out.width(), out.height(), fill)
                p = QPainter(bg)
                p.drawImage(0, 0, out)
                p.end()
                out = bg
            l.image = out
        self.channels = [(n, im.transformed(t, mode)) for n, im in self.channels]
        nw, nh = self.layers[0].image.width(), self.layers[0].image.height()
        if crop:
            a = math.radians(degrees)
            w, h = self.w, self.h
            long_, short = (w, h) if w >= h else (h, w)
            s, c = abs(math.sin(a)), abs(math.cos(a))
            if short <= 2 * s * c * long_ or abs(s - c) < 1e-10:
                x = 0.5 * short
                wr, hr = (x / s, x / c) if w >= h else (x / c, x / s)
            else:
                c2 = c * c - s * s
                wr, hr = (w * c - h * s) / c2, (h * c - w * s) / c2
            wr, hr = int(wr), int(hr)
            r = QRect((nw - wr) // 2, (nh - hr) // 2, wr, hr)
            for l in self.layers:
                l.image = l.image.copy(r)
            self.channels = [(n, im.copy(r)) for n, im in self.channels]
            nw, nh = wr, hr
            tmap = tmap * QTransform.fromTranslate(-r.x(), -r.y())
        self.w, self.h = nw, nh
        self._move_text(tmap)
        self.set_selection(None)
        self.sizeChanged.emit()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def perspective(self, quad, crop=False, fill: QColor | None = None):
        """Perspective correction: the quadrilateral quad (4 points: top left, top right, bottom right,
        bottom left) becomes a rectangle. Without cropping the image size stays the same
        and everything is stretched along; with cropping only the straightened rectangle remains."""
        import math
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QPolygonF
        tl, tr, br, bl = quad
        dist = lambda a, b: math.hypot(a.x() - b.x(), a.y() - b.y())
        tw = max(1.0, (dist(tl, tr) + dist(bl, br)) / 2)
        th = max(1.0, (dist(tl, bl) + dist(tr, br)) / 2)
        cx = sum(q.x() for q in quad) / 4
        cy = sum(q.y() for q in quad) / 4
        if crop:
            x0, y0 = 0.0, 0.0
            nw, nh = int(round(tw)), int(round(th))
        else:
            x0, y0 = cx - tw / 2, cy - th / 2
            nw, nh = self.w, self.h
        target = QPolygonF([QPointF(x0, y0), QPointF(x0 + tw, y0), QPointF(x0 + tw, y0 + th), QPointF(x0, y0 + th)])
        t = QTransform()
        if not QTransform.quadToQuad(QPolygonF(list(quad)), target, t):
            return False
        self.push_undo("Perspectiefcorrectie")
        for i, l in enumerate(self.layers):
            bg = fill is not None and i == 0 and l.name in BG_NAMES
            out = new_image(nw, nh, fill if bg else None)
            p = QPainter(out)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setTransform(t)
            p.drawImage(0, 0, l.image)
            p.end()
            l.image = out
            l.text = None  # text and vectors become a regular (distorted) raster layer
            l.vector = None
        chans = []
        for n, im in self.channels:
            out = new_image(nw, nh)
            p = QPainter(out)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.setTransform(t)
            p.drawImage(0, 0, im)
            p.end()
            chans.append((n, out))
        self.channels = chans
        self.w, self.h = nw, nh
        self.set_selection(None)
        self.sizeChanged.emit()
        self.structureChanged.emit()
        self.changed.emit(QRect())
        return True

    def add_borders(self, left, top, right, bottom, color: QColor):
        self.canvas_size(self.w + left + right, self.h + top + bottom, left, top, color)
        self.undo_stack[-1] = ("Randen toevoegen", self.undo_stack[-1][1])

    def arrange_layer(self, where):
        n = len(self.layers)
        self.move_layer(n if where == "top" else -n, "Schikken")

    def promote_background(self):
        l = self.layers[0]
        if l.name not in BG_NAMES:
            return
        self.push_undo("Laag maken van achtergrondlaag")
        l.name = self.next_raster_name()
        self.structureChanged.emit()

    def promote_selection(self):
        if self.sel is None:
            return
        img = QImage(self.layer().image)
        p = QPainter(img)
        p.setCompositionMode(CM.CompositionMode_DestinationIn)
        p.drawImage(0, 0, self.sel)
        p.end()
        self.add_layer(Layer("Laag gemaakt van selectie", img), label="Laag maken van selectie")

    def modify_selection(self, kind, amount):
        if self.sel is None:
            return
        arr = ops.qimage_to_mask(self.sel).astype(np.float32)
        n = int(amount)
        if kind == "feather":
            arr = ops.box_blur(arr, n)
        else:
            b = arr > 127
            if kind == "contract":
                b = ~b
            for _ in range(n):  # dilation, 1 pixel per step
                nb = b.copy()
                nb[1:] |= b[:-1]
                nb[:-1] |= b[1:]
                nb[:, 1:] |= b[:, :-1]
                nb[:, :-1] |= b[:, 1:]
                b = nb
            if kind == "contract":
                b = ~b
            arr = b * 255.0
        self.push_undo({"feather": "Doezelen", "expand": "Uitbreiden", "contract": "Inkrimpen"}[kind])
        self.set_selection(ops.mask_to_qimage(np.clip(arr, 0, 255)))
