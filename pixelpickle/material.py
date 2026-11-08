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
from PySide6.QtCore import QPointF, QRect, QRectF, Qt
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
    # een punt kan ook (positie 0..1, kleur) zijn, voor ongelijke afstanden
    "Wit-transparant": ["#ffffff", "#ffffff00"],
    "Zwart-transparant": ["#000000", "#00000000"],
    "Regenboog vervagend": [(0, "#ff0000"), (0.2, "#ffff00"), (0.4, "#00ff00"), (0.6, "#00ffff"),
                            (0.8, "#0000ff"), (1, "#ff00ff00")],
    "Duotoon blauw": ["#e3f2fd", "#1e64c8", "#0a1f4d"],
    "Duotoon groen": ["#effae0", "#4caf50", "#0f3d14"],
    "Duotoon rood": ["#ffe5e0", "#d32f2f", "#4a0b0b"],
    "Duotoon paars": ["#f3e5f5", "#8e44ad", "#2e0b3d"],
    "Duotoon sepia": ["#fbf3e4", "#b07d4f", "#3b2414"],
    "Duotoon ivoor": ["#fffdf5", "#f1e6c8"],
    "Duotoon lavendel": ["#ece6f5", "#9b8bc0", "#463c5c"],
    "Grijstinten": ["#f2f2f2", "#9e9e9e", "#3a3a3a"],
    "Ochtend": [(0, "#1d4e89"), (0.45, "#7fb2e5"), (0.5, "#fde3a7"), (0.55, "#9ccc65"), (1, "#2e6b1f")],
    "Woestijn": [(0, "#7ec8f2"), (0.48, "#d9eef9"), (0.52, "#f2d29b"), (1, "#a8642a")],
    "Nacht": [(0, "#020617"), (0.6, "#1e2a5a"), (0.85, "#4b3b78"), (1, "#c76b98")],
    "Zomerlucht": ["#2f80ed", "#56ccf2", "#e0f7ff"],
    "Herfst": ["#5d2a0c", "#b5541c", "#e8a33d", "#f6d58e"],
    "Lente": ["#d4f5c4", "#8fd694", "#f9e79f", "#f8b4c8"],
    "Aarde": ["#3e2c1c", "#7a5c3a", "#a99067", "#d8c9a3"],
    "IJs": ["#ffffff", "#d6f1ff", "#8fd3f4", "#3b8fc4"],
    "Lava": ["#1a0000", "#7a0c00", "#e33b00", "#ffb000", "#fff3a0"],
    "Aurora": ["#04121f", "#0b6e4f", "#30d5a0", "#7b4bc9", "#04121f"],
    "Pauw": ["#023047", "#0a9396", "#94d2bd", "#2a9d8f", "#005f73"],
    "Neon blauw": [(0, "#001a33"), (0.35, "#00b4ff"), (0.5, "#e6fbff"), (0.65, "#00b4ff"), (1, "#001a33")],
    "Neon roze": [(0, "#2a0018"), (0.35, "#ff2d95"), (0.5, "#ffe3f1"), (0.65, "#ff2d95"), (1, "#2a0018")],
    "Neon groen": [(0, "#001a05"), (0.35, "#39ff14"), (0.5, "#eaffe5"), (0.65, "#39ff14"), (1, "#001a05")],
    "Chroom": [(0, "#2b2b2b"), (0.3, "#f5f5f5"), (0.48, "#8a8a8a"), (0.52, "#3a3a3a"), (0.75, "#d9d9d9"),
               (1, "#5c5c5c")],
    "Staal": [(0, "#4b5563"), (0.25, "#d1d5db"), (0.5, "#6b7280"), (0.75, "#e5e7eb"), (1, "#374151")],
    "Messing": [(0, "#6b4e16"), (0.3, "#e9c46a"), (0.5, "#a07a2c"), (0.75, "#f4dc8f"), (1, "#5c4211")],
    "Brons": [(0, "#4a2c12"), (0.3, "#cd7f32"), (0.55, "#7a4a1e"), (0.8, "#e3a869"), (1, "#3d230d")],
    "Rosé goud": [(0, "#7a4a3f"), (0.3, "#f2c2b0"), (0.55, "#b77b6a"), (0.8, "#fbe0d6"), (1, "#6e4035")],
    "Blauw metaal": [(0, "#0b1d3a"), (0.3, "#9fb6e0"), (0.5, "#2b4a80"), (0.75, "#d6e2f5"), (1, "#122a52")],
}


