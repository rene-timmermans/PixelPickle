"""Hulpfuncties voor effecten (alleen NumPy en Pillow; geen SciPy)."""
import numpy as np

from ..imageops import box_blur, hsl_to_rgb, rgb_to_hsl  # noqa: F401


def f32(a):
    return a.astype(np.float32)


def to_u8(a):
    return np.clip(np.rint(a), 0, 255).astype(np.uint8)


def gray(a):
    """Luminantie (H, W) float32 0..255."""
    a = a.astype(np.float32)
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def with_rgb(a, rgb):
    """Nieuwe RGBA met de alfa van a en de gegeven rgb (float of uint8)."""
    out = a.copy()
    out[..., :3] = to_u8(rgb)
    return out


def blur(x, radius):
    """Benadering van gaussiaans vervagen. x: 2D of 3D float. radius in pixels (float mag)."""
    r = int(round(radius))
    return box_blur(x.astype(np.float32), r) if r >= 1 else x.astype(np.float32)


def blur_rgba(a, radius):
    """Vervagen met correcte behandeling van transparantie. Geeft uint8 RGBA."""
    al = a[..., 3:4].astype(np.float32) / 255
    pm = blur(a[..., :3].astype(np.float32) * al, radius)
    al2 = blur(al[..., 0], radius)[..., None]
    rgb = np.where(al2 > 1e-6, pm / np.maximum(al2, 1e-6), 0)
    return np.dstack([to_u8(rgb), to_u8(al2[..., 0] * 255)])


def convolve(x, kernel):
    """Kleine 2D convolutie (kernel als lijst/array), randen herhaald. x: 2D of 3D float."""
    k = np.asarray(kernel, np.float32)
    kh, kw = k.shape
    py, px = kh // 2, kw // 2
    pad = ((py, py), (px, px)) + (((0, 0),) if x.ndim == 3 else ())
    p = np.pad(x.astype(np.float32), pad, mode="edge")
    h, w = x.shape[:2]
    out = np.zeros_like(x, dtype=np.float32)
    for j in range(kh):
        for i in range(kw):
            if k[j, i] != 0:
                out += k[j, i] * p[j:j + h, i:i + w]
    return out


def sobel(g):
    """Gradiënten (gx, gy) van een 2D float beeld."""
    gx = convolve(g, [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]])
    gy = convolve(g, [[-1, -2, -1], [0, 0, 0], [1, 2, 1]])
    return gx, gy


def remap(a, mx, my, edge="clamp", fill=(0, 0, 0, 0)):
    """Bilineair bemonsteren: out[y, x] = a[my[y, x], mx[y, x]].
    edge: "clamp" (rand herhalen), "wrap" (tegelen), "mirror" (spiegelen), "fill" (kleur/transparant)."""
    h, w = a.shape[:2]
    al = a[..., 3:4].astype(np.float32) / 255
    src = np.dstack([a[..., :3].astype(np.float32) * al, al * 255])  # voorvermenigvuldigd
    x0 = np.floor(mx).astype(np.int64)
    y0 = np.floor(my).astype(np.int64)
    fx = (mx - x0).astype(np.float32)[..., None]
    fy = (my - y0).astype(np.float32)[..., None]

    def idx(v, n):
        if edge == "wrap":
            return np.mod(v, n)
        if edge == "mirror":
            v = np.mod(v, 2 * n)
            return np.where(v >= n, 2 * n - 1 - v, v)
        return np.clip(v, 0, n - 1)

    def get(xx, yy):
        s = src[idx(yy, h), idx(xx, w)]
        if edge == "fill":
            inside = ((xx >= 0) & (xx < w) & (yy >= 0) & (yy < h))[..., None]
            f = np.array(fill, np.float32)
            fpm = np.concatenate([f[:3] * f[3] / 255, f[3:4]])
            s = np.where(inside, s, fpm)
        return s
    out = (get(x0, y0) * (1 - fx) * (1 - fy) + get(x0 + 1, y0) * fx * (1 - fy)
           + get(x0, y0 + 1) * (1 - fx) * fy + get(x0 + 1, y0 + 1) * fx * fy)
    alpha = out[..., 3:4]
    rgb = np.where(alpha > 1e-3, out[..., :3] / np.maximum(alpha / 255, 1e-6), 0)
    return np.dstack([to_u8(rgb), to_u8(alpha[..., 0])])


def grid(h, w):
    """Coördinaatroosters (yy, xx) float32."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    return yy, xx


def noise(h, w, seed=1, channels=None):
    rng = np.random.default_rng(seed)
    return rng.random((h, w) if channels is None else (h, w, channels), dtype=np.float32)


def smooth_noise(h, w, scale, seed=1):
    """Vloeiende waarderuis 0..1 (voor texturen), scale = korrelgrootte in pixels."""
    s = max(1, int(scale))
    small = noise(h // s + 2, w // s + 2, seed)
    yy, xx = grid(h, w)
    gx, gy = xx / s, yy / s
    x0, y0 = gx.astype(int), gy.astype(int)
    fx, fy = gx - x0, gy - y0
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a = small[y0, x0] * (1 - fx) + small[y0, x0 + 1] * fx
    b = small[y0 + 1, x0] * (1 - fx) + small[y0 + 1, x0 + 1] * fx
    return a * (1 - fy) + b * fy


def lerp(a, b, t):
    return a + (b - a) * t
