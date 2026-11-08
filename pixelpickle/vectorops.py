"""Bewerkingen op hele vectorobjecten (menu Objecten en het snelmenu van vectorobjecten): uitlijnen,
verdelen, even groot maken, schikken en groeperen. Objecten zijn de dicts uit vectorlayer.py; een selectie
is een lijst indexen in layer.vector, in de volgorde waarin ze gekozen zijn (de eerste is de maatstaf bij
Even groot maken)."""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QTransform

from . import vectorlayer as V


def obj_bounds(obj) -> QRectF:
    return V.qpath(obj).boundingRect()


def sel_bounds(objs, sel) -> QRectF:
    r = QRectF()
    for i in sel:
        r = r.united(obj_bounds(objs[i]))
    return r


def _move(obj, dx, dy):
    if dx or dy:
        V.transform([obj], QTransform.fromTranslate(dx, dy))


def expand_groups(objs, sel):
    """Een gekozen object uit een groep neemt de hele groep mee (volgorde blijft)."""
    out = list(sel)
    groups = {objs[i].get("group") for i in sel if objs[i].get("group")}
    for i, o in enumerate(objs):
        if o.get("group") in groups and i not in out:
            out.append(i)
    return out


# ---------------------------------------------------------------- uitlijnen
ALIGN = ("top", "bottom", "left", "right", "vcenter", "hcenter", "canvas", "canvas_h", "canvas_v")


def align(objs, sel, how, canvas: QRectF):
    """Uitlijnen op de gezamenlijke omhullende (of op het doek). 'vcenter' = verticaal centreren
    (de middens op één horizontale lijn), 'hcenter' = horizontaal centreren (op één verticale lijn)."""
    if not sel:
        return
    ref = sel_bounds(objs, sel)
    for i in sel:
        b = obj_bounds(objs[i])
        dx = dy = 0.0
        if how == "top":
            dy = ref.top() - b.top()
        elif how == "bottom":
            dy = ref.bottom() - b.bottom()
        elif how == "left":
            dx = ref.left() - b.left()
        elif how == "right":
            dx = ref.right() - b.right()
        elif how == "vcenter":
            dy = ref.center().y() - b.center().y()
        elif how == "hcenter":
            dx = ref.center().x() - b.center().x()
        elif how in ("canvas", "canvas_h", "canvas_v"):
            # op het doek: de selectie als geheel centreren (onderlinge plaats blijft)
            if how in ("canvas", "canvas_h"):
                dx = canvas.center().x() - ref.center().x()
            if how in ("canvas", "canvas_v"):
                dy = canvas.center().y() - ref.center().y()
        _move(objs[i], dx, dy)


# ---------------------------------------------------------------- verdelen
DISTRIBUTE = ("v_top", "v_center", "v_bottom", "h_left", "h_center", "h_right", "h_space", "v_space")


def distribute(objs, sel, how):
    """Gelijke afstanden tussen de objecten; de buitenste twee blijven staan (minstens drie objecten)."""
    if len(sel) < 3:
        return False
    horizontal = how.startswith("h_")
    key = {"v_top": lambda b: b.top(), "v_center": lambda b: b.center().y(), "v_bottom": lambda b: b.bottom(),
           "h_left": lambda b: b.left(), "h_center": lambda b: b.center().x(), "h_right": lambda b: b.right(),
           "h_space": lambda b: b.left(), "v_space": lambda b: b.top()}[how]
    items = sorted(sel, key=lambda i: key(obj_bounds(objs[i])))
    bs = [obj_bounds(objs[i]) for i in items]
    if how in ("h_space", "v_space"):
        size = sum(b.width() if horizontal else b.height() for b in bs)
        span = (bs[-1].right() - bs[0].left()) if horizontal else (bs[-1].bottom() - bs[0].top())
        gap = (span - size) / (len(bs) - 1)
        pos = bs[0].left() if horizontal else bs[0].top()
        for i, b in zip(items, bs):
            cur = b.left() if horizontal else b.top()
            _move(objs[i], pos - cur if horizontal else 0, 0 if horizontal else pos - cur)
            pos += (b.width() if horizontal else b.height()) + gap
        return True
    first, last = key(bs[0]), key(bs[-1])
    step = (last - first) / (len(bs) - 1)
    for k, (i, b) in enumerate(zip(items, bs)):
        want = first + step * k
        d = want - key(b)
        _move(objs[i], d if horizontal else 0, 0 if horizontal else d)
    return True


# ---------------------------------------------------------------- even groot
def same_size(objs, sel, how):
    """Even groot als het eerst gekozen object: 'h' breedte, 'v' hoogte, 'both' beide (rond het eigen midden)."""
    if len(sel) < 2:
        return False
    ref = obj_bounds(objs[sel[0]])
    for i in sel[1:]:
        b = obj_bounds(objs[i])
        sx = ref.width() / b.width() if how in ("h", "both") and b.width() > 1e-6 else 1.0
        sy = ref.height() / b.height() if how in ("v", "both") and b.height() > 1e-6 else 1.0
        c = b.center()
        t = QTransform.fromTranslate(-c.x(), -c.y()) * QTransform.fromScale(sx, sy) * QTransform.fromTranslate(c.x(), c.y())
        w = objs[i]["width"]
        V.transform([objs[i]], t)
        objs[i]["width"] = w  # de lijn blijft even dik
    return True


# ---------------------------------------------------------------- schikken
def arrange(objs, sel, how):
    """Volgorde (stapeling) wijzigen: 'top' vooraan, 'up' één omhoog, 'down' één omlaag, 'bottom' achteraan.
    Geeft (nieuwe lijst, nieuwe selectie) terug."""
    chosen = [objs[i] for i in sorted(sel)]
    rest = [o for i, o in enumerate(objs) if i not in set(sel)]
    if how == "top":
        new = rest + chosen
    elif how == "bottom":
        new = chosen + rest
    else:
        new = list(objs)
        order = sorted(sel, reverse=(how == "up"))
        for i in order:
            j = i + 1 if how == "up" else i - 1
            if 0 <= j < len(new) and new[j] not in chosen:
                new[i], new[j] = new[j], new[i]
    ids = {id(o) for o in chosen}
    return new, [k for k, o in enumerate(new) if id(o) in ids]


# ---------------------------------------------------------------- groeperen
def group(objs, sel):
    if len(sel) < 2:
        return False
    gid = max([o.get("group", 0) for o in objs] + [0]) + 1
    for i in sel:
        objs[i]["group"] = gid
    return True


def ungroup(objs, sel):
    done = False
    for i in sel:
        if objs[i].pop("group", None) is not None:
            done = True
    return done