def default_gradient():
    return {"kind": "gradient", "preset": "Voorgrond-achtergrond", "style": 0, "angle": 0, "repeats": 0,
            "invert": False, "cx": 50, "cy": 50}


def default_pattern():
    return {"kind": "pattern", "name": "Bakstenen", "image": pattern_image("Bakstenen"), "angle": 0, "scale": 100}


# eigen verlopen (verloopbewerker), bewaard in de instellingen: {naam: [[positie, spec], ...]}
USER_PREFIX = "user:"
USER_GRADIENTS = {}


def set_user_gradients(d):
    USER_GRADIENTS.clear()
    for k, v in (d or {}).items():
        try:
            USER_GRADIENTS[str(k)] = [(float(p), str(c)) for p, c in v]
        except (TypeError, ValueError):
            continue


def _rgba(spec, fg, bg):
    if ":" in spec and spec.split(":")[0] in (FG, BG):  # voor- of achtergrondkleur met eigen dekking
        src, alpha = spec.split(":", 1)
        c = QColor(fg if src == FG else bg)
        return (c.red(), c.green(), c.blue(), max(0, min(255, int(float(alpha)))))
    if spec in (FG, FG0, BG, BG0):
        c = QColor(fg if spec in (FG, FG0) else bg)
        return (c.red(), c.green(), c.blue(), 0 if spec.endswith("0") else c.alpha())
    if len(spec) == 9:  # #rrggbbaa
        return (int(spec[1:3], 16), int(spec[3:5], 16), int(spec[5:7], 16), int(spec[7:9], 16))
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
    if name and name.startswith(USER_PREFIX) and name[len(USER_PREFIX):] in USER_GRADIENTS:
        entries = USER_GRADIENTS[name[len(USER_PREFIX):]]
    else:
        entries = GRADIENTS.get(name, GRADIENTS["Voorgrond-achtergrond"])
    return stops_lut(entries, fg, bg)


def stops_lut(entries, fg, bg):
    """256 x 4 tabel uit kleurpunten: specs op gelijke afstand of [(positie, spec)]."""
    x = np.linspace(0, 1, 256)
    if all(isinstance(e, (tuple, list)) for e in entries):
        entries = sorted(entries, key=lambda e: float(e[0]))
        pos = [float(e[0]) for e in entries]
        stops = [_rgba(e[1], fg, bg) for e in entries]
    else:
        pos = np.linspace(0, 1, len(entries))
        stops = [_rgba(e, fg, bg) for e in entries]
    return _interp(x, pos, stops)


def gradient_names():
    """Sleutels van alle verlopen: ingebouwd, zelf gemaakt, dan die uit een eigen installatie."""
    return list(GRADIENTS) + [USER_PREFIX + n for n in USER_GRADIENTS] + list(psp_gradients())


def gradient_label(key):
    from .i18n import tr
    if key.startswith(USER_PREFIX):
        return key[len(USER_PREFIX):]
    return tr(key[4:]) if key.startswith("psp:") else tr(key)


