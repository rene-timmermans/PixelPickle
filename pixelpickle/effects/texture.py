"""Rand-, belichtings-, foto- en textuureffecten en het eigen filter (benaderingen van PSP XI)."""
import math

import numpy as np

from . import Bool, Choice, Color, Int, effect
from .common import blur, convolve, gray, grid, hsl_to_rgb, noise, rgb_to_hsl, sobel, to_u8, with_rgb, remap


# ---------------------------------------------------------------- hulpfuncties

def _rgb(a):
    return a[..., :3].astype(np.float32)


def _col(c, ctx):
    if isinstance(c, str):
        c = ctx.fg if c == "fg" else ctx.bg
    return np.array(c[:3], np.float32)


def _px(v, ctx, lo=0.0):
    return max(lo, v * ctx.scale)


def _shift_stack(x):
    """De 9 verschoven versies (3x3 omgeving) van x met herhaalde randen."""
    h, w = x.shape[:2]
    pad = ((1, 1), (1, 1)) + (((0, 0),) if x.ndim == 3 else ())
    p = np.pad(x, pad, mode="edge")
    return [p[j:j + h, i:i + w] for j in range(3) for i in range(3)]


def _max3(x):
    s = _shift_stack(x)
    out = s[0]
    for t in s[1:]:
        out = np.maximum(out, t)
    return out


def _min3(x):
    s = _shift_stack(x)
    out = s[0]
    for t in s[1:]:
        out = np.minimum(out, t)
    return out


_TABLES = {}


def _table(seed):
    t = _TABLES.get(seed)
    if t is None:
        t = np.random.default_rng(seed).random((256, 256), dtype=np.float32)
        _TABLES[seed] = t
    return t


def vnoise(x, y, seed=1):
    """Waarderuis 0..1 op willekeurige (float) coördinaten; periode 256 roostercellen."""
    t = _table(seed)
    x0 = np.floor(x)
    y0 = np.floor(y)
    fx = (x - x0).astype(np.float32)
    fy = (y - y0).astype(np.float32)
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    xi = x0.astype(np.int64) & 255
    yi = y0.astype(np.int64) & 255
    xj = (xi + 1) & 255
    yj = (yi + 1) & 255
    a = t[yi, xi] + (t[yi, xj] - t[yi, xi]) * fx
    b = t[yj, xi] + (t[yj, xj] - t[yj, xi]) * fx
    return a + (b - a) * fy


def fbm(x, y, seed=1, octaves=4, gain=0.5):
    """Fractale ruis 0..1."""
    tot, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        f = 2.0 ** o
        tot = tot + amp * vnoise(x * f + o * 31.7, y * f + o * 17.3, seed + o)
        norm += amp
        amp *= gain
    return tot / norm


def _coords(h, w, scale, angle=0.0, stretch=1.0):
    """Gedraaide/uitgerekte coördinaten gedeeld door scale (korrelgrootte in pixels)."""
    yy, xx = grid(h, w)
    s = max(scale, 0.3)
    if angle:
        c, si = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        xx, yy = xx * c + yy * si, -xx * si + yy * c
    return xx / (s * stretch), yy / s


def _light_vec(angle, elevation):
    """angle: richting van de lichtbron (0 = boven, met de klok mee), elevation in graden."""
    az, el = math.radians(angle), math.radians(max(1.0, min(90.0, elevation)))
    return np.array([math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)], np.float32)


def lighting(height, angle, elevation=45, depth=1.0, shininess=0.0):
    """Belichting van een hoogteveld. Geeft (diffuus genormaliseerd zodat vlak = 1, glans 0..1)."""
    gx, gy = sobel(height)
    k = depth / 8.0
    nx, ny = -gx * k, -gy * k
    inv = 1.0 / np.sqrt(nx * nx + ny * ny + 1.0)
    L = _light_vec(angle, elevation)
    d = (nx * L[0] + ny * L[1] + L[2]) * inv
    diff = np.clip(d, 0, None) / max(L[2], 0.25)
    diff = np.minimum(diff, 2.5)
    spec = None
    if shininess > 0:
        H = L + np.array([0, 0, 1], np.float32)
        H /= np.linalg.norm(H)
        nh = np.clip((nx * H[0] + ny * H[1] + H[2]) * inv, 0, 1)
        flat = float(H[2])
        p = 10 + shininess * 0.9
        spec = np.clip(nh ** p - flat ** p * 0.6, 0, 1) * (shininess / 100.0) * 1.4
    return diff, spec


def _compose(rgb, diff, spec, color, ambience=0, intensity=50):
    """rgb * (ambient + licht) + glans."""
    amb = 0.6 + ambience / 100.0 * 0.6
    lit = amb + intensity / 100.0 * 0.8 * diff
    out = rgb * (lit[..., None] * (color / 255.0))
    if spec is not None:
        out = out + spec[..., None] * color * 1.2
    return out


def _tone(g, stops):
    """g 0..1 -> kleur via kleurstops [(pos, (r,g,b)), ...]."""
    pos = [s[0] for s in stops]
    return np.stack([np.interp(g, pos, [s[1][c] for s in stops]) for c in range(3)], axis=-1).astype(np.float32)


