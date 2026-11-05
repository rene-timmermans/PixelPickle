"""3D-effecten, kunstzinnige effecten (Art Media) en artistieke effecten (menu Effecten).

Eigen benaderingen van de Paint Shop Pro XI effecten; alleen NumPy en Pillow.
"""
import math

import numpy as np

from ..imageops import box_blur
from . import Bool, Choice, Color, Int, effect
from .common import blur, blur as _gblur, gray, hsl_to_rgb, noise, remap, rgb_to_hsl, smooth_noise, sobel, to_u8

BEVEL_SHAPES = ["Schuin", "Rond", "Hol", "Dubbel", "Rug", "Getrapt"]


# ---------------------------------------------------------------- hulpfuncties

def _px(v, ctx, lo=1.0):
    return max(lo, v * ctx.scale)


def _rgb(a):
    return a[..., :3].astype(np.float32)


def _alpha(a):
    return a[..., 3].astype(np.float32) / 255


def _out(a, rgb, alpha=None):
    out = a.copy()
    out[..., :3] = to_u8(rgb)
    if alpha is not None:
        out[..., 3] = to_u8(alpha * 255)
    return out


def _shift(x, dy, dx, fill=0.0):
    """Verschuif een 2D array over (dy, dx) gehele pixels; vrijgekomen ruimte krijgt fill."""
    h, w = x.shape[:2]
    out = np.full_like(x, fill)
    dy, dx = int(round(dy)), int(round(dx))
    if abs(dy) >= h or abs(dx) >= w:
        return out
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    out[yd, xd] = x[ys, xs]
    return out


def _blur1(x, r):
    """Eén doorgang boxvervaging (lineaire helling bij randen)."""
    r = int(round(r))
    return box_blur(x.astype(np.float32), r, passes=1) if r >= 1 else x.astype(np.float32)


def _dist_inside(mask, w, pad=True):
    """0 op de rand van het masker (of de beeldrand), oplopend tot 1 op afstand w binnenin."""
    w = max(1, int(round(w)))
    if pad:
        p = w + 1
        m = np.pad(mask, p)
        b = _blur1(m, w)[p:-p, p:-p]
    else:
        b = _blur1(mask, w)
    return np.clip(2 * b - 1, 0, 1)


def _dist_outside(mask, w):
    """1 binnen het masker, aflopend naar 0 op afstand w erbuiten."""
    w = max(1, int(round(w)))
    return np.clip(2 * _blur1(mask, w), 0, 1)


def _profile(d, shape):
    d = np.clip(d, 0, 1)
    if shape == 1:
        return np.sqrt(1 - (1 - d) ** 2)
    if shape == 2:
        return 1 - np.sqrt(np.clip(1 - d * d, 0, 1))
    if shape == 3:
        t = np.clip(d * 2, 0, 2)
        f = np.floor(np.minimum(t, 1.999))
        s = t - f
        return (f + s * s * (3 - 2 * s)) / 2
    if shape == 4:
        return np.sin(np.pi * d)
    if shape == 5:
        t = d * 3
        f = np.floor(np.minimum(t, 2.999))
        s = np.clip((t - f) * 2, 0, 1)
        return (f + s) / 3
    return d


def _light(H, angle, elev, shininess=0):
    """Belichting van hoogteveld H (pixels). angle: 0 = boven, met de klok mee (graden).
    Geeft (diffuus verschil t.o.v. vlak, spiegeling) terug."""
    gx, gy = sobel(H)
    gx /= 8
    gy /= 8
    nz = 1 / np.sqrt(gx * gx + gy * gy + 1)
    nx, ny = -gx * nz, -gy * nz
    a, e = math.radians(angle), math.radians(elev)
    lx, ly, lz = math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)
    diff = nx * lx + ny * ly + nz * lz - lz
    hx, hy, hz = lx, ly, lz + 1
    n = math.sqrt(hx * hx + hy * hy + hz * hz)
    hx, hy, hz = hx / n, hy / n, hz / n
    p = 6 + shininess * 1.5
    spec = np.clip(nx * hx + ny * hy + nz * hz, 0, 1) ** p - hz ** p
    return diff, np.clip(spec, 0, 1)


def _apply_light(rgb, diff, spec, color=(255, 255, 255), intensity=1.0, shine=0.0, ambience=0.0):
    col = np.asarray(color, np.float32)
    base = rgb * (1 + ambience)
    d = (diff * intensity * 2.2)[..., None]
    out = np.where(d > 0, base + d * col, base * (1 + d))
    return out + (spec * shine)[..., None] * col