def gradient_stops(name):
    """Kleurpunten van een verloop om te bewerken: [(positie, spec)], specs als in GRADIENTS."""
    if name.startswith(USER_PREFIX):
        return list(USER_GRADIENTS.get(name[len(USER_PREFIX):], []))
    psp = psp_gradients().get(name)
    if psp is not None:  # PSP-verloop: kleuren en (vereenvoudigd) dekking per kleurpunt
        cstops, astops = psp
        out = []
        for pos, _, rgb, typ in cstops:
            a = int(_interp([pos], [p[0] for p in astops], [[p[2]] for p in astops])[0][0]) if astops else 255
            spec = f"{FG}:{a}" if typ == 1 else f"{BG}:{a}" if typ == 2 else "#%02x%02x%02x%02x" % (*rgb, a)
            out.append((float(pos), spec))
        return out
    entries = GRADIENTS.get(name, GRADIENTS["Voorgrond-achtergrond"])
    if all(isinstance(e, tuple) for e in entries):
        return [(float(p), c) for p, c in entries]
    n = len(entries)
    return [(i / max(n - 1, 1), c) for i, c in enumerate(entries)]


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
    """[(naam, pad)] van de patronen uit een eigen installatie, de map Patronen/Patterns van de gebruiker en
    de eigen map met patronen (Bestand > Voorkeuren > Bestandslocaties)."""
    global _psp_pat
    if _psp_pat is None:
        import glob
        _psp_pat, seen = [], set()
        exts = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff")
        for d in psp_dirs():
            cands = glob.glob(os.path.join(glob.escape(d), "Corel_08", "**", "*"), recursive=True)
            for sub in ("Patronen", "Patterns"):
                cands += glob.glob(os.path.join(glob.escape(d), sub, "**", "*"), recursive=True)
            for f in sorted(cands):
                stem, ext = os.path.splitext(os.path.basename(f))
                name = _pattern_name(stem)
                if name in PATTERNS:  # zelfde naam als een eigen patroon: apart houden
                    name += " 2"
                if ext.lower() in exts and name not in seen:
                    seen.add(name)
                    _psp_pat.append((name, f))
        try:  # eigen map met patronen
            from . import userdata
            own = userdata.folder("patterns", create=False)
            if os.path.isdir(own):
                for f in sorted(glob.glob(os.path.join(glob.escape(own), "**", "*"), recursive=True)):
                    stem, ext = os.path.splitext(os.path.basename(f))
                    if ext.lower() in exts and stem not in seen and stem not in PATTERNS:
                        seen.add(stem)
                        _psp_pat.append((stem, f))
        except Exception:  # noqa: BLE001 - een onleesbare map mag de patronen niet breken
            pass
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


# ---------------------------------------------------------------- meer eigen patronen (naadloos)
def _ramp(a, colors):
    """a in 0..1 -> kleur langs een reeks kleuren (hex)."""
    cols = np.array([[int(c[k:k + 2], 16) for k in (1, 3, 5)] for c in colors], np.float32)
    pos = np.linspace(0, 1, len(cols))
    out = np.empty(a.shape + (4,), np.float32)
    for ch in range(3):
        out[..., ch] = np.interp(a, pos, cols[:, ch])
    out[..., 3] = 255
    return out


def _voronoi(n, count, seed):
    """Naadloze Voronoi-cellen: (afstand tot dichtstbijzijnde punt, tot op één na, celnummer)."""
    rng = np.random.default_rng(seed)
    pts = rng.random((count, 2)) * n
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    d1 = np.full((n, n), 1e9, np.float32)
    d2 = np.full((n, n), 1e9, np.float32)
    idx = np.zeros((n, n), np.int32)
    for k, (px, py) in enumerate(pts):
        dx = np.abs(xx - px)
        dy = np.abs(yy - py)
        dx = np.minimum(dx, n - dx)
        dy = np.minimum(dy, n - dy)
        d = np.hypot(dx, dy)
        closer = d < d1
        d2 = np.where(closer, d1, np.minimum(d2, d))
        idx = np.where(closer, k, idx)
        d1 = np.where(closer, d, d1)
    return d1, d2, idx


def _coords(n):
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    return xx, yy


def _pat_leopard(n=128):
    d1, d2, idx = _voronoi(n, 28, 21)
    base = _ramp(_fbm(n, 22) * 0.6 + 0.2, ["#c98f3c", "#e8b765"])
    edge = d2 - d1
    ring = (d1 > 4.5) & (d1 < 8.5) & (edge > 1.5)
    centre = d1 <= 4.5
    base[ring, :3] = (40, 25, 12)
    base[centre, :3] = base[centre, :3] * 0.8
    return _np_img(base)


