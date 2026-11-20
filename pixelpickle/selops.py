"""Selection operations (Selections > Modify menu and related), on masks as NumPy arrays.
A mask is uint8 (0..255) or bool, the same size as the canvas."""
import numpy as np

from . import imageops as ops


# ---------------------------------------------------------------- connected components
def components(b: np.ndarray):
    """Connected components (4 neighbors) of a boolean mask. Returns (labels per pixel, area per label);
    label 0 is the background, components are 1..n. Works with horizontal runs, so it is fast on large photos too."""
    h, w = b.shape
    r, s, e = ops._runs(b)
    n = len(r)
    if n == 0:
        return np.zeros((h, w), np.int32), np.zeros(1, np.int64)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    rl, sl, el = r.tolist(), s.tolist(), e.tolist()
    rs = np.searchsorted(r, np.arange(h + 1)).tolist()
    for row in range(1, h):
        a0, a1 = rs[row - 1], rs[row]   # runs in the previous row
        b0, b1 = rs[row], rs[row + 1]   # runs in this row
        i, j = a0, b0
        while i < a1 and j < b1:
            if sl[i] < el[j] and sl[j] < el[i]:  # overlap: same component
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
            if el[i] < el[j]:
                i += 1
            else:
                j += 1
    roots = np.array([find(i) for i in range(n)])
    uniq, lab = np.unique(roots, return_inverse=True)
    lab = lab + 1
    area = np.zeros(len(uniq) + 1, np.int64)
    np.add.at(area, lab, e - s)
    acc = np.zeros((h, w + 1), np.int32)
    np.add.at(acc, (r, s), lab)
    np.add.at(acc, (r, e), -lab)
    return np.cumsum(acc, axis=1)[:, :w], area


def grow_from(sim: np.ndarray, seed: np.ndarray) -> np.ndarray:
    """The components of 'sim' that touch the initial selection 'seed' (grow contiguously)."""
    lab, _ = components(sim | seed)
    keep = np.unique(lab[seed])
    keep = keep[keep > 0]
    return np.isin(lab, keep)


def remove_specks_holes(m: np.ndarray, size: int, specks=True, holes=True) -> np.ndarray:
    """Remove isolated selected specks and small holes in the selection (smaller than 'size' pixels)."""
    b = m > 127
    out = m.copy()
    if specks:
        lab, area = components(b)
        small = area < size
        small[0] = False
        out[small[lab]] = 0
    if holes:
        hole = ~(out > 127)
        lab, area = components(hole)
        # a 'hole' does not touch the canvas edge (otherwise it is simply the outside)
        edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        small = area < size
        small[0] = False
        small[edge] = False
        out[small[lab]] = 255
    return out


# ---------------------------------------------------------------- distance to the edge
def _dilate(b: np.ndarray) -> np.ndarray:
    nb = b.copy()
    nb[1:] |= b[:-1]
    nb[:-1] |= b[1:]
    nb[:, 1:] |= b[:, :-1]
    nb[:, :-1] |= b[:, 1:]
    return nb


def dilate(b, n):
    for _ in range(int(n)):
        b = _dilate(b)
    return b


def erode(b, n):
    return ~dilate(~b, n)


def depth(b: np.ndarray, n: int) -> np.ndarray:
    """Distance (in steps, at most n) from each selected pixel to the edge of the selection."""
    d = np.zeros(b.shape, np.float32)
    cur = b.copy()
    for k in range(1, int(n) + 1):
        cur = erode(cur, 1)
        d += cur
        if not cur.any():
            break
    return d


# ---------------------------------------------------------------- operations
def feather_side(m: np.ndarray, n: int, side: str) -> np.ndarray:
    """Feather inward ('inside'), outward ('outside') or both ('both')."""
    b = m > 127
    n = max(1, int(n))
    if side == "inside":
        a = np.clip((depth(b, n) + 1) / (n + 1), 0, 1)
        return (np.where(b, a, 0) * 255).astype(np.uint8)
    if side == "outside":
        out_d = depth(~b, n)  # distance outside the selection
        a = np.clip(1 - out_d / (n + 1), 0, 1)
        return (np.where(b, 1.0, np.where(out_d < n, a, 0)) * 255).astype(np.uint8)
    return np.clip(ops.box_blur(m.astype(np.float32), n), 0, 255).astype(np.uint8)


def unfeather(m: np.ndarray, threshold: int) -> np.ndarray:
    """Remove feathering: hard edge at the threshold (1..100 %)."""
    return np.where(m >= threshold * 2.55, 255, 0).astype(np.uint8)


def smooth(m: np.ndarray, amount: int) -> np.ndarray:
    """Smooth angular edges: blur and sharpen again at the midpoint, with a soft edge."""
    soft = ops.box_blur(m.astype(np.float32), max(1, int(amount)))
    b = soft >= 127.5
    return ops.antialias_mask(b, "outside")


def antialias(m: np.ndarray, where: str) -> np.ndarray:
    """Shape-based anti-alias: soften jagged edges, inside or outside the edge."""
    return ops.antialias_mask(m > 127, where)


def recover_antialias(m: np.ndarray, layer_alpha: np.ndarray) -> np.ndarray:
    """Restore anti-alias: along the edge of the selection, pick up the half transparent edge pixels of the layer
    (the object's anti-alias) again."""
    b = m > 127
    band = dilate(b, 2) & ~erode(b, 2)
    out = m.astype(np.float32)
    out[band] = np.maximum(out[band], np.minimum(layer_alpha[band].astype(np.float32), 255))
    return np.clip(out, 0, 255).astype(np.uint8)


def borders(m: np.ndarray, width: int, side: str, aa=True) -> np.ndarray:
    """Select borders: a band along the edge, inside, outside or on both sides."""
    b = m > 127
    n = max(1, int(width))
    if side == "inside":
        band = b & ~erode(b, n)
    elif side == "outside":
        band = dilate(b, n) & ~b
    else:
        half = max(1, n // 2)
        band = dilate(b, n - half) & ~erode(b, half)
    return ops.antialias_mask(band, "outside") if aa else (band * 255).astype(np.uint8)


def similar_colors(rgba: np.ndarray, m: np.ndarray, tol: int) -> np.ndarray:
    """All pixels that resemble a color in the selection (tolerance 0..200 like the magic wand)."""
    sel = m > 127
    if not sel.any():
        return sel
    rgb = rgba[..., :3].astype(np.int16)
    cols = rgb[sel]
    # representative colors: rounded and de-duplicated (at most a few hundred)
    step = max(4, int(tol * 1.275) // 2 or 4)
    q = np.unique((cols // step) * step + step // 2, axis=0)
    if len(q) > 512:
        q = q[np.random.default_rng(1).choice(len(q), 512, replace=False)]
    limit = tol * 1.275 + step / 2
    flat = rgb.reshape(-1, 3)
    hit = np.zeros(len(flat), bool)
    for k in range(0, len(q), 32):
        c = q[k:k + 32][:, None, :]
        dist = np.abs(flat[None, :, :] - c).max(axis=2)
        hit |= (dist <= limit).any(axis=0)
    return hit.reshape(m.shape) | sel


def color_range(rgba: np.ndarray, color, tol: int, softness: int) -> np.ndarray:
    """Color range: how strongly each pixel resembles 'color' (0..255), with a soft transition."""
    d = np.abs(rgba[..., :3].astype(np.float32) - np.array(color[:3], np.float32)).max(axis=2)
    t = tol * 1.275
    s = max(1.0, softness * 1.275)
    return np.clip((1 - (d - t) / s) * 255, 0, 255).astype(np.uint8)