def _vignette(h, w, amount):
    yy, xx = grid(h, w)
    cy, cx = (h - 1) / 2, (w - 1) / 2
    r2 = ((yy - cy) ** 2 + (xx - cx) ** 2) / max(1.0, cx * cx + cy * cy)
    return 1 - amount * r2 ** 1.3


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / max(1e-6, e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def _lum_keep(rgb, ref_gray):
    g2 = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    return rgb * (ref_gray / np.maximum(g2, 1.0))[..., None]


def _lic(seed_field, theta, length, steps=12, mode="max"):
    """Strepen trekken langs richtingsveld theta (lijnintegraalconvolutie, gevectoriseerd)."""
    h, w = seed_field.shape
    yy, xx = np.mgrid[0:h, 0:w]
    dx, dy = np.cos(theta), np.sin(theta)
    n = max(1, int(steps))
    acc = np.zeros((h, w), np.float32)
    for k in range(n + 1):
        t = length * k / n
        sx = np.clip(np.rint(xx - dx * t).astype(np.int64), 0, w - 1)
        sy = np.clip(np.rint(yy - dy * t).astype(np.int64), 0, h - 1)
        v = seed_field[sy, sx]
        if mode == "max":
            acc = np.maximum(acc, v * (1 - 0.8 * k / (n + 1)))
        else:
            acc += v
    return acc if mode == "max" else acc / (n + 1)


# ================================================================ Randeffecten

@effect(0x808b, "Rembrandtiek licht")
def dilate(a, ctx):
    return with_rgb(a, _max3(a[..., :3]))


@effect(0x808d, "Rembrandtiek donker")
def erode(a, ctx):
    return with_rgb(a, _min3(a[..., :3]))


def _enhance(a, k):
    rgb = _rgb(a)
    mean = convolve(rgb, np.full((3, 3), 1 / 9))
    return with_rgb(a, rgb + (rgb - mean) * k)


@effect(0x807d, "Accentueren")
def enhance(a, ctx):
    return _enhance(a, 1.0)


@effect(0x807e, "Sterker accentueren")
def enhance_more(a, ctx):
    return _enhance(a, 2.5)


@effect(0x807f, "Alle zoeken")
def find_all(a, ctx):
    rgb = _rgb(a)
    lap = convolve(rgb, [[-1, -1, -1], [-1, 8, -1], [-1, -1, -1]])
    return with_rgb(a, np.abs(lap) * 1.5)


@effect(0x8080, "Horizontale zoeken")
def find_horizontal(a, ctx):
    rgb = _rgb(a)
    e = convolve(rgb, [[-1, -2, -1], [0, 0, 0], [1, 2, 1]])
    return with_rgb(a, np.abs(e) * 0.75)


@effect(0x8081, "Verticale zoeken")
def find_vertical(a, ctx):
    rgb = _rgb(a)
    e = convolve(rgb, [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]])
    return with_rgb(a, np.abs(e) * 0.75)


@effect(0x82da, "High-pass", [Int("radius", "Straal", 1, 100, 10), Bool("desat", "Kleur verwijderen", False)])
def high_pass(a, ctx, radius, desat):
    rgb = _rgb(a)
    out = 128 + (rgb - blur(rgb, _px(radius, ctx, 1)))
    if desat:
        out = np.repeat(gray(np.clip(out, 0, 255))[..., None], 3, axis=2)
    return with_rgb(a, out)


@effect(0x8082, "Contour overtrekken")
def trace_contour(a, ctx):
    b = a[..., :3] >= 128
    edge = np.zeros_like(b)
    edge[:, :-1] |= b[:, :-1] != b[:, 1:]
    edge[:-1, :] |= b[:-1, :] != b[1:, :]
    return with_rgb(a, np.where(edge, 0, 255))


# ================================================================ Belichtingseffecten

def _spot_params(i, on, x, y, d, col):
    return [Bool(f"on{i}", f"Lamp {i} aan", on), Color(f"color{i}", f"Lamp {i} kleur", col),
            Int(f"x{i}", f"Lamp {i} horizontaal %", 0, 100, x), Int(f"y{i}", f"Lamp {i} verticaal %", 0, 100, y),
            Int(f"dir{i}", f"Lamp {i} richting", 0, 359, d), Int(f"cone{i}", f"Lamp {i} kegelgrootte", 1, 89, 30),
            Int(f"int{i}", f"Lamp {i} intensiteit", 0, 100, 70)]


@effect(0x80c6, "Lampen", [Int("darkness", "Duisternis", 0, 100, 60)]
        + _spot_params(1, True, 30, 15, 150, (255, 255, 255))
        + _spot_params(2, False, 75, 15, 210, (255, 230, 170)))
def lights(a, ctx, darkness, on1, color1, x1, y1, dir1, cone1, int1, on2, color2, x2, y2, dir2, cone2, int2):
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    diag = math.hypot(h, w)
    total = np.full((h, w, 3), 1 - darkness / 100, np.float32)
    for on, col, x, y, d, cone, inten in ((on1, color1, x1, y1, dir1, cone1, int1),
                                         (on2, color2, x2, y2, dir2, cone2, int2)):
        if not on:
            continue
        px, py = x / 100 * (w - 1), y / 100 * (h - 1)
        vx, vy = xx - px, yy - py
        dist = np.sqrt(vx * vx + vy * vy) + 1e-3
        az = math.radians(d)
        cosang = (vx * math.sin(az) - vy * math.cos(az)) / dist
        c0 = math.cos(math.radians(cone))
        c1 = math.cos(math.radians(cone * 0.55))
        f = _smoothstep(c0, c1, cosang)
        near = np.exp(-(dist / (0.03 * diag + 1)) ** 2)  # gloed bij de bron
        fall = np.exp(-(dist / (0.85 * diag)) ** 2)
        k = (inten / 100) * 1.6 * np.maximum(f * fall, near * 0.6)
        total += k[..., None] * (_col(col, ctx) / 255)
    return with_rgb(a, _rgb(a) * total)


@effect(0x80c5, "Zon", [Color("color", "Kleur", (255, 255, 255)), Int("x", "Horizontaal %", 0, 100, 70),
                        Int("y", "Verticaal %", 0, 100, 30), Int("bright", "Helderheid lichtvlek", 0, 200, 100),
                        Int("rays", "Dichtheid stralen", 1, 200, 50), Int("raybright", "Helderheid stralen", 0, 100, 50),
                        Int("circles", "Helderheid cirkels", 0, 100, 50)])