def _hash(*arrs, seed=1):
    x = np.uint64((seed * 0x9E3779B97F4A7C15 + 0x632BE5AB) & 0xFFFFFFFFFFFFFFFF)
    with np.errstate(over="ignore"):
        for v in arrs:
            x = (x ^ np.asarray(v).astype(np.int64).astype(np.uint64)) * np.uint64(0xFF51AFD7ED558CCD)
            x = x ^ (x >> np.uint64(29))
        x = x * np.uint64(0xC4CEB9FE1A85EC53)
        x = x ^ (x >> np.uint64(32))
    return ((x >> np.uint64(40)).astype(np.float32)) / float(1 << 24)


def _strokes(h, w, angle, width, length, seed=1):
    """Streeptextuur: (waarde per streek 0..1, profiel 0..1 dwars en langs de streek)."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    u = xx * ca + yy * sa
    v = -xx * sa + yy * ca
    vw = v / max(width, 0.5)
    row = np.floor(vw)
    fr = vw - row
    length = max(length, 1.0)
    us = (u + _hash(row, seed=seed) * length) / length
    seg = np.floor(us)
    t = us - seg
    val = _hash(row, seg, seed=seed + 7)
    prof = np.sin(np.pi * fr) * np.sqrt(np.sin(np.pi * t))
    return val, prof.astype(np.float32)


def _edges(g, r=1.0):
    gx, gy = sobel(blur(g, r))
    return np.hypot(gx, gy)


# ---------------------------------------------------------------- 3D-effecten

@effect(0x80a0, "Als knop", [Int("height", "Hoogte", 1, 250, 34), Int("width", "Breedte", 1, 250, 34),
                              Int("opacity", "Dekking", 1, 100, 75),
                              Choice("edge", "Rand", ["Massief", "Transparant"], 1),
                              Color("color", "Kleur", "bg")])
def buttonize(a, ctx, height, width, opacity, edge, color):
    h, w = a.shape[:2]
    hh = min(_px(height, ctx), max(1.0, h / 2))
    ww = min(_px(width, ctx), max(1.0, w / 2))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.stack([yy / hh, xx / ww, (w - 1 - xx) / ww, (h - 1 - yy) / hh])  # boven, links, rechts, onder
    reg = np.argmin(d, axis=0)
    m = np.min(d, axis=0)
    band = m < 1
    sign = np.array([1.0, 0.6, -0.6, -1.0], np.float32)[reg]
    op = opacity / 100
    rgb = _rgb(a)
    if edge == 1:
        amt = (op * (1 - np.clip(m, 0, 1)) * np.abs(sign))[..., None]
        lit = rgb + (255 - rgb) * amt
        dark = rgb * (1 - amt)
        res = np.where((sign > 0)[..., None], lit, dark)
    else:
        c = np.asarray(color, np.float32)
        s = np.abs(sign)[..., None] * 0.6
        shaded = np.where((sign > 0)[..., None], c + (255 - c) * s, c * (1 - s))
        res = rgb * (1 - op) + shaded * op
    res = np.where(band[..., None], res, rgb)
    return _out(a, res)


@effect(0x80a2, "Ciseleren", [Int("size", "Grootte", 1, 200, 20), Bool("transparent", "Transparant", True),
                              Color("color", "Kleur", "bg")])
def chisel(a, ctx, size, transparent, color):
    s = _px(size, ctx)
    al = _alpha(a)
    rgb = _rgb(a)
    col = np.asarray(color, np.float32)
    if al.min() > 0.98:
        d = _dist_inside(np.ones_like(al), s)
        band = d < 1
        diff, _ = _light(d * s, 315, 30)
        base = rgb if transparent else np.broadcast_to(col, rgb.shape)
        res = _apply_light(base, diff, 0 * diff, intensity=0.6)
        return _out(a, np.where(band[..., None], res, rgb))
    hgt = _dist_outside(al, s)
    ring = (hgt > 0) & (al < 0.999)
    diff, _ = _light((1 - hgt) * -s, 315, 30)
    if transparent:
        shade = np.where(diff > 0, 255.0, 0.0)
        ra = np.clip(np.abs(diff) * 2.5, 0, 0.85) * (hgt > 0)
        base_rgb = np.broadcast_to(shade[..., None], rgb.shape)
    else:
        base_rgb = _apply_light(np.broadcast_to(col, rgb.shape), diff, 0 * diff, intensity=0.6)
        ra = np.clip(hgt * 50, 0, 1)
    ra = np.where(ring, ra, 0)
    oa = al + ra * (1 - al)
    res = (rgb * al[..., None] + base_rgb * (ra * (1 - al))[..., None]) / np.maximum(oa, 1e-6)[..., None]
    return _out(a, res, oa)


@effect(0x809f, "Gestanst", [Int("vertical", "Verticaal", -100, 100, 10), Int("horizontal", "Horizontaal", -100, 100, 10),
                             Int("opacity", "Dekking", 1, 100, 60), Int("blur", "Vervaging", 0, 100, 15),
                             Color("shadow", "Schaduwkleur", (0, 0, 0)),
                             Bool("fill", "Binnenkant opvullen met kleur", False),
                             Color("fillcolor", "Opvulkleur", (255, 255, 255))])
def cutout(a, ctx, vertical, horizontal, opacity, blur, shadow, fill, fillcolor):
    al = _alpha(a)
    dy, dx = vertical * ctx.scale, horizontal * ctx.scale
    r = blur * ctx.scale
    p = int(abs(dy) + abs(dx) + 3 * r + 3)
    outside = np.pad(1 - al, p, constant_values=1.0)
    sh = _shift(outside, dy, dx, 1.0)
    sh = _gblur(sh, r / 2)[p:-p, p:-p]
    s = (np.clip(sh, 0, 1) * opacity / 100)[..., None]
    interior = np.broadcast_to(np.asarray(fillcolor, np.float32), a.shape[:2] + (3,)) if fill else _rgb(a)
    res = interior * (1 - s) + np.asarray(shadow, np.float32) * s
    return _out(a, res)


@effect(0x809e, "Slagschaduw", [Int("vertical", "Verticaal", -100, 100, 10), Int("horizontal", "Horizontaal", -100, 100, 10),
                                Int("opacity", "Dekking", 1, 100, 50), Int("blur", "Vervaging", 0, 100, 5),
                                Color("color", "Kleur", (0, 0, 0))])
def drop_shadow(a, ctx, vertical, horizontal, opacity, blur, color):
    al = _alpha(a)
    r = blur * ctx.scale
    sh = _shift(al, vertical * ctx.scale, horizontal * ctx.scale, 0.0)
    sh = _gblur(sh, r / 2)
    s = np.clip(sh, 0, 1) * opacity / 100
    oa = al + s * (1 - al)
    res = (_rgb(a) * al[..., None] + np.asarray(color, np.float32) * (s * (1 - al))[..., None]) \
        / np.maximum(oa, 1e-6)[..., None]
    return _out(a, res, oa)


_BEVEL_PARAMS = [Choice("shape", "Afschuining", BEVEL_SHAPES, 0), Int("width", "Breedte", 1, 100, 20),
                 Int("smoothness", "Gladheid", 0, 100, 20), Int("depth", "Diepte", 1, 100, 10),
                 Int("ambience", "Omgevingslicht", -100, 100, 0), Int("shininess", "Glans", 0, 100, 0),
                 Int("angle", "Hoek", 0, 359, 315), Int("intensity", "Intensiteit", 0, 100, 50),
                 Int("elevation", "Hoogte", 0, 90, 30), Color("color", "Kleur", (255, 255, 255))]


def _bevel_light(rgb, d, ctx, shape, width, smoothness, depth, ambience, shininess, angle, intensity, elevation, color):
    wpx = _px(width, ctx)
    H = _profile(d, shape)
    sm = smoothness / 100 * wpx * 0.5
    H = blur(H, sm) if sm >= 1 else blur(H, 1) if wpx > 3 else H
    H = H * depth * ctx.scale * 2
    diff, spec = _light(H, angle, elevation, shininess)
    return _apply_light(rgb, diff, spec, color, intensity / 100, shininess / 100, ambience / 100)


@effect(0x80b2, "Afschuining binnen", _BEVEL_PARAMS)
def inner_bevel(a, ctx, shape, width, smoothness, depth, ambience, shininess, angle, intensity, elevation, color):
    d = _dist_inside(_alpha(a), _px(width, ctx))
    res = _bevel_light(_rgb(a), d, ctx, shape, width, smoothness, depth, ambience, shininess, angle,
                       intensity, elevation, color)
    return _out(a, res)


@effect(0x80b3, "Afschuining buiten", _BEVEL_PARAMS)
def outer_bevel(a, ctx, shape, width, smoothness, depth, ambience, shininess, angle, intensity, elevation, color):
    al = _alpha(a)
    wpx = _px(width, ctx)
    rgb = _rgb(a)
    if al.min() > 0.98:  # geen transparantie: de beeldrand is de selectierand
        d = _dist_inside(al, wpx)
        res = _bevel_light(rgb, d, ctx, shape, width, smoothness, depth, ambience, shininess, angle,
                           intensity, elevation, color)
        return _out(a, res)
    hgt = _dist_outside(al, wpx)
    m = al[..., None]
    pm = _blur1(rgb * m, wpx)
    sa = _blur1(al, wpx)[..., None]
    spread = np.where(sa > 1e-4, pm / np.maximum(sa, 1e-4), 0)
    base = rgb * m + spread * (1 - m)
    lit = _bevel_light(base, hgt, ctx, shape, width, smoothness, depth, ambience, shininess, angle,
                       intensity, elevation, color)
    ring = np.clip(hgt * 40, 0, 1)
    oa = np.maximum(al, ring)
    res = np.where(m >= 0.999, rgb, lit)
    return _out(a, res, oa)


# ---------------------------------------------------------------- kunstzinnige effecten (Art Media)

def _paper(h, w, ctx, amount=10):
    return (smooth_noise(h, w, 2 * ctx.scale + 1, ctx.seed + 3) - 0.5) * amount + \
        (noise(h, w, ctx.seed + 5) - 0.5) * amount * 0.6


def _sketch(a, ctx, detail, angle=45, width=2.5, length=18, contrast=1.0, edge_w=0.8):
    h, w = a.shape[:2]
    g = blur(gray(a), _px(1, ctx, 0))
    e = np.clip(_edges(g, 0) / 60 * (0.3 + detail / 50), 0, 1)
    dark = np.clip((1 - g / 255) * contrast, 0, 1)
    val, prof = _strokes(h, w, angle, _px(width, ctx, 1.2), _px(length, ctx, 3), ctx.seed)
    hatch = np.clip((dark * (0.6 + detail / 100) - val * 0.55) * 3, 0, 1) * (0.55 + 0.45 * prof)
    return np.clip(e * edge_w + hatch * 0.8, 0, 1), e, val, prof


@effect(0x80a4, "Zwart potlood", [Int("detail", "Detail", 1, 100, 50), Int("opacity", "Dekking", 1, 100, 50)])
def black_pencil(a, ctx, detail, opacity):
    h, w = a.shape[:2]
    ink, *_ = _sketch(a, ctx, detail)
    sk = 250 * (1 - ink) + _paper(h, w, ctx, 8)
    op = opacity / 100
    return _out(a, _rgb(a) * (1 - op) + sk[..., None] * op)


@effect(0x80aa, "Houtskool", [Int("detail", "Detail", 1, 100, 50), Int("opacity", "Dekking", 1, 100, 50)])
def charcoal(a, ctx, detail, opacity):
    h, w = a.shape[:2]
    g = blur(gray(a), _px(1.5, ctx, 0))
    dark = np.clip((1 - g / 255 - 0.15) * 1.7, 0, 1)
    e = np.clip(_edges(g, 0) / 50 * (0.3 + detail / 50), 0, 1)
    v1, p1 = _strokes(h, w, 60, _px(4, ctx, 1.5), _px(26, ctx, 4), ctx.seed)
    v2, p2 = _strokes(h, w, 120, _px(4, ctx, 1.5), _px(26, ctx, 4), ctx.seed + 11)
    tex = np.maximum(v1 * p1, v2 * p2 * 0.8)
    ink = np.clip(dark * (0.8 + detail / 100) + (dark > 0.05) * (tex - 0.4) * 0.6 + e * 0.6, 0, 1)
    ink = blur(ink, _px(1, ctx, 0))
    grain = noise(h, w, ctx.seed + 2)
    sk = 245 * (1 - ink) * (0.9 + 0.1 * grain) + 10 * (1 - ink) * 0 + _paper(h, w, ctx, 10)
    op = opacity / 100
    return _out(a, _rgb(a) * (1 - op) + sk[..., None] * op)


@effect(0x80a6, "Kleurkrijt", [Int("detail", "Detail", 1, 100, 50), Int("opacity", "Dekking", 1, 100, 50)])
def colored_chalk(a, ctx, detail, opacity):
    h, w = a.shape[:2]
    rgb = blur(_rgb(a), _px(1, ctx, 0))
    g = gray(rgb)
    val, prof = _strokes(h, w, 50, _px(3.5, ctx, 1.2), _px(16, ctx, 3), ctx.seed)
    grain = smooth_noise(h, w, _px(1.5, ctx, 1), ctx.seed + 4)
    cov = np.clip(g / 255 * 1.2 + 0.25 - val * 0.6 * (0.5 + detail / 100) - (1 - grain) * 0.3, 0, 1)
    cov = cov * (0.55 + 0.45 * prof)
    e = np.clip(_edges(g, 0) / 80 * detail / 50, 0, 1)
    chalk = np.clip((rgb - 128) * 1.25 + 150, 0, 255)
    paper = 70 + 25 * grain
    res = paper[..., None] * (1 - cov[..., None]) + chalk * cov[..., None]
    res = res * (1 - 0.6 * e[..., None])
    op = opacity / 100
    return _out(a, _rgb(a) * (1 - op) + res * op)


@effect(0x80a9, "Kleurpotlood", [Int("detail", "Detail", 1, 100, 50), Int("opacity", "Dekking", 1, 100, 50)])
def colored_pencil(a, ctx, detail, opacity):
    h, w = a.shape[:2]
    rgb = blur(_rgb(a), _px(1, ctx, 0))
    g = gray(rgb)
    val, prof = _strokes(h, w, 45, _px(2.2, ctx, 1.1), _px(20, ctx, 3), ctx.seed)
    e = np.clip(_edges(g, 0) / 70 * (0.3 + detail / 50), 0, 1)
    cov = np.clip(0.62 + (val - 0.5) * (0.3 + detail / 150) + 0.3 * (prof - 0.5), 0, 1)
    res = 252 - (252 - rgb) * cov[..., None] * 1.15
    res = res * (1 - 0.55 * e[..., None]) + _paper(h, w, ctx, 6)[..., None]
    op = opacity / 100
    return _out(a, _rgb(a) * (1 - op) + res * op)


@effect(0x80c8, "Potlood", [Int("luminance", "Luminantie", 0, 100, 50), Int("detail", "Detail", 1, 100, 50),
                            Int("opacity", "Dekking", 1, 100, 100), Color("color", "Kleur", (255, 255, 255))])
def pencil(a, ctx, luminance, detail, opacity, color):
    h, w = a.shape[:2]
    g = gray(a)
    e = _edges(g, _px(1, ctx, 0) * (1.5 - detail / 100))
    e = np.clip(e / 255 * (0.5 + detail / 15), 0, 1) ** 0.8
    bg = np.asarray(color, np.float32) * (0.6 + luminance / 125)
    val, prof = _strokes(h, w, 45, _px(2, ctx, 1), _px(14, ctx, 3), ctx.seed)
    ink = np.clip(e * (0.8 + 0.4 * val * prof), 0, 1)[..., None]
    lum = g[..., None] / 255
    pencil_col = 40 + 60 * lum
    res = bg * (1 - ink) + pencil_col * ink + _paper(h, w, ctx, 5)[..., None]
    op = opacity / 100
    return _out(a, _rgb(a) * (1 - op) + res * op)


@effect(0x80bc, "Penseelstreken", [Int("softness", "Zachtheid", 0, 100, 2), Int("bristles", "Haren", 1, 100, 18),
                                   Int("width", "Breedte", 1, 100, 5), Int("opacity", "Dekking", 0, 100, 30),
                                   Int("length", "Lengte", 1, 100, 10), Int("density", "Dichtheid", 1, 100, 50),
                                   Int("angle", "Hoek", 0, 359, 315), Color("color", "Kleur", (255, 255, 255))])
def brush_strokes(a, ctx, softness, bristles, width, opacity, length, density, angle, color):
    h, w = a.shape[:2]
    rgb = blur(_rgb(a), _px(softness, ctx, 0) / 2)
    wpx = _px(width * 2, ctx, 1)
    lpx = _px(length * 3, ctx, 2)
    sa_ = 45
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ca, sn = math.cos(math.radians(sa_)), math.sin(math.radians(sa_))
    u = xx * ca + yy * sn
    v = -xx * sn + yy * ca
    vw = v / wpx
    row = np.floor(vw)
    fr = vw - row
    us = (u + _hash(row, seed=ctx.seed) * lpx) / lpx
    seg = np.floor(us)
    t = us - seg
    on = _hash(row, seg, seed=ctx.seed + 3) < (0.2 + density / 125)
    bri = np.floor(fr * bristles)
    bv = _hash(row, seg, bri, seed=ctx.seed + 9)
    taper = np.clip(np.sin(np.pi * t) * 2.5, 0, 1)
    tex = (0.4 + 0.6 * bv) * np.sin(np.pi * fr) ** 0.3 * taper * on
    tex = blur(tex, 1 if wpx > 3 else 0)
    diff, spec = _light(tex * wpx * 0.6, angle, 35, 20)
    res = _apply_light(rgb, diff, spec, color, 0.6 * opacity / 100, 0.15 * opacity / 100)
    return _out(a, res)


# ---------------------------------------------------------------- artistieke effecten

@effect(0x80c4, "Oude krant", [Int("years", "Aantal jaren", 10, 100, 80)])
def aged_newspaper(a, ctx, years):
    h, w = a.shape[:2]
    t = years / 100
    g = gray(blur(_rgb(a), _px(0.6 + t, ctx, 0)))
    g = 128 + (g - 128) * (1 - 0.35 * t)
    paper = np.array([238, 222, 180], np.float32) - np.array([10, 30, 70], np.float32) * t
    stain = smooth_noise(h, w, _px(60, ctx, 2), ctx.seed) * 0.6 + smooth_noise(h, w, _px(12, ctx, 1), ctx.seed + 1) * 0.4
    stain = np.clip((stain - 0.45) * 2, 0, 1) * t
    l = g[..., None] / 255
    res = paper * l * (1 - 0.25 * stain[..., None]) + np.array([60, 45, 30], np.float32) * (1 - l) * 0.3
    res = res + (noise(h, w, ctx.seed + 2)[..., None] - 0.5) * 12 * t
    return _out(a, res)


@effect(0x81f1, "Ballen en bellen", [Int("coverage", "Dekking van canvas", 1, 100, 40),
                                     Int("size", "Gemiddelde grootte", 2, 500, 60),
                                     Int("variation", "Grootte-variatie", 0, 100, 50),
                                     Choice("kind", "Type", ["Bellen", "Ballen"], 0),
                                     Int("seed", "Willekeurig getal", 0, 9999, 1)])
def balls_bubbles(a, ctx, coverage, size, variation, kind, seed):
    h, w = a.shape[:2]
    rng = np.random.default_rng(seed * 7919 + ctx.seed)
    r0 = _px(size / 2, ctx, 1)
    n = int(np.clip(coverage / 100 * h * w / (np.pi * r0 * r0) * 0.8, 1, 1500))
    out = _rgb(a).copy()
    al = _alpha(a).copy()
    src = out.copy()
    L = np.array([-0.45, -0.55, 0.7], np.float32)
    L /= np.linalg.norm(L)
    Hh = L + np.array([0, 0, 1], np.float32)
    Hh /= np.linalg.norm(Hh)
    for _ in range(n):
        r = max(1.0, r0 * (1 + (rng.random() * 2 - 1) * variation / 100 * 0.8))
        cy, cx = rng.random() * h, rng.random() * w
        y0, y1 = max(0, int(cy - r)), min(h, int(cy + r) + 2)
        x0, x1 = max(0, int(cx - r)), min(w, int(cx + r) + 2)
        if y1 <= y0 or x1 <= x0:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        nx, ny = (xx + 0.5 - cx) / r, (yy + 0.5 - cy) / r
        rr = nx * nx + ny * ny
        cov = np.clip((1 - np.sqrt(rr)) * r + 0.5, 0, 1)
        if not cov.any():
            continue
        nz = np.sqrt(np.clip(1 - rr, 0, 1))
        diff = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
        spec = np.clip(nx * Hh[0] + ny * Hh[1] + nz * Hh[2], 0, 1) ** 40
        reg = out[y0:y1, x0:x1]
        if kind == 1:
            iy, ix = min(h - 1, int(cy)), min(w - 1, int(cx))
            base = src[iy, ix]
            col = base * (0.25 + 0.85 * diff[..., None]) + 255 * spec[..., None]
            k = cov[..., None]
            out[y0:y1, x0:x1] = reg * (1 - k) + col * k
            al[y0:y1, x0:x1] = np.maximum(al[y0:y1, x0:x1], cov)
        else:
            rim = np.clip(np.sqrt(rr), 0, 1) ** 4
            op = (0.12 + 0.5 * rim + 0.9 * spec) * cov
            tint = 255 * (0.6 + 0.4 * diff)
            out[y0:y1, x0:x1] = reg * (1 - op[..., None]) + tint[..., None] * op[..., None]
            al[y0:y1, x0:x1] = al[y0:y1, x0:x1] + op * (1 - al[y0:y1, x0:x1])
    return _out(a, out, al)


@effect(0x80ab, "Chroom", [Int("flaws", "Vouwen", 0, 10, 2), Int("brightness", "Helderheid", 0, 100, 50),
                           Bool("original", "Oorspronkelijke kleur gebruiken", True),
                           Color("color", "Kleur", (255, 255, 255))])
def chrome(a, ctx, flaws, brightness, original, color):
    g = blur(gray(a), _px(2, ctx, 0)) / 255
    m = 0.5 - 0.5 * np.cos(2 * np.pi * g * (flaws + 0.75))
    m = np.clip(m + (brightness - 50) / 100, 0, 1)
    m = m[..., None]
    if original:
        res = _rgb(a) * (0.25 + 1.0 * m) + 80 * m ** 4
    else:
        res = np.asarray(color, np.float32) * (0.1 + 0.9 * m) + 60 * m ** 4
    return _out(a, res)


@effect(0x80c7, "Gekleurde randen", [Int("detail", "Detail", 1, 100, 50), Int("intensity", "Intensiteit", 0, 100, 50),
                                     Color("color", "Kleur", (255, 255, 255))])
def colored_edges(a, ctx, detail, intensity, color):
    rgb = _rgb(a)
    e = _edges(gray(a), _px(2.5 - detail / 50, ctx, 0))
    e = np.clip(e / (300 - intensity * 2.6), 0, 1) ** 0.7
    k = (e * (0.3 + intensity / 140))[..., None]
    res = rgb * (1 - k) + np.asarray(color, np.float32) * k
    return _out(a, res)


@effect(0x80cc, "Gekleurde folie", [Int("blur", "Vervaging", 0, 20, 5), Int("detail", "Detail", 1, 100, 50),
                                    Int("density", "Dichtheid", 1, 100, 50)])
def colored_foil(a, ctx, blur, detail, density):
    h, w = a.shape[:2]
    rgb = _rgb(a)
    g = _gblur(gray(a), _px(blur, ctx, 0)) / 255
    wav = smooth_noise(h, w, _px(40, ctx, 2), ctx.seed)
    hue = (g * (1 + density / 15) + wav * 0.5) % 1.0
    foil = hsl_to_rgb(hue, np.full_like(hue, 0.85), np.full_like(hue, 0.55))
    diff, spec = _light(g * detail * 0.6 * ctx.scale ** 0 * 3, 315, 40, 30)
    foil = _apply_light(foil, diff, spec, intensity=0.8, shine=0.6)
    res = rgb * 0.35 + foil * 0.65
    return _out(a, res)


@effect(0x80c9, "Contouren", [Int("spacing", "Afstand", 2, 128, 16), Color("color", "Lijnkleur", (0, 0, 0))])
def contours(a, ctx, spacing, color):
    g = blur(gray(a), _px(1.5, ctx, 0))
    q = np.floor(g / spacing)
    line = (q != _shift(q, 0, 1, np.nan)) | (q != _shift(q, 1, 0, np.nan))
    line &= ~np.isnan(_shift(q, 0, 1, np.nan)) | ~np.isnan(_shift(q, 1, 0, np.nan))
    k = blur(line.astype(np.float32), 0.6 * ctx.scale)
    k = np.clip(np.maximum(k * 1.6, line * 1.0), 0, 1)[..., None]
    res = _rgb(a) * (1 - k) + np.asarray(color, np.float32) * k
    return _out(a, res)


@effect(0x80bf, "Email", [Int("detail", "Detail", 1, 100, 30), Int("density", "Dichtheid", 1, 100, 40),
                          Int("thickness", "Dikte", 1, 20, 5), Int("angle", "Hoek", 0, 359, 315),
                          Color("color", "Kleur", (255, 255, 255))])
def enamel(a, ctx, detail, density, thickness, angle, color):
    rgb = blur(_rgb(a), _px(thickness / 2, ctx, 0))
    g = gray(rgb) / 255
    n = 2 + density / 6
    t = g * n
    f = np.floor(t)
    s = np.clip((t - f - 0.5) * (1 + detail / 10) + 0.5, 0, 1)
    H = (f + s * s * (3 - 2 * s)) / n
    H = blur(H, _px(thickness / 3, ctx, 0)) * (5 + detail * 0.6) * min(1.0, ctx.scale * 2 + 0.5)
    diff, spec = _light(H * 3, angle, 35, 60)
    res = _apply_light(rgb, diff, spec, color, 0.5, 1.2)
    return _out(a, res)


@effect(0x80a7, "Oplichtende randen", [Int("intensity", "Intensiteit", 0, 100, 50), Int("sharpness", "Scherpte", 0, 100, 50)])
def glowing_edges(a, ctx, intensity, sharpness):
    rgb = blur(_rgb(a), _px((100 - sharpness) / 30, ctx, 0))
    e = np.zeros_like(rgb)
    for c in range(3):
        gx, gy = sobel(rgb[..., c])
        e[..., c] = np.hypot(gx, gy)
    res = e * (0.3 + intensity / 30) * (0.6 + sharpness / 100)
    return _out(a, res)


@effect(0x80a8, "Neonkleuren", [Int("intensity", "Intensiteit", 0, 100, 50), Int("sharpness", "Scherpte", 0, 100, 50)])
def neon_glow(a, ctx, intensity, sharpness):
    rgb = _rgb(a)
    hh, ss, ll = rgb_to_hsl(blur(rgb, _px(1, ctx, 0)))
    neon = hsl_to_rgb((hh + 0.5) % 1.0, np.ones_like(hh), np.full_like(hh, 0.55))
    e = _edges(gray(a), _px((100 - sharpness) / 30, ctx, 0))
    e = np.clip(e / 255 * (0.5 + intensity / 20), 0, 1)
    glow = blur(e, _px(3, ctx, 0))
    k = np.clip(e + glow * 0.8 * (intensity / 50), 0, 1)[..., None]
    res = neon * k + 255 * (e[..., None] ** 2) * 0.4
    return _out(a, res)


@effect(0x818b, "Halftoon", [Choice("pattern", "Halftoonpatroon", ["Rond", "Lijn", "Vierkant"], 0),
                             Int("size", "Grootte", 2, 100, 8), Int("angle", "Rasterhoek", 0, 359, 45),
                             Choice("scheme", "Kleurenschema", ["Grijswaarden", "RGB"], 0)])
def halftone(a, ctx, pattern, size, angle, scheme):
    h, w = a.shape[:2]
    s = _px(size, ctx, 2)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    src = blur(_rgb(a), s / 3)
    chans = [(gray(src), angle)] if scheme == 0 else [(src[..., c], angle + o) for c, o in enumerate((15, 75, 0))]
    planes = []
    for val, ang in chans:
        ca, sn = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        u = xx * ca + yy * sn
        v = -xx * sn + yy * ca
        cu = (np.floor(u / s) + 0.5) * s
        cv = (np.floor(v / s) + 0.5) * s
        cx = np.clip(np.rint(cu * ca - cv * sn), 0, w - 1).astype(np.int64)
        cy = np.clip(np.rint(cu * sn + cv * ca), 0, h - 1).astype(np.int64)
        lv = val[cy, cx] / 255
        cover = (1 - lv) if scheme == 0 else lv  # inktaandeel
        du, dv = u - cu, v - cv
        if pattern == 0:
            dist = np.hypot(du, dv)
            rad = s * np.sqrt(cover / np.pi)
            rad = np.where(cover > 0.785, s * (0.5 + (cover - 0.785) * 1.0), rad)
            k = np.clip(rad - dist + 0.5, 0, 1)
        elif pattern == 1:
            k = np.clip(cover * s / 2 - np.abs(dv) + 0.5, 0, 1)
        else:
            k = np.clip(np.sqrt(cover) * s / 2 - np.maximum(np.abs(du), np.abs(dv)) + 0.5, 0, 1)
        planes.append(k)
    if scheme == 0:
        res = np.repeat((255 * (1 - planes[0]))[..., None], 3, axis=2)
    else:
        res = np.stack(planes, axis=-1) * 255
    return _out(a, res)


@effect(0x80a1, "Glanzende waslaag")
def hot_wax(a, ctx):
    rgb = blur(_rgb(a), _px(2, ctx, 0))
    g = gray(rgb) / 255
    wax = np.asarray(ctx.fg, np.float32)
    base = rgb * 0.55 + wax * 0.45
    diff, spec = _light(blur(g, _px(2, ctx, 0)) * 40 * min(1.0, ctx.scale + 0.3), 315, 40, 40)
    res = _apply_light(base, diff, spec, intensity=0.8, shine=1.0)
    return _out(a, res)


@effect(0x81e5, "Vergrootglas", [Int("cx", "Midden X %", 0, 100, 50), Int("cy", "Midden Y %", 0, 100, 50),
                                 Int("radius", "Straal %", 1, 100, 30), Int("magnification", "Vergroting %", 100, 500, 200)])
def magnifying_lens(a, ctx, cx, cy, radius, magnification):
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    px, py = cx / 100 * (w - 1), cy / 100 * (h - 1)
    R = max(1.0, radius / 100 * min(h, w) / 2 * 1.6)
    dx, dy = xx - px, yy - py
    r = np.hypot(dx, dy)
    rn = np.clip(r / R, 0, 1)
    m = magnification / 100
    f = (1 / m) * (1 - rn ** 2) + rn ** 2
    inside = r < R
    mx = np.where(inside, px + dx * f, xx)
    my = np.where(inside, py + dy * f, yy)
    res = remap(a, mx, my).astype(np.float32)
    nx, ny = dx / R, dy / R
    nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
    spec = np.clip(-0.4 * nx - 0.5 * ny + 0.77 * nz, 0, 1) ** 60
    rim = np.clip((rn - 0.9) * 10, 0, 1)
    k = inside.astype(np.float32)
    shade = (1 - 0.35 * rim) * k + (1 - k)
    res[..., :3] = res[..., :3] * shade[..., None] + (255 * spec * k * 0.8)[..., None]
    edge = np.clip(1 - np.abs(r - R) / max(1.0, R * 0.03), 0, 1)
    res[..., :3] = res[..., :3] * (1 - edge[..., None] * 0.7) + 40 * edge[..., None] * 0.7
    out = a.copy()
    out[..., :3] = to_u8(res[..., :3])
    out[..., 3] = np.where(inside, res[..., 3], a[..., 3]).astype(np.uint8)
    return out


@effect(0x80bd, "Topografie", [Int("width", "Breedte", 1, 100, 25), Int("density", "Dichtheid", 1, 100, 40),
                               Int("angle", "Hoek", 0, 359, 315), Color("color", "Kleur", (255, 255, 255))])
def topography(a, ctx, width, density, angle, color):
    rgb = _rgb(a)
    g = blur(gray(a), _px(1, ctx, 0)) / 255
    n = 2 + density / 3
    q = np.floor(g * n) / n
    wpx = _px(width / 8, ctx, 0)
    H = _blur1(q, wpx) if wpx >= 1 else q
    H = H * n * _px(3, ctx, 0.5)
    diff, spec = _light(H, angle, 35)
    res = _apply_light(rgb, diff, spec, color, 0.6)
    return _out(a, res)
