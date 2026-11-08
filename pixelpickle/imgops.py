"""Bewerkingen van het menu Afbeelding: kleurdiepte verminderen, kanalen splitsen en combineren,
berekeningen tussen twee afbeeldingen en fotolijsten. Alles werkt op RGBA-arrays (uint8)."""
import math

import numpy as np
from PIL import Image

# ---------------------------------------------------------------- kleurdiepte verminderen
METHODS = ("nearest", "diffusion", "ordered")
_BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.float32) / 16 - 0.5


def _bayer(h, w):
    return np.tile(_BAYER, (h // 4 + 1, w // 4 + 1))[:h, :w]


def web_palette():
    """Vast palet van 216 kleuren (6 niveaus per kanaal)."""
    lv = [0, 51, 102, 153, 204, 255]
    return [(r, g, b) for r in lv for g in lv for b in lv]


def standard16():
    return [(0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0), (0, 0, 128), (128, 0, 128), (0, 128, 128),
            (192, 192, 192), (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0), (0, 0, 255), (255, 0, 255),
            (0, 255, 255), (255, 255, 255)]


def make_palette(rgba_list, colors, kind="optimal"):
    """Palet (Pillow 'P'-beeld) voor deze beelden samen: optimaal (mediaansnede) of vast (web/standaard)."""
    if kind == "optimal":
        joined = np.concatenate([a[..., :3].reshape(-1, 3) for a in rgba_list], axis=0)
        if len(joined) > 1_500_000:  # voor het palet volstaat een steekproef
            joined = joined[np.random.default_rng(1).choice(len(joined), 1_500_000, replace=False)]
        side = int(math.ceil(math.sqrt(len(joined))))
        pad = np.zeros((side * side, 3), np.uint8)
        pad[:len(joined)] = joined
        pad[len(joined):] = joined[0]
        img = Image.fromarray(pad.reshape(side, side, 3), "RGB")
        pal = img.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        return pal
    cols = standard16() if colors <= 16 else web_palette()
    if colors == 2:
        cols = [(0, 0, 0), (255, 255, 255)]
    flat = [v for c in cols for v in c]
    flat += flat[:3] * (256 - len(cols))
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat[:768])
    return pal


def quantize(rgba: np.ndarray, palette_img, method="diffusion") -> np.ndarray:
    """Kleuren terugbrengen naar het palet. method: dichtstbijzijnde kleur, foutdiffusie of geordende dithering."""
    rgb = rgba[..., :3]
    if method == "ordered":
        # geordende dithering: kleine ruis volgens een Bayer-patroon, daarna dichtstbijzijnde kleur
        spread = 48.0
        rgb = np.clip(rgb.astype(np.float32) + _bayer(*rgb.shape[:2])[..., None] * spread, 0, 255).astype(np.uint8)
    img = Image.fromarray(np.ascontiguousarray(rgb), "RGB")
    q = img.quantize(palette=palette_img, dither=Image.Dither.FLOYDSTEINBERG if method == "diffusion" else Image.Dither.NONE)
    out = rgba.copy()
    out[..., :3] = np.asarray(q.convert("RGB"))
    return out


def two_colors(rgba: np.ndarray, method="diffusion") -> np.ndarray:
    """Zwart-wit (2 kleuren) op basis van de helderheid."""
    y = rgba[..., 0] * 0.299 + rgba[..., 1] * 0.587 + rgba[..., 2] * 0.114
    if method == "diffusion":
        img = Image.fromarray(np.clip(y, 0, 255).astype(np.uint8), "L").convert("1")  # Floyd-Steinberg
        bw = np.asarray(img, np.uint8) * 255
    else:
        if method == "ordered":
            y = y + _bayer(*y.shape) * 255
        bw = np.where(y >= 128, 255, 0).astype(np.uint8)
    out = rgba.copy()
    out[..., 0] = out[..., 1] = out[..., 2] = bw
    return out


def reduce_bits(rgba: np.ndarray, bits=(5, 5, 5), ordered=False) -> np.ndarray:
    """32.000 kleuren (5-5-5 bits) of 64.000 kleuren (5-6-5 bits), eventueel met geordende dithering."""
    out = rgba.copy()
    noise = _bayer(*rgba.shape[:2]) if ordered else None
    for c, b in enumerate(bits):
        levels = (1 << b) - 1
        v = rgba[..., c].astype(np.float32) / 255 * levels
        if noise is not None:
            v = v + noise
        out[..., c] = np.clip(np.round(v), 0, levels) / levels * 255
    return out


# ---------------------------------------------------------------- kanalen
def split(rgba: np.ndarray, model: str):
    """Kanalen als grijswaardenbeelden: [(naam, uint8 array)]. model: rgb, hsl of cmyk."""
    rgb = rgba[..., :3].astype(np.float32) / 255
    if model == "rgb":
        return [("Rood", rgba[..., 0]), ("Groen", rgba[..., 1]), ("Blauw", rgba[..., 2])]
    if model == "hsl":
        from . import imageops as ops
        h, s, l = ops.rgb_to_hsl(rgba[..., :3].astype(np.float32))
        return [("Tint", (h * 255).astype(np.uint8)), ("Verzadiging", (s * 255).astype(np.uint8)),
                ("Lichtheid", (l * 255).astype(np.uint8))]
    k = 1 - rgb.max(axis=2)
    den = np.maximum(1 - k, 1e-6)
    c = (1 - rgb[..., 0] - k) / den
    m = (1 - rgb[..., 1] - k) / den
    y = (1 - rgb[..., 2] - k) / den
    to8 = lambda a: np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8)  # noqa: E731
    return [("Cyaan", to8(c)), ("Magenta", to8(m)), ("Geel", to8(y)), ("Zwart", to8(k))]


