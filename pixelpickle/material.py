"""Materialen naast een effen kleur: verlopen en patronen (zoals in PSP).

Een materiaal is None (effen kleur) of een dict:
- {"kind": "gradient", "preset": naam, "style": 0..3, "angle": graden, "repeats": n, "invert": bool,
   "cx": %, "cy": %}  stijl 0 lineair, 1 rechthoekig, 2 zonnestraal (cirkels), 3 radiaal (rond draaiend)
- {"kind": "pattern", "name": naam, "image": QImage, "angle": graden, "scale": %}

render() maakt er een afbeelding van voor een rechthoek in documentcoördinaten. Een verloop loopt over
'span' (bijvoorbeeld de selectie of de vorm); een patroon ligt vast ten opzichte van de linkerbovenhoek
van het document, zodat aansluitende streken naadloos op elkaar passen."""
import math
import os
import re

import numpy as np
from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QTransform

from . import imageops as ops
from .document import new_image

STYLES = ["Lineair", "Rechthoekig", "Zonnestraal", "Radiaal"]

# vaste verlopen; FG/BG worden bij gebruik vervangen door voorgrond- en achtergrondkleur
FG, BG, FG0, BG0 = "fg", "bg", "fg0", "bg0"
GRADIENTS = {
    "Voorgrond-achtergrond": [FG, BG],
    "Voorgrond-transparant": [FG, FG0],
    "Achtergrond-transparant": [BG, BG0],
    "Zwart-wit": ["#000000", "#ffffff"],
    "Regenboog": ["#ff0000", "#ffff00", "#00ff00", "#00ffff", "#0000ff", "#ff00ff", "#ff0000"],
    "Zonsondergang": ["#2b1055", "#d53369", "#ff8a00", "#ffe259"],
    "Vuur": ["#000000", "#800000", "#ff4000", "#ffc000", "#ffffa0"],
    "Goud": ["#7a5b10", "#f6e27a", "#b8860b", "#fff3b0", "#8a6a12"],
    "Zilver": ["#555555", "#eeeeee", "#888888", "#ffffff", "#666666"],
    "Koper": ["#5a2e0e", "#e8a36b", "#8c4a1c", "#f7c99a", "#6b3410"],
    "Hemel": ["#1e3c72", "#2a5298", "#a8c0ff", "#ffffff"],
    "Zee": ["#003b46", "#07575b", "#66a5ad", "#c4dfe6"],
    "Bos": ["#0b3d0b", "#2e7d32", "#9ccc65", "#f1f8e9"],
    "Pastel": ["#ffd1dc", "#fff5ba", "#c1f0c1", "#bde0fe", "#e2c2ff"],
}


def default_gradient():
    return {"kind": "gradient", "preset": "Voorgrond-achtergrond", "style": 0, "angle": 0, "repeats": 0,
            "invert": False, "cx": 50, "cy": 50}


def default_pattern():
    return {"kind": "pattern", "name": "Bakstenen", "image": pattern_image("Bakstenen"), "angle": 0, "scale": 100}


def _rgba(spec, fg, bg):
    if spec in (FG, FG0, BG, BG0):
        c = QColor(fg if spec in (FG, FG0) else bg)
        return (c.red(), c.green(), c.blue(), 0 if spec.endswith("0") else c.alpha())
    c = QColor(spec)
    return (c.red(), c.green(), c.blue(), 255)


def _interp(x, pos, vals, mids=None):
    """Waarden tussen de punten; mids (0..100) verschuift het midden tussen twee punten (zoals PSP)."""
    pos = np.asarray(pos, np.float32)
    vals = np.asarray(vals, np.float32)
    if len(pos) == 1:
        return np.repeat(vals[:1], len(x), axis=0)
    out = np.empty((len(x),) + vals.shape[1:], np.float32)
    for k, xv in enumerate(x):
        if xv <= pos[0]:
            out[k] = vals[0]
            continue
        if xv >= pos[-1]:
            out[k] = vals[-1]
            continue
        i = int(np.searchsorted(pos, xv, side="right")) - 1
        span = pos[i + 1] - pos[i]
        f = 0.0 if span <= 0 else (xv - pos[i]) / span
        if mids is not None:
            m = min(max(mids[i] / 100, 0.01), 0.99)
            if abs(m - 0.5) > 1e-3:
                f = f ** (math.log(0.5) / math.log(m))
        out[k] = vals[i] + (vals[i + 1] - vals[i]) * f
    return out