def sunburst(a, ctx, color, x, y, bright, rays, raybright, circles):
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    diag = math.hypot(h, w)
    px, py = x / 100 * (w - 1), y / 100 * (h - 1)
    vx, vy = xx - px, yy - py
    r = np.sqrt(vx * vx + vy * vy) / diag
    light = (bright / 100) * (np.exp(-(r / 0.04) ** 2) * 1.2 + np.exp(-(r / 0.18) ** 2) * 0.35)
    n = max(4, rays * 2)
    rng = np.random.default_rng(ctx.seed)
    tab = rng.random(n + 1).astype(np.float32) ** 3
    tab[-1] = tab[0]
    ang = (np.arctan2(vy, vx) / (2 * np.pi) + 0.5) * n
    i0 = np.floor(ang).astype(np.int64) % n
    fr = ang - np.floor(ang)
    rayv = tab[i0] * (1 - fr) + tab[i0 + 1] * fr
    light = light + (raybright / 100) * 0.9 * rayv * np.exp(-r / 0.25) * (1 - np.exp(-(r / 0.02) ** 2))
    # halo's langs de lijn van de bron door het midden
    cx, cy = (w - 1) / 2, (h - 1) / 2
    for t, rad, s in ((0.4, 0.03, 0.5), (0.7, 0.012, 0.8), (1.25, 0.05, 0.35), (1.6, 0.025, 0.6), (1.9, 0.08, 0.25)):
        hx, hy = px + (cx - px) * t, py + (cy - py) * t
        d = np.sqrt((xx - hx) ** 2 + (yy - hy) ** 2) / diag
        ring = np.exp(-((d - rad) / (rad * 0.25 + 0.002)) ** 2) * 0.7 + (d < rad) * 0.35
        light = light + (circles / 100) * s * ring
    col = _col(color, ctx) / 255
    rgb = _rgb(a) / 255
    add = np.clip(light, 0, 2)[..., None] * col
    out = 1 - (1 - rgb) * np.clip(1 - add, 0, 1)  # schermen
    return with_rgb(a, out * 255)


# ================================================================ Foto-effecten

_ERAS = ["Daguerreotypie", "Albuminedruk", "Cyanotypie", "Platinadruk", "Vroege kleurenfoto", "Box camera",
         "Cross processing"]


@effect(0x82fe, "Tijdmachine", [Choice("style", "Stijl", _ERAS), Int("intensity", "Intensiteit", 0, 100, 100)])
def time_machine(a, ctx, style, intensity):
    h, w = a.shape[:2]
    rgb = _rgb(a)
    g = gray(a) / 255
    if style == 0:
        gs = blur(g, _px(1, ctx))
        gs = 0.08 + gs * 0.84
        out = _tone(gs, [(0, (22, 24, 27)), (0.5, (120, 122, 121)), (1, (228, 228, 218))])
        out = out * _vignette(h, w, 0.55)[..., None]
        out += (noise(h, w, ctx.seed) - 0.5)[..., None] * 10
    elif style == 1:
        gs = np.clip(0.06 + g * 0.9, 0, 1)
        out = _tone(gs, [(0, (48, 26, 14)), (0.45, (150, 102, 58)), (1, (246, 226, 178))])
        out = out * _vignette(h, w, 0.35)[..., None]
    elif style == 2:
        out = _tone(g, [(0, (6, 28, 72)), (0.5, (52, 104, 160)), (1, (222, 234, 242))])
    elif style == 3:
        gs = g * g * (3 - 2 * g) * 0.6 + g * 0.4
        out = _tone(gs, [(0, (24, 21, 19)), (0.5, (132, 123, 110)), (1, (242, 238, 228))])
    elif style == 4:
        hh, s, l = rgb_to_hsl(rgb)
        s = s * 0.55
        l = 0.1 + l * 0.8
        out = hsl_to_rgb(hh, s, l).astype(np.float32) * np.array([1.06, 1.0, 0.86], np.float32)
        dots = blur(noise(h, w, ctx.seed, 3) - 0.5, _px(1, ctx))
        out += dots * 70
        out = blur(out, _px(1, ctx))
    elif style == 5:
        c = np.clip((g - 0.5) * 1.5 + 0.5, 0, 1)
        out = np.repeat((c * 255)[..., None], 3, axis=2)
        yy, xx = grid(h, w)
        r2 = ((yy - (h - 1) / 2) ** 2 + (xx - (w - 1) / 2) ** 2) / max(1.0, ((h - 1) / 2) ** 2 + ((w - 1) / 2) ** 2)
        soft = blur(out, _px(3, ctx))
        out = out + (soft - out) * np.clip(r2 * 1.5, 0, 1)[..., None]
        out = out * _vignette(h, w, 0.85)[..., None]
    else:
        n = rgb / 255
        r = _smoothstep(0.05, 0.95, n[..., 0]) * 0.8 + n[..., 0] * 0.2
        gg = np.clip(n[..., 1] * 1.1 - 0.03, 0, 1)
        b = 0.22 + n[..., 2] * 0.5
        out = np.stack([r, gg, b], axis=-1) * 255
        out[..., :2] += 12
    t = intensity / 100
    return with_rgb(a, rgb + (out - rgb) * t)


_FILMS = ["Geen", "Levendig", "Levendige huidtinten", "Gedempt rood", "Versterkt rood", "Weelderig gebladerte",
          "Warme aardtinten", "Glamour"]
_FILTERS = ["Geen", "Nachteffect", "Koeler", "Warmer", "Oranje", "Champagne", "Zonsondergang", "Aangepast"]
_FILTER_COL = [None, (40, 70, 160), (120, 175, 255), (255, 200, 140), (255, 150, 40), (250, 215, 160),
               (255, 110, 50)]


def _hue_w(hh, center, width):
    d = np.abs(hh - center)
    d = np.minimum(d, 1 - d)
    return np.clip(1 - d / width, 0, 1)


@effect(0x8319, "Film en filters", [Choice("film", "Filmlook", _FILMS, 1), Choice("filter", "Creatief filter", _FILTERS),
                                    Color("color", "Filterkleur", (255, 160, 60)), Int("density", "Dichtheid", 0, 100, 25),
                                    Bool("keeplum", "Luminantie behouden", True)])
