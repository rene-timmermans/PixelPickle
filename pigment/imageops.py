"""Pixelbewerkingen met NumPy: conversies, vulgebieden, maskers en aanpassingen."""
from bisect import bisect_right

import numpy as np
from PySide6.QtCore import QLineF, QRect
from PySide6.QtGui import QImage

FMT = QImage.Format.Format_ARGB32_Premultiplied


def qimage_to_rgba(img: QImage) -> np.ndarray:
    """QImage naar (h, w, 4) uint8 RGBA, niet voorvermenigvuldigd. Altijd een kopie."""
    im = img.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h, bpl = im.width(), im.height(), im.bytesPerLine()
    buf = np.frombuffer(im.constBits(), np.uint8, count=bpl * h)
    return buf.reshape(h, bpl)[:, : w * 4].reshape(h, w, 4).copy()


def rgba_to_qimage(arr: np.ndarray) -> QImage:
    arr = np.ascontiguousarray(arr, dtype=np.uint8)
    h, w = arr.shape[:2]
    im = QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
    return im.convertToFormat(FMT)  # maakt een eigen kopie


def qimage_to_mask(img: QImage) -> np.ndarray:
    """Alpha8 QImage naar (h, w) uint8."""
    if img.format() != QImage.Format.Format_Alpha8:
        img = img.convertToFormat(QImage.Format.Format_Alpha8)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    buf = np.frombuffer(img.constBits(), np.uint8, count=bpl * h)
    return buf.reshape(h, bpl)[:, :w].copy()


def mask_to_qimage(m: np.ndarray) -> QImage:
    m = np.ascontiguousarray(m, dtype=np.uint8)
    h, w = m.shape
    return QImage(m.data, w, h, w, QImage.Format.Format_Alpha8).copy()


def mask_bbox(m: np.ndarray):
    rows = np.flatnonzero(m.any(axis=1))
    if rows.size == 0:
        return QRect()
    cols = np.flatnonzero(m.any(axis=0))
    return QRect(int(cols[0]), int(rows[0]), int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1))


def _runs(e: np.ndarray):
    """Aaneengesloten True stukken per rij: (rij, start, eind)."""
    pad = np.zeros((e.shape[0], e.shape[1] + 2), np.int8)
    pad[:, 1:-1] = e
    d = np.diff(pad, axis=1)
    r, s = np.nonzero(d == 1)
    _, t = np.nonzero(d == -1)
    return r, s, t


MAX_EDGES = 150_000


def mask_edges(m: np.ndarray):
    """Omtrek van een selectiemasker als lijnstukken (voor de mierenlijn).
    Bij extreem grillige selecties wordt alleen het omsluitende kader getoond."""
    sel = m > 127
    h, w = sel.shape
    lines = []
    p = np.zeros((h + 2, w), bool)
    p[1:-1] = sel
    hor = p[1:] != p[:-1]
    if np.count_nonzero(np.diff(hor, axis=1)) > 2 * MAX_EDGES:
        b = mask_bbox(sel)
        x0, y0, x1, y1 = b.x(), b.y(), b.x() + b.width(), b.y() + b.height()
        return [QLineF(x0, y0, x1, y0), QLineF(x1, y0, x1, y1), QLineF(x1, y1, x0, y1), QLineF(x0, y1, x0, y0)]
    r, s, t = _runs(hor)
    lines += [QLineF(a, y, b, y) for y, a, b in zip(r.tolist(), s.tolist(), t.tolist())]
    p2 = np.zeros((h, w + 2), bool)
    p2[:, 1:-1] = sel
    r, s, t = _runs((p2[:, 1:] != p2[:, :-1]).T)
    lines += [QLineF(x, a, x, b) for x, a, b in zip(r.tolist(), s.tolist(), t.tolist())]
    return lines


def similar(rgba: np.ndarray, x: int, y: int, tol: int) -> np.ndarray:
    seed = rgba[y, x].astype(np.int16)
    d = np.abs(rgba.astype(np.int16) - seed).max(axis=2)
    return d <= tol