def gradient_lut(name, fg, bg):
    """256 x 4 tabel (RGBA, niet voorvermenigvuldigd)."""
    x = np.linspace(0, 1, 256)
    psp = psp_gradients().get(name)
    if psp is not None:
        cstops, astops = psp
        cols = []
        for _, _, rgb, typ in cstops:
            c = QColor(fg) if typ == 1 else QColor(bg) if typ == 2 else None
            cols.append((c.red(), c.green(), c.blue()) if c is not None else rgb)
        rgb = _interp(x, [c[0] for c in cstops], cols, [c[1] for c in cstops])
        alpha = _interp(x, [a[0] for a in astops], [[a[2]] for a in astops], [a[1] for a in astops]) \
            if astops else np.full((256, 1), 255, np.float32)
        return np.concatenate([rgb, alpha], axis=1)
    stops = [_rgba(s, fg, bg) for s in GRADIENTS.get(name, GRADIENTS["Voorgrond-achtergrond"])]
    return _interp(x, np.linspace(0, 1, len(stops)), stops)


def gradient_names():
    """Sleutels van alle verlopen: eerst de eigen, dan die uit PSP."""
    return list(GRADIENTS) + list(psp_gradients())


def gradient_label(key):
    from .i18n import tr
    return tr(key[4:]) if key.startswith("psp:") else tr(key)


# ---------------------------------------------------------------- verlopen en patronen uit PSP
def psp_dirs():
    """Mappen van een PSP installatie (Wine/Bottles) en de PSP map in Documenten van de gebruiker."""
    import glob
    home = os.path.expanduser("~")
    prefixes = (glob.glob(f"{home}/.var/app/com.usebottles.bottles/data/bottles/bottles/*/drive_c")
                + glob.glob(f"{home}/.local/share/bottles/bottles/*/drive_c") + [f"{home}/.wine/drive_c"])
    out = []
    for pre in prefixes:
        out += glob.glob(os.path.join(glob.escape(pre), "Program Files*", "Corel", "*Paint Shop Pro*"))
        out += glob.glob(os.path.join(glob.escape(pre), "Program Files*", "Jasc Software Inc", "Paint Shop Pro*"))
        out += glob.glob(os.path.join(glob.escape(pre), "users", "*", "Documents", "*PSP*"))
        out += glob.glob(os.path.join(glob.escape(pre), "users", "*", "My Documents", "*PSP*"))
    return [d for d in out if os.path.isdir(d)]


def read_grd(path):
    """PSP/Photoshop verloopbestand (.PspGradient, .grd versie 3).
    Geeft [(naam, kleurpunten, dekkingspunten)]; kleurpunt = (positie 0..1, midden %, (r, g, b), soort)
    met soort 0 eigen kleur, 1 voorgrond, 2 achtergrond; dekkingspunt = (positie, midden %, 0..255)."""
    import struct
    b = open(path, "rb").read()
    if b[:4] != b"8BGR":
        return []
    ver, n = struct.unpack(">HH", b[4:8])
    if ver != 3:
        return []
    o, out = 8, []
    for _ in range(n):
        ln = b[o]
        name = b[o + 1:o + 1 + ln].decode("latin-1")
        o += 1 + ln
        nc, = struct.unpack(">H", b[o:o + 2])
        o += 2
        cs = []
        for _ in range(nc):
            loc, mid, model, c1, c2, c3, c4, typ = struct.unpack(">IIHHHHHH", b[o:o + 20])
            o += 20
            if model == 0:
                rgb = (c1 >> 8, c2 >> 8, c3 >> 8)
            elif model == 1:  # HSB
                q = QColor.fromHsvF((c1 / 65535) % 1.0, c2 / 65535, c3 / 65535)
                rgb = (q.red(), q.green(), q.blue())
            elif model == 2:  # CMYK
                q = QColor.fromCmykF(c1 / 65535, c2 / 65535, c3 / 65535, c4 / 65535)
                rgb = (q.red(), q.green(), q.blue())
            else:  # grijs en overige: helderheid uit de eerste waarde
                rgb = (c1 >> 8,) * 3
            cs.append((loc / 4096, mid, rgb, typ))
        na, = struct.unpack(">H", b[o:o + 2])
        o += 2
        al = []
        for _ in range(na):
            loc, mid, op = struct.unpack(">IIH", b[o:o + 10])
            o += 10
            al.append((loc / 4096, mid, min(op, 255)))
        o += 6
        if cs:
            out.append((name, sorted(cs, key=lambda c: c[0]), sorted(al, key=lambda a: a[0])))
    return out


