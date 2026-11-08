"""Bewerkingen op de paden van de Pen (en op opgepakte vectorobjecten): het snelmenu Bewerken,
Knooppunttype en Geselecteerde knooppunten transformeren.

Een pad is {"nodes": [[punt, in, uit], ...], "closed": bool, "types": {index: type}}; punten zijn QPointF,
'in' en 'uit' de handvatten (of None). Een selectie is een verzameling (pad, knooppunt).
Knooppunttypen (zoals PSP):
  "sym"    symmetrisch: handvatten op één lijn en even lang
  "asym"   asymmetrisch: handvatten op één lijn, eigen lengte
  "cusp"   punt: handvatten onafhankelijk (een scherpe knik)
  "smooth" glad/raaklijn: vloeiende overgang, ook tussen een rechte lijn en een kromme"""
import math

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QTransform

TYPES = ("asym", "sym", "cusp", "smooth")


def _len(v):
    return math.hypot(v.x(), v.y())


def clone_paths(paths):
    out = []
    for p in paths:
        out.append({"nodes": [[QPointF(n[0]), QPointF(n[1]) if n[1] is not None else None,
                               QPointF(n[2]) if n[2] is not None else None] for n in p["nodes"]],
                    "closed": p["closed"], "types": dict(p.get("types", {}))})
    return out


def infer_type(node):
    """Type van een knooppunt uit de stand van de handvatten (voor paden zonder opgeslagen type)."""
    pt, a, b = node[0], node[1], node[2]
    if a is None or b is None:
        return "cusp" if (a is not None or b is not None) else "smooth"
    va, vb = a - pt, b - pt
    la, lb = _len(va), _len(vb)
    if la < 1e-6 or lb < 1e-6:
        return "cusp"
    cos = (va.x() * vb.x() + va.y() * vb.y()) / (la * lb)
    if cos < -0.999:
        return "sym" if abs(la - lb) < 0.5 else "asym"
    return "cusp"


def node_type(path, ni):
    return path.get("types", {}).get(ni) or infer_type(path["nodes"][ni])


def neighbours(path, ni):
    n = path["nodes"]
    prev = n[ni - 1] if ni > 0 or (path["closed"] and len(n) > 2) else None
    nxt = n[(ni + 1) % len(n)] if ni < len(n) - 1 or (path["closed"] and len(n) > 2) else None
    return prev, nxt


def set_type(path, ni, t):
    """Knooppunttype instellen en de handvatten daarop aanpassen."""
    node = path["nodes"][ni]
    path.setdefault("types", {})[ni] = t
    pt = node[0]
    if t == "cusp":
        return
    prev, nxt = neighbours(path, ni)
    if node[1] is None and node[2] is None or t == "smooth":
        # handvatten maken (of bijwerken) in de richting van de buren
        a = prev[0] if prev is not None else pt
        b = nxt[0] if nxt is not None else pt
        d = b - a
        ln = _len(d) or 1.0
        u = QPointF(d.x() / ln, d.y() / ln)
        lin = (_len(pt - a) / 3) if prev is not None else 0
        lout = (_len(b - pt) / 3) if nxt is not None else 0
        if t == "smooth" and node[1] is not None and node[2] is not None:
            lin, lout = _len(node[1] - pt), _len(node[2] - pt)
        node[1] = pt - u * lin if prev is not None else None
        node[2] = pt + u * lout if nxt is not None else None
        if t != "sym":
            return
    a = node[1] if node[1] is not None else pt
    b = node[2] if node[2] is not None else pt
    va, vb = a - pt, b - pt
    la, lb = _len(va), _len(vb)
    la, lb = (la or lb), (lb or la)  # één handvat: het andere krijgt dezelfde lengte
    # gemeenschappelijke richting: van het in-handvat naar het uit-handvat
    d = vb - va
    ln = _len(d) or 1.0
    u = QPointF(d.x() / ln, d.y() / ln)
    if t == "sym":
        la = lb = (la + lb) / 2 or 10.0
    node[1] = pt - u * la
    node[2] = pt + u * lb