def connected(sim: np.ndarray, x: int, y: int) -> np.ndarray:
    """Vulgebied (4 buren) vanaf (x, y) binnen het booleaanse masker sim."""
    h, w = sim.shape
    out = np.zeros((h, w), bool)
    if not sim[y, x]:
        return out
    r, s, e = _runs(sim)
    rs = np.searchsorted(r, np.arange(h + 1)).tolist()
    rl, sl, el = r.tolist(), s.tolist(), e.tolist()
    lo, hi = rs[y], rs[y + 1]
    k = bisect_right(el, x, lo, hi)
    seen = bytearray(len(rl))
    seen[k] = 1
    stack = [k]
    while stack:
        k = stack.pop()
        row, a, b = rl[k], sl[k], el[k]
        for rr in (row - 1, row + 1):
            if 0 <= rr < h:
                lo, hi = rs[rr], rs[rr + 1]
                j = bisect_right(el, a, lo, hi)
                while j < hi and sl[j] < b:
                    if not seen[j]:
                        seen[j] = 1
                        stack.append(j)
                    j += 1
    idx = np.flatnonzero(np.frombuffer(bytes(seen), np.uint8))
    acc = np.zeros((h, w + 1), np.int32)
    np.add.at(acc, (r[idx], s[idx]), 1)
    np.add.at(acc, (r[idx], e[idx]), -1)
    return np.cumsum(acc, axis=1)[:, :w] > 0


def region_mask(rgba, x, y, tol, contiguous=True) -> np.ndarray:
    sim = similar(rgba, x, y, tol)
    return connected(sim, x, y) if contiguous else sim


def box_blur(a: np.ndarray, radius: int, passes: int = 3) -> np.ndarray:
    """Snelle benadering van gaussiaans vervagen (2D of 3D float array)."""
    if radius < 1:
        return a
    out = a.astype(np.float32)
    for _ in range(passes):
        for axis in (0, 1):
            n = out.shape[axis]
            c = np.cumsum(out, axis=axis, dtype=np.float32)
            pad_shape = list(out.shape)
            pad_shape[axis] = 1
            c = np.concatenate([np.zeros(pad_shape, np.float32), c], axis=axis)
            idx = np.arange(n)
            hi = np.minimum(idx + radius + 1, n)
            lo = np.maximum(idx - radius, 0)
            cnt = (hi - lo).astype(np.float32)
            shape = [1] * out.ndim
            shape[axis] = n
            out = (np.take(c, hi, axis=axis) - np.take(c, lo, axis=axis)) / cnt.reshape(shape)
    return out


# ---------------------------------------------------------------- aanpassingen

def adj_brightness_contrast(a, brightness=0, contrast=0):
    rgb = a[..., :3].astype(np.float32)
    c = contrast * 2.55
    f = (259 * (c + 255)) / (255 * (259 - c))
    rgb = (rgb - 128) * f + 128 + brightness * 2.55
    out = a.copy()
    out[..., :3] = np.clip(rgb, 0, 255)
    return out


def adj_invert(a):
    out = a.copy()
    out[..., :3] = 255 - out[..., :3]
    return out


def adj_grayscale(a):
    out = a.copy()
    y = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
    out[..., 0] = out[..., 1] = out[..., 2] = np.clip(y, 0, 255)
    return out


def adj_blur(a, radius=2):
    out = a.copy()
    alpha = a[..., 3:4].astype(np.float32) / 255
    pm = a[..., :3].astype(np.float32) * alpha  # vervagen in voorvermenigvuldigde ruimte
    pm = box_blur(pm, int(radius))
    al = box_blur(alpha[..., 0], int(radius))[..., None]
    rgb = np.where(al > 1e-6, pm / np.maximum(al, 1e-6), 0)
    out[..., :3] = np.clip(rgb, 0, 255)
    out[..., 3] = np.clip(al[..., 0] * 255, 0, 255)
    return out


def adj_sharpen(a, radius=2, amount=100):
    blur = box_blur(a[..., :3].astype(np.float32), int(radius))
    rgb = a[..., :3] + (a[..., :3] - blur) * (amount / 100)
    out = a.copy()
    out[..., :3] = np.clip(rgb, 0, 255)
    return out


# ---------------------------------------------------------------- kleurruimtes

def rgb_to_hsl(rgb):
    """rgb float 0..255 (..., 3) naar h (0..1), s, l (0..1)."""
    c = rgb / 255.0
    mx, mn = c.max(axis=-1), c.min(axis=-1)
    l = (mx + mn) / 2
    d = mx - mn
    s = np.where(d < 1e-6, 0, d / np.maximum(1e-6, 1 - np.abs(2 * l - 1)))
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    dd = np.where(d < 1e-6, 1, d)
    h = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4)) / 6
    h = np.where(d < 1e-6, 0, h)
    return h, np.clip(s, 0, 1), l


