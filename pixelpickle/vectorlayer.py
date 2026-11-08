"""Vectorlagen: lijnen en vormen die bewerkbaar blijven zolang je met de afbeelding bezig bent.

Een vectorlaag heeft layer.vector = [object, ...]; layer.image is alleen de weergave en wordt na elke
wijziging opnieuw getekend (zoals bij tekstlagen). Een object is een gewone dict, zodat kopiëren
(ongedaan maken) en bewaren in .ora eenvoudig zijn:

    {"nodes": [[[x, y], [inx, iny] | None, [uitx, uity] | None], ...],
     "closed": bool,
     "stroke": [r, g, b, a] | None,   # None = geen rand
     "fill": [r, g, b, a] | None,     # None = geen vulling (alleen gesloten paden worden gevuld)
     "width": float, "style": int, "join": int, "miter": float, "aa": bool}
"""
import copy

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPainterPathStroker, QPen

PEN_STYLES = [Qt.PenStyle.SolidLine, Qt.PenStyle.DashLine, Qt.PenStyle.DotLine, Qt.PenStyle.DashDotLine,
              Qt.PenStyle.DashDotDotLine]
JOINS = [Qt.PenJoinStyle.MiterJoin, Qt.PenJoinStyle.RoundJoin, Qt.PenJoinStyle.BevelJoin]


def copy_vector(v):
    return copy.deepcopy(v) if v is not None else None


def _pt(p):
    return QPointF(p[0], p[1]) if p is not None else None


def _lst(q):
    return [q.x(), q.y()] if q is not None else None


def color_list(c, none=False):
    return None if none or c is None else list(QColor(c).getRgb())


def make_object(nodes, closed, stroke, fill, width, style=0, join=0, miter=15.0, aa=True):
    """nodes: [[QPointF, QPointF|None, QPointF|None], ...] (zoals de Pen ze gebruikt)."""
    return {"nodes": [[_lst(n[0]), _lst(n[1]), _lst(n[2])] for n in nodes], "closed": bool(closed),
            "stroke": stroke, "fill": fill, "width": float(width), "style": int(style), "join": int(join),
            "miter": float(miter), "aa": bool(aa)}


def qt_nodes(obj):
    return [[_pt(n[0]), _pt(n[1]), _pt(n[2])] for n in obj["nodes"]]


def contours(obj):
    """Alle contouren van een object: [(nodes, closed)]. Een samengesteld object (bijvoorbeeld een letter
    met een gat) heeft naast de eerste contour nog 'more': [{"nodes": ..., "closed": ...}, ...]."""
    return [(obj["nodes"], obj["closed"])] + [(c["nodes"], c["closed"]) for c in obj.get("more", [])]


def _add_contour(path, nodes, closed):
    n = [[_pt(q[0]), _pt(q[1]), _pt(q[2])] for q in nodes]
    if not n:
        return
    path.moveTo(n[0][0])
    segs = list(zip(n, n[1:])) + ([(n[-1], n[0])] if closed and len(n) > 2 else [])
    for a, b in segs:
        if a[2] is None and b[1] is None:
            path.lineTo(b[0])
        else:
            path.cubicTo(a[2] if a[2] is not None else a[0], b[1] if b[1] is not None else b[0], b[0])
    if closed and len(n) > 2:
        path.closeSubpath()


def qpath(obj):
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)  # gaten in samengestelde objecten blijven open
    for nodes, closed in contours(obj):
        _add_contour(path, nodes, closed)
    return path


def is_closed(obj):
    return any(closed for _, closed in contours(obj))


def pen_for(obj):
    if obj.get("stroke") is None or obj["width"] <= 0:
        return QPen(Qt.PenStyle.NoPen)
    pen = QPen(QColor(*obj["stroke"]), obj["width"])
    pen.setStyle(PEN_STYLES[obj.get("style", 0)])
    pen.setJoinStyle(JOINS[obj.get("join", 0)])
    pen.setMiterLimit(obj.get("miter", 15))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap if obj.get("join", 0) == 1 else Qt.PenCapStyle.FlatCap)
    return pen