def film_filters(a, ctx, film, filter, color, density, keeplum):
    rgb = _rgb(a)
    out = rgb
    if film:
        hh, s, l = rgb_to_hsl(rgb)
        if film == 1:
            s = s * 1.3
            l = (l - 0.5) * 1.15 + 0.5
        elif film == 2:
            wgt = _hue_w(hh, 0.07, 0.08)
            s = s * (1 + 0.2 * wgt)
            l = l + 0.04 * wgt
        elif film == 3:
            s = s * (1 - 0.5 * _hue_w(hh, 0.0, 0.08))
        elif film == 4:
            s = s * (1 + 0.6 * _hue_w(hh, 0.0, 0.08))
        elif film == 5:
            s = s * (1 + 0.5 * np.maximum(_hue_w(hh, 0.33, 0.12), _hue_w(hh, 0.58, 0.1)))
        elif film == 6:
            s = s * (1 + 0.5 * _hue_w(hh, 0.08, 0.1))
        if film != 7:
            out = hsl_to_rgb(hh, np.clip(s, 0, 1), np.clip(l, 0, 1)).astype(np.float32)
        else:
            soft = blur(rgb, _px(6, ctx))
            scr = 255 - (255 - rgb) * (255 - soft) / 255
            out = rgb + (scr - rgb) * 0.45
            out = gray_mix(out, 0.1)
    if filter:
        fc = _col(color, ctx) if filter == 7 else np.array(_FILTER_COL[filter], np.float32)
        ref = out[..., 0] * 0.299 + out[..., 1] * 0.587 + out[..., 2] * 0.114
        d = density / 100
        tinted = out * (fc / 255)
        mixed = out + (tinted - out) * d
        if keeplum:
            mixed = _lum_keep(mixed, ref)
        if filter == 1:
            mixed = mixed * (1 - 0.45 * d)
        out = mixed
    return with_rgb(a, out)


def gray_mix(rgb, t):
    g = (rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114)[..., None]
    return rgb + (g - rgb) * t


@effect(0x82e6, "Zwartwitfilm", [Color("color", "Filterkleur", (255, 120, 0)), Int("strength", "Sterkte", 0, 100, 50),
                                 Int("brightness", "Helderheid", -100, 100, 0), Int("clarity", "Helderheid details", 0, 100, 0)])
def bw_film(a, ctx, color, strength, brightness, clarity):
    rgb = _rgb(a)
    fc = _col(color, ctx) + 1
    fw = fc / fc.sum()
    lum = np.array([0.299, 0.587, 0.114], np.float32)
    t = strength / 100
    wgt = lum + (fw - lum) * t
    wgt = wgt / wgt.sum()
    g = rgb @ wgt
    if clarity:
        g = g + (g - blur(g, _px(12, ctx, 1))) * clarity / 60
    g = g + brightness * 1.0
    return with_rgb(a, np.repeat(g[..., None], 3, axis=2))


@effect(0x82e7, "Infrarode film", [Int("strength", "Sterkte", 0, 100, 60), Int("glow", "Gloed", 0, 100, 30),
                                   Int("grain", "Korrel", 0, 100, 20)])
def infrared(a, ctx, strength, glow, grain):
    h, w = a.shape[:2]
    rgb = _rgb(a)
    lum = np.array([0.299, 0.587, 0.114], np.float32)
    ir = np.array([0.35, 1.45, -0.8], np.float32)
    t = strength / 100
    g = np.clip(rgb @ (lum + (ir - lum) * t), 0, 255)
    if glow:
        bright = np.clip(g - 140, 0, None) * 2
        halo = blur(bright, _px(14, ctx, 1))
        g = 255 - (255 - g) * (255 - np.clip(halo * glow / 100, 0, 255)) / 255
    if grain:
        nz = noise(h, w, ctx.seed) - 0.5
        g = g + nz * grain * 0.9
    return with_rgb(a, np.repeat(g[..., None], 3, axis=2))


@effect(0x80c3, "Sepiakleuring", [Int("amount", "Mate van veroudering", 0, 100, 30)])
def sepia(a, ctx, amount):
    g = gray(a) / 255
    t = amount / 100
    gs = g * (1 - 0.18 * t) + 0.09 * t
    tone = np.array([1.0, 1.0, 1.0], np.float32) + (np.array([1.12, 0.86, 0.58], np.float32) - 1) * (0.35 + 0.65 * t)
    out = (gs[..., None] * 255) * tone
    return with_rgb(a, out)


# ================================================================ Textuureffecten

@effect(0x80a5, "Lamellen", [Int("width", "Breedte", 2, 100, 10), Int("opacity", "Dekking", 0, 100, 50),
                             Color("color", "Kleur", (0, 0, 0)), Bool("horizontal", "Horizontaal", False),
                             Bool("lefttop", "Licht van links/boven", False)])
def blinds(a, ctx, width, opacity, color, horizontal, lefttop):
    h, w = a.shape[:2]
    wd = _px(width, ctx, 1.5)
    yy, xx = grid(h, w)
    pos = yy if horizontal else xx
    t = np.mod(pos, wd) / wd
    shade = t if lefttop else 1 - t
    k = (opacity / 100 * shade)[..., None]
    rgb = _rgb(a)
    return with_rgb(a, rgb + (_col(color, ctx) - rgb) * k)


def _fine_leather(a, ctx, color, angle, blr, transp, count, length):
    h, w = a.shape[:2]
    rgb = blur(_rgb(a), _px(blr, ctx))
    sc = _px(30, ctx, 1)
    x, y = _coords(h, w, sc, angle=37, stretch=1 + length / 10)
    n = fbm(x, y, ctx.seed, 3)
    m = 1 + count / 8
    lines = np.abs(np.sin(n * m * np.pi))
    furrow = 1 - _smoothstep(0, 0.18, lines)
    height = gray(np.clip(rgb, 0, 255)) * 0.15 - furrow * 25
    diff, spec = lighting(height, angle, 45, 1.0, 20)
    out = _compose(rgb, diff, spec, _col(color, ctx), 0, 50)
    dark = rgb * (0.35 + 0.65 * transp / 100)
    out = out + (dark - out) * furrow[..., None] * 0.8
    return with_rgb(a, out)


@effect(0x80ce, "Fijn leer", [Color("color", "Lichtkleur", (255, 255, 255)), Int("angle", "Hoek", 0, 359, 315),
                              Int("blur", "Vervaging", 0, 20, 1), Int("transp", "Transparantie", 0, 100, 40),
                              Int("count", "Aantal groeven", 1, 100, 40), Int("length", "Lengte groeven", 1, 50, 10)])
def fine_leather_fx(a, ctx, color, angle, count, length, transp, **kw):
    return _fine_leather(a, ctx, color, angle, kw.get("blur", 1), transp, count, length)


@effect(0x80ca, "Bont", [Int("blur", "Vervaging", 0, 20, 0), Int("density", "Dichtheid", 1, 100, 50),
                         Int("length", "Lengte", 1, 100, 15), Int("transp", "Transparantie", 0, 100, 0)])
