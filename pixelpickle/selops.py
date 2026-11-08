"""Selectiebewerkingen (menu Selecties > Wijzigen en verwanten), op maskers als NumPy-arrays.
Een masker is uint8 (0..255) of bool, even groot als het doek."""
import numpy as np

from . import imageops as ops


# ---------------------------------------------------------------- samenhangende stukken
def components(b: np.ndarray):
    """Samenhangende stukken (4 buren) van een booleaans masker. Geeft (labels per pixel, oppervlak per label);
    label 0 is de achtergrond, stukken zijn 1..n. Werkt met horizontale stroken, dus ook op grote foto's snel."""
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
        a0, a1 = rs[row - 1], rs[row]   # stroken in de vorige rij
        b0, b1 = rs[row], rs[row + 1]   # stroken in deze rij
        i, j = a0, b0
        while i < a1 and j < b1:
            if sl[i] < el[j] and sl[j] < el[i]:  # overlappen: zelfde stuk
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
    """De stukken van 'sim' die de beginselectie 'seed' raken (aaneengesloten uitbreiden)."""
    lab, _ = components(sim | seed)
    keep = np.unique(lab[seed])
    keep = keep[keep > 0]
    return np.isin(lab, keep)


def remove_specks_holes(m: np.ndarray, size: int, specks=True, holes=True) -> np.ndarray:
    """Losse geselecteerde stipjes en kleine gaten in de selectie (kleiner dan 'size' pixels) weghalen."""
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
        # een 'gat' raakt de rand van het doek niet (anders is het gewoon de buitenkant)
        edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        small = area < size
        small[0] = False
        small[edge] = False
        out[small[lab]] = 255
    return out


# ---------------------------------------------------------------- afstand tot de rand
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
    """Afstand (in stappen, hoogstens n) van elk geselecteerd pixel tot de rand van de selectie."""
    d = np.zeros(b.shape, np.float32)
    cur = b.copy()
    for k in range(1, int(n) + 1):
        cur = erode(cur, 1)
        d += cur
        if not cur.any():
            break
    return d


# ---------------------------------------------------------------- bewerkingen
def feather_side(m: np.ndarray, n: int, side: str) -> np.ndarray:
    """Doezelen naar binnen ('inside'), naar buiten ('outside') of beide ('both')."""
    b = m > 127
    n = max(1, int(n))
    if side == "inside":
        a = np.clip((depth(b, n) + 1) / (n + 1), 0, 1)
        return (np.where(b, a, 0) * 255).astype(np.uint8)
    if side == "outside":
        out_d = depth(~b, n)  # afstand buiten de selectie
        a = np.clip(1 - out_d / (n + 1), 0, 1)
        return (np.where(b, 1.0, np.where(out_d < n, a, 0)) * 255).astype(np.uint8)
    return np.clip(ops.box_blur(m.astype(np.float32), n), 0, 255).astype(np.uint8)


def unfeather(m: np.ndarray, threshold: int) -> np.ndarray:
    """Doezelen opheffen: harde rand op de drempel (1..100 %)."""
    return np.where(m >= threshold * 2.55, 255, 0).astype(np.uint8)


def smooth(m: np.ndarray, amount: int) -> np.ndarray:
    """Hoekige randen gladmaken: vervagen en weer scherp maken op de helft, met een zachte rand."""
    soft = ops.box_blur(m.astype(np.float32), max(1, int(amount)))
    b = soft >= 127.5
    return ops.antialias_mask(b, "outside")


def antialias(m: np.ndarray, where: str) -> np.ndarray:
    """Op vorm gebaseerde anti-alias: kartelranden zacht maken, binnen of buiten de rand."""
    return ops.antialias_mask(m > 127, where)


def recover_antialias(m: np.ndarray, layer_alpha: np.ndarray) -> np.ndarray:
    """Anti-alias herstellen: langs de rand van de selectie de half doorzichtige randpixels van de laag
    (de anti-alias van het voorwerp) weer meenemen."""
    b = m > 127
    band = dilate(b, 2) & ~erode(b, 2)
    out = m.astype(np.float32)
    out[band] = np.maximum(out[band], np.minimum(layer_alpha[band].astype(np.float32), 255))
    return np.clip(out, 0, 255).astype(np.uint8)


def borders(m: np.ndarray, width: int, side: str, aa=True) -> np.ndarray:
    """Selectieranden selecteren: een band langs de rand, binnen, buiten of aan beide kanten."""
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
    """Alle pixels die op een kleur uit de selectie lijken (tolerantie 0..200 zoals de toverstaf)."""
    sel = m > 127
    if not sel.any():
        return sel
    rgb = rgba[..., :3].astype(np.int16)
    cols = rgb[sel]
    # representatieve kleuren: afgerond en ontdubbeld (hoogstens enkele honderden)
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
    """Kleurbereik: hoe sterk elke pixel op 'color' lijkt (0..255), met een zachte overgang."""
    d = np.abs(rgba[..., :3].astype(np.float32) - np.array(color[:3], np.float32)).max(axis=2)
    t = tol * 1.275
    s = max(1.0, softness * 1.275)
    return np.clip((1 - (d - t) / s) * 255, 0, 255).astype(np.uint8)