_psp_grad = None
_psp_pat = None


def psp_gradients():
    """{'psp:naam': (kleurpunten, dekkingspunten)} uit de PSP installatie (eenmalig ingelezen)."""
    global _psp_grad
    if _psp_grad is None:
        import glob
        _psp_grad = {}
        for d in psp_dirs():
            files = sorted(glob.glob(os.path.join(glob.escape(d), "**", "*.PspGradient"), recursive=True)
                           + glob.glob(os.path.join(glob.escape(d), "**", "*.grd"), recursive=True))
            for f in files:
                try:
                    for name, cs, al in read_grd(f):
                        if name.lower() != "current gradient":
                            _psp_grad.setdefault("psp:" + _gradient_name(name), (cs, al))
                except Exception:  # beschadigd of onbekend bestand overslaan
                    continue
    return _psp_grad


# leesbare namen voor de meegeleverde patronen (op bestandsnummer)
PATTERN_NAMES = {1: "Bellen", 2: "Canvas", 3: "Sinaasappelhuid", 4: "Luipaard", 5: "Tijger", 6: "Zebra",
                 52: "Craquelé", 53: "Veren", 54: "Paarse zijde", 55: "Oranje marmer", 56: "Verfrommeld papier",
                 57: "Blauwe wolken", 58: "Rijstpapier", 59: "Parket", 60: "Mahonie", 61: "Groen brokaat",
                 62: "Damast", 63: "Bloemetjes", 64: "Tapijt"}


def _pattern_name(stem):
    m = re.match(r"^Corel_08_(\d+)$", stem)
    if not m:
        return stem  # eigen patroon van de gebruiker: bestandsnaam
    n = int(m.group(1))
    if n in PATTERN_NAMES:
        return PATTERN_NAMES[n]
    if 7 <= n <= 51:
        return f"Lijntekening {n - 6}"
    return f"Patroon {n}"


def _gradient_name(name):
    """Voorvoegsels van makers weghalen en met een hoofdletter beginnen."""
    name = re.sub(r"^(smg_|sb_|soe)", "", name).replace("_", " ").strip()
    return name[:1].upper() + name[1:] if name else name


def psp_patterns():
    """[(naam, pad)] van de patronen uit PSP (Corel_08) en de map Patronen/Patterns van de gebruiker."""
    global _psp_pat
    if _psp_pat is None:
        import glob
        _psp_pat, seen = [], set()
        for d in psp_dirs():
            cands = glob.glob(os.path.join(glob.escape(d), "Corel_08", "**", "*"), recursive=True)
            for sub in ("Patronen", "Patterns"):
                cands += glob.glob(os.path.join(glob.escape(d), sub, "**", "*"), recursive=True)
            for f in sorted(cands):
                stem, ext = os.path.splitext(os.path.basename(f))
                name = _pattern_name(stem)
                if ext.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff") and name not in seen:
                    seen.add(name)
                    _psp_pat.append((name, f))
    return _psp_pat