def hsl_to_rgb(h, s, l):
    c = (1 - np.abs(2 * l - 1)) * s
    hp = (h % 1.0) * 6
    x = c * (1 - np.abs(hp % 2 - 1))
    z = np.zeros_like(h)
    i = np.floor(hp).astype(int) % 6
    r = np.choose(i, [c, x, z, z, x, c])
    g = np.choose(i, [x, c, c, x, z, z])
    b = np.choose(i, [z, z, x, c, c, x])
    m = l - c / 2
    return np.stack([r + m, g + m, b + m], axis=-1) * 255


def adj_hsl(a, hue=0, saturation=0, lightness=0):
    rgb = a[..., :3].astype(np.float32)
    h, s, l = rgb_to_hsl(rgb)
    h = h + hue / 360
    s = np.clip(s * (1 + saturation / 100), 0, 1) if saturation <= 0 else np.clip(s + (1 - s) * saturation / 100, 0, 1)
    l = np.clip(l + (lightness / 100) * (1 - l if lightness > 0 else l), 0, 1)
    out = a.copy()
    out[..., :3] = np.clip(hsl_to_rgb(h, s, l), 0, 255)
    return out


def adj_colorize(a, hue=0, saturation=50):
    rgb = a[..., :3].astype(np.float32)
    _, _, l = rgb_to_hsl(rgb)
    out = a.copy()
    out[..., :3] = np.clip(hsl_to_rgb(np.full_like(l, hue / 360), np.full_like(l, saturation / 100), l), 0, 255)
    return out


def adj_rgb(a, red=0, green=0, blue=0):
    out = a.astype(np.float32)
    for i, v in enumerate((red, green, blue)):
        out[..., i] = out[..., i] * (1 + v / 100) if v < 0 else out[..., i] + (255 - out[..., i]) * v / 100
    return np.clip(out, 0, 255).astype(np.uint8)


def adj_levels(a, black=0, white=255, gamma=100):
    rgb = a[..., :3].astype(np.float32)
    rgb = np.clip((rgb - black) / max(1, white - black), 0, 1) ** (100 / max(1, gamma))
    out = a.copy()
    out[..., :3] = rgb * 255
    return out


def adj_threshold(a, level=128):
    y = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
    out = a.copy()
    v = np.where(y >= level, 255, 0)
    out[..., 0] = out[..., 1] = out[..., 2] = v
    return out


def adj_posterize(a, levels=4):
    n = max(2, int(levels))
    out = a.copy()
    rgb = a[..., :3].astype(np.float32)
    out[..., :3] = np.round(np.round(rgb / 255 * (n - 1)) * 255 / (n - 1))
    return out


def adj_solarize(a, threshold=128):
    out = a.copy()
    rgb = out[..., :3]
    out[..., :3] = np.where(rgb > threshold, 255 - rgb, rgb)
    return out


def adj_noise(a, amount=10, mono=0):
    rgb = a[..., :3].astype(np.float32)
    shape = rgb.shape[:2] + ((1,) if mono else (3,))
    rgb = rgb + np.random.normal(0, amount * 2.55, shape).astype(np.float32)
    out = a.copy()
    out[..., :3] = np.clip(rgb, 0, 255)
    return out


def adj_unsharp(a, radius=2, amount=100, clip=0):
    blur = box_blur(a[..., :3].astype(np.float32), int(radius))
    diff = a[..., :3] - blur
    diff = np.where(np.abs(diff) >= clip, diff, 0)
    out = a.copy()
    out[..., :3] = np.clip(a[..., :3] + diff * amount / 100, 0, 255)
    return out


def adj_emboss(a):
    y = (a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114).astype(np.float32)
    p = np.pad(y, 1, mode='edge')
    e = 128 + (p[2:, 2:] - p[:-2, :-2])
    out = a.copy()
    out[..., 0] = out[..., 1] = out[..., 2] = np.clip(e, 0, 255)
    return out


def adj_median(a, radius=1):
    """Mediaanfilter (klein, via gestapelde verschuivingen)."""
    r = int(radius)
    p = np.pad(a[..., :3], ((r, r), (r, r), (0, 0)), mode='edge')
    h, w = a.shape[:2]
    stack = [p[dy:dy + h, dx:dx + w] for dy in range(2 * r + 1) for dx in range(2 * r + 1)]
    out = a.copy()
    out[..., :3] = np.median(np.stack(stack), axis=0)
    return out


