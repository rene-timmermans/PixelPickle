"""Documentmodel: lagen, selectie en geschiedenis (ongedaan maken)."""
import numpy as np
from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QTransform

from . import imageops as ops

FMT = ops.FMT
CM = QPainter.CompositionMode

# Mengmodi in exact dezelfde volgorde als PSP XI. (Nederlandse naam, Qt modus of None = NumPy, OpenRaster naam)
BLEND_MODES = [
    ("Normaal", CM.CompositionMode_SourceOver, "svg:src-over"),
    ("Donkerder", CM.CompositionMode_Darken, "svg:darken"),
    ("Lichter", CM.CompositionMode_Lighten, "svg:lighten"),
    ("Kleurtoon", None, "svg:hue"),
    ("Kleurtoon (oud)", None, "brushwork:hue-legacy"),
    ("Verzadiging", None, "svg:saturation"),
    ("Verzadiging (oud)", None, "brushwork:saturation-legacy"),
    ("Kleur", None, "svg:color"),
    ("Kleur (oud)", None, "brushwork:color-legacy"),
    ("Luminantie", None, "svg:luminosity"),
    ("Luminantie (oud)", None, "brushwork:luminosity-legacy"),
    ("Vermenigvuldigen", CM.CompositionMode_Multiply, "svg:multiply"),
    ("Scherm", CM.CompositionMode_Screen, "svg:screen"),
    ("Oplossen", None, "brushwork:dissolve"),
    ("Bedekken", CM.CompositionMode_Overlay, "svg:overlay"),
    ("Hard licht", CM.CompositionMode_HardLight, "svg:hard-light"),
    ("Zacht licht", CM.CompositionMode_SoftLight, "svg:soft-light"),
    ("Verschil", CM.CompositionMode_Difference, "svg:difference"),
    ("Tegenhouden", CM.CompositionMode_ColorDodge, "svg:color-dodge"),
    ("Doordrukken", CM.CompositionMode_ColorBurn, "svg:color-burn"),
    ("Uitsluiting", CM.CompositionMode_Exclusion, "svg:exclusion"),
]
# Gereedschappen hebben er in PSP nog één extra: alleen schilderen waar de laag transparant is
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
    """Niet-scheidbare mengfuncties. cb = onderlaag, cs = bovenlaag, waarden 0..1."""
    if key.endswith("-legacy"):  # oude PSP methode: HSL componenten vervangen
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
    """Meng src (of het deel src_rect daarvan) over dst; geeft het resultaat terug (dst wordt aangepast).
    origin: positie van dst in documentcoördinaten (voor 'Oplossen')."""
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
    if key == "brushwork:dissolve":
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


def new_image(w, h, color=None) -> QImage:
    img = QImage(w, h, FMT)
    img.fill(color if color is not None else Qt.GlobalColor.transparent)
    return img


def apply_region(dst: QImage, rect: QRect, new_local: QImage, mask: QImage | None):
    """Zet new_local (formaat van rect) in dst op rect, alleen binnen het masker."""
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
    """Schrijf pixels naar een laag; respecteert 'transparantie vergrendelen'."""
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
        self.adjust = None      # aanpassingslaag: (effect cid, parameters); image is dan het masker
        self.link_set = 0       # koppelingsset: lagen met hetzelfde nummer bewegen samen
        self.highlight = None   # markeerkleur in het lagenpalet (QColor) of None
        self.kind = "raster"    # "raster", "group" (lagengroep) of "mask" (maskerlaag)
        self.group = None       # de groep (kop-laag) waar deze laag in zit, of None
        self.collapsed = False  # groep ingeklapt in het lagenpalet
        self.text = None        # bewerkbare tekst (zie textlayer.py); image is dan de weergave

    def clone(self):
        # QImage kopie deelt pixels tot er geschreven wordt (copy on write)
        l = Layer(self.name, QImage(self.image), self.opacity, self.visible, self.mode, self.lock_alpha)
        l.adjust = (self.adjust[0], dict(self.adjust[1])) if self.adjust else None
        l.link_set = self.link_set
        l.highlight = QColor(self.highlight) if self.highlight is not None else None
        l.kind, l.collapsed, l.group = self.kind, self.collapsed, self.group
        from .textlayer import copy_text
        l.text = copy_text(self.text)
        return l


def clone_layers(layers):
    """Kloon een lagenlijst en laat de groepsverwijzingen naar de nieuwe kopieën wijzen."""
    clones = [l.clone() for l in layers]
    m = {id(o): c for o, c in zip(layers, clones)}
    for c in clones:
        c.group = m.get(id(c.group)) if c.group is not None else None
    return clones