def gradient_t(m, w, h, span):
    """Positie 0..1 in het verloop voor elk punt van een w x h vlak; span = (x, y, b, h) relatief."""
    sx, sy, sw, sh = span
    sw, sh = max(sw, 1), max(sh, 1)
    cx = sx + sw * m.get("cx", 50) / 100
    cy = sy + sh * m.get("cy", 50) / 100
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xx + 0.5 - cx, yy + 0.5 - cy
    a = math.radians(m.get("angle", 0))
    style = m.get("style", 0)
    if style == 0:  # lineair: hoek 0 = van boven naar beneden
        ux, uy = math.sin(a), math.cos(a)
        half = abs(sw / 2 * ux) + abs(sh / 2 * uy)
        t = (dx * ux + dy * uy) / (2 * max(half, 1e-6)) + 0.5
    elif style == 1:  # rechthoekig
        ca, sa = math.cos(a), math.sin(a)
        rx, ry = dx * ca + dy * sa, -dx * sa + dy * ca
        hw = max(cx - sx, sx + sw - cx, 1)
        hh = max(cy - sy, sy + sh - cy, 1)
        t = np.maximum(np.abs(rx) / hw, np.abs(ry) / hh)
    elif style == 2:  # zonnestraal: cirkels vanuit het middelpunt
        far = max(math.hypot(px - cx, py - cy) for px in (sx, sx + sw) for py in (sy, sy + sh))
        t = np.hypot(dx, dy) / max(far, 1)
    else:  # radiaal: rond het middelpunt draaiend
        t = np.mod((np.arctan2(dx, -dy) - a) / (2 * math.pi), 1.0)
    t = np.clip(t, 0, 1)
    n = int(m.get("repeats", 0))
    if n > 0:
        tt = t * (n + 1)
        t = np.where(tt >= n + 1, 1.0, tt - np.floor(tt))
    if m.get("invert"):
        t = 1 - t
    return t


def render_gradient(m, rect, span, fg, bg):
    lut = gradient_lut(m.get("preset"), fg, bg)
    t = gradient_t(m, rect.width(), rect.height(),
                   (span.x() - rect.x(), span.y() - rect.y(), span.width(), span.height()))
    idx = np.clip((t * 255 + 0.5).astype(np.int32), 0, 255)
    return ops.rgba_to_qimage(np.clip(lut[idx], 0, 255).astype(np.uint8))


def pattern_brush(m, origin=(0, 0)):
    """QBrush met het patroon (geschaald en gedraaid); origin = documentpunt dat op (0, 0) valt."""
    br = QBrush(m["image"])
    t = QTransform()
    t.translate(-origin[0], -origin[1])
    t.rotate(m.get("angle", 0))
    s = max(m.get("scale", 100), 1) / 100
    t.scale(s, s)
    br.setTransform(t)
    return br


def render(m, rect, span=None, fg=QColor(0, 0, 0), bg=QColor(255, 255, 255)):
    """Afbeelding (grootte rect) van materiaal m; rect en span in documentcoördinaten."""
    rect = QRect(rect)
    if m is None or rect.isEmpty():
        return None
    if m["kind"] == "gradient":
        return render_gradient(m, rect, QRect(span) if span is not None and not span.isEmpty() else rect, fg, bg)
    img = new_image(rect.width(), rect.height())
    p = QPainter(img)
    p.fillRect(img.rect(), pattern_brush(m, (rect.x(), rect.y())))
    p.end()
    return img


def brush(m, span, fg, bg):
    """QBrush voor tekenen met QPainter (vormen, lijnen) over 'span' in documentcoördinaten."""
    span = QRect(span)
    if m is None or span.isEmpty():
        return None
    if m["kind"] == "pattern":
        return pattern_brush(m)
    br = QBrush(render_gradient(m, span, span, fg, bg))
    br.setTransform(QTransform.fromTranslate(span.x(), span.y()))
    return br