def combine(channels, model: str) -> np.ndarray:
    """Kanalen (grijswaardenarrays, zelfde grootte) weer samenvoegen tot een RGBA-beeld."""
    h, w = channels[0].shape
    out = np.full((h, w, 4), 255, np.uint8)
    if model == "rgb":
        for i in range(3):
            out[..., i] = channels[i]
        return out
    if model == "hsl":
        from . import imageops as ops
        hh, s, l = (c.astype(np.float32) / 255 for c in channels[:3])
        out[..., :3] = np.clip(ops.hsl_to_rgb(hh, s, l), 0, 255).astype(np.uint8)
        return out
    c, m, y, k = (ch.astype(np.float32) / 255 for ch in channels[:4])
    out[..., 0] = np.clip(255 * (1 - c) * (1 - k), 0, 255)
    out[..., 1] = np.clip(255 * (1 - m) * (1 - k), 0, 255)
    out[..., 2] = np.clip(255 * (1 - y) * (1 - k), 0, 255)
    return out


def to_gray_rgba(g: np.ndarray) -> np.ndarray:
    return np.dstack([g, g, g, np.full_like(g, 255)])


def gray_of(rgba: np.ndarray) -> np.ndarray:
    return np.clip(rgba[..., 0] * 0.299 + rgba[..., 1] * 0.587 + rgba[..., 2] * 0.114 + 0.5, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- berekeningen
FUNCTIONS = ("add", "subtract", "multiply", "difference", "lighter", "darker", "average", "and", "or", "xor")


def arithmetic(a: np.ndarray, b: np.ndarray, func: str, channel=None, divisor=1, bias=0, clip=True) -> np.ndarray:
    """Twee afbeeldingen (RGBA, zelfde grootte) met elkaar verrekenen: resultaat = (a f b) / deler + verschuiving.
    channel: None = alle kleurkanalen, anders 0/1/2 (de andere kanalen komen uit a). clip: afkappen op 0..255,
    anders rond laten lopen."""
    A = a[..., :3].astype(np.int32)
    B = b[..., :3].astype(np.int32)
    if func == "add":
        r = A + B
    elif func == "subtract":
        r = A - B
    elif func == "multiply":
        r = A * B // 255
    elif func == "difference":
        r = np.abs(A - B)
    elif func == "lighter":
        r = np.maximum(A, B)
    elif func == "darker":
        r = np.minimum(A, B)
    elif func == "average":
        r = (A + B) // 2
    elif func == "and":
        r = A & B
    elif func == "or":
        r = A | B
    else:
        r = A ^ B
    r = r // max(1, int(divisor)) + int(bias)
    r = np.clip(r, 0, 255) if clip else np.mod(r, 256)
    out = a.copy()
    if channel is None:
        out[..., :3] = r
    else:
        out[..., channel] = r[..., channel]
    out[..., 3] = np.maximum(a[..., 3], b[..., 3])
    return out


# ---------------------------------------------------------------- fotolijsten
FRAMES = ("simple", "wood", "gold", "silver", "mat", "polaroid", "shadow")


def frame_image(W, H, style, t, color):
    """Fotolijst als laag (W x H, midden doorzichtig) met lijstbreedte t pixels. color: QColor (voor de
    eenvoudige lijst, de rand van het passe-partout en de achtergrond van de schaduwlijst)."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, QTransform
    from . import material as M
    from .document import new_image
    img = new_image(W, H)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    t = max(1, min(int(t), min(W, H) // 2 - 1))
    bottom_t = t * 3 if style == "polaroid" else t
    o = QRectF(0, 0, W, H)
    i = QRectF(t, t, W - 2 * t, H - t - bottom_t)
    if style == "shadow":
        # schaduw rond het midden (de lijst ligt onder de foto): zachte, donkere rand naar rechtsonder
        p.fillRect(o, QColor(color))
        for k in range(12, 0, -1):
            a = int(10 + (12 - k) * 6)
            p.fillRect(i.translated(t * 0.25, t * 0.25).adjusted(-k, -k, k, k), QColor(0, 0, 0, max(0, a // 3)))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(i, Qt.GlobalColor.transparent)
        p.end()
        return img
    sides = {  # vier trapezia met verstek: (punten, kant)
        "top": [o.topLeft(), o.topRight(), i.topRight(), i.topLeft()],
        "right": [o.topRight(), o.bottomRight(), i.bottomRight(), i.topRight()],
        "bottom": [o.bottomRight(), o.bottomLeft(), i.bottomLeft(), i.bottomRight()],
        "left": [o.bottomLeft(), o.topLeft(), i.topLeft(), i.bottomLeft()],
    }
    shade = {"top": QColor(255, 255, 255, 70), "left": QColor(255, 255, 255, 35),
             "right": QColor(0, 0, 0, 45), "bottom": QColor(0, 0, 0, 80)}
    for name, pts in sides.items():
        poly = QPolygonF(pts)
        if style in ("gold", "silver"):
            preset = "Goud" if style == "gold" else "Zilver"
            lut = M.gradient_lut(preset, QColor(0, 0, 0), QColor(255, 255, 255))
            a, b = pts[0], pts[3]  # van de buitenrand naar de binnenrand
            if name in ("top", "bottom"):
                g = QLinearGradient(QPointF(0, a.y()), QPointF(0, b.y()))
            else:
                g = QLinearGradient(QPointF(a.x(), 0), QPointF(b.x(), 0))
            for k in range(0, 256, 32):
                c = lut[k]
                g.setColorAt(k / 255, QColor(int(c[0]), int(c[1]), int(c[2])))
            brush = QBrush(g)
        elif style == "wood":
            brush = QBrush(M.pattern_image("Hout"))
            if name in ("left", "right"):
                brush.setTransform(QTransform().rotate(90))
        elif style == "polaroid":
            brush = QBrush(QColor(250, 250, 247))
        elif style == "mat":
            brush = QBrush(QColor(242, 238, 228))
        else:
            brush = QBrush(QColor(color))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(brush)
        p.drawPolygon(poly)
        if style not in ("polaroid", "mat", "simple"):
            p.setBrush(shade[name])
            p.drawPolygon(poly)
    if style == "mat":  # passe-partout: smalle lijst buiten, schuine snede binnen
        outer = max(2, t // 4)
        path = QPainterPath()
        path.addRect(o)
        path.addRect(o.adjusted(outer, outer, -outer, -outer))
        p.fillPath(path, QColor(color))
        p.setPen(QPen(QColor(200, 194, 180), max(1.0, t / 30)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(i.adjusted(-1, -1, 1, 1))
    else:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 90), 1))
        p.drawRect(i.adjusted(-0.5, -0.5, 0.5, 0.5))
        if style != "polaroid":
            p.setPen(QPen(QColor(0, 0, 0, 120), 1))
            p.drawRect(o.adjusted(0.5, 0.5, -0.5, -0.5))
    p.end()
    return img