def fur(a, ctx, density, length, transp, **kw):
    h, w = a.shape[:2]
    rgb = blur(_rgb(a), _px(kw.get("blur", 0), ctx))
    seeds = (noise(h, w, ctx.seed) < 0.04 + density / 100 * 0.25).astype(np.float32)
    x, y = _coords(h, w, _px(60, ctx, 1))
    theta = 1.2 + (fbm(x, y, ctx.seed + 7, 2) - 0.5) * 3.0
    tex = _lic(seeds, theta, _px(length, ctx, 1), steps=min(14, max(2, int(length * ctx.scale))))
    tex = blur(tex, 0.6 * ctx.scale) if ctx.scale >= 1.5 else tex
    out = rgb * (0.45 + 0.85 * tex)[..., None]
    out = out + (_rgb(a) - out) * (transp / 100)
    return with_rgb(a, out)


_MOS_P = [Int("cols", "Aantal kolommen", 1, 100, 20), Int("rows", "Aantal rijen", 1, 100, 20),
          Bool("sym", "Symmetrisch", True)]


def _tile_grid(h, w, cols, rows, sym):
    tw = w / max(1, cols)
    th = tw if sym else h / max(1, rows)
    return tw, max(th, 1e-3)


def _tile_mean(rgb, ids, n):
    flat = ids.ravel()
    cnt = np.bincount(flat, minlength=n).astype(np.float32)
    means = np.stack([np.bincount(flat, rgb[..., c].ravel(), minlength=n) for c in range(3)], axis=-1)
    means = means / np.maximum(cnt, 1)[:, None]
    return means[ids]


@effect(0x80b9, "Mozaïek - antiek", _MOS_P + [Int("diffusion", "Tegeldiffusie", 0, 100, 30),
                                               Int("grout", "Voegbreedte", 0, 20, 3),
                                               Int("groutop", "Voegdekking", 0, 100, 70)])
def mosaic_antique(a, ctx, cols, rows, sym, diffusion, grout, groutop):
    h, w = a.shape[:2]
    rgb = _rgb(a)
    tw, th = _tile_grid(h, w, cols, rows, sym)
    yy, xx = grid(h, w)
    jx, jy = _coords(h, w, max(4.0, min(tw, th) * 0.8))
    px = xx + (vnoise(jx, jy, ctx.seed) - 0.5) * tw * 0.35
    py = yy + (vnoise(jx + 50, jy + 50, ctx.seed + 3) - 0.5) * th * 0.35
    u, v = px / tw, py / th
    cx = np.floor(u).astype(np.int64)
    cy = np.floor(v).astype(np.int64)
    cx -= cx.min()
    cy -= cy.min()
    ncx = int(cx.max()) + 1
    ids = cy * ncx + cx
    mean = _tile_mean(rgb, ids, int(ids.max()) + 1)
    col = mean + (blur(rgb, _px(1, ctx)) - mean) * (diffusion / 100)
    fu, fv = u - np.floor(u), v - np.floor(v)
    d = np.minimum(np.minimum(fu, 1 - fu) * tw, np.minimum(fv, 1 - fv) * th)
    gw = _px(grout, ctx) / 2
    bev = np.clip(d - gw, 0, None)
    bw = max(1.0, min(_px(2, ctx, 1), min(tw, th) * 0.15))
    height = np.minimum(bev, bw) / bw * 6 + (noise(h, w, ctx.seed + 9) - 0.5) * 3
    diff, _ = lighting(height, 315, 45, 1.0)
    out = col * (0.7 + 0.3 * np.minimum(diff, 1.6))[..., None]
    ing = (d < gw)[..., None]
    gcol = rgb + (np.array([70, 66, 60], np.float32) - rgb) * (groutop / 100)
    out = np.where(ing, gcol, out)
    return with_rgb(a, out)


@effect(0x80ba, "Mozaïek - glas", _MOS_P + [Int("curv", "Glaskromming", 0, 100, 40),
                                             Int("edge", "Randkromming", 0, 100, 30),
                                             Int("grout", "Voegbreedte", 0, 20, 2),
                                             Int("groutop", "Voegdekking", 0, 100, 70)])
def mosaic_glass(a, ctx, cols, rows, sym, curv, edge, grout, groutop):
    h, w = a.shape[:2]
    tw, th = _tile_grid(h, w, cols, rows, sym)
    yy, xx = grid(h, w)
    u, v = xx / tw, yy / th
    fu, fv = u - np.floor(u) - 0.5, v - np.floor(v) - 0.5
    ccx, ccy = (np.floor(u) + 0.5) * tw, (np.floor(v) + 0.5) * th
    r2 = fu * fu + fv * fv
    k = 1 + curv / 100 * 1.5 + edge / 100 * 3 * r2
    mx = ccx + fu * tw * k
    my = ccy + fv * th * k
    out = remap(a, mx, my, edge="clamp")
    rgb = _rgb(out)
    m = np.maximum(np.abs(fu), np.abs(fv)) * 2
    shade = 1 - (edge / 100) * 0.55 * m ** 4 + 0.25 * (edge / 100 + 0.2) * np.clip(-(fu + fv), 0, 1) * m ** 2
    rgb = rgb * shade[..., None]
    d = np.minimum((0.5 - np.abs(fu)) * tw, (0.5 - np.abs(fv)) * th)
    ing = (d < _px(grout, ctx) / 2)[..., None]
    gcol = rgb * (1 - 0.8 * groutop / 100)
    res = np.where(ing, gcol, rgb)
    o = a.copy()
    o[..., :3] = to_u8(res)
    return o


@effect(0x80c1, "Gepolijste steen", [Int("blur", "Vervaging", 0, 20, 2), Int("detail", "Detail", 1, 100, 30),
                                     Int("polish", "Polijsten", 1, 100, 50), Int("angle", "Hoek", 0, 359, 315),
                                     Color("color", "Kleur", (255, 255, 255))])