def preview(m, w, h, fg, bg):
    """Voorbeeldje voor knoppen en lijsten."""
    if m is None:
        img = new_image(w, h, fg)
        return img
    img = new_image(w, h, QColor(255, 255, 255))
    p = QPainter(img)
    for y in range(0, h, 6):  # ruitjes onder transparante delen
        for x in range(0, w, 6):
            if (x // 6 + y // 6) % 2:
                p.fillRect(x, y, 6, 6, QColor(204, 204, 204))
    if m["kind"] == "gradient":
        p.drawImage(0, 0, render_gradient(m, QRect(0, 0, w, h), QRect(0, 0, w, h), fg, bg))
    else:
        mm = dict(m)
        mm["scale"] = max(10, min(m.get("scale", 100), 100))
        p.fillRect(0, 0, w, h, pattern_brush(mm))
    p.end()
    return img


# ---------------------------------------------------------------- ingebouwde patronen
def _np_img(a):
    return ops.rgba_to_qimage(np.clip(a, 0, 255).astype(np.uint8))


def _rgb(a, c1, c2):
    """a in 0..1 -> mengsel van kleur c1 (0) en c2 (1)."""
    c1, c2 = np.array(c1, np.float32), np.array(c2, np.float32)
    out = np.empty(a.shape + (4,), np.float32)
    out[..., :3] = c1 + (c2 - c1) * a[..., None]
    out[..., 3] = 255
    return out


def _smooth_noise(n, cells, seed):
    """Naadloos herhalende ruis van n x n pixels."""
    rng = np.random.default_rng(seed)
    g = rng.random((cells, cells)).astype(np.float32)
    x = np.arange(n) * cells / n
    i0 = np.floor(x).astype(int)
    f = x - i0
    f = f * f * (3 - 2 * f)
    i1 = (i0 + 1) % cells
    rows = g[i0][:, i0] * (1 - f)[None, :] + g[i0][:, i1] * f[None, :]
    rows2 = g[i1][:, i0] * (1 - f)[None, :] + g[i1][:, i1] * f[None, :]
    return rows * (1 - f)[:, None] + rows2 * f[:, None]


def _fbm(n, seed):
    return sum(_smooth_noise(n, c, seed + k) / (k + 1) for k, c in enumerate((4, 8, 16, 32))) / 2.083


def _paint(n, fn):
    img = new_image(n, n)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    fn(p, n)
    p.end()
    return img


def _bricks(p, n):
    p.fillRect(0, 0, n, n, QColor(150, 150, 140))
    bh = n // 4
    for row in range(4):
        off = (n // 4) if row % 2 else 0
        for col in range(-1, 2):
            x = col * n // 2 + off
            c = QColor(160 + (row * 7 + col * 13) % 30, 70 + (row * 11) % 20, 50)
            p.fillRect(x + 2, row * bh + 2, n // 2 - 3, bh - 3, c)


def _checker(p, n):
    p.fillRect(0, 0, n, n, QColor(255, 255, 255))
    p.fillRect(0, 0, n // 2, n // 2, QColor(0, 0, 0))
    p.fillRect(n // 2, n // 2, n // 2, n // 2, QColor(0, 0, 0))


def _stripes(p, n):
    p.fillRect(0, 0, n, n, QColor(245, 245, 245))
    p.fillRect(0, 0, n, n // 2, QColor(40, 90, 170))


def _diagonal(p, n):
    p.fillRect(0, 0, n, n, QColor(255, 230, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(20, 20, 20))
    for k in (-1, 0, 1):
        path = QPainterPath()
        o = k * n
        path.moveTo(o, n)
        path.lineTo(o + n / 2, n)
        path.lineTo(o + n, 0)
        path.lineTo(o + n / 2, 0)
        path.closeSubpath()
        p.drawPath(path)


def _dots(p, n):
    p.fillRect(0, 0, n, n, QColor(255, 255, 255))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(220, 30, 60))
    r = n / 6
    for cx, cy in ((n / 4, n / 4), (3 * n / 4, 3 * n / 4)):
        p.drawEllipse(QPointF(cx, cy), r, r)


def _grid(p, n):
    p.fillRect(0, 0, n, n, QColor(255, 255, 255))
    p.setPen(QPen(QColor(120, 160, 220), 1))
    for k in range(0, n, n // 4):
        p.drawLine(k, 0, k, n)
        p.drawLine(0, k, n, k)


def _tiles(p, n):
    p.fillRect(0, 0, n, n, QColor(235, 235, 230))
    for i in range(2):
        for j in range(2):
            c = QColor(70, 130, 160) if (i + j) % 2 else QColor(220, 225, 230)
            p.fillRect(i * n // 2 + 1, j * n // 2 + 1, n // 2 - 2, n // 2 - 2, c)


def _zigzag(p, n):
    p.fillRect(0, 0, n, n, QColor(250, 240, 220))
    p.setPen(QPen(QColor(200, 60, 40), n / 8))
    for y0 in (n / 4, 3 * n / 4):
        path = QPainterPath(QPointF(-n / 4, y0))
        for k in range(5):
            path.lineTo(k * n / 4, y0 + (-n / 8 if k % 2 == 0 else n / 8))
        p.drawPath(path)


def _waves(p, n):
    p.fillRect(0, 0, n, n, QColor(225, 240, 255))
    p.setPen(QPen(QColor(30, 100, 190), n / 10))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for y0 in (n / 4, 3 * n / 4):
        path = QPainterPath(QPointF(0, y0))
        for k in range(n + 1):
            path.lineTo(k, y0 + math.sin(k / n * 2 * math.pi) * n / 10)
        p.drawPath(path)


def _hexes(p, n):
    p.fillRect(0, 0, n, n, QColor(250, 210, 80))
    p.setPen(QPen(QColor(150, 100, 20), 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    r = n / 4
    for cx, cy in ((0, 0), (n, 0), (0, n), (n, n), (n / 2, n / 2)):
        path = QPainterPath()
        for k in range(7):
            a = math.radians(60 * k)
            pt = QPointF(cx + r * math.cos(a), cy + r * math.sin(a))
            path.moveTo(pt) if k == 0 else path.lineTo(pt)
        p.drawPath(path)


def _numpy_pattern(kind, n=128):
    if kind == "Hout":
        y = np.arange(n, dtype=np.float32)[:, None] * np.ones((1, n), np.float32)
        noise = _fbm(n, 3)
        a = (np.sin((y / n * 6 + noise * 3) * 2 * math.pi) + 1) / 2
        return _np_img(_rgb(a ** 0.6, (110, 60, 25), (200, 140, 80)))
    if kind == "Marmer":
        x = np.arange(n, dtype=np.float32)[None, :] * np.ones((n, 1), np.float32)
        noise = _fbm(n, 7)
        a = np.abs(np.sin((x / n * 2 + noise * 4) * math.pi))
        return _np_img(_rgb(a ** 0.3, (90, 90, 100), (245, 245, 240)))
    if kind == "Wolken":
        return _np_img(_rgb(_fbm(n, 11), (60, 120, 220), (255, 255, 255)))
    if kind == "Zand":
        rng = np.random.default_rng(5)
        a = _fbm(n, 13) * 0.6 + rng.random((n, n)).astype(np.float32) * 0.4
        return _np_img(_rgb(a, (170, 140, 90), (240, 215, 160)))
    if kind == "Linnen":
        rng = np.random.default_rng(9)
        k = np.arange(n, dtype=np.float32)
        a = (np.sin(k * 2 * math.pi / 4)[None, :] + np.sin(k * 2 * math.pi / 4)[:, None]) / 4 + 0.5
        a = a * 0.7 + rng.random((n, n)).astype(np.float32) * 0.3
        return _np_img(_rgb(a, (190, 180, 160), (240, 235, 220)))
    return None


PATTERNS = {
    "Bakstenen": lambda: _paint(64, _bricks),
    "Schaakbord": lambda: _paint(32, _checker),
    "Strepen": lambda: _paint(16, _stripes),
    "Diagonaal": lambda: _paint(32, _diagonal),
    "Stippen": lambda: _paint(32, _dots),
    "Ruitjes": lambda: _paint(32, _grid),
    "Tegels": lambda: _paint(48, _tiles),
    "Zigzag": lambda: _paint(32, _zigzag),
    "Golven": lambda: _paint(48, _waves),
    "Honingraat": lambda: _paint(56, _hexes),
    "Hout": lambda: _numpy_pattern("Hout"),
    "Marmer": lambda: _numpy_pattern("Marmer"),
    "Wolken": lambda: _numpy_pattern("Wolken"),
    "Zand": lambda: _numpy_pattern("Zand"),
    "Linnen": lambda: _numpy_pattern("Linnen"),
}
_cache = {}


def pattern_image(name):
    """Ingebouwd patroon of een patroon uit PSP (op naam)."""
    if name not in _cache:
        if name in PATTERNS:
            _cache[name] = PATTERNS[name]()
        else:
            path = dict(psp_patterns()).get(name)
            img = QImage(path) if path else QImage()
            _cache[name] = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied) if not img.isNull() else None
    return _cache[name]


def pattern_names():
    return list(PATTERNS) + [n for n, _ in psp_patterns()]
