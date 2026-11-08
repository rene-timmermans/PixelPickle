"""Aanpassingen uit het menu Aanpassen (fotocorrectie, kleur, helderheid, ruis, vervagen, lenscorrectie)."""
import numpy as np

from ..imageops import box_blur, hsl_to_rgb, rgb_to_hsl
from . import Bool, Choice, Curve, Int, effect
from .common import blur, blur_rgba, gray, grid, remap, sobel, to_u8, with_rgb

# ------------------------------------------------------------------ hulpfuncties


def _rgb(a):
    return a[..., :3].astype(np.float32)


def _lum(rgb):
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def _px(v, ctx, lo=1):
    """Pixelmaat geschaald naar de voorbeeldschaal (geheel getal >= lo)."""
    return max(lo, int(round(v * ctx.scale)))


def _valid(a):
    m = a[..., 3] > 0
    return m if m.any() else np.ones(a.shape[:2], bool)


def _pct(ch, mask, p):
    """Percentiel p (0..100) van een uint8 kanaal binnen het masker (via histogram)."""
    hist = np.bincount(ch[mask].ravel(), minlength=256).astype(np.float64)
    cdf = np.cumsum(hist)
    return int(np.searchsorted(cdf, cdf[-1] * p / 100.0))


def _stretch_bounds(a, clip=0.5):
    m = _valid(a)
    lo = np.array([_pct(a[..., c], m, clip) for c in range(3)], np.float32)
    hi = np.array([_pct(a[..., c], m, 100 - clip) for c in range(3)], np.float32)
    hi = np.maximum(hi, lo + 1)
    return lo, hi


def _sat(rgb, f):
    y = _lum(rgb)[..., None]
    return y + (rgb - y) * f


def _apply_lut(a, luts):
    """luts: (256,) of (3, 256) float; geeft uint8 RGBA met alfa van a."""
    luts = np.asarray(luts, np.float32)
    if luts.ndim == 1:
        luts = np.stack([luts] * 3)
    lut = to_u8(luts)
    out = a.copy()
    for c in range(3):
        out[..., c] = lut[c][a[..., c]]
    return out


def _monotone_lut(points):
    """Monotone kubische interpolatie (Fritsch-Carlson) van [x, y] punten tot een LUT van 256 waarden."""
    pts = {}
    for p in points or []:
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            continue
        pts[int(round(min(255, max(0, x))))] = min(255.0, max(0.0, y))
    if len(pts) < 2:
        if len(pts) == 1:
            return np.full(256, list(pts.values())[0], np.float32)
        return np.arange(256, dtype=np.float32)
    xs = np.array(sorted(pts), np.float64)
    ys = np.array([pts[int(x)] for x in xs], np.float64)
    n = len(xs)
    d = np.diff(ys) / np.diff(xs)
    m = np.empty(n)
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        m[i] = 0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2
    for i in range(n - 1):
        if d[i] == 0:
            m[i] = m[i + 1] = 0.0
        else:
            al, be = m[i] / d[i], m[i + 1] / d[i]
            s = al * al + be * be
            if s > 9:
                t = 3 / np.sqrt(s)
                m[i], m[i + 1] = t * al * d[i], t * be * d[i]
    x = np.arange(256, dtype=np.float64)
    k = np.clip(np.searchsorted(xs, x, side="right") - 1, 0, n - 2)
    h = xs[k + 1] - xs[k]
    t = np.clip((x - xs[k]) / h, 0, 1)
    t2, t3 = t * t, t * t * t
    y = ((2 * t3 - 3 * t2 + 1) * ys[k] + (t3 - 2 * t2 + t) * h * m[k]
         + (-2 * t3 + 3 * t2) * ys[k + 1] + (t3 - t2) * h * m[k + 1])
    y = np.where(x < xs[0], ys[0], np.where(x > xs[-1], ys[-1], y))
    return np.clip(y, 0, 255).astype(np.float32)


def _guided(p, r, eps):
    """Zelfgeleid filter (He et al.): randbehoudend vervagen. p float 0..255 (2D/3D), eps in 255²-eenheden."""
    r = int(r)
    if r < 1:
        return p.astype(np.float32)
    q = p.astype(np.float32) - 128

    def mb(x):
        return box_blur(x, r, passes=1)
    m = mb(q)
    v = np.maximum(mb(q * q) - m * m, 0)
    aa = v / (v + eps)
    bb = m - aa * m
    return mb(aa) * q + mb(bb) + 128