def _pat_zebra(n=128):
    xx, yy = _coords(n)
    # rustige, golvende strepen: alleen grove vervorming
    warp = _smooth_noise(n, 3, 31) * 1.4 + _smooth_noise(n, 6, 32) * 0.35
    v = np.sin((xx / n * 5 + warp) * 2 * math.pi)
    a = np.clip((v + 0.15) * 4, 0, 1)  # zachte maar duidelijke rand
    return _np_img(_ramp(a, ["#f4f1ea", "#151515"]))


def _pat_tiger(n=128):
    xx, yy = _coords(n)
    warp = _fbm(n, 41) * 2.5
    v = np.sin((yy / n * 5 + warp) * 2 * math.pi)
    width = _smooth_noise(n, 4, 42) * 0.6
    a = (v > 0.75 - width).astype(np.float32)
    base = _ramp(_fbm(n, 43) * 0.5 + 0.25, ["#d46a1c", "#f2a345"])
    base[a > 0, :3] = (25, 15, 10)
    return _np_img(base)


def _pat_giraffe(n=128):
    d1, d2, idx = _voronoi(n, 14, 51)
    rng = np.random.default_rng(52)
    shade = rng.random(14)[idx] * 0.25
    a = np.where(d2 - d1 < 3.2, 0.0, 0.6 + shade)
    return _np_img(_ramp(a, ["#f3e3c2", "#b8662b", "#8a4519"]))


def _pat_snake(n=128):
    xx, yy = _coords(n)
    s_ = n / 8
    row = np.floor(yy / s_)
    x2 = xx + (row % 2) * s_ / 2
    cx = (np.floor(x2 / s_) + 0.5) * s_
    cy = (row + 0.5) * s_
    d = np.hypot(x2 - cx, (yy - cy) * 1.3) / (s_ * 0.55)
    a = np.clip(1 - d, 0, 1) ** 0.5
    return _np_img(_ramp(a * 0.8 + _fbm(n, 61) * 0.2, ["#1f2a14", "#4f6b2a", "#a7b56a"]))


def _pat_crackle(n=128):
    d1, d2, _ = _voronoi(n, 30, 71)
    a = np.clip((d2 - d1) / 3.0, 0, 1)
    return _np_img(_ramp(a * 0.85 + _fbm(n, 72) * 0.15, ["#4a4038", "#e8dfcf", "#f6f0e4"]))


def _pat_paper(n=128):
    rng = np.random.default_rng(81)
    a = _fbm(n, 82) * 0.5 + rng.random((n, n)).astype(np.float32) * 0.15 + 0.35
    return _np_img(_ramp(a, ["#e9e4d8", "#fbf8f0"]))


def _pat_kraft(n=128):
    rng = np.random.default_rng(91)
    a = _fbm(n, 92) * 0.6 + rng.random((n, n)).astype(np.float32) * 0.25
    return _np_img(_ramp(a, ["#8f6a3e", "#c49a64"]))


def _pat_denim(n=128):
    xx, yy = _coords(n)
    twill = ((xx + yy) % 4 < 2).astype(np.float32)
    rng = np.random.default_rng(101)
    a = twill * 0.35 + _fbm(n, 102) * 0.35 + rng.random((n, n)).astype(np.float32) * 0.3
    return _np_img(_ramp(a, ["#1c2e52", "#3d5a8c", "#8fa8cf"]))


def _pat_tartan(p, n):
    """Schotse ruit: rode grond met doorschijnende groene en blauwe banen en een dunne gele lijn."""
    p.fillRect(0, 0, n, n, QColor(176, 30, 38))
    bands = ((0, n * 0.30, QColor(25, 80, 50, 150)), (n * 0.38, n * 0.12, QColor(25, 40, 95, 150)),
             (n * 0.62, n * 0.04, QColor(240, 200, 60, 200)), (n * 0.75, n * 0.10, QColor(25, 80, 50, 120)))
    for start, w, col in bands:
        p.fillRect(QRectF(start, 0, w, n), col)
        p.fillRect(QRectF(0, start, n, w), col)
    p.setPen(QPen(QColor(0, 0, 0, 40), 1))  # fijne weefstructuur
    for k in range(-n, n, 3):
        p.drawLine(QPointF(k, 0), QPointF(k + n, n))