def paint(p: QPainter, objs):
    for obj in objs:
        if len(obj["nodes"]) < 2:
            continue
        p.setRenderHint(QPainter.RenderHint.Antialiasing, obj.get("aa", True))
        fill = is_closed(obj) and obj.get("fill") is not None
        p.setBrush(QBrush(QColor(*obj["fill"])) if fill else Qt.BrushStyle.NoBrush)
        p.setPen(pen_for(obj))
        p.drawPath(qpath(obj))


def render(objs, w, h):
    from .document import new_image
    img = new_image(w, h)
    p = QPainter(img)
    paint(p, objs)
    p.end()
    return img


def transform(objs, t):
    """Alle punten en handvatten door een (affiene) transformatie halen."""
    for obj in objs:
        for nodes, _ in contours(obj):
            for n in nodes:
                for k in range(3):
                    if n[k] is not None:
                        q = t.map(QPointF(n[k][0], n[k][1]))
                        n[k] = [q.x(), q.y()]
        # lijnbreedte meeschalen (gemiddelde schaal; 1 bij verschuiven, draaien en spiegelen)
        s = (abs(t.m11() * t.m22() - t.m12() * t.m21())) ** 0.5
        obj["width"] = obj["width"] * s


def hit(obj, pt, tol):
    """Ligt pt op (de rand of de vulling van) dit object?"""
    path = qpath(obj)
    st = QPainterPathStroker()
    st.setWidth(max(obj.get("width", 1), 1) + 2 * tol)
    if st.createStroke(path).contains(pt):
        return True
    return is_closed(obj) and obj.get("fill") is not None and path.contains(pt)


def bounds(objs):
    r = QRectF()
    for obj in objs:
        r = r.united(qpath(obj).boundingRect().adjusted(-obj["width"], -obj["width"], obj["width"], obj["width"]))
    return r


def path_to_nodes(path: QPainterPath):
    """Een QPainterPath (bijvoorbeeld van een rechthoek of ovaal) omzetten in knooppunten per deelpad:
    [(nodes, closed), ...] met nodes zoals de Pen ze gebruikt."""
    out = []
    nodes = None
    i = 0
    count = path.elementCount()
    while i < count:
        e = path.elementAt(i)
        if e.type == QPainterPath.ElementType.MoveToElement:
            if nodes:
                out.append(nodes)
            nodes = [[QPointF(e.x, e.y), None, None]]
            i += 1
        elif e.type == QPainterPath.ElementType.LineToElement:
            nodes.append([QPointF(e.x, e.y), None, None])
            i += 1
        else:  # CurveTo + 2 x CurveToData
            c1 = QPointF(e.x, e.y)
            c2e, end = path.elementAt(i + 1), path.elementAt(i + 2)
            nodes[-1][2] = c1
            nodes.append([QPointF(end.x, end.y), QPointF(c2e.x, c2e.y), None])
            i += 3
    if nodes:
        out.append(nodes)
    result = []
    for n in out:
        closed = len(n) > 2 and abs(n[0][0].x() - n[-1][0].x()) < 1e-6 and abs(n[0][0].y() - n[-1][0].y()) < 1e-6
        if closed:  # laatste punt valt samen met het eerste: samenvoegen
            last = n.pop()
            n[0][1] = last[1]
        result.append((n, closed))
    return result


def object_from_path(path: QPainterPath, stroke, fill, width, **style):
    """Vectorobject uit een QPainterPath (alle deelpaden als contouren van één samengesteld object)."""
    parts = path_to_nodes(path)
    if not parts:
        return None
    nodes, closed = parts[0]
    obj = make_object(nodes, closed, stroke, fill, width, **style)
    if len(parts) > 1:
        obj["more"] = [{"nodes": [[_lst(n[0]), _lst(n[1]), _lst(n[2])] for n in nd], "closed": cl}
                       for nd, cl in parts[1:]]
    return obj