def polished_stone(a, ctx, detail, polish, angle, color, **kw):
    h, w = a.shape[:2]
    rgb = blur(_rgb(a), _px(kw.get("blur", 2), ctx))
    g = gray(np.clip(rgb, 0, 255))
    x, y = _coords(h, w, _px(40, ctx, 1))
    vein = np.abs(np.sin((x * 0.6 + y * 0.3 + fbm(x, y, ctx.seed, 4) * 6) * np.pi))
    height = blur(g, _px(polish / 25, ctx)) * (detail / 40) + (1 - vein) * 6
    diff, spec = lighting(height, angle, 50, 1.0, 40 + polish * 0.6)
    out = _compose(rgb * (0.9 + 0.1 * vein[..., None]), diff, spec, _col(color, ctx), 0, 50)
    return with_rgb(a, out)


@effect(0x80cd, "Ruw leer", [Color("light", "Lichtkleur", (255, 255, 255)), Color("leather", "Leerkleur", (150, 100, 60)),
                             Int("angle", "Hoek", 0, 359, 315), Int("lum", "Luminantie", -100, 100, 0),
                             Int("contrast", "Contrast", 0, 100, 50), Int("sharp", "Scherpte", 0, 100, 50),
                             Int("blur", "Vervaging", 0, 20, 1)])
def rough_leather(a, ctx, light, leather, angle, lum, contrast, sharp, **kw):
    h, w = a.shape[:2]
    rgb = blur(_rgb(a), _px(kw.get("blur", 1), ctx))
    g = gray(np.clip(rgb, 0, 255))
    x, y = _coords(h, w, _px(3, ctx, 0.6))
    grain = fbm(x, y, ctx.seed, 3)
    grain = np.abs(grain - 0.5) * 2
    height = g * (sharp / 60) + grain * contrast * 0.6
    diff, spec = lighting(height, angle, 40, 1.0, 10)
    base = _col(leather, ctx) * (0.75 + 0.5 * (g / 255))[..., None]
    out = _compose(base, diff, spec, _col(light, ctx), lum, 50)
    return with_rgb(a, out)


@effect(0x80be, "Zandsteen", [Int("blur", "Vervaging", 0, 20, 1), Int("detail", "Detail", 1, 100, 40),
                              Int("lum", "Luminantie", -100, 100, 0), Int("angle", "Hoek", 0, 359, 315),
                              Color("color", "Kleur", (255, 255, 255))])
def sandstone(a, ctx, detail, lum, angle, color, **kw):
    h, w = a.shape[:2]
    rgb = blur(_rgb(a), _px(kw.get("blur", 1), ctx))
    g = gray(np.clip(rgb, 0, 255))
    nz = noise(h, w, ctx.seed)
    x, y = _coords(h, w, _px(8, ctx, 1))
    layers = fbm(x * 0.3, y * 2.0, ctx.seed + 1, 3)
    height = g * (detail / 50) + nz * 12 + layers * 20
    diff, _ = lighting(height, angle, 45, 1.0)
    out = _compose(rgb * (0.85 + 0.3 * nz[..., None] * 0.5 + 0.15 * layers[..., None]), diff, None,
                   _col(color, ctx), lum, 50)
    return with_rgb(a, out)


def _light_params(angle=315, depth=10, shine=0):
    return [Int("smooth", "Gladheid", 0, 100, 20), Int("depth", "Diepte", 0, 100, depth),
            Int("ambience", "Omgevingslicht", -100, 100, 0), Int("shine", "Glans", 0, 100, shine),
            Color("color", "Kleur", (255, 255, 255)), Int("angle", "Hoek", 0, 359, angle),
            Int("intensity", "Intensiteit", 0, 100, 50), Int("elevation", "Hoogte", 0, 90, 30)]


_PATTERNS = ["Goud", "Marmer", "Hout", "Graniet", "Koper", "Jade"]


def _pattern(h, w, kind, sc, seed):
    x, y = _coords(h, w, sc)
    n = fbm(x, y, seed, 4)
    if kind == 0:
        t, st = n, [(0, (120, 80, 10)), (0.5, (220, 170, 50)), (1, (255, 235, 140))]
    elif kind == 1:
        t = np.abs(np.sin((x * 0.5 + n * 5) * np.pi))
        st = [(0, (110, 110, 120)), (0.25, (200, 200, 205)), (1, (245, 244, 240))]
    elif kind == 2:
        t = np.mod(np.sqrt((x * 0.3) ** 2 + (y * 2.5) ** 2) * 0.4 + n * 2, 1)
        st = [(0, (95, 55, 25)), (0.6, (165, 110, 60)), (1, (200, 145, 85))]
    elif kind == 3:
        t = np.clip(n * 0.6 + vnoise(x * 6, y * 6, seed + 5) * 0.4, 0, 1)
        st = [(0, (40, 40, 45)), (0.5, (130, 125, 125)), (0.75, (190, 160, 150)), (1, (235, 230, 230))]
    elif kind == 4:
        t, st = n, [(0, (90, 40, 20)), (0.5, (185, 100, 55)), (0.8, (225, 150, 100)), (1, (90, 150, 120))]
    else:
        t, st = n, [(0, (20, 80, 50)), (0.5, (70, 160, 110)), (1, (190, 235, 200))]
    return _tone(t, st)


def _material_patterns():
    """De eigen naadloze patronen uit Materialen (vaste lijst, vertaald)."""
    from .. import material
    return list(material.PATTERNS)


def _installed_patterns():
    """Patronen uit een eigen installatie of de map Patronen van de gebruiker (alleen ingelezen bij gebruik)."""
    from .. import material
    return [n for n, _ in material.psp_patterns()]


def _tiled_pattern(name, h, w, size, ctx):
    """Patroon uit Materialen of een eigen installatie, getegeld over h x w, als RGB (float)."""
    from PySide6.QtCore import QRect
    from .. import material, imageops as ops
    img = material.pattern_image(name)
    if img is None or img.isNull():
        return np.full((h, w, 3), 128, np.float32)
    m = {"kind": "pattern", "image": img, "angle": 0, "scale": max(1.0, size * ctx.scale)}
    out = material.render(m, QRect(0, 0, w, h))
    return ops.qimage_to_rgba(out)[..., :3].astype(np.float32)


