"""Distortion, geometric, image and reflection effects (compatible with Paint Shop Pro XI).

All geometric effects use an inverse mapping: for each output pixel it is computed
where in the source to sample, after which common.remap does the bilinear sampling.
"""
import math

import numpy as np

from . import Bool, Choice, Color, Int, effect
from .common import blur, f32, gray, grid, remap, smooth_noise, to_u8

EDGE = ["Achtergrondkleur", "Herhalen", "Transparant", "Omloop"]
TAU = 2 * math.pi


def _edge(mode, ctx):
    """Edge mode -> (edge, fill) for remap."""
    if mode == 0:
        return "fill", (*ctx.bg, 255)
    if mode == 2:
        return "fill", (0, 0, 0, 0)
    if mode == 3:
        return "wrap", (0, 0, 0, 0)
    return "clamp", (0, 0, 0, 0)


def _remap(a, mx, my, mode, ctx):
    e, f = _edge(mode, ctx)
    return remap(a, mx, my, e, f)


def _edge_param(default=1, label="Randmodus"):
    return Choice("edge", label, EDGE, default)


def _center(h, w, px, py):
    """Center from percentages (0..100) of width/height."""
    return px / 100 * (w - 1), py / 100 * (h - 1)


def _center_off(h, w, ox, oy):
    """Center from an offset -100..100 relative to the image center."""
    return (w - 1) / 2 * (1 + ox / 100), (h - 1) / 2 * (1 + oy / 100)


def _radial(a, ctx, cx, cy, rx, ry, func, mode=1):
    """Radial distortion within an ellipse (rx, ry): source radius = func(rho) for rho < 1."""
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    rx, ry = max(rx, 0.5), max(ry, 0.5)
    nx, ny = (xx - cx) / rx, (yy - cy) / ry
    rho = np.sqrt(nx * nx + ny * ny)
    inside = rho < 1
    rs = func(np.clip(rho, 0, 1))
    k = np.where(inside & (rho > 1e-6), rs / np.maximum(rho, 1e-6), 1.0)
    return _remap(a, cx + nx * k * rx, cy + ny * k * ry, mode, ctx)


def _rotate_map(xx, yy, cx, cy, theta):
    """Source position for rotating the content by theta (rad, positive = clockwise on screen)."""
    dx, dy = xx - cx, yy - cy
    c, s = np.cos(theta), np.sin(theta)
    return cx + dx * c + dy * s, cy - dx * s + dy * c


def _sphere_curve(t, k):
    """Convex (k>0) or concave (k<0) profile curve for t in 0..1 (k = -1..1)."""
    t = np.clip(t, 0, 1)
    if k >= 0:
        f = np.arcsin(t) * (2 / math.pi)
    else:
        f = np.sin(t * (math.pi / 2))
    return t + (f - t) * abs(k)


def _signed_curve(u, k):
    return np.sign(u) * _sphere_curve(np.abs(u), k)


# ================================================================ Distortion effects

@effect(0x80ae, "Krullen", [Int("cols", "Aantal kolommen", 1, 100, 3), Int("rows", "Aantal rijen", 1, 100, 3),
                            Bool("sym", "Symmetrisch", True), Int("radius", "Straal (%)", 1, 100, 50),
                            Int("strength", "Sterkte", 0, 100, 50), Bool("cw", "Met de klok mee", True)])
def curlicues(a, ctx, cols, rows, sym, radius, strength, cw):
    h, w = a.shape[:2]
    if sym:
        rows = cols
    cwid, chei = w / cols, h / rows
    yy, xx = grid(h, w)
    ccx = (np.floor(xx / cwid) + 0.5) * cwid - 0.5
    ccy = (np.floor(yy / chei) + 0.5) * chei - 0.5
    R = max(radius / 100 * min(cwid, chei), 0.5)
    dx, dy = xx - ccx, yy - ccy
    r = np.sqrt(dx * dx + dy * dy)
    t = np.clip(1 - r / R, 0, 1)
    theta = (strength / 100 * 3 * math.pi) * t * t * (1 if cw else -1)
    mx, my = _rotate_map(xx, yy, ccx, ccy, theta)
    return _remap(a, mx, my, 1, ctx)


