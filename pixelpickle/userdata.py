"""Eigen penselen, vormen en fotolijsten van de gebruiker, en de mappen waar die staan
(Bestand > Voorkeuren > Bestandslocaties). Standaard in ~/.local/share/PixelPickle/<soort>.

- penseel: PNG in grijswaarden; zwart (en dekkend) is waar het penseel verf geeft
- vorm: JSON met contouren, genormaliseerd naar 0..1 binnen het omhullende kader
- fotolijst: PNG met een doorzichtig midden"""
import json
import os
import re

import numpy as np
from PySide6.QtCore import QSettings, QStandardPaths, Qt
from PySide6.QtGui import QImage, QPainterPath

KINDS = {"brushes": "Penselen", "shapes": "Vormen", "frames": "Fotolijsten", "patterns": "Patronen"}


def default_folder(kind):
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation) or \
        os.path.expanduser("~/.local/share")
    return os.path.join(base, "PixelPickle", KINDS[kind])


def folder(kind, create=True):
    path = QSettings("PixelPickle", "PixelPickle").value(f"loc_{kind}", "") or default_folder(kind)
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def set_folder(kind, path):
    QSettings("PixelPickle", "PixelPickle").setValue(f"loc_{kind}", path or "")


def safe_name(name):
    name = re.sub(r'[\\/:*?"<>|]+', "_", name.strip())
    return name or "naamloos"


def _list(kind, ext):
    d = folder(kind, create=False)
    if not os.path.isdir(d):
        return []
    return sorted((os.path.splitext(f)[0], os.path.join(d, f)) for f in os.listdir(d) if f.lower().endswith(ext))


# ---------------------------------------------------------------- penselen
def brush_names():
    return [n for n, _ in _list("brushes", ".png")]


def save_brush(name, weight: np.ndarray):
    """weight: 0..1 (1 = volle verf). Bewaard als grijswaarden-PNG (zwart = verf)."""
    g = np.clip(255 - weight * 255, 0, 255).astype(np.uint8)
    g = np.ascontiguousarray(g)
    img = QImage(g.data, g.shape[1], g.shape[0], g.strides[0], QImage.Format.Format_Grayscale8).copy()
    path = os.path.join(folder("brushes"), safe_name(name) + ".png")
    img.save(path)
    return path


def brush_weight_from_image(img: QImage) -> np.ndarray:
    """Penseelpunt uit een afbeelding: hoe donkerder en dekkender, hoe meer verf (0..1), bijgesneden."""
    from . import imageops as ops
    a = ops.qimage_to_rgba(img.convertToFormat(ops.FMT)).astype(np.float32)
    lum = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
    w = (1 - lum / 255) * (a[..., 3] / 255)
    if not (a[..., 3] < 255).any() and w.max() < 0.05:  # geheel licht en dekkend: helderheid omkeren
        w = lum / 255
    ys, xs = np.nonzero(w > 0.01)
    if len(xs):
        w = w[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return w


def load_brush(name) -> np.ndarray | None:
    path = dict(_list("brushes", ".png")).get(name)
    if not path:
        return None
    img = QImage(path).convertToFormat(QImage.Format.Format_Grayscale8)
    if img.isNull():
        return None
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.constBits(), np.uint8, count=img.bytesPerLine() * h).reshape(h, img.bytesPerLine())[:, :w]
    return 1 - arr.astype(np.float32) / 255


# ---------------------------------------------------------------- vormen
def shape_names():
    return [n for n, _ in _list("shapes", ".json")]


def save_shape(name, objs):
    """Vectorobjecten als eigen vorm bewaren (contouren genormaliseerd naar het omhullende kader)."""
    from . import vectorlayer as V
    path_all = QPainterPath()
    for o in objs:
        path_all.addPath(V.qpath(o))
    r = path_all.boundingRect()
    w, h = max(r.width(), 1e-6), max(r.height(), 1e-6)

    def norm(q):
        return None if q is None else [(q[0] - r.x()) / w, (q[1] - r.y()) / h]
    contours = []
    for o in objs:
        for nodes, closed in V.contours(o):
            contours.append({"nodes": [[norm(n[0]), norm(n[1]), norm(n[2])] for n in nodes], "closed": closed})
    path = os.path.join(folder("shapes"), safe_name(name) + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"contours": contours, "aspect": w / h}, f)
    return path


def shape_path(name, x, y, w, h) -> QPainterPath | None:
    """De eigen vorm in het kader (x, y, w, h)."""
    from . import vectorlayer as V
    p = dict(_list("shapes", ".json")).get(name)
    if not p:
        return None
    try:
        data = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    for c in data.get("contours", []):
        nodes = [[None if q is None else [x + q[0] * w, y + q[1] * h] for q in n] for n in c["nodes"]]
        V._add_contour(path, nodes, c.get("closed", False))
    return path


# ---------------------------------------------------------------- fotolijsten
def frame_names():
    return [n for n, _ in _list("frames", ".png")]


def save_frame(name, img: QImage):
    path = os.path.join(folder("frames"), safe_name(name) + ".png")
    img.save(path)
    return path


def load_frame(name) -> QImage | None:
    p = dict(_list("frames", ".png")).get(name)
    img = QImage(p) if p else QImage()
    return None if img.isNull() else img
