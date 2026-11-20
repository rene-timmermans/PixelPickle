"""Editable text layers.

A text layer is a regular Layer with a 'text' dictionary; layer.image is the rendered view.
The text starts (baseline of the first line) at the anchor point (x, y) and is then placed by 'matrix'
(QTransform: m11, m12, m21, m22, dx, dy). This way moving, scaling and rotating stay possible
without the text becoming pixels. The structure is compatible with text in .pspimage files."""
import copy

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen, QTransform

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


# pattern images of text materials (QImage does not belong in the copyable text data)
_MAT_IMAGES = {}


def _store_mat(m):
    """Material (gradient/pattern) as copyable data; a pattern image goes into a registry."""
    if m is None:
        return None
    out = {k: v for k, v in m.items() if k != "image"}
    if m.get("kind") == "pattern" and m.get("image") is not None:
        key = f"img{m['image'].cacheKey()}"
        _MAT_IMAGES[key] = m["image"]
        out["image_key"] = key
    return out


def mat_dict(stored):
    """Back to a material as material.py expects it (with the pattern image)."""
    if stored is None:
        return None
    m = dict(stored)
    if m.get("kind") == "pattern":
        from . import material
        m["image"] = _MAT_IMAGES.get(m.get("image_key")) or material.pattern_image(m.get("name", ""))
        if m["image"] is None:
            return None
    return m


def new_text(text, x, y, opts, fg, bg, fg_none=False, bg_none=False, fg_mat=None, bg_mat=None):
    """Text data from the tool options. Fill = background, stroke = foreground; both
    can also be a gradient or pattern (fg_mat/bg_mat)."""
    return dict(
        fill_mat=None if bg_none else _store_mat(bg_mat), stroke_mat=None if fg_none else _store_mat(fg_mat),
        mat_fg=fg.getRgb()[:3], mat_bg=bg.getRgb()[:3],
        text=text, x=float(x), y=float(y), matrix=IDENTITY,
        family=opts["font"], size=float(opts["font_size"]), units="pt" if opts["text_units"] == 0 else "px",
        bold=bool(opts["bold"]), italic=bool(opts["italic"]), underline=bool(opts["underline"]),
        align=int(opts["text_align"]), stroke_width=float(opts["text_stroke"]), leading=float(opts["leading"]),
        tracking=float(opts["tracking"]), antialias=bool(opts["antialias"]),
        fill=None if bg_none else bg.getRgb()[:3], stroke=None if (fg_none or opts["text_stroke"] <= 0) else fg.getRgb()[:3],
    )


def copy_text(t):
    return copy.deepcopy(t) if t is not None else None


def transform(t):
    m = t.get("matrix", IDENTITY)
    return QTransform(m[0], m[1], m[2], m[3], m[4], m[5])


def set_transform(t, tr: QTransform):
    t["matrix"] = (tr.m11(), tr.m12(), tr.m21(), tr.m22(), tr.dx(), tr.dy())


def _font(style, px_per_pt):
    f = QFont(style["family"])
    size = style["size"] * (px_per_pt if style.get("units", "pt") == "pt" else 1.0)
    f.setPixelSize(max(1, round(size)))
    if "weight" in style:
        f.setWeight(QFont.Weight(min(1000, max(1, int(style["weight"])))))
    else:
        f.setBold(style.get("bold", False))
    f.setItalic(style.get("italic", False))
    f.setUnderline(style.get("underline", False))
    if style.get("tracking"):
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, style["tracking"] / 10)
    return f


def _runs(t):
    """Formatting runs: [(style, stroke, fill, text)]. PixelPickle text has one style;
    text from .pspimage files can have more."""
    if t.get("runs"):
        return t["runs"]
    return [(t, t.get("stroke"), t.get("fill"), t["text"])]


def path_and_strokes(t, px_per_pt=1.0):
    """List of (path, stroke, fill, stroke width) in local coordinates (anchor point = 0,0)."""
    lines = [[]]  # per line: [(font, stroke, fill, text)]
    for style, stroke, fill, chunk in _runs(t):
        parts = chunk.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                lines.append([])
            lines[-1].append((_font(style, px_per_pt), stroke, fill, part, style))
    out = []
    widths = [sum(QFontMetricsF(f).horizontalAdvance(txt) for f, _, _, txt, _ in ln) for ln in lines]
    maxw = max(widths) if widths else 0
    y = 0.0
    align = t.get("align", 0)
    for ln, w in zip(lines, widths):
        x = [0.0, -w / 2, -w][align] if align else 0.0
        spacing = 0.0
        for f, stroke, fill, txt, style in ln:
            fm = QFontMetricsF(f)
            spacing = max(spacing, fm.lineSpacing())
            if txt:
                p = QPainterPath()
                p.addText(QPointF(x, y), f, txt)
                out.append((p, stroke, fill, style.get("stroke_width", t.get("stroke_width", 1.0)) or 1.0))
            x += fm.horizontalAdvance(txt)
        if not ln:
            spacing = QFontMetricsF(_font(t, px_per_pt)).lineSpacing()
        y += spacing + t.get("leading", 0.0)
    return out