@effect(0x8287, "Verplaatsingstoewijzing", [Choice("map", "Toewijzing", ["Eigen helderheid", "Ruistextuur"]),
                                            Int("strength", "Sterkte", 0, 100, 20),
                                            Int("scale", "Schaal", 1, 100, 20), _edge_param(1)])
def displacement(a, ctx, map, strength, scale, edge):
    h, w = a.shape[:2]
    s = strength * ctx.scale
    grain = max(1.0, scale * ctx.scale)
    if map == 0:
        g = gray(a) * (a[..., 3].astype(np.float32) / 255) / 255
        m1 = blur(g, grain / 4)
        m2 = blur(g.T, grain / 4).T  # same map, for y a slightly different course through the gradient
        gy, gx = np.gradient(m2)
        m2 = np.clip(m1 + (gx - gy) * grain, 0, 1)
    else:
        m1 = smooth_noise(h, w, grain, ctx.seed)
        m2 = smooth_noise(h, w, grain, ctx.seed + 7919)
    yy, xx = grid(h, w)
    return _remap(a, xx + (m1 - 0.5) * 2 * s, yy + (m2 - 0.5) * 2 * s, edge, ctx)


@effect(0x818f, "Lensvervorming", [Choice("kind", "Vervormingstype", ["Ton", "Visoog", "Visoog (sferisch)", "Kussen"]),
                                   Int("strength", "Sterkte / gezichtsveld", 0, 100, 50),
                                   Int("cx", "Horizontaal (%)", 0, 100, 50), Int("cy", "Verticaal (%)", 0, 100, 50),
                                   _edge_param(1)])
def lens(a, ctx, kind, strength, cx, cy, edge):
    h, w = a.shape[:2]
    x0, y0 = _center(h, w, cx, cy)
    yy, xx = grid(h, w)
    R = max(math.hypot(w, h) / 2, 1)
    dx, dy = (xx - x0) / R, (yy - y0) / R
    r = np.sqrt(dx * dx + dy * dy)
    k = strength / 100
    if kind == 0:      # barrel: center enlarged, edges compressed
        rs = r * (1 + k * r * r)
    elif kind == 3:    # pincushion
        rs = r / (1 + k * r * r)
    elif kind == 1:    # fisheye
        th = k * math.radians(85)
        rs = r if th < 1e-4 else np.tan(np.minimum(r, 1.5) * th) / math.tan(th)
    else:              # fisheye (spherical): sphere within the inscribed circle
        Rc = max(min(w, h) / 2 / R, 1e-6)
        t = r / Rc
        rs = np.where(t < 1, _sphere_curve(t, k) * Rc, r)
    f = np.where(r > 1e-6, rs / np.maximum(r, 1e-6), 1.0)
    return _remap(a, x0 + dx * f * R, y0 + dy * f * R, edge, ctx)


def _bulge(k):
    """Smooth radial profile function: k>0 enlarges the center, k<0 pinches (|k| < 1 stays monotone)."""
    k = max(-0.95, min(0.95, k))
    return lambda t: t * (1 - k * (1 - t) ** 2)


def _pinch_punch(a, ctx, k):
    h, w = a.shape[:2]
    return _radial(a, ctx, (w - 1) / 2, (h - 1) / 2, w / 2, h / 2, _bulge(k))


@effect(0x8094, "Knijpen", [Int("strength", "Sterkte (%)", -100, 100, 50)])
def pinch(a, ctx, strength):
    return _pinch_punch(a, ctx, -strength / 100)


@effect(0x8095, "Platslaan", [Int("strength", "Sterkte (%)", -100, 100, 50)])
def punch(a, ctx, strength):
    return _pinch_punch(a, ctx, strength / 100)


@effect(0x808e, "Pixelvorming", [Int("bw", "Blokbreedte", 1, 100, 10), Int("bh", "Blokhoogte", 1, 100, 10),
                                 Bool("sym", "Symmetrisch", True)])