def apply_mask(out: QImage, layer, r: QRect) -> QImage:
    """Maskerlaag: wit toont, zwart verbergt wat eronder ligt (binnen dezelfde groep)."""
    base = ops.qimage_to_rgba(out).astype(np.float32)
    m = ops.qimage_to_rgba(layer.image.copy(r)).astype(np.float32)
    lum = (m[..., 0] * 0.299 + m[..., 1] * 0.587 + m[..., 2] * 0.114) / 255 * (m[..., 3] / 255)
    k = 1 - layer.opacity * (1 - lum)
    base[..., 3] *= k
    return ops.rgba_to_qimage(np.clip(np.rint(base), 0, 255))


def apply_adjustment(out: QImage, layer, r: QRect) -> QImage:
    """Pas het effect van een aanpassingslaag toe op wat eronder ligt, via het masker van de laag."""
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
    changed = Signal(QRect)        # beeldgebied gewijzigd (leeg = alles)
    structureChanged = Signal()    # lagenlijst of eigenschappen
    selectionChanged = Signal()
    sizeChanged = Signal()
    historyChanged = Signal()
    titleChanged = Signal()

    _counter = 0

    def __init__(self, w, h, background: QColor | None = QColor(255, 255, 255)):
        super().__init__()
        self.w, self.h = w, h
        if background is not None:
            self.layers = [Layer("Achtergrond", new_image(w, h, background))]
        else:
            self.layers = [Layer("Raster 1", new_image(w, h))]
        self.active = 0
        self.sel: QImage | None = None
        self.sel_lines = []
        self.path = None
        Document._counter += 1
        self.untitled = f"Afbeelding{Document._counter}"
        self._modified = False
        self.undo_stack = []
        self.redo_stack = []
        self.raster_counter = 1
        self.px_per_pt = 1.0  # tekst in punten: 72 dpi (bij PSP bestanden uit de resolutie berekend)

    # ------------------------------------------------------------ algemeen
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
        return f"Raster {self.raster_counter}"

    # ------------------------------------------------------------ geschiedenis
    def snapshot(self):
        return dict(w=self.w, h=self.h, layers=clone_layers(self.layers),
                    active=self.active, sel=QImage(self.sel) if self.sel is not None else None,
                    sel_lines=list(self.sel_lines))

    def restore(self, s):
        size_changed = (s["w"], s["h"]) != (self.w, self.h)
        self.w, self.h = s["w"], s["h"]
        self.layers = clone_layers(s["layers"])
        self.active = min(s["active"], len(self.layers) - 1)
        self.sel = s["sel"]
        self.sel_lines = s["sel_lines"]
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

    def redo(self):
        if not self.redo_stack:
            return
        label, s = self.redo_stack.pop()
        self.undo_stack.append((label, self.snapshot()))
        self.restore(s)
        self.set_modified(True)
        self.historyChanged.emit()

    # ------------------------------------------------------------ samenstellen
    def children(self, g, layers=None):
        """Directe kinderen van groep g (None = hoofdniveau), van onder naar boven."""
        L = self.layers if layers is None else layers
        ids = {id(x) for x in L}
        return [l for l in L if l.group is g or (g is None and l.group is not None and id(l.group) not in ids)]

    def subtree(self, l):
        """De laag zelf plus (bij een groep) alles erin, in lijstvolgorde."""
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
        """Zorg dat de inhoud van elke groep direct onder de groepskop staat."""
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
                if not l.visible or l.opacity <= 0:
                    continue
                if l.kind == "group":
                    buf = comp(self.children(l, L))
                    blend_onto(out, buf, l.mode, l.opacity, None, r.topLeft())
                elif l.kind == "mask":
                    out = apply_mask(out, l, r)
                elif l.adjust is not None:
                    out = apply_adjustment(out, l, r)
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

    # ------------------------------------------------------------ selectie
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

    # ------------------------------------------------------------ lagen
    def add_layer(self, layer=None, index=None, label="Nieuwe rasterlaag"):
        self.push_undo(label)
        if layer is None:
            layer = Layer(self.next_raster_name(), new_image(self.w, self.h))
        act = self.layer()
        if index is None:
            # nieuwe laag boven de actieve, in dezelfde groep (in een groep als de kop actief is)
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
            return  # er moet altijd minstens één gewone laag overblijven
        self.push_undo("Laag verwijderen")
        first = self.layers.index(gone[0])
        self.layers = [l for l in self.layers if l not in gone]
        self.active = max(0, min(first, len(self.layers)) - 1) if first > 0 else 0
        self.normalize()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def move_layer(self, delta, label="Laag verplaatsen"):
        """Verplaats de actieve laag (met inhoud, bij een groep) tussen de lagen van hetzelfde niveau.
        delta mag groter dan 1 zijn; wordt begrensd tot boven- of onderaan."""
        act = self.layer()
        sib = self.children(act.group)
        i = sib.index(act)
        j = max(0, min(len(sib) - 1, i + delta))
        if j == i:
            return
        self.push_undo(label)
        sib.insert(j, sib.pop(i))
        rank = {id(l): k for k, l in enumerate(sib)}
        # herorden door de broers en zussen in hun nieuwe volgorde terug te zetten
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
                blend_onto(img, up.image, up.mode, up.opacity)
        low.image = img
        self.layers.remove(up)
        self.active = self.layers.index(low)
        self.structureChanged.emit()
        self.changed.emit(QRect())

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
        self.layers = [Layer("Achtergrond", self.flattened(background))]
        self.active = 0
        self.structureChanged.emit()
        self.changed.emit(QRect())

    # ------------------------------------------------------------ groepen en maskers
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
        if act.name == "Achtergrond" and act.group is None and self.layers.index(act) == 0:
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
        """Lagen > Schikken > In groep zetten: in de groep direct boven of onder de laag."""
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
        """Maak een grijswaardenmasker: show_all, hide_all, show_sel, hide_sel, luminance, alpha."""
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
            if act.name == "Achtergrond" and act.group is None and self.layers.index(act) == 0:
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

    def selection_from_mask(self):
        l = self.layer()
        if l.kind != "mask" and l.adjust is None:
            return
        a = ops.qimage_to_rgba(l.image).astype(np.float32)
        v = (a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114) * a[..., 3] / 255
        self.push_undo("Selectie vanuit masker")
        self.set_selection(ops.mask_to_qimage(np.clip(v, 0, 255)))

    # ------------------------------------------------------------ geometrie
    def render_text(self, layer):
        from .textlayer import render
        layer.image = render(layer.text, self.w, self.h, self.px_per_pt)

    def _move_text(self, tmap: QTransform, layers=None):
        """Tekstlagen meebewegen met een geometrische bewerking, zodat ze bewerkbaar blijven."""
        from .textlayer import set_transform, transform
        for l in (layers if layers is not None else self.layers):
            if l.text is not None:
                set_transform(l.text, transform(l.text) * tmap)
                self.render_text(l)

    def _transform_all(self, fn, sel_fn, w, h, label, tmap=None):
        self.push_undo(label)
        for l in self.layers:
            l.image = fn(l.image)
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
            l.image = fn_for(i == 0 and l.name == "Achtergrond")(l.image)
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
        self.push_undo("Spiegelen" if horizontal else "Omdraaien")
        t = QTransform.fromScale(-1, 1) if horizontal else QTransform.fromScale(1, -1)
        if self.layer().text is not None:
            m = QTransform(-1, 0, 0, 1, self.w, 0) if horizontal else QTransform(1, 0, 0, -1, 0, self.h)
            self._move_text(m, [self.layer()])
        else:
            self.layer().image = self.layer().image.transformed(t)
        self.changed.emit(QRect())
        self.structureChanged.emit()

    # ------------------------------------------------------------ pixelfilters
    def apply_to_layer(self, fn, label, base: QImage | None = None, push=True):
        """Pas fn(rgba)->rgba toe op de actieve laag, binnen de selectie."""
        layer = self.layer()
        src = base if base is not None else layer.image
        r = self.selection_bbox() if self.sel is not None else self.rect()
        if r.isEmpty():
            return
        local = src.copy(r)
        result = ops.rgba_to_qimage(fn(ops.qimage_to_rgba(local)))
        out = QImage(src)
        apply_region(out, r, result, self.sel)
        if push:
            self.push_undo(label)
        layer.image = out
        self.changed.emit(r)
        self.structureChanged.emit()

    # ------------------------------------------------------------ uitbreidingen
    def rotate_free(self, degrees, crop=False, fill: QColor | None = None):
        import math
        t = QTransform().rotate(degrees)
        tmap = QImage.trueMatrix(t, self.w, self.h)
        mode = Qt.TransformationMode.SmoothTransformation
        self.push_undo("Vrij roteren")
        for i, l in enumerate(self.layers):
            out = l.image.transformed(t, mode)
            if fill is not None and i == 0 and l.name == "Achtergrond":
                bg = new_image(out.width(), out.height(), fill)
                p = QPainter(bg)
                p.drawImage(0, 0, out)
                p.end()
                out = bg
            l.image = out
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
            nw, nh = wr, hr
            tmap = tmap * QTransform.fromTranslate(-r.x(), -r.y())
        self.w, self.h = nw, nh
        self._move_text(tmap)
        self.set_selection(None)
        self.sizeChanged.emit()
        self.structureChanged.emit()
        self.changed.emit(QRect())

    def add_borders(self, left, top, right, bottom, color: QColor):
        self.canvas_size(self.w + left + right, self.h + top + bottom, left, top, color)
        self.undo_stack[-1] = ("Randen toevoegen", self.undo_stack[-1][1])

    def arrange_layer(self, where):
        n = len(self.layers)
        self.move_layer(n if where == "top" else -n, "Schikken")

    def promote_background(self):
        l = self.layers[0]
        if l.name != "Achtergrond":
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
            for _ in range(n):  # dilatatie, 1 pixel per stap
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