def _pat_argyle(p, n):
    """Ruitpatroon (argyle): ruiten in twee tinten met een fijne stippellijn eroverheen."""
    p.fillRect(0, 0, n, n, QColor(40, 60, 110))
    p.setPen(Qt.PenStyle.NoPen)
    h = n / 2
    for cx, cy, col in ((h, h, QColor(200, 170, 90)), (0, 0, QColor(120, 40, 50)), (n, 0, QColor(120, 40, 50)),
                        (0, n, QColor(120, 40, 50)), (n, n, QColor(120, 40, 50))):
        p.setBrush(col)
        path = QPainterPath(QPointF(cx, cy - h))
        path.lineTo(cx + h / 2, cy)
        path.lineTo(cx, cy + h)
        path.lineTo(cx - h / 2, cy)
        path.closeSubpath()
        p.drawPath(path)
    pen = QPen(QColor(240, 240, 230), 1.2)
    pen.setDashPattern([3, 3])
    p.setPen(pen)
    for k in range(-2, 3):  # lijnen door de hoeken van de ruiten, naadloos herhalend
        p.drawLine(QPointF(k * h, 0), QPointF(k * h + h, n))
        p.drawLine(QPointF(k * h + h, 0), QPointF(k * h, n))


def _pat_herringbone(p, n):
    p.fillRect(0, 0, n, n, QColor(150, 105, 60))
    w, h = n / 8, n / 2
    for k in range(-2, 10):
        for j in range(-1, 3):
            x, y = k * w, j * h + (k % 2) * h / 2
            path = QPainterPath()
            if k % 2 == 0:
                path.moveTo(x, y + w)
                path.lineTo(x + w, y)
                path.lineTo(x + w, y + h)
                path.lineTo(x, y + h + w)
            else:
                path.moveTo(x, y)
                path.lineTo(x + w, y + w)
                path.lineTo(x + w, y + h + w)
                path.lineTo(x, y + h)
            path.closeSubpath()
            tone = 120 + ((k * 7 + j * 13) % 5) * 12
            p.setBrush(QColor(tone + 40, tone - 5, tone - 55))
            p.setPen(QPen(QColor(70, 45, 25), 1))
            p.drawPath(path)


def _pat_cork(n=128):
    rng = np.random.default_rng(111)
    a = _fbm(n, 112) * 0.5 + rng.random((n, n)).astype(np.float32) * 0.5
    a = np.where(rng.random((n, n)) < 0.04, a * 0.4, a)
    return _np_img(_ramp(a, ["#6b4423", "#b98552", "#d9a96f"]))


def _pat_granite(n=128):
    rng = np.random.default_rng(121)
    a = rng.random((n, n)).astype(np.float32) * 0.5 + _fbm(n, 122) * 0.5
    img = _ramp(a, ["#3a3a3a", "#8c8c8c", "#d6d6d6"])
    spots = rng.random((n, n)) < 0.03
    img[spots, :3] = (180, 120, 110)
    return _np_img(img)


def _pat_leather(n=128):
    d1, d2, _ = _voronoi(n, 60, 131)
    a = np.clip((d2 - d1) / 2.5, 0, 1) * 0.6 + _fbm(n, 132) * 0.4
    return _np_img(_ramp(a, ["#3b2414", "#7a4a26", "#a8693a"]))


def _pat_corrugated(n=64):
    xx, yy = _coords(n)
    a = (np.sin(xx / n * 8 * 2 * math.pi) + 1) / 2
    return _np_img(_ramp(a, ["#8a6a42", "#d6b27c"]))


