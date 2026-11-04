"""Bewerkbare tekstlagen.

Een tekstlaag is een gewone Layer met een 'text' dictionary; layer.image is de getekende weergave.
De tekst begint (basislijn van de eerste regel) op het ankerpunt (x, y) en wordt daarna door 'matrix'
(QTransform: m11, m12, m21, m22, dx, dy) geplaatst. Zo blijven verplaatsen, schalen en draaien
mogelijk zonder dat de tekst pixels wordt. Dezelfde opbouw gebruikt PSP in .pspimage bestanden."""
import copy

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen, QTransform

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def new_text(text, x, y, opts, fg, bg, fg_none=False, bg_none=False):
    """Tekstgegevens uit de gereedschapsopties. Vulling = achtergrondkleur, rand = voorgrondkleur (zoals PSP)."""
    return dict(
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
    """Opmaakdelen: [(stijl, rand, vulling, tekst)]. Pigment tekst heeft één stijl; PSP tekst kan er meer hebben."""
    if t.get("runs"):
        return t["runs"]
    return [(t, t.get("stroke"), t.get("fill"), t["text"])]


def path_and_strokes(t, px_per_pt=1.0):
    """Lijst van (pad, rand, vulling, randdikte) in lokale coördinaten (ankerpunt = 0,0)."""
    lines = [[]]  # per regel: [(lettertype, rand, vulling, tekst)]
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


def render(t, W, H, px_per_pt=1.0) -> QImage:
    from .document import new_image
    img = new_image(W, H)
    if not t or not t.get("text"):
        return img
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, t.get("antialias", True))
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, t.get("antialias", True))
    p.setTransform(transform(t))
    p.translate(t["x"], t["y"])
    for path, stroke, fill, sw in path_and_strokes(t, px_per_pt):
        if fill is not None:
            p.fillPath(path, QColor(*fill))
        if stroke is not None:
            pen = QPen(QColor(*stroke), sw)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            p.strokePath(path, pen)
    p.end()
    return img


def bounds(t, px_per_pt=1.0) -> QRectF:
    """Omhullende rechthoek op het canvas (voor aanklikken en het tekstkader)."""
    r = QRectF()
    for path, *_ in path_and_strokes(t, px_per_pt):
        r = r.united(path.boundingRect())
    if r.isNull():
        return r
    return transform(t).mapRect(r.translated(t["x"], t["y"]))