def drag_handle(path, ni, k, new_pos):
    """Handvat k (1 in, 2 uit) verplaatsen; het andere handvat volgt volgens het knooppunttype."""
    node = path["nodes"][ni]
    node[k] = QPointF(new_pos)
    other = 2 if k == 1 else 1
    t = node_type(path, ni)
    if node[other] is None or t == "cusp":
        return
    v = node[k] - node[0]
    ln = _len(v)
    if ln < 1e-6:
        return
    length = ln if t == "sym" else _len(node[other] - node[0])
    node[other] = node[0] - QPointF(v.x() / ln, v.y() / ln) * length


# ---------------------------------------------------------------- segmenten
def line_before(path, ni):
    prev, _ = neighbours(path, ni)
    if prev is None:
        return
    path["nodes"][ni][1] = None
    prev[2] = None


def line_after(path, ni):
    _, nxt = neighbours(path, ni)
    if nxt is None:
        return
    path["nodes"][ni][2] = None
    nxt[1] = None


def curve_before(path, ni):
    prev, _ = neighbours(path, ni)
    if prev is None:
        return
    node = path["nodes"][ni]
    a, b = prev[0], node[0]
    if prev[2] is None:
        prev[2] = a + (b - a) / 3
    if node[1] is None:
        node[1] = b + (a - b) / 3


def curve_after(path, ni):
    _, nxt = neighbours(path, ni)
    if nxt is None:
        return
    node = path["nodes"][ni]
    a, b = node[0], nxt[0]
    if node[2] is None:
        node[2] = a + (b - a) / 3
    if nxt[1] is None:
        nxt[1] = b + (a - b) / 3


def to_line(path, ni):
    line_before(path, ni)
    line_after(path, ni)


# ---------------------------------------------------------------- paden
def reverse_contour(path):
    path["nodes"] = [[n[0], n[2], n[1]] for n in reversed(path["nodes"])]
    k = len(path["nodes"]) - 1
    path["types"] = {k - i: t for i, t in path.get("types", {}).items()}


def is_end(path, ni):
    return not path["closed"] and ni in (0, len(path["nodes"]) - 1)


def join(paths, a, b):
    """Twee eindpunten verbinden met een recht stuk. Zelfde pad: sluiten; twee paden: één pad maken.
    Geeft de nieuwe lijst paden terug, of None als het niet kan."""
    (pa, na), (pb, nb) = a, b
    if not (is_end(paths[pa], na) and is_end(paths[pb], nb)):
        return None
    if pa == pb:
        if na == nb or len(paths[pa]["nodes"]) < 3:
            return None
        paths[pa]["closed"] = True
        return paths
    first, second = paths[pa], paths[pb]
    if na == 0:  # het eerste pad moet eindigen bij het verbindingspunt
        reverse_contour(first)
    if nb != 0:  # het tweede pad moet beginnen bij het verbindingspunt
        reverse_contour(second)
    off = len(first["nodes"])
    joined = {"nodes": first["nodes"] + second["nodes"], "closed": False,
              "types": {**first.get("types", {}), **{i + off: t for i, t in second.get("types", {}).items()}}}
    rest = [p for i, p in enumerate(paths) if i not in (pa, pb)]
    return rest[:min(pa, pb)] + [joined] + rest[min(pa, pb):]