def _pat_bubbles(p, n):
    p.fillRect(0, 0, n, n, QColor(30, 90, 170))
    rng = np.random.default_rng(141)
    for _ in range(18):
        x, y, r = rng.random() * n, rng.random() * n, 4 + rng.random() * 10
        for dx in (-n, 0, n):
            for dy in (-n, 0, n):
                g = QPointF(x + dx, y + dy)
                p.setPen(QPen(QColor(200, 230, 255, 200), 1.5))
                p.setBrush(QColor(120, 180, 240, 90))
                p.drawEllipse(g, r, r)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(255, 255, 255, 200))
                p.drawEllipse(QPointF(g.x() - r * 0.35, g.y() - r * 0.35), r * 0.22, r * 0.22)


def _scatter(p, n, seed, count, draw):
    rng = np.random.default_rng(seed)
    for _ in range(count):
        x, y = rng.random() * n, rng.random() * n
        c = rng.random(3)
        for dx in (-n, 0, n):
            for dy in (-n, 0, n):
                draw(p, x + dx, y + dy, c, rng)


def _pat_confetti(p, n):
    p.fillRect(0, 0, n, n, QColor(255, 255, 255))
    cols = [QColor("#e63946"), QColor("#f4a261"), QColor("#2a9d8f"), QColor("#457b9d"), QColor("#e9c46a"),
            QColor("#9b5de5")]

    def draw(p, x, y, c, rng):
        p.save()
        p.translate(x, y)
        p.rotate(c[0] * 360)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(cols[int(c[1] * len(cols)) % len(cols)])
        p.drawRect(QRectF(-3, -1.5, 6, 3))
        p.restore()
    _scatter(p, n, 151, 40, draw)


def _pat_stars(p, n):
    p.fillRect(0, 0, n, n, QColor(10, 14, 40))

    def draw(p, x, y, c, rng):
        r = 0.6 + c[0] * 1.6
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 230, int(140 + c[1] * 115)))
        p.drawEllipse(QPointF(x, y), r, r)
    _scatter(p, n, 161, 45, draw)


def _pat_hearts(p, n):
    p.fillRect(0, 0, n, n, QColor(255, 235, 240))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(220, 40, 80))
    for cx, cy in ((n / 4, n / 4), (3 * n / 4, 3 * n / 4)):
        s_ = n / 7
        path = QPainterPath(QPointF(cx, cy + s_))
        path.cubicTo(QPointF(cx - 1.6 * s_, cy), QPointF(cx - 0.8 * s_, cy - 1.1 * s_), QPointF(cx, cy - 0.4 * s_))
        path.cubicTo(QPointF(cx + 0.8 * s_, cy - 1.1 * s_), QPointF(cx + 1.6 * s_, cy), QPointF(cx, cy + s_))
        p.drawPath(path)


def _pat_flowers(p, n):
    p.fillRect(0, 0, n, n, QColor(240, 248, 232))
    for cx, cy, col in ((n / 4, n / 4, "#e76f51"), (3 * n / 4, 3 * n / 4, "#6d5dfc")):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(col))
        for k in range(5):
            a = math.radians(k * 72)
            p.drawEllipse(QPointF(cx + math.cos(a) * n / 14, cy + math.sin(a) * n / 14), n / 16, n / 16)
        p.setBrush(QColor("#f4d35e"))
        p.drawEllipse(QPointF(cx, cy), n / 20, n / 20)


def _pat_mosaic(n=128):
    d1, d2, idx = _voronoi(n, 40, 171)
    rng = np.random.default_rng(172)
    pal = np.array([[int(c[k:k + 2], 16) for k in (1, 3, 5)] for c in
                    ("#1d3557", "#457b9d", "#a8dadc", "#e9c46a", "#e76f51", "#2a9d8f")], np.float32)
    cols = pal[rng.integers(0, len(pal), 40)][idx]
    img = np.empty((n, n, 4), np.float32)
    img[..., :3] = cols
    img[..., 3] = 255
    img[(d2 - d1) < 1.6, :3] = (235, 230, 220)
    return _np_img(img)