def _pattern_by_index(i, h, w, size, ctx):
    """Kleurpatroon nummer i: eerst de eigen sculptuurpatronen, dan Materialen, dan een eigen installatie."""
    if i < len(_PATTERNS):
        return _pattern(h, w, i, _px(40 * size / 100, ctx, 1), ctx.seed)
    names = _material_patterns() + _installed_patterns()
    k = i - len(_PATTERNS)
    return _tiled_pattern(names[k], h, w, size, ctx) if k < len(names) else _pattern(h, w, 0, _px(40, ctx, 1), ctx.seed)


@effect(0x80b0, "Sculptuur", [Choice("pattern", "Patroon", _PATTERNS + _material_patterns(), extra=_installed_patterns),
                              Int("size", "Grootte %", 10, 400, 100)]
        + _light_params(315, 10, 20))
def sculpture(a, ctx, pattern, size, smooth, depth, ambience, shine, color, angle, intensity, elevation):
    h, w = a.shape[:2]
    pat = _pattern_by_index(pattern, h, w, size, ctx)
    hgt = blur(gray(a), _px(smooth / 10, ctx))
    diff, spec = lighting(hgt, angle, elevation, depth / 4, shine)
    return with_rgb(a, _compose(pat, diff, spec, _col(color, ctx), ambience, intensity))


@effect(0x80c0, "Zacht plastic", [Int("blur", "Vervaging", 0, 20, 2), Int("detail", "Detail", 1, 100, 40),
                                  Int("density", "Dichtheid", 1, 100, 40), Int("angle", "Hoek", 0, 359, 315),
                                  Color("color", "Kleur", (255, 255, 255))])
def soft_plastic(a, ctx, detail, density, angle, color, **kw):
    rgb = blur(_rgb(a), _px(kw.get("blur", 2), ctx))
    g = gray(np.clip(rgb, 0, 255)) / 255
    lv = 2 + density // 8
    q = np.round(g * lv) / lv
    hgt = blur(q * 255, _px(2 + (100 - detail) / 12, ctx, 1)) * (0.4 + detail / 60)
    diff, spec = lighting(hgt, angle, 45, 1.0, 80)
    rgbq = blur(rgb, _px(2, ctx))
    return with_rgb(a, _compose(rgbq, diff, spec, _col(color, ctx), 0, 50))


@effect(0x80cb, "Stro", [Int("blur", "Vervaging", 0, 20, 0), Int("density", "Dichtheid", 1, 100, 50),
                         Int("length", "Lengte", 1, 100, 30), Int("width", "Breedte", 1, 10, 2),
                         Int("transp", "Transparantie", 0, 100, 20)])
def straw(a, ctx, density, length, width, transp, **kw):
    h, w = a.shape[:2]
    rgb = blur(_rgb(a), _px(kw.get("blur", 0), ctx))
    x, y = _coords(h, w, _px(70, ctx, 1))
    tex = np.zeros((h, w), np.float32)
    wr = _px(width, ctx) / 2
    ln = _px(length, ctx, 1)
    steps = min(12, max(2, int(ln / max(1.0, wr))))
    for i in range(2):
        seeds = (noise(h, w, ctx.seed + 11 * i) < 0.003 + density / 100 * 0.03).astype(np.float32)
        if wr >= 0.75:
            seeds = (blur(seeds, wr) > 0.08).astype(np.float32)
        base = 0.5 if i == 0 else 2.2
        theta = base + (fbm(x, y, ctx.seed + 3 + i, 2) - 0.5) * 1.6
        tex = np.maximum(tex, _lic(seeds, theta, ln, steps))
    lit = 0.5 + 0.75 * tex
    out = rgb * lit[..., None] + tex[..., None] * np.array([40, 30, 0], np.float32)
    out = out + (_rgb(a) - out) * (transp / 100)
    return with_rgb(a, out)


_TEXTURES = ["Steen", "Stof", "Papier", "Ruis", "Bakstenen", "Golven", "Gekreukt"]


def _texture(h, w, kind, sc, seed):
    x, y = _coords(h, w, sc)
    if kind == 0:
        n = fbm(x, y, seed, 4)
        return n * 0.6 + _smoothstep(0, 0.08, np.abs(fbm(x * 0.7, y * 0.7, seed + 2, 3) - 0.5)) * 0.4
    if kind == 1:
        t = np.sin(x * np.pi * 2) * np.sin(y * np.pi * 2) * 0.5 + 0.5
        return t * 0.8 + vnoise(x * 4, y * 4, seed) * 0.2
    if kind == 2:
        return fbm(x * 2, y * 2, seed, 5, 0.65)
    if kind == 3:
        return vnoise(x * 4, y * 4, seed)
    if kind == 4:
        row = np.floor(y / 1.0)
        bx = x / 2 + (np.mod(row, 2) * 0.5)
        fx, fy = bx - np.floor(bx), y - row
        d = np.minimum(np.minimum(fx, 1 - fx) * 2, np.minimum(fy, 1 - fy))
        return _smoothstep(0.02, 0.1, d) * (0.85 + 0.15 * vnoise(x * 3, y * 3, seed))
    if kind == 5:
        return np.sin((y + fbm(x, y, seed, 2) * 1.2) * np.pi) * 0.5 + 0.5
    n = fbm(x, y, seed, 4)
    return 1 - np.abs(n - 0.5) * 2


@effect(0x80b1, "Textuur", [Choice("texture", "Textuur", _TEXTURES + _material_patterns(), extra=_installed_patterns),
                            Int("size", "Grootte %", 10, 400, 100)]
        + _light_params(315, 10, 0))
def texture(a, ctx, texture, size, smooth, depth, ambience, shine, color, angle, intensity, elevation):
    h, w = a.shape[:2]
    if texture < len(_TEXTURES):
        tex = _texture(h, w, texture, _px(24 * size / 100, ctx, 1), ctx.seed) * 255
    else:  # patroon uit Materialen of een eigen installatie: de helderheid wordt het reliëf
        names = _material_patterns() + _installed_patterns()
        k = texture - len(_TEXTURES)
        rgb = _tiled_pattern(names[min(k, len(names) - 1)], h, w, size, ctx)
        tex = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    tex = blur(tex, _px(smooth / 20, ctx))
    diff, spec = lighting(tex, angle, elevation, depth / 10 * ctx.scale, shine)
    return with_rgb(a, _compose(_rgb(a), diff, spec, _col(color, ctx), ambience, intensity))