def pixelate(a, ctx, bw, bh, sym):
    h, w = a.shape[:2]
    if sym:
        bh = bw
    bw = max(1, int(round(bw * ctx.scale)))
    bh = max(1, int(round(bh * ctx.scale)))
    if bw == 1 and bh == 1:
        return a.copy()
    al = a[..., 3:4].astype(np.float32) / 255
    src = np.dstack([a[..., :3].astype(np.float32) * al, al * 255]).astype(np.float64)
    ys, xs = np.arange(0, h, bh), np.arange(0, w, bw)
    sums = np.add.reduceat(np.add.reduceat(src, ys, axis=0), xs, axis=1)
    cy = np.diff(np.append(ys, h))[:, None, None]
    cx = np.diff(np.append(xs, w))[None, :, None]
    mean = sums / (cy * cx)
    out = mean[np.arange(h) // bh][:, np.arange(w) // bw]
    alpha = out[..., 3:4]
    rgb = np.where(alpha > 1e-3, out[..., :3] / np.maximum(alpha / 255, 1e-6), 0)
    return np.dstack([to_u8(rgb), to_u8(alpha[..., 0])])


@effect(0x818a, "Poolcoördinaten", [Choice("mode", "Omzetting", ["Rechthoekig naar polair", "Polair naar rechthoekig"]),
                                    _edge_param(1)])
def polar(a, ctx, mode, edge):
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    rx, ry = max(w / 2, 0.5), max(h / 2, 0.5)
    if mode == 0:
        nx, ny = (xx - cx) / rx, (yy - cy) / ry
        r = np.sqrt(nx * nx + ny * ny)
        ang = np.mod(np.arctan2(nx, -ny), TAU)  # 0 = top, clockwise
        mx = ang / TAU * w - 0.5
        my = r * h - 0.5
    else:
        ang = (xx + 0.5) / w * TAU
        r = (yy + 0.5) / h
        mx = cx + r * np.sin(ang) * rx
        my = cy - r * np.cos(ang) * ry
    return _remap(a, mx, my, edge, ctx)


@effect(0x8092, "Rimpeling", [Int("cx", "Horizontaal (%)", 0, 100, 50), Int("cy", "Verticaal (%)", 0, 100, 50),
                              Int("amp", "Amplitude", 0, 100, 10), Int("wave", "Golflengte", 1, 100, 20),
                              _edge_param(0)])
def ripple(a, ctx, cx, cy, amp, wave, edge):
    h, w = a.shape[:2]
    x0, y0 = _center(h, w, cx, cy)
    yy, xx = grid(h, w)
    dx, dy = xx - x0, yy - y0
    r = np.sqrt(dx * dx + dy * dy)
    A = amp / 2 * ctx.scale
    lam = max(wave * ctx.scale, 1.0)
    d = A * np.sin(TAU * r / lam)
    f = np.where(r > 1e-6, (r + d) / np.maximum(r, 1e-6), 1.0)
    return _remap(a, x0 + dx * f, y0 + dy * f, edge, ctx)


@effect(0x80b8, "Stralenkrans", [Int("ox", "Horizontaal", -100, 100, 0), Int("oy", "Verticaal", -100, 100, 0),
                                 Int("amp", "Amplitude", 0, 100, 20), Int("freq", "Frequentie", 1, 50, 5),
                                 Int("radius", "Straal (%)", 0, 100, 25), _edge_param(0)])
def spike_halo(a, ctx, ox, oy, amp, freq, radius, edge):
    h, w = a.shape[:2]
    x0, y0 = _center_off(h, w, ox, oy)
    yy, xx = grid(h, w)
    dx, dy = xx - x0, yy - y0
    r = np.sqrt(dx * dx + dy * dy)
    phi = np.arctan2(dy, dx)
    D = max(min(w, h) / 2, 1.0)
    R0 = radius / 100 * D
    ramp = np.clip((r - R0) / (0.3 * D), 0, 1)
    A = amp / 100 * 0.25 * D
    d = A * ramp * ramp * np.sin(4 * freq * phi)
    f = np.where(r > 1e-6, (r + d) / np.maximum(r, 1e-6), 1.0)
    return _remap(a, x0 + dx * f, y0 + dy * f, edge, ctx)


@effect(0x8091, "Spiraal", [Int("degrees", "Graden", -720, 720, 180)])
def twirl(a, ctx, degrees):
    h, w = a.shape[:2]
    cx, cy = (w - 1) / 2, (h - 1) / 2
    yy, xx = grid(h, w)
    R = max(math.hypot(w, h) / 2, 1)
    dx, dy = xx - cx, yy - cy
    t = np.clip(1 - np.sqrt(dx * dx + dy * dy) / R, 0, 1)
    theta = math.radians(degrees) * t * t
    mx, my = _rotate_map(xx, yy, cx, cy, theta)
    return _remap(a, mx, my, 1, ctx)


@effect(0x80b6, "Bolvorm", [Int("ox", "Horizontaal", -100, 100, 0), Int("oy", "Verticaal", -100, 100, 0),
                            Int("size", "Grootte (%)", 1, 100, 50), Int("strength", "Sterkte", -100, 100, 50)])
def warp(a, ctx, ox, oy, size, strength):
    h, w = a.shape[:2]
    x0, y0 = _center_off(h, w, ox, oy)
    R = size / 100 * max(w, h) / 2
    return _radial(a, ctx, x0, y0, R, R, _bulge(strength / 100))


@effect(0x8093, "Golf", [Int("hamp", "Horizontale amplitude", 0, 100, 10), Int("hwave", "Horizontale golflengte", 1, 100, 40),
                         Int("vamp", "Verticale amplitude", 0, 100, 10), Int("vwave", "Verticale golflengte", 1, 100, 40),
                         _edge_param(0)])
def wave(a, ctx, hamp, hwave, vamp, vwave, edge):
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    s = ctx.scale
    mx = xx + hamp / 2 * s * np.sin(TAU * yy / max(hwave * s, 1.0))
    my = yy + vamp / 2 * s * np.sin(TAU * xx / max(vwave * s, 1.0))
    return _remap(a, mx, my, edge, ctx)


@effect(0x8090, "Wind", [Choice("dir", "Windrichting", ["Van links", "Van rechts"]),
                         Int("strength", "Windsterkte", 1, 100, 50)])
def wind(a, ctx, dir, strength):
    h, w = a.shape[:2]
    al = a[..., 3:4].astype(np.float32) / 255
    src = np.dstack([a[..., :3].astype(np.float32) * al, al * 255])
    if dir == 1:
        src = src[:, ::-1]
    L = max(strength * ctx.scale * 0.4, 0.5)
    rng = np.random.default_rng(ctx.seed)
    row = rng.random(h).astype(np.float32)
    rowL = (L * (0.3 + 1.4 * row * row))[:, None]
    dec = np.exp(-1.0 / rowL)  # decay per row: streaks of different lengths
    sm = np.empty_like(src)
    cur = src[:, 0].copy()
    lum = src[..., :3].mean(axis=2)
    curl = lum[:, 0].copy()
    sm[:, 0] = cur
    for x in range(1, w):
        v = src[:, x]
        # bright pixels are blown along as streaks
        brighter = (curl * dec[:, 0] > lum[:, x])[:, None]
        cur = np.where(brighter, cur * dec + v * (1 - dec), v)
        curl = np.where(brighter[:, 0], curl * dec[:, 0] + lum[:, x] * (1 - dec[:, 0]), lum[:, x])
        sm[:, x] = cur
    mix = 0.35 + 0.5 * strength / 100
    out = src + (sm - src) * mix
    if dir == 1:
        out = out[:, ::-1]
    alpha = out[..., 3:4]
    rgb = np.where(alpha > 1e-3, out[..., :3] / np.maximum(alpha / 255, 1e-6), 0)
    return np.dstack([to_u8(rgb), to_u8(alpha[..., 0])])


# ================================================================ Geometric effects

def _polygon_map(a, ctx, sides, edge):
    """Distort the image into a regular polygon (sides) or circle (sides=0)."""
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    rx, ry = max(w / 2, 0.5), max(h / 2, 0.5)
    nx, ny = (xx - cx) / rx, (yy - cy) / ry
    r = np.sqrt(nx * nx + ny * ny)
    phi = np.arctan2(ny, nx)
    if sides:
        seg = TAU / sides
        rel = np.mod(phi + math.pi / 2, seg) - seg / 2  # point at the top
        rp = math.cos(seg / 2) / np.cos(rel)
    else:
        rp = 1.0
    rho = r / rp
    c, s = np.cos(phi), np.sin(phi)
    rs = 1.0 / np.maximum(np.maximum(np.abs(c), np.abs(s)), 1e-6)  # radius of the square
    k = rho * rs
    k = np.where(rho > 1, k * rho, k)  # outside the shape is certainly outside the image
    return _remap(a, cx + c * k * rx, cy + s * k * ry, edge, ctx)


@effect(0x8098, "Cirkel", [_edge_param(2)])
def circle(a, ctx, edge):
    return _polygon_map(a, ctx, 0, edge)


@effect(0x8099, "Vijfhoek", [_edge_param(2)])
def pentagon(a, ctx, edge):
    return _polygon_map(a, ctx, 5, edge)


@effect(0x8096, "Cilinder - horizontaal", [Int("strength", "Sterkte (%)", -100, 100, 50)])
def cylinder_h(a, ctx, strength):
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    cx = (w - 1) / 2
    u = (xx - cx) / max(cx, 0.5)
    return _remap(a, cx + _signed_curve(u, strength / 100) * max(cx, 0.5), yy, 1, ctx)


@effect(0x8097, "Cilinder - verticaal", [Int("strength", "Sterkte (%)", -100, 100, 50)])
def cylinder_v(a, ctx, strength):
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    cy = (h - 1) / 2
    v = (yy - cy) / max(cy, 0.5)
    return _remap(a, xx, cy + _signed_curve(v, strength / 100) * max(cy, 0.5), 1, ctx)


def _perspective(a, ctx, distortion, edge, vertical):
    if vertical:
        a = a.transpose(1, 0, 2)
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    d = distortion / 100
    sl = max(1 - max(0.0, -d), 0.01)  # length of the left side
    sr = max(1 - max(0.0, d), 0.01)
    t = xx / max(w - 1, 1)
    # perspective-correct distribution along x (hyperbolic)
    u = t * sr / (sl + (sr - sl) * t) if abs(sr - sl) > 1e-6 else t
    sc = sl + (sr - sl) * t  # visible height in this column
    cy = (h - 1) / 2
    mx = u * (w - 1)
    my = cy + (yy - cy) / sc
    out = _remap(a, mx, my, edge, ctx)
    return out.transpose(1, 0, 2).copy() if vertical else out


@effect(0x809c, "Perspectief - horizontaal", [Int("dist", "Vervorming", -100, 100, 30), _edge_param(2)])
def persp_h(a, ctx, dist, edge):
    return _perspective(a, ctx, dist, edge, False)


@effect(0x809d, "Perspectief - verticaal", [Int("dist", "Vervorming", -100, 100, 30), _edge_param(2)])
def persp_v(a, ctx, dist, edge):
    return _perspective(a, ctx, dist, edge, True)


@effect(0x809a, "Scheeftrekking", [Choice("dir", "Richting", ["Horizontaal", "Verticaal"]),
                                   Int("angle", "Hoek", -45, 45, 20), _edge_param(2)])
def skew(a, ctx, dir, angle, edge):
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    t = math.tan(math.radians(angle))
    if dir == 0:
        mx, my = xx + (yy - (h - 1) / 2) * t, yy
    else:
        mx, my = xx, yy + (xx - (w - 1) / 2) * t
    return _remap(a, mx, my, edge, ctx)


@effect(0x8189, "Sferisch", [Int("strength", "Sterkte", -100, 100, 50), Choice("shape", "Vorm", ["Cirkel", "Ellips"])])
def spherize(a, ctx, strength, shape):
    h, w = a.shape[:2]
    if shape == 0:
        rx = ry = min(w, h) / 2
    else:
        rx, ry = w / 2, h / 2
    k = strength / 100
    return _radial(a, ctx, (w - 1) / 2, (h - 1) / 2, rx, ry, lambda t: _sphere_curve(t, k))


# ================================================================ Image effects

@effect(0x80bb, "Verschuiving", [Int("dx", "Horizontale verschuiving (%)", -100, 100, 50),
                                 Int("dy", "Verticale verschuiving (%)", -100, 100, 50), _edge_param(3)])
def offset(a, ctx, dx, dy, edge):
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    sx = int(round(dx / 100 * w))
    sy = int(round(dy / 100 * h))
    if edge == 3:
        return np.roll(a, (sy, sx), axis=(0, 1)).copy()
    return _remap(a, xx - sx, yy - sy, edge, ctx)


@effect(0x80c2, "Paginakrul", [Choice("corner", "Hoek", ["Linksboven", "Rechtsboven", "Linksonder", "Rechtsonder"], 3),
                               Int("width", "Breedte (%)", 1, 100, 40), Int("height", "Hoogte (%)", 1, 100, 40),
                               Int("radius", "Straal", 1, 100, 40), Color("color", "Kleur krul", "bg"),
                               Choice("edge", "Randmodus", ["Transparant", "Achtergrondkleur"], 0)])
def page_curl(a, ctx, corner, width, height, radius, color, edge):
    fx, fy = corner in (1, 3), corner in (2, 3)

    def flip(b):
        if fx:
            b = b[:, ::-1]
        if fy:
            b = b[::-1]
        return b

    src = flip(a)
    h, w = src.shape[:2]
    yy, xx = grid(h, w)
    Wc, Hc = max(width / 100 * w, 1.0), max(height / 100 * h, 1.0)
    nx, ny = 1 / Wc, 1 / Hc
    nl = math.hypot(nx, ny)
    nx, ny = nx / nl, ny / nl
    c0 = nx * Wc
    d = xx * nx + yy * ny - c0  # < 0: corner side of the fold line
    R = max(radius / 100 * 0.35 * c0, 0.5)
    q = np.clip(-d / R, 0, 1)
    asn = np.arcsin(q)
    s_top = R * (math.pi - asn)
    s_low = R * asn

    def source(s):
        k = d + s  # back along the normal to the original position
        return xx - k * nx, yy - k * ny

    tx, ty = source(s_top)
    lx, ly = source(s_low)
    top_ok = (d <= 0) & (d >= -R) & (tx >= -0.5) & (ty >= -0.5)
    low_ok = (d <= 0) & (d >= -R) & (lx >= -0.5) & (ly >= -0.5) & ~top_ok
    low = remap(src, lx, ly, "clamp").astype(np.float32)

    bg = np.array([0, 0, 0, 0] if edge == 0 else [*ctx.bg, 255], np.float32)
    out = np.empty((h, w, 4), np.float32)
    out[:] = bg
    flat = d > 0
    base = src.astype(np.float32)
    shadow = 1 - 0.35 * np.exp(-np.maximum(d, 0) / (0.6 * R))
    base_sh = base.copy()
    base_sh[..., :3] *= shadow[..., None]
    out = np.where(flat[..., None], base_sh, out)
    # inside of the curl (back of the paper) with cylinder lighting
    alpha_t = math.pi - asn
    shade_t = (0.6 + 0.4 * np.sin(alpha_t / 2 + 0.3))[..., None]
    col = np.array([*color[:3], 255], np.float32)
    curl = np.concatenate([np.clip(col[:3] * shade_t * 1.1, 0, 255),
                           np.broadcast_to(col[3:], (h, w, 1))], axis=2)
    out = np.where(top_ok[..., None], curl, out)
    shade_l = (0.55 + 0.45 * np.cos(asn))[..., None]
    lowc = low.copy()
    lowc[..., :3] *= shade_l
    out = np.where(low_ok[..., None], lowc, out)
    # respect the original transparency for the curled paper
    talpha = remap(src, tx, ty, "clamp")[..., 3].astype(np.float32)
    out[..., 3] = np.where(top_ok, talpha, out[..., 3])
    return flip(to_u8(out)).copy()


@effect(0x8188, "Naadloze herhaling", [Choice("method", "Methode", ["Rand", "Hoekpunt", "Spiegelen"]),
                                       Choice("dir", "Richting", ["Horizontaal", "Verticaal", "Bidirectioneel"], 2),
                                       Int("trans", "Overgang (%)", 1, 100, 50)])
def seamless(a, ctx, method, dir, trans):
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    dox, doy = dir in (0, 2), dir in (1, 2)
    if method == 2:
        mx = (1 - np.abs(2 * (xx + 0.5) / w - 1)) * w - 0.5 if dox else xx
        my = (1 - np.abs(2 * (yy + 0.5) / h - 1)) * h - 0.5 if doy else yy
        return remap(a, mx, my, "clamp")
    T = trans / 100
    wx = np.clip(np.minimum(xx + 0.5, w - 0.5 - xx) / max(T * w / 2, 1e-6), 0, 1) if dox else np.ones_like(xx)
    wy = np.clip(np.minimum(yy + 0.5, h - 0.5 - yy) / max(T * h / 2, 1e-6), 0, 1) if doy else np.ones_like(yy)
    if method == 0:
        wt = wx * wy
    else:
        wt = np.minimum(wx, wy)
    wt = wt * wt * (3 - 2 * wt)
    rolled = np.roll(a, (h // 2 if doy else 0, w // 2 if dox else 0), axis=(0, 1))
    al0 = f32(a[..., 3:4]) / 255
    al1 = f32(rolled[..., 3:4]) / 255
    wt = wt[..., None]
    pm = f32(a[..., :3]) * al0 * wt + f32(rolled[..., :3]) * al1 * (1 - wt)
    al = al0 * wt + al1 * (1 - wt)
    rgb = np.where(al > 1e-4, pm / np.maximum(al, 1e-6), 0)
    return np.dstack([to_u8(rgb), to_u8(al[..., 0] * 255)])


# ================================================================ Reflection effects

@effect(0x80ac, "Weerspiegeling", [Int("opacity", "Dekking", 0, 100, 100), Int("intensity", "Intensiteit", 1, 100, 50),
                                   Int("cx", "Horizontale verschuiving (%)", 0, 100, 50),
                                   Int("cy", "Verticale verschuiving (%)", 0, 100, 50), Bool("ellipse", "Elliptisch", False)])
def feedback(a, ctx, opacity, intensity, cx, cy, ellipse):
    h, w = a.shape[:2]
    x0, y0 = _center(h, w, cx, cy)
    yy, xx = grid(h, w)
    dx, dy = xx - x0, yy - y0
    ex = np.where(dx >= 0, max(w - 1 - x0, 0.5), max(x0, 0.5))
    ey = np.where(dy >= 0, max(h - 1 - y0, 0.5), max(y0, 0.5))
    nx, ny = dx / ex, dy / ey
    rho = np.sqrt(nx * nx + ny * ny) if ellipse else np.maximum(np.abs(nx), np.abs(ny))
    f = 0.9 - 0.6 * intensity / 100      # reduction per repetition
    n = 1 + intensity // 5               # number of repetitions
    lf = math.log(f)
    k = np.floor(np.log(np.maximum(rho, 1e-9)) / lf)
    k = np.clip(k, 0, n)
    sc = np.exp(-k * lf)  # 1/f^k
    fb = remap(a, x0 + dx * sc, y0 + dy * sc, "clamp")
    if opacity >= 100:
        return fb
    o = opacity / 100
    al0, al1 = f32(a[..., 3:4]) / 255, f32(fb[..., 3:4]) / 255
    pm = f32(a[..., :3]) * al0 * (1 - o) + f32(fb[..., :3]) * al1 * o
    al = al0 * (1 - o) + al1 * o
    rgb = np.where(al > 1e-4, pm / np.maximum(al, 1e-6), 0)
    return np.dstack([to_u8(rgb), to_u8(al[..., 0] * 255)])


@effect(0x80ad, "Caleidoscoop", [Int("ox", "Horizontale verschuiving", -100, 100, 0),
                                 Int("oy", "Verticale verschuiving", -100, 100, 0),
                                 Int("angle", "Draaihoek", 0, 359, 0), Int("scale", "Schaalfactor", -100, 100, 0),
                                 Int("petals", "Aantal bloembladen", 2, 31, 10), Int("orbits", "Aantal banen", 0, 5, 0),
                                 Int("suction", "Radiale zuiging", 0, 100, 0), _edge_param(1)])
def kaleidoscope(a, ctx, ox, oy, angle, scale, petals, orbits, suction, edge):
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    x0, y0 = _center_off(h, w, ox, oy)
    dx, dy = xx - cx, yy - cy
    r = np.sqrt(dx * dx + dy * dy)
    phi = np.mod(np.arctan2(dy, dx), TAU)
    W = TAU / petals
    idx = np.floor(phi / W)
    p = phi - idx * W
    p = np.where(np.mod(idx, 2) == 1, W - p, p)
    Rm = max(math.hypot(w, h) / 2, 1.0)
    t = r / Rm
    if orbits:
        n = orbits + 1
        tt = t * n
        fi = np.floor(tt)
        fr = tt - fi
        t = np.where(np.mod(fi, 2) == 1, 1 - fr, fr)
    if suction:
        t = t ** (1 / (1 + suction / 25))
    sr = t * min(w, h) / 2 * 2.0 ** (scale / 50)
    sa = p + math.radians(angle) - W / 2 - math.pi / 2
    return _remap(a, x0 + sr * np.cos(sa), y0 + sr * np.sin(sa), edge, ctx)


def _tri(t):
    """Triangle wave 0..1..0 with period 2 (mirrored tiling)."""
    m = np.mod(t, 2)
    return np.where(m > 1, 2 - m, m)


@effect(0x80af, "Patroon", [Int("ox", "Horizontale verschuiving", -100, 100, 0), Int("oy", "Verticale verschuiving", -100, 100, 0),
                            Int("angle", "Draaihoek", 0, 359, 0), Int("scale", "Schaalfactor", -100, 100, 0),
                            Int("cols", "Aantal kolommen", 1, 20, 2), Int("rows", "Aantal rijen", 1, 20, 2),
                            Int("hshift", "Horizontale opschuiving (%)", -100, 100, 0),
                            Int("vshift", "Verticale opschuiving (%)", -100, 100, 0)])
def pattern(a, ctx, ox, oy, angle, scale, cols, rows, hshift, vshift):
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    # output in tile units around the center
    u = ((xx + 0.5) / w - 0.5 + hshift / 100) * cols
    v = ((yy + 0.5) / h - 0.5 + vshift / 100) * rows
    th = math.radians(angle)
    c, s = math.cos(th), math.sin(th)
    u, v = u * c + v * s, -u * s + v * c
    z = 2.0 ** (-scale / 50)
    u, v = u * z, v * z
    sx = _tri(u + 0.5 * cols + ox / 200) * w - 0.5
    sy = _tri(v + 0.5 * rows + oy / 200) * h - 0.5
    return remap(a, sx, sy, "clamp")


@effect(0x80b7, "Roterende spiegel", [Int("ox", "Horizontale verschuiving", -100, 100, 0),
                                      Int("oy", "Verticale verschuiving", -100, 100, 0),
                                      Int("angle", "Draaihoek", 0, 359, 0), _edge_param(1)])
def rotating_mirror(a, ctx, ox, oy, angle, edge):
    h, w = a.shape[:2]
    yy, xx = grid(h, w)
    px, py = _center_off(h, w, ox, oy)
    th = math.radians(angle)
    nx, ny = math.cos(th), math.sin(th)  # 0 degrees: vertical mirror line
    d = (xx - px) * nx + (yy - py) * ny
    k = np.where(d > 0, 2 * d, 0)
    return _remap(a, xx - k * nx, yy - k * ny, edge, ctx)