def merge(paths, a, b):
    """Twee eindpunten samenvoegen tot één knooppunt halverwege. Zelfde pad: het pad sluit zich;
    twee paden: ze worden één pad. Geeft de nieuwe lijst paden terug, of None als het niet kan."""
    (pa, na), (pb, nb) = a, b
    if not (is_end(paths[pa], na) and is_end(paths[pb], nb)) or (pa == pb and na == nb):
        return None
    mid = (paths[pa]["nodes"][na][0] + paths[pb]["nodes"][nb][0]) / 2
    if pa == pb:
        p = paths[pa]
        if len(p["nodes"]) < 3:
            return None
        first, last = p["nodes"][0], p["nodes"][-1]
        first[0], first[1] = mid, last[1]
        p["nodes"].pop()
        p["types"] = {i: t for i, t in p.get("types", {}).items() if i < len(p["nodes"])}
        p["closed"] = True
        return paths
    first_len = len(paths[pa]["nodes"])
    out = join(paths, a, b)
    if out is None:
        return None
    joined = out[min(pa, pb)]
    k = first_len - 1  # laatste punt van het eerste deel; het volgende is het begin van het tweede
    n1, n2 = joined["nodes"][k], joined["nodes"][k + 1]
    n1[0] = mid
    n1[2] = n2[2]
    del joined["nodes"][k + 1]
    joined["types"] = {(i if i <= k else i - 1): t for i, t in joined.get("types", {}).items() if i != k + 1}
    return out


def break_at(paths, pi, ni):
    """Pad onderbreken bij een knooppunt: een gesloten pad wordt open, een open pad wordt twee paden."""
    p = paths[pi]
    n = p["nodes"]
    if p["closed"]:
        n2 = n[ni:] + n[:ni]
        first = n2[0]
        n2.append([QPointF(first[0]), first[1], None])
        first[1] = None
        p["nodes"], p["closed"], p["types"] = n2, False, {}
        return paths
    if ni in (0, len(n) - 1):
        return paths  # al een eindpunt
    a = {"nodes": n[:ni + 1], "closed": False, "types": {}}
    copy_node = n[ni]
    b = {"nodes": [[QPointF(copy_node[0]), None, copy_node[2]]] + n[ni + 1:], "closed": False, "types": {}}
    a["nodes"][-1] = [copy_node[0], copy_node[1], None]
    return paths[:pi] + [a, b] + paths[pi + 1:]


def duplicate(paths, pis, offset=QPointF(0, 0)):
    """Kopieën van de paden pis achteraan toevoegen (met een verschuiving)."""
    new = clone_paths([paths[i] for i in sorted(set(pis))])
    for p in new:
        for node in p["nodes"]:
            for k in range(3):
                if node[k] is not None:
                    node[k] = node[k] + offset
    return paths + new, list(range(len(paths), len(paths) + len(new)))


# ---------------------------------------------------------------- transformeren
def selection_rect(paths, sel):
    pts = [paths[pi]["nodes"][ni][0] for pi, ni in sel]
    if not pts:
        return QRectF()
    xs, ys = [q.x() for q in pts], [q.y() for q in pts]
    return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def transform_nodes(paths, sel, t: QTransform):
    """Geselecteerde knooppunten (met hun handvatten) door t halen, rond het midden van de selectie."""
    if not sel:
        return
    c = selection_rect(paths, sel).center()
    full = QTransform.fromTranslate(-c.x(), -c.y()) * t * QTransform.fromTranslate(c.x(), c.y())
    for pi, ni in sel:
        node = paths[pi]["nodes"][ni]
        for k in range(3):
            if node[k] is not None:
                node[k] = full.map(node[k])


def transforms():
    """De transformaties van het menu: naam -> QTransform (rond het midden)."""
    return {
        "flip": QTransform.fromScale(1, -1),
        "mirror": QTransform.fromScale(-1, 1),
        "contract": QTransform.fromScale(0.9, 0.9),
        "expand": QTransform.fromScale(1 / 0.9, 1 / 0.9),
    }


def rotate(deg):
    return QTransform().rotate(deg)


def skew(deg_x=0.0, deg_y=0.0):
    return QTransform(1, math.tan(math.radians(deg_y)), math.tan(math.radians(deg_x)), 1, 0, 0)