def glyph_paths(t, px_per_pt=1.0, per_char=False):
    """Paths of the text on the canvas (with position and transformation): [(path, stroke, fill, stroke width)].
    per_char: one path per letter (for Convert text to curves > As individual letter shapes)."""
    if t.get("on_path"):
        return [(p, s, f, w) for p, s, f, w, _ in _on_path_glyphs(t, px_per_pt)]
    m = transform(t) * QTransform()  # copy
    place = QTransform.fromTranslate(t["x"], t["y"]) * m
    if not per_char:
        return [(place.map(p), s, f, w) for p, s, f, w in path_and_strokes(t, px_per_pt)]
    out = []
    lines = [[]]
    for style, stroke, fill, chunk in _runs(t):
        for i, part in enumerate(chunk.replace("\r\n", "\n").replace("\r", "\n").split("\n")):
            if i > 0:
                lines.append([])
            lines[-1].append((_font(style, px_per_pt), stroke, fill, part, style))
    widths = [sum(QFontMetricsF(f).horizontalAdvance(txt) for f, _, _, txt, _ in ln) for ln in lines]
    y, align = 0.0, t.get("align", 0)
    for ln, w in zip(lines, widths):
        x = [0.0, -w / 2, -w][align] if align else 0.0
        spacing = 0.0
        for f, stroke, fill, txt, style in ln:
            fm = QFontMetricsF(f)
            spacing = max(spacing, fm.lineSpacing())
            for k, ch in enumerate(txt):
                if not ch.isspace():
                    p = QPainterPath()
                    p.addText(QPointF(x + fm.horizontalAdvance(txt[:k]), y), f, ch)
                    out.append((place.map(p), stroke, fill, style.get("stroke_width", t.get("stroke_width", 1.0)) or 1.0))
            x += fm.horizontalAdvance(txt)
        if not ln:
            spacing = QFontMetricsF(_font(t, px_per_pt)).lineSpacing()
        y += spacing + t.get("leading", 0.0)
    return out


def _on_path_glyphs(t, px_per_pt=1.0):
    """Text along a path (Fit text to path): each letter sits on the path, rotated along the direction.
    Returns [(path on the canvas, stroke, fill, stroke width, text)]."""
    from . import vectorlayer as V
    guide = QPainterPath()
    V._add_contour(guide, t["on_path"]["nodes"], t["on_path"].get("closed", False))
    total = guide.length()
    if total <= 0:
        return []
    out = []
    s = float(t.get("path_offset", 0.0))
    for style, stroke, fill, chunk in _runs(t):
        f = _font(style, px_per_pt)
        fm = QFontMetricsF(f)
        for ch in chunk.replace("\r", " ").replace("\n", " "):
            adv = fm.horizontalAdvance(ch)
            mid = s + adv / 2
            if mid > total:
                return out
            if not ch.isspace():
                pct = guide.percentAtLength(mid)
                pt, ang = guide.pointAtPercent(pct), guide.angleAtPercent(pct)
                g = QPainterPath()
                g.addText(QPointF(-adv / 2, 0), f, ch)
                tr_ = QTransform.fromTranslate(pt.x(), pt.y())
                tr_ = QTransform().rotate(-ang) * tr_
                out.append((tr_.map(g), stroke, fill, style.get("stroke_width", t.get("stroke_width", 1.0)) or 1.0, ch))
            s += adv
    return out


def render(t, W, H, px_per_pt=1.0) -> QImage:
    from .document import new_image
    img = new_image(W, H)
    if not t or not t.get("text"):
        return img
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, t.get("antialias", True))
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, t.get("antialias", True))
    if t.get("on_path"):  # text along a path: the letters are already in place on the canvas
        parts = [(gp, st, fi, sw) for gp, st, fi, sw, _ in _on_path_glyphs(t, px_per_pt)]
    else:
        p.setTransform(transform(t))
        p.translate(t["x"], t["y"])
        parts = path_and_strokes(t, px_per_pt)
    fill_br = stroke_br = None
    if t.get("fill_mat") or t.get("stroke_mat"):
        from . import material
        span = QRectF()
        for path, *_ in parts:
            span = span.united(path.boundingRect())
        span = span.toAlignedRect()
        fg, bg = QColor(*t.get("mat_fg", (0, 0, 0))), QColor(*t.get("mat_bg", (255, 255, 255)))
        fill_br = material.brush(mat_dict(t.get("fill_mat")), span, fg, bg) if t.get("fill_mat") else None
        stroke_br = material.brush(mat_dict(t.get("stroke_mat")), span, fg, bg) if t.get("stroke_mat") else None
    base_fill, base_stroke = t.get("fill"), t.get("stroke")
    for path, stroke, fill, sw in parts:
        if fill is not None:
            # the material applies to text with the regular fill; words with their own color keep that
            p.fillPath(path, fill_br if fill_br is not None and tuple(fill) == tuple(base_fill or ()) else QColor(*fill))
        if stroke is not None:
            pen = QPen(stroke_br if stroke_br is not None and tuple(stroke) == tuple(base_stroke or ()) else QColor(*stroke), sw)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            p.strokePath(path, pen)
    p.end()
    return img


def bounds(t, px_per_pt=1.0) -> QRectF:
    """Bounding rectangle on the canvas (for clicking and the text frame)."""
    r = QRectF()
    if t.get("on_path"):
        for path, *_ in _on_path_glyphs(t, px_per_pt):
            r = r.united(path.boundingRect())
        return r
    for path, *_ in path_and_strokes(t, px_per_pt):
        r = r.united(path.boundingRect())
    if r.isNull():
        return r
    return transform(t).mapRect(r.translated(t["x"], t["y"]))