def _median(x, r, axis=None):
    """Mediaan van uint8 (H, W, C) over een (2r+1)² venster, of 1D langs axis=1 (horizontaal)."""
    r = int(r)
    if r < 1:
        return x.copy()
    h, w = x.shape[:2]
    if axis == 1:
        p = np.pad(x, ((0, 0), (r, r), (0, 0)), mode="edge")
        offs = [(0, dx) for dx in range(2 * r + 1)]
    else:
        p = np.pad(x, ((r, r), (r, r), (0, 0)), mode="edge")
        offs = [(dy, dx) for dy in range(2 * r + 1) for dx in range(2 * r + 1)]
    k = len(offs)
    out = np.empty_like(x)
    rows = max(1, int(40_000_000 // max(1, k * w * x.shape[2])))
    for y0 in range(0, h, rows):
        y1 = min(h, y0 + rows)
        st = np.stack([p[y0 + dy:y1 + dy, dx:dx + w] for dy, dx in offs])
        out[y0:y1] = np.partition(st, k // 2, axis=0)[k // 2]
    return out


def _vmean(x, r):
    """Gemiddelde langs de verticale as (box, straal r)."""
    if r < 1:
        return x
    n = x.shape[0]
    c = np.concatenate([np.zeros((1,) + x.shape[1:], np.float32), np.cumsum(x, axis=0, dtype=np.float32)])
    idx = np.arange(n)
    hi = np.minimum(idx + r + 1, n)
    lo = np.maximum(idx - r, 0)
    return (c[hi] - c[lo]) / (hi - lo).reshape((-1,) + (1,) * (x.ndim - 1)).astype(np.float32)


def _tone(rgb, shadows, highlights, base_r):
    """Schaduwen (+ = lichter) en hoge lichten (+ = lichter, - = donkerder) via een lokaal luminantiemasker."""
    y = _lum(rgb)
    base = blur(y, base_r) / 255
    base = np.clip(base * 0.6 + (y / 255) * 0.4, 0, 1)
    ws = np.clip(1 - base / 0.6, 0, 1) ** 2
    wh = np.clip((base - 0.4) / 0.6, 0, 1) ** 2
    delta = shadows / 100 * 110 * ws + highlights / 100 * 110 * wh
    # licht maken met zachte schouder: compenseer zodat witten niet hard afknippen
    return rgb + delta[..., None]


def _unsharp(rgb, radius, amount):
    if amount == 0 or radius < 1:
        return rgb
    return rgb + (rgb - blur(rgb, radius)) * amount


def _premul(a):
    al = a[..., 3:4].astype(np.float32) / 255
    return np.dstack([a[..., :3].astype(np.float32) * al, al * 255])


def _unpremul(p):
    al = p[..., 3:4]
    rgb = np.where(al > 1e-3, p[..., :3] / np.maximum(al / 255, 1e-6), 0)
    return np.dstack([to_u8(rgb), to_u8(al[..., 0])])


def _auto_fix(a, strength=1.0):
    rgb = _rgb(a)
    lo, hi = _stretch_bounds(a, 0.5)
    # mix van per-kanaal rekken (kleurzweem weg) en gezamenlijk rekken (kleur behouden)
    lo2 = lo * 0.6 + lo.min() * 0.4
    hi2 = hi * 0.6 + hi.max() * 0.4
    st = (rgb - lo2) / np.maximum(hi2 - lo2, 1) * 255
    st = np.clip(st, 0, 255)
    m = _valid(a)
    mean = float(_lum(st)[m].mean()) / 255
    g = np.clip(np.log(0.5) / np.log(np.clip(mean, 0.05, 0.95)), 0.75, 1.33)
    g = 1 + (g - 1) * 0.5
    st = 255 * (st / 255) ** (1 / g)
    st = _sat(st, 1.12)
    return rgb + (st - rgb) * strength


# ------------------------------------------------------------------ fotocorrectie


@effect(0x8240, "Eénstaps-fotocorrectie")
def one_step_fix(a, ctx):
    return with_rgb(a, _auto_fix(a))


@effect(0x82d8, "Slimme fotocorrectie", [
    Int("brightness", "Helderheid algemeen", -100, 100, 0), Int("shadows", "Schaduwen", -100, 100, 0),
    Int("highlights", "Lichte delen", -100, 100, 0), Int("saturation", "Verzadiging", -100, 100, 0),
    Int("focus", "Focus (verscherpen)", 0, 100, 0), Bool("auto", "Automatisch kleurbalans/niveaus", True)])
def smart_fix(a, ctx, brightness, shadows, highlights, saturation, focus, auto):
    rgb = _auto_fix(a) if auto else _rgb(a)
    if brightness:
        g = 2 ** (-brightness / 100)
        rgb = 255 * (np.clip(rgb, 0, 255) / 255) ** g
    if shadows or highlights:
        rgb = _tone(rgb, shadows, highlights, max(1, max(a.shape[:2]) / 60))
    if saturation:
        rgb = _sat(rgb, 1 + saturation / 100)
    if focus:
        rgb = _unsharp(rgb, _px(1.5, ctx, 0), focus / 60)
    return with_rgb(a, rgb)


# ------------------------------------------------------------------ ruis


def _denoise(rgb, ctx, strength, detail):
    y = _lum(rgb)
    ch = rgb - y[..., None]
    s = strength / 100
    yf = _guided(y, _px(2, ctx), (4 + 22 * s) ** 2)
    yf = yf + (y - yf) * (detail / 100) * 0.6
    chf = _guided(ch + 128, _px(1 + 3 * s, ctx), (6 + 30 * s) ** 2) - 128
    chf = blur(chf, _px(1 + 2 * s, ctx, 0))
    return yf[..., None] + chf


@effect(0x82f1, "Eénstaps-grofkorreligheid verwijderen")
def one_step_denoise(a, ctx):
    return with_rgb(a, _denoise(_rgb(a), ctx, 50, 40))


@effect(0x82c1, "Grofkorreligheid van digitale camera verwijderen", [
    Int("strength", "Correctie (sterkte)", 0, 100, 50), Int("detail", "Details behouden %", 0, 100, 50),
    Int("sharpen", "Verscherpen", 0, 100, 0)])
def dcnr(a, ctx, strength, detail, sharpen):
    rgb = _rgb(a)
    if strength > 0:
        rgb = _denoise(rgb, ctx, strength, detail)
    if sharpen:
        rgb = _unsharp(rgb, _px(1, ctx, 0), sharpen / 50)
    return with_rgb(a, rgb)


# ------------------------------------------------------------------ kleur


@effect(0x82dc, "Kleurbalans", [
    Choice("range", "Bereik", ["Schaduwen", "Middentonen", "Lichte tonen"], 1),
    Int("cr", "Cyaan - rood", -100, 100, 0), Int("mg", "Magenta - groen", -100, 100, 0),
    Int("yb", "Geel - blauw", -100, 100, 0), Bool("preserve", "Helderheid behouden", True)])
def color_balance(a, ctx, range, cr, mg, yb, preserve):
    rgb = _rgb(a)
    y0 = _lum(rgb)
    L = y0 / 255
    w = [np.clip(1 - L / 0.55, 0, 1) ** 1.5, 4 * L * (1 - L), np.clip((L - 0.45) / 0.55, 0, 1) ** 1.5][int(range)]
    v = np.array([cr - (mg + yb) / 2, mg - (cr + yb) / 2, yb - (cr + mg) / 2], np.float32) * 0.6
    rgb = rgb + w[..., None] * v
    if preserve:
        rgb = rgb + (y0 - _lum(rgb))[..., None]
    return with_rgb(a, rgb)


@effect(0x8062, "Kanaalmenger", [
    Choice("out", "Uitvoerkanaal", ["Rood", "Groen", "Blauw"]),
    Int("red", "Rood %", -200, 200, 100), Int("green", "Groen %", -200, 200, 0), Int("blue", "Blauw %", -200, 200, 0),
    Int("constant", "Constante %", -200, 200, 0), Bool("mono", "Monochroom", False)])
def channel_mixer(a, ctx, out, red, green, blue, constant, mono):
    rgb = _rgb(a)
    mix = rgb[..., 0] * (red / 100) + rgb[..., 1] * (green / 100) + rgb[..., 2] * (blue / 100) + constant / 100 * 255
    if mono:
        res = np.repeat(mix[..., None], 3, axis=-1)
    else:
        res = rgb.copy()
        res[..., int(out)] = mix
    return with_rgb(a, res)


@effect(0x8064, "Vervagingscorrectie", [Int("amount", "Mate", 0, 100, 45)])
def fade_correction(a, ctx, amount):
    rgb = _rgb(a)
    s = amount / 100
    lo, hi = _stretch_bounds(a, 0.3 + 1.5 * s)
    st = np.clip((rgb - lo) / (hi - lo) * 255, 0, 255)
    st = _sat(st, 1 + 0.6 * s)
    return with_rgb(a, rgb + (st - rgb) * min(1.0, s * 1.5))


@effect(0x806a, "Verhelderen", [Int("strength", "Sterkte", 1, 10, 5)])
def clarify(a, ctx, strength):
    rgb = _rgb(a)
    y = _lum(rgb)
    r = max(1, max(a.shape[:2]) / 45)
    base = _guided(y, int(round(r)), 30 ** 2)
    detail = y - base
    L = y / 255
    w = 0.4 + 2.4 * L * (1 - L)
    dy = detail * (strength * 0.12) * w
    return with_rgb(a, rgb + dy[..., None])


@effect(0x8075, "Curven", [Curve("points", "Curve"), Choice("channel", "Kanaal", ["RGB", "Rood", "Groen", "Blauw"])])
def curves(a, ctx, points, channel):
    lut = _monotone_lut(points)
    ident = np.arange(256, dtype=np.float32)
    luts = np.stack([lut] * 3) if channel == 0 else np.stack([lut if c == channel - 1 else ident for c in range(3)])
    return _apply_lut(a, luts)


@effect(0x8053, "Lichtste delen/middentonen/schaduwen", [
    Int("shadow", "Schaduw", -100, 100, 0), Int("midtone", "Middentoon", -100, 100, 0),
    Int("highlight", "Lichte delen", -100, 100, 0)])
def hms(a, ctx, shadow, midtone, highlight):
    pts = [[0, 0], [64, 64 + shadow * 0.6], [128, 128 + midtone * 0.8], [192, 192 + highlight * 0.6], [255, 255]]
    lut = _monotone_lut(pts)
    rgb = _rgb(a)
    y = _lum(rgb)
    yi = np.clip(np.rint(y), 0, 255).astype(np.int32)
    return with_rgb(a, rgb + (lut[yi] - y)[..., None])


@effect(0x8070, "Histogram aanpassen", [
    Int("low", "Invoer laag", 0, 254, 0), Int("high", "Invoer hoog", 1, 255, 255),
    Int("gamma", "Gamma × 100", 10, 500, 100), Int("out_low", "Uitvoer min", 0, 255, 0),
    Int("out_high", "Uitvoer max", 0, 255, 255)])
def histogram_adjust(a, ctx, low, high, gamma, out_low, out_high):
    x = np.arange(256, dtype=np.float32)
    hi = max(high, low + 1)
    t = np.clip((x - low) / (hi - low), 0, 1) ** (100 / max(1, gamma))
    return _apply_lut(a, out_low + t * (out_high - out_low))


@effect(0x8056, "Histogram egaliseren")
def equalize(a, ctx):
    rgb = _rgb(a)
    y = _lum(rgb)
    yi = np.clip(np.rint(y), 0, 255).astype(np.int64)
    m = _valid(a)
    hist = np.bincount(yi[m], minlength=256).astype(np.float64)
    cdf = np.cumsum(hist)
    c0 = cdf[np.nonzero(hist)[0][0]]
    lut = np.clip((cdf - c0) / max(cdf[-1] - c0, 1) * 255, 0, 255).astype(np.float32)
    return with_rgb(a, rgb + (lut[yi] - y)[..., None])


@effect(0x8057, "Histogram uitbreiden")
def stretch(a, ctx):
    lo, hi = _stretch_bounds(a, 0.5)
    x = np.arange(256, dtype=np.float32)
    return _apply_lut(a, np.stack([(x - lo[c]) / (hi[c] - lo[c]) * 255 for c in range(3)]))


@effect(0x805f, "Kleurtoonverdeling", [
    Int("source", "Bronkleurtoon", 0, 359, 0), Int("range", "Bereik", 1, 180, 30),
    Int("target", "Doelkleurtoon", 0, 359, 0), Int("saturation", "Verzadiging", -100, 100, 0)])
def hue_map(a, ctx, source, range, target, saturation):
    rgb = _rgb(a)
    h, s, l = rgb_to_hsl(rgb)
    d = (h * 360 - source + 180) % 360 - 180
    w = np.clip(1 - np.abs(d) / range, 0, 1)
    w = w * w * (3 - 2 * w)
    shift = ((target - source + 180) % 360 - 180) / 360
    h2 = h + shift * w
    sf = 1 + saturation / 100 * w
    s2 = np.clip(s * sf, 0, 1)
    return with_rgb(a, hsl_to_rgb(h2.astype(np.float32), s2.astype(np.float32), l))


# ------------------------------------------------------------------ vervagen / verscherpen


@effect(0x82fb, "Velddiepte", [
    Int("focus", "Focusgrootte %", 0, 100, 50), Int("amount", "Vervaging", 0, 100, 40),
    Int("feather", "Doezelen %", 0, 100, 50)])
def depth_of_field(a, ctx, focus, amount, feather):
    h, w = a.shape[:2]
    if amount == 0:
        return a.copy()
    b = blur_rgba(a, amount * 0.2 * ctx.scale)
    yy, xx = grid(h, w)
    rx, ry = max(focus / 100 * w / 2, 0.5), max(focus / 100 * h / 2, 0.5)
    d = np.sqrt(((xx - (w - 1) / 2) / rx) ** 2 + ((yy - (h - 1) / 2) / ry) ** 2)
    f = max(feather / 100, 0.02)
    t = np.clip((d - 1) / f, 0, 1)
    t = (t * t * (3 - 2 * t))[..., None]
    out = _premul(a) * (1 - t) + _premul(b) * t
    return _unpremul(out)


@effect(0x808f, "Bewegingsvervaging", [Int("angle", "Hoek", 0, 359, 0), Int("strength", "Sterkte (px)", 1, 100, 10)])
def motion_blur(a, ctx, angle, strength):
    L = strength * ctx.scale
    if L < 1:
        return a.copy()
    h, w = a.shape[:2]
    n = int(min(64, np.ceil(L))) + 1
    th = np.deg2rad(angle)
    ux, uy = np.cos(th), -np.sin(th)
    R = int(np.ceil(L / 2)) + 1
    P = np.pad(_premul(a), ((R, R), (R, R), (0, 0)), mode="edge")
    acc = np.zeros((h, w, 4), np.float32)
    for t in np.linspace(-L / 2, L / 2, n):
        dx, dy = int(round(t * ux)), int(round(t * uy))
        acc += P[R + dy:R + dy + h, R + dx:R + dx + w]
    return _unpremul(acc / n)


@effect(0x8288, "Radiaal vervagen", [
    Choice("kind", "Type", ["Draaien", "Zoomen", "Kronkelen"]), Int("strength", "Sterkte", 0, 100, 30),
    Int("cx", "Horizontale verschuiving %", -100, 100, 0), Int("cy", "Verticale verschuiving %", -100, 100, 0),
    Int("twirl", "Kronkelgraden", -90, 90, 30)])
def radial_blur(a, ctx, kind, strength, cx, cy, twirl):
    if strength == 0:
        return a.copy()
    h, w = a.shape[:2]
    P = _premul(a).reshape(-1, 4)
    yy, xx = grid(h, w)
    cxp = (w - 1) / 2 * (1 + cx / 100)
    cyp = (h - 1) / 2 * (1 + cy / 100)
    dx, dy = xx - cxp, yy - cyp
    r = np.sqrt(dx * dx + dy * dy)
    ang = np.arctan2(dy, dx)
    rmax = max(float(r.max()), 1.0)
    s = strength / 100
    n = 16
    acc = np.zeros((h * w, 4), np.float32)
    for t in np.linspace(-0.5, 0.5, n):
        if kind == 0:  # draaien
            a2, r2 = ang + t * s * np.deg2rad(30), r
        elif kind == 1:  # zoomen
            a2, r2 = ang, r * (1 + t * s * 0.4)
        else:  # kronkelen: draaien langs een spiraal
            a2 = ang + t * s * np.deg2rad(20) + np.deg2rad(twirl) * t * s * (1 - r / rmax)
            r2 = r * (1 + t * s * 0.15)
        sx = np.clip(np.rint(cxp + r2 * np.cos(a2)), 0, w - 1).astype(np.int64)
        sy = np.clip(np.rint(cyp + r2 * np.sin(a2)), 0, h - 1).astype(np.int64)
        acc += P[(sy * w + sx).ravel()]
    return _unpremul((acc / n).reshape(h, w, 4))


def _blend(base, top, mode):
    b, t = base / 255, top / 255
    if mode == 0:  # bedekken
        r = np.where(b < 0.5, 2 * b * t, 1 - 2 * (1 - b) * (1 - t))
    elif mode == 1:  # zacht licht
        r = (1 - 2 * t) * b * b + 2 * t * b
    else:  # hard licht
        r = np.where(t < 0.5, 2 * b * t, 1 - 2 * (1 - b) * (1 - t))
    return r * 255


@effect(0x82db, "High-pass verscherpen", [
    Int("radius", "Straal", 1, 100, 10), Int("strength", "Sterkte", 0, 100, 50),
    Choice("mode", "Mengmodus", ["Bedekken", "Zacht licht", "Hard licht"])])
def high_pass(a, ctx, radius, strength, mode):
    rgb = _rgb(a)
    hp = np.clip(128 + (rgb - blur(rgb, radius * ctx.scale)), 0, 255)
    res = _blend(rgb, hp, mode)
    return with_rgb(a, rgb + (res - rgb) * strength / 100)


@effect(0x8192, "Zachte focus", [
    Int("softness", "Zachtheid", 0, 100, 35), Int("halo", "Halo hoeveelheid", 0, 100, 20),
    Int("halo_size", "Halo grootte", 0, 100, 50)])
def soft_focus(a, ctx, softness, halo, halo_size):
    rgb = _rgb(a)
    b = blur(rgb, max(1.0, 4 * ctx.scale))
    out = rgb + (b - rgb) * softness / 100 * 0.85
    if halo:
        hb = blur(rgb, max(1.0, (2 + halo_size * 0.25) * ctx.scale))
        y = _lum(hb)
        thr = 230 - halo * 1.3
        m = np.clip((y - thr) / max(255 - thr, 1), 0, 1)[..., None] * (halo / 100)
        out = 255 - (255 - out) * (1 - hb / 255 * m)  # bleken (screen)
    return with_rgb(a, out)


@effect(0x8307, "Huid effenen", [Int("amount", "Mate", 0, 100, 50)])
def skin_smooth(a, ctx, amount):
    rgb = _rgb(a)
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    cb = 128 - 0.168736 * R - 0.331264 * G + 0.5 * B
    cr = 128 + 0.5 * R - 0.418688 * G - 0.081312 * B
    y = _lum(rgb)
    m = np.exp(-((cb - 108) / 14) ** 2 - ((cr - 152) / 16) ** 2) * np.clip((y - 30) / 40, 0, 1)
    m = np.clip(blur(m, _px(2, ctx)) * 1.5, 0, 1)
    sm = _guided(rgb, _px(3, ctx), 18 ** 2)
    sm = blur(sm, _px(1, ctx, 0))
    t = (m * amount / 100)[..., None]
    return with_rgb(a, rgb + (sm - rgb) * t)


@effect(0x82b3, "Achtergrondlicht", [Int("strength", "Sterkte", 0, 100, 50)])
def backlighting(a, ctx, strength):
    return with_rgb(a, _tone(_rgb(a), 0, -strength * 0.8, max(1, max(a.shape[:2]) / 60)))


@effect(0x82b1, "Invulflits", [Int("strength", "Sterkte", 0, 100, 50)])
def fill_flash(a, ctx, strength):
    return with_rgb(a, _tone(_rgb(a), strength * 0.8, 0, max(1, max(a.shape[:2]) / 60)))


@effect(0x806e, "Rode ogen verwijderen", [Int("strength", "Sterkte", 0, 100, 75),
                                           Int("eye_size", "Max. oogdiameter (%)", 1, 15, 4)])
def red_eye(a, ctx, strength, eye_size=4):
    """Alleen rode ogen: kleine, losstaande rode vlekken. Een vlek telt mee als er in een ruime omgeving
    (een paar keer de grootste oogdiameter) weinig ander rood is; grote rode vlakken zoals kleding, een
    bal of een muur vallen zo af. Met een selectie werkt het alleen daarbinnen."""
    rgb = _rgb(a)
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    gb = (G + B) / 2
    ratio = R / np.maximum(gb, 8)
    red = np.clip((ratio - 1.8) / 0.8, 0, 1) * np.clip((R - 70) / 40, 0, 1)
    h, w = red.shape
    d_max = max(2.0, max(h, w) * eye_size / 100)          # grootste oogdiameter in pixels
    core = (red > 0.35).astype(np.float32)
    # aandeel rood in een ruime omgeving: bij een pupil laag (er omheen zit oogwit, iris en huid)
    around = blur(core, max(1.0, d_max * 1.2))
    near = blur(core, max(0.6, d_max * 0.25))
    isolated = np.clip((0.22 - around) / 0.12, 0, 1) * np.clip((near - 0.05) / 0.1, 0, 1)
    # het masker iets laten uitlopen zodat de rand van de pupil ook meegaat
    keep = np.clip(blur(isolated, max(0.6, d_max * 0.15)) * 3, 0, 1)
    m = red * keep
    m = np.clip(blur(m, _px(1, ctx, 0)) * 1.3, 0, 1) * (strength / 100)
    newR = np.minimum(R, gb * 0.9)
    dark = 0.85
    out = rgb.copy()
    out[..., 0] = R + (newR * dark - R) * m
    out[..., 1] = G + (G * dark - G) * m
    out[..., 2] = B + (B * dark - B) * m
    return with_rgb(a, out)


def _edge_near(y, radius, thr=40.0):
    gx, gy = sobel(y)
    e = np.clip(np.sqrt(gx * gx + gy * gy) / (4 * thr), 0, 1)
    return np.clip(blur(e, radius) * 3, 0, 1)


@effect(0x82d9, "Eénstaps-paarse uitvloeiingscorrectie")
def purple_fringe(a, ctx):
    rgb = _rgb(a)
    y = _lum(rgb)
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    purple = np.clip((np.minimum(R * 0.6 + B * 0.4, B) - G - 15) / 40, 0, 1) * np.clip((B - R * 0.7) / 30 + 0.5, 0, 1)
    m = purple * _edge_near(y, _px(3, ctx))
    gray3 = np.repeat(np.minimum(y, (R + G + B) / 3)[..., None], 3, axis=-1)
    return with_rgb(a, rgb + (gray3 - rgb) * m[..., None])


@effect(0x82c4, "Kleurafwijking verwijderen", [Int("radius", "Straal", 1, 20, 4), Int("strength", "Sterkte", 0, 100, 60)])
def chromatic_aberration(a, ctx, radius, strength):
    rgb = _rgb(a)
    y = _lum(rgb)
    ch = rgb - y[..., None]
    r = _px(radius, ctx)
    near = _edge_near(y, r)
    # kleur die lokaal afwijkt van de omgeving (randkleur) wordt naar de omgevingskleur gebracht
    chb = blur(ch, r * 3)
    dev = np.sqrt(((ch - chb) ** 2).sum(-1))
    m = near * np.clip(dev / 30, 0, 1) * (strength / 100)
    ch2 = ch + (chb * 0.5 - ch) * m[..., None]
    return with_rgb(a, y[..., None] + ch2)


# ------------------------------------------------------------------ herstel / ruis


@effect(0x806f, "Automatisch krasjes verwijderen", [
    Bool("light", "Lichte krassen verwijderen", True), Bool("dark", "Donkere krassen verwijderen", True),
    Choice("strength", "Sterkte", ["Mild", "Normaal", "Sterk"], 1)])
def scratch_removal(a, ctx, light, dark, strength):
    if not (light or dark):
        return a.copy()
    rgb = _rgb(a)
    med = _median(a[..., :3], [2, 3, 4][strength], axis=1).astype(np.float32)
    d = _lum(rgb) - _lum(med)
    dv = _vmean(d, _px(6, ctx))  # krassen zijn lange (verticale) lijnen
    thr = [22, 14, 9][strength]
    m = np.zeros_like(d)
    if light:
        m = np.maximum(m, np.clip((dv - thr) / thr, 0, 1) * (d > 0))
    if dark:
        m = np.maximum(m, np.clip((-dv - thr) / thr, 0, 1) * (d < 0))
    return with_rgb(a, rgb + (med - rgb) * m[..., None])


@effect(0x806d, "De-interliniëring", [Choice("keep", "Behouden scanlijnen", ["Oneven", "Even"])])
def deinterlace(a, ctx, keep):
    out = a.copy()
    h = a.shape[0]
    if h < 2:
        return out
    f = a.astype(np.float32)
    rows = np.arange(1 - keep, h, 2) if keep == 0 else np.arange(0, h, 2)
    up = np.clip(rows - 1, 0, h - 1)
    dn = np.clip(rows + 1, 0, h - 1)
    up = np.where(up == rows, dn, up)
    dn = np.where(dn == rows, up, dn)
    out[rows] = to_u8((f[up] + f[dn]) / 2)
    return out


@effect(0x806b, "Verwijdering JPEG-artefact", [
    Choice("strength", "Sterkte", ["Laag", "Normaal", "Hoog", "Maximaal"], 1), Int("crisp", "Scherpte", 0, 100, 0)])
def jpeg_artifacts(a, ctx, strength, crisp):
    rgb = _rgb(a)
    r = _px([1, 2, 2, 3][strength], ctx)
    eps = [6, 10, 16, 24][strength] ** 2
    sm = _guided(rgb, r, eps)
    out = sm + (rgb - sm) * (crisp / 100) * 0.6
    if crisp:
        out = _unsharp(out, _px(1, ctx, 0), crisp / 200)
    return with_rgb(a, out)


@effect(0x806c, "Verwijdering moiré-patroon", [
    Int("details", "Fijne details", 0, 20, 2), Int("bands", "Kleurbanden verwijderen", 0, 20, 0)])
def moire(a, ctx, details, bands):
    rgb = _rgb(a)
    y = _lum(rgb)
    ch = rgb - y[..., None]
    if details:
        y = blur(y, details * 0.5 * ctx.scale)
        ch = blur(ch, max(1.0, details * ctx.scale))
    if bands:
        ch = blur(ch, max(1.0, bands * 2 * ctx.scale))
    return with_rgb(a, y[..., None] + ch)


@effect(0x808a, "Vlekken verwijderen")
def despeckle(a, ctx):
    out = a.copy()
    out[..., :3] = _median(a[..., :3], 1)
    return out


@effect(0x8068, "Vloeiend met behoud van rand", [Int("amount", "Mate", 0, 100, 10)])
def edge_preserving_smooth(a, ctx, amount):
    if amount == 0:
        return a.copy()
    rgb = _rgb(a)
    s = amount / 100
    out = _guided(rgb, _px(1 + 5 * s, ctx), (3 + 40 * s) ** 2)
    if amount > 50:
        out = _guided(out, _px(1 + 5 * s, ctx), (3 + 40 * s) ** 2)
    return with_rgb(a, out)


@effect(0x8074, "Peper-en-zoutfilter", [Int("size", "Vlekgrootte", 1, 7, 3), Int("sensitivity", "Gevoeligheid", 1, 100, 30)])
def salt_pepper(a, ctx, size, sensitivity):
    r = max(1, int(round((size // 2 + 1) * min(1.0, ctx.scale * 2))))
    med = _median(a[..., :3], r).astype(np.float32)
    rgb = _rgb(a)
    d = np.abs(_lum(rgb) - _lum(med))
    thr = (101 - sensitivity) * 1.2
    m = np.clip((d - thr) / max(thr * 0.25, 2), 0, 1)[..., None]
    return with_rgb(a, rgb + (med - rgb) * m)


@effect(0x8067, "Vloeiend met behoud van textuur", [Int("amount", "Mate", 0, 100, 10)])
def texture_preserving_smooth(a, ctx, amount):
    if amount == 0:
        return a.copy()
    rgb = _rgb(a)
    y = _lum(rgb)
    r = _px(2, ctx)
    m = blur(y, r)
    sd = np.sqrt(np.maximum(blur(y * y, r) - m * m, 0))
    s = amount / 100
    # vlakke gebieden (lage lokale variatie) worden gladgemaakt, textuur blijft
    w = np.clip(1.3 - sd / (10 + 40 * s), 0, 1) * min(1.0, 0.5 + s)
    sm = blur(rgb, _px(1 + 2 * s, ctx))
    return with_rgb(a, rgb + (sm - rgb) * w[..., None])


# ------------------------------------------------------------------ lenscorrectie


def _radial(a, fn):
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    R = max(np.hypot(cx, cy), 1e-6)
    dx, dy = (xx - cx) / R, (yy - cy) / R
    r = np.sqrt(dx * dx + dy * dy)
    rs = fn(r)
    k = np.where(r > 1e-9, rs / np.maximum(r, 1e-9), 1)
    return remap(a, cx + dx * k * R, cy + dy * k * R, edge="clamp")


@effect(0x818d, "Tonvormige vertekening corrigeren", [Int("strength", "Sterkte", 0, 100, 10)])
def barrel(a, ctx, strength):
    if strength == 0:
        return a.copy()
    k = strength / 100 * 0.3
    return _radial(a, lambda r: r * (1 - k * r * r) / (1 - k))


@effect(0x818e, "Bolvormige vertekening corrigeren", [Int("strength", "Sterkte", 0, 100, 25)])
def fisheye(a, ctx, strength):
    if strength == 0:
        return a.copy()
    t = strength / 100 * 2.5
    return _radial(a, lambda r: np.arctan(t * r) / np.arctan(t))


@effect(0x818c, "Speldenkussenvervorming corrigeren", [Int("strength", "Sterkte", 0, 100, 10)])
def pincushion(a, ctx, strength):
    if strength == 0:
        return a.copy()
    k = strength / 100 * 0.5
    return _radial(a, lambda r: r * (1 + k * r * r) / (1 + k))