# ---------------------------------------------------------------- overeenkomst (tolerantie zoals PSP: 0 tot 200)
MATCH_MODES = ["Geen", "RGB-waarde", "Kleur", "Helderheid", "Perceptueel", "Traditioneel", "Alles dekkend", "Dekking"]


def rgb_to_lab(rgb):
    c = rgb / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    x = (c[..., 0] * 0.4124 + c[..., 1] * 0.3576 + c[..., 2] * 0.1805) / 0.95047
    y = c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722
    z = (c[..., 0] * 0.0193 + c[..., 1] * 0.1192 + c[..., 2] * 0.9505) / 1.08883
    f = lambda t: np.where(t > 0.008856, np.cbrt(t), 7.787 * t + 16 / 116)  # noqa: E731
    fx, fy, fz = f(x), f(y), f(z)
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], axis=-1)


def match_distance(rgba: np.ndarray, x: int, y: int, mode: int) -> np.ndarray:
    """Afstand (0..255) van elke pixel tot de pixel op (x, y) volgens de PSP overeenkomstmodus."""
    a = rgba.astype(np.float32)
    s = a[y, x]
    if mode in (0, 6):
        return np.zeros(a.shape[:2], np.float32)
    if mode == 1:  # RGB-waarde
        return np.sqrt(((a[..., :3] - s[:3]) ** 2).sum(axis=-1) / 3)
    if mode == 5:  # traditioneel: grootste verschil per kanaal
        return np.abs(a[..., :3] - s[:3]).max(axis=-1)
    if mode == 7:  # dekking
        return np.abs(a[..., 3] - s[3])
    if mode == 4:  # perceptueel: Lab kleurafstand
        lab = rgb_to_lab(a[..., :3])
        return np.sqrt(((lab - rgb_to_lab(s[None, None, :3])) ** 2).sum(axis=-1)) * 2.55
    Y = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
    sY = s[0] * 0.299 + s[1] * 0.587 + s[2] * 0.114
    if mode == 3:  # helderheid
        return np.abs(Y - sY)
    cb, cr = a[..., 2] - Y, a[..., 0] - Y  # kleur: vooral chroma
    return np.sqrt((cb - (s[2] - sY)) ** 2 + (cr - (s[0] - sY)) ** 2) * 0.9 + np.abs(Y - sY) * 0.25


def region_mask2(rgba, x, y, tol, contiguous=True, mode=1) -> np.ndarray:
    """Vulgebied met PSP tolerantie (0 tot 200)."""
    if mode == 6:  # alles dekkend
        sim = rgba[..., 3] > 0
    elif mode == 0 or tol >= 200:
        sim = np.ones(rgba.shape[:2], bool)
    else:
        sim = match_distance(rgba, x, y, mode) <= tol * 1.275
    return connected(sim, x, y) if contiguous else sim