def _tile_dist(h, w, shape, s):
    """Afstand (pixels) tot de rand van de tegel en tegel-id."""
    yy, xx = grid(h, w)
    if shape == 1:  # vierkant
        u, v = xx / s, yy / s
        fu, fv = u - np.floor(u), v - np.floor(v)
        return np.minimum(np.minimum(fu, 1 - fu), np.minimum(fv, 1 - fv)) * s
    if shape == 0:  # driehoek: drie lijnfamilies onder 60 graden
        hh = s * math.sqrt(3) / 2
        d = None
        for ang in (90, 30, 150):
            r = math.radians(ang)
            t = (xx * math.cos(r) + yy * math.sin(r)) / hh
            f = t - np.floor(t)
            dd = np.minimum(f, 1 - f) * hh
            d = dd if d is None else np.minimum(d, dd)
        return d
    # zeshoek (puntige bovenkant) via kubuscoördinaten
    size = s / math.sqrt(3)
    q = (math.sqrt(3) / 3 * xx - yy / 3) / size
    r = (2 / 3 * yy) / size
    cx, cz = q, r
    cy = -cx - cz
    rx, ry, rz = np.rint(cx), np.rint(cy), np.rint(cz)
    dx, dy, dz = np.abs(rx - cx), np.abs(ry - cy), np.abs(rz - cz)
    m1 = (dx > dy) & (dx > dz)
    m2 = ~m1 & (dy > dz)
    rx = np.where(m1, -ry - rz, rx)
    ry = np.where(m2, -rx - rz, ry)
    rz = np.where(~m1 & ~m2, -rx - ry, rz)
    centx = size * math.sqrt(3) * (rx + rz / 2)
    centy = size * 1.5 * rz
    px, py = xx - centx, yy - centy
    apo = s / 2
    m = None
    for ang in (0, 60, 120):
        rr = math.radians(ang)
        p = np.abs(px * math.cos(rr) + py * math.sin(rr))
        m = p if m is None else np.maximum(m, p)
    return apo - m


@effect(0x80b4, "Mozaïekstukjes", [Choice("shape", "Tegelvorm", ["Driehoek", "Vierkant", "Zeshoek"], 1),
                                    Int("size", "Tegelgrootte", 4, 200, 24), Int("border", "Randgrootte", 0, 20, 2)]
        + _light_params(315, 20, 20))
def tiles(a, ctx, shape, size, border, smooth, depth, ambience, shine, color, angle, intensity, elevation):
    h, w = a.shape[:2]
    s = _px(size, ctx, 2)
    d = _tile_dist(h, w, shape, s)
    bw = _px(border, ctx) / 2
    bev = _px(2 + smooth / 10, ctx, 1)
    hgt = np.clip((d - bw) / bev, 0, 1) * 30
    diff, spec = lighting(hgt, angle, elevation, depth / 10 * ctx.scale, shine)
    out = _compose(_rgb(a), diff, spec, _col(color, ctx), ambience, intensity)
    out = np.where((d < bw)[..., None], 0, out)
    return with_rgb(a, out)


@effect(0x80a3, "Weefpatroon", [Int("gap", "Tussenruimte", 0, 50, 4), Int("width", "Breedte", 1, 100, 12),
                                Int("opacity", "Dekking", 0, 100, 50), Color("weave", "Weefkleur", (255, 255, 255)),
                                Color("gapcol", "Kleur tussenruimte", (0, 0, 0)), Bool("fill", "Tussenruimte vullen", True)])
def weave(a, ctx, gap, width, opacity, weave, gapcol, fill):
    h, w = a.shape[:2]
    wd = _px(width, ctx, 1)
    gp = _px(gap, ctx)
    per = wd + gp
    yy, xx = grid(h, w)
    ux, uy = np.mod(xx, per), np.mod(yy, per)
    inv = ux < wd  # verticale draad
    inh = uy < wd  # horizontale draad
    cell = (np.floor(xx / per) + np.floor(yy / per)).astype(np.int64) % 2 == 0
    prof_v = np.sin(np.clip(ux / wd, 0, 1) * np.pi)
    prof_h = np.sin(np.clip(uy / wd, 0, 1) * np.pi)
    # langs de draad: donkerder waar hij onder de andere duikt
    along_v = np.sin(np.clip(uy / per, 0, 1) * np.pi)
    along_h = np.sin(np.clip(ux / per, 0, 1) * np.pi)
    vert_on_top = np.where(inv & inh, cell, inv)
    prof = np.where(vert_on_top, prof_v * (0.7 + 0.3 * np.where(cell, along_v, 1)),
                    prof_h * (0.7 + 0.3 * np.where(~cell, along_h, 1)))
    rgb = _rgb(a)
    op = opacity / 100
    strand = rgb + (_col(weave, ctx) - rgb) * (op * 0.4)
    strand = strand * (1 - op + op * (0.35 + 0.75 * prof))[..., None]
    gapc = (np.broadcast_to(_col(gapcol, ctx), rgb.shape) if fill else rgb)
    out = np.where((inv | inh)[..., None], strand, gapc)
    return with_rgb(a, out)


# ================================================================ Eigen filter

_KP = [Int(f"k{r}{c}", f"Rij {r + 1} kol {c + 1}", -100, 100, 1 if (r, c) == (2, 2) else 0)
       for r in range(5) for c in range(5)]


@effect(0x807c, "Eigen filter", _KP + [Int("divisor", "Deler", 1, 999, 1), Int("bias", "Basis", -255, 255, 0),
                                       Bool("absval", "Absolute waarde (anders afkappen)", False),
                                       Bool("alpha", "Ook alfakanaal filteren", False)])
def user_filter(a, ctx, divisor, bias, absval, alpha, **k):
    kern = np.array([[k.get(f"k{r}{c}", 0) for c in range(5)] for r in range(5)], np.float32)
    nch = 4 if alpha else 3
    src = a[..., :nch].astype(np.float32)
    res = convolve(src, kern) / max(1, divisor) + bias
    if absval:
        res = np.abs(res)
    out = a.copy()
    out[..., :nch] = to_u8(res)
    return out