def _pat_terrazzo(n=128):
    rng = np.random.default_rng(181)
    img = _ramp(_fbm(n, 182) * 0.3 + 0.6, ["#d9d4cc", "#f1ede6"])
    d1, d2, idx = _voronoi(n, 70, 183)
    chips = d1 < 2.0 + rng.random(70)[idx] * 3
    pal = np.array([[200, 90, 70], [60, 70, 80], [230, 180, 90], [120, 150, 140]], np.float32)
    img[chips, :3] = pal[rng.integers(0, 4, 70)][idx][chips]
    return _np_img(img)


def _pat_camo(n=128):
    a = _fbm(n, 191)
    b = _fbm(n, 192)
    img = _ramp(np.zeros((n, n), np.float32), ["#5b6b3a", "#5b6b3a"])
    img[a > 0.48, :3] = (120, 110, 70)
    img[b > 0.52, :3] = (45, 50, 30)
    img[(a < 0.38) & (b < 0.42), :3] = (150, 140, 100)
    return _np_img(img)


def _pat_rust(n=128):
    rng = np.random.default_rng(201)
    a = _fbm(n, 202) * 0.7 + rng.random((n, n)).astype(np.float32) * 0.3
    return _np_img(_ramp(a, ["#3d1f10", "#8b3a12", "#c26a2a", "#d9a066"]))


def _pat_concrete(n=128):
    rng = np.random.default_rng(211)
    a = _fbm(n, 212) * 0.6 + rng.random((n, n)).astype(np.float32) * 0.25 + 0.1
    img = _ramp(a, ["#8a8a86", "#c4c3be"])
    pores = rng.random((n, n)) < 0.01
    img[pores, :3] = (90, 90, 88)
    return _np_img(img)


def _pat_grass(p, n):
    p.fillRect(0, 0, n, n, QColor(70, 120, 40))
    rng = np.random.default_rng(221)
    for _ in range(260):
        x, y = rng.random() * n, rng.random() * n
        h = 6 + rng.random() * 10
        lean = (rng.random() - 0.5) * 6
        g = int(110 + rng.random() * 100)
        p.setPen(QPen(QColor(40 + int(rng.random() * 50), g, 30), 1.2))
        for dx in (-n, 0, n):
            for dy in (-n, 0, n):
                p.drawLine(QPointF(x + dx, y + dy), QPointF(x + dx + lean, y + dy - h))


def _pat_wood_dark(n=128):
    xx, yy = _coords(n)
    a = (np.sin((xx / n * 10 + _fbm(n, 231) * 2.5) * 2 * math.pi) + 1) / 2
    return _np_img(_ramp(a ** 0.7, ["#2b160a", "#5a3218", "#7a4724"]))


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
    "Luipaard": _pat_leopard,
    "Zebra": _pat_zebra,
    "Tijger": _pat_tiger,
    "Giraf": _pat_giraffe,
    "Slangenhuid": _pat_snake,
    "Craquelé": _pat_crackle,
    "Papier": _pat_paper,
    "Pakpapier": _pat_kraft,
    "Spijkerstof": _pat_denim,
    "Schotse ruit": lambda: _paint(96, _pat_tartan),
    "Ruitpatroon": lambda: _paint(64, _pat_argyle),
    "Visgraat": lambda: _paint(64, _pat_herringbone),
    "Kurk": _pat_cork,
    "Graniet": _pat_granite,
    "Leer": _pat_leather,
    "Golfkarton": _pat_corrugated,
    "Bubbels": lambda: _paint(96, _pat_bubbles),
    "Confetti": lambda: _paint(96, _pat_confetti),
    "Sterrenhemel": lambda: _paint(128, _pat_stars),
    "Hartjes": lambda: _paint(48, _pat_hearts),
    "Bloemetjes": lambda: _paint(64, _pat_flowers),
    "Mozaïek": _pat_mosaic,
    "Terrazzo": _pat_terrazzo,
    "Camouflage": _pat_camo,
    "Roest": _pat_rust,
    "Beton": _pat_concrete,
    "Gras": lambda: _paint(96, _pat_grass),
    "Donker hout": _pat_wood_dark,
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