def antialias_mask(m: np.ndarray, where="outside") -> np.ndarray:
    """m: bool masker. Geeft uint8 met zachte rand binnen of buiten de selectie."""
    f = m.astype(np.float32) * 255
    b = box_blur(f, 1, passes=1)
    return np.clip(np.maximum(f, b) if where == "outside" else np.minimum(f, b), 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- snappen langs randen
def edge_map(rgba: np.ndarray) -> np.ndarray:
    y = (rgba[..., 0] * 0.299 + rgba[..., 1] * 0.587 + rgba[..., 2] * 0.114).astype(np.float32)
    y = box_blur(y, 1, passes=1)
    p = np.pad(y, 1, mode="edge")
    gx = (p[1:-1, 2:] - p[1:-1, :-2]) * 2 + (p[:-2, 2:] - p[:-2, :-2]) + (p[2:, 2:] - p[2:, :-2])
    gy = (p[2:, 1:-1] - p[:-2, 1:-1]) * 2 + (p[2:, :-2] - p[:-2, :-2]) + (p[2:, 2:] - p[:-2, 2:])
    g = np.hypot(gx, gy)
    mx = np.percentile(g, 99.5) or 1
    return np.clip(g / mx, 0, 1)


def snap_segment(G: np.ndarray, a, b, rng: int, stiffness=0.15):
    """Zoek tussen a en b het pad met de sterkste randen binnen een band van +-rng pixels
    (dynamisch programmeren). Begin- en eindpunt liggen vast. Geeft lijst (x, y)."""
    ax, ay = a
    bx, by = b
    L = float(np.hypot(bx - ax, by - ay))
    if L < 2 or rng < 1:
        return [(ax, ay), (bx, by)]
    n = int(L) + 1
    t = np.linspace(0, 1, n)
    nx, ny = -(by - ay) / L, (bx - ax) / L
    offs = np.arange(-rng, rng + 1, dtype=np.float32)
    X = ax + t[:, None] * (bx - ax) + offs[None, :] * nx
    Y = ay + t[:, None] * (by - ay) + offs[None, :] * ny
    h, w = G.shape
    xi = np.clip(np.rint(X).astype(int), 0, w - 1)
    yi = np.clip(np.rint(Y).astype(int), 0, h - 1)
    cost = 1.0 - G[yi, xi]
    idx = np.arange(n)
    limit = np.minimum(idx, n - 1 - idx)[:, None]
    cost = np.where(np.abs(offs)[None, :] > limit, np.inf, cost)
    M = len(offs)
    acc = cost[0].copy()
    back = np.zeros((n, M), np.int8)
    inf = np.full(1, np.inf, np.float32)
    for i in range(1, n):
        up = np.concatenate([inf, acc[:-1]]) + stiffness
        dn = np.concatenate([acc[1:], inf]) + stiffness
        stack = np.stack([acc, up, dn])
        k = np.argmin(stack, axis=0)
        acc = stack[k, np.arange(M)] + cost[i]
        back[i] = k
    j = rng
    path = []
    for i in range(n - 1, -1, -1):
        path.append((float(X[i, j]), float(Y[i, j])))
        k = back[i, j]
        j = j - 1 if k == 1 else (j + 1 if k == 2 else j)
    path.reverse()
    return path


def smooth_points(pts, amount):
    if amount <= 0 or len(pts) < 5:
        return pts
    a = np.array(pts, np.float32)
    k = int(amount) * 2 + 1
    pad = np.concatenate([a[-k:], a, a[:k]])  # gesloten vorm
    ker = np.ones(k, np.float32) / k
    sx = np.convolve(pad[:, 0], ker, mode="same")[k:-k]
    sy = np.convolve(pad[:, 1], ker, mode="same")[k:-k]
    return list(zip(sx.tolist(), sy.tolist()))


def snap_point(G: np.ndarray, x, y, rng: int):
    """Verplaats een aangeklikt punt naar de sterkste rand in de buurt (dichtbij weegt zwaarder)."""
    h, w = G.shape
    x0, x1 = max(0, int(x) - rng), min(w, int(x) + rng + 1)
    y0, y1 = max(0, int(y) - rng), min(h, int(y) + rng + 1)
    if x1 <= x0 or y1 <= y0:
        return x, y
    win = G[y0:y1, x0:x1]
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dist = np.hypot(xx - x, yy - y) / max(rng, 1)
    score = win - dist * 0.35
    score[dist > 1] = -1
    if win.max() < 0.15:
        return x, y
    j = np.unravel_index(np.argmax(score), score.shape)
    return float(xx[j]) + 0.5, float(yy[j]) + 0.5


def snap_path(G: np.ndarray, a, b, rng: int, depth=3):
    """snap_segment, maar splitst het stuk als het pad tegen de rand van het bereik aanloopt,
    zodat ook sterk gebogen randen gevolgd worden."""
    path = snap_segment(G, a, b, rng)
    if depth <= 0 or len(path) < 8:
        return path
    ax, ay = a
    bx, by = b
    L = float(np.hypot(bx - ax, by - ay))
    nx, ny = -(by - ay) / L, (bx - ax) / L
    offs = [abs((x - ax) * nx + (y - ay) * ny) for x, y in path]
    if max(offs) < rng - 1.5:
        return path
    # splitspunt: zoek loodrecht op de koorde (vanuit het midden) naar de sterkste rand
    mx, my = (ax + bx) / 2, (ay + by) / 2
    reach = int(min(L / 2, rng * 4))
    ts = np.arange(-reach, reach + 1, dtype=np.float32)
    h, w = G.shape
    xs = np.clip(np.rint(mx + ts * nx).astype(int), 0, w - 1)
    ys = np.clip(np.rint(my + ts * ny).astype(int), 0, h - 1)
    score = G[ys, xs] - np.abs(ts) / max(reach, 1) * 0.3
    k = int(np.argmax(score))
    mid = (float(xs[k]) + 0.5, float(ys[k]) + 0.5)
    left = snap_path(G, a, mid, rng, depth - 1)
    right = snap_path(G, mid, b, rng, depth - 1)
    return left + right[1:]
