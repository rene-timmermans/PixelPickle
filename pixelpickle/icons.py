"""Eigen lijniconen voor de werkbalken: allemaal in dezelfde stijl en op hetzelfde raster van 24 x 24,
getekend in één kleur (standaard de accentkleur van het thema). Zo zien de gereedschappen er gelijk uit,
op een licht en een donker thema, en zijn ze niet afhankelijk van emoji uit het lettertype.

Elke tekenfunctie krijgt een QPainter die al geschaald is naar het raster van 24 en een pen in de
iconkleur. 'fill' is dezelfde kleur, voor dichte vlakjes."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication

P = QPointF
SIZES = (16, 20, 24, 32, 48)


def icon_color():
    """Accentkleur van het thema (dezelfde als de pijlknop van een te volle werkbalk)."""
    pal = QApplication.palette()
    c = QColor(pal.highlight().color())
    # te donker of te licht ten opzichte van de achtergrond: wat bijstellen zodat het zichtbaar blijft
    bg = pal.window().color()
    if abs(c.lightness() - bg.lightness()) < 70:
        c = c.lighter(150) if bg.lightness() < 128 else c.darker(150)
    return c


def _path(*pts, close=False):
    path = QPainterPath(P(*pts[0]))
    for x, y in pts[1:]:
        path.lineTo(x, y)
    if close:
        path.closeSubpath()
    return path


def _arrowhead(p, tip, angle_deg, size=3.5):
    a = math.radians(angle_deg)
    for d in (150, -150):
        b = a + math.radians(d)
        p.drawLine(P(*tip), P(tip[0] + size * math.cos(b), tip[1] + size * math.sin(b)))


# ---------------------------------------------------------------- gereedschappen
def pan(p, fill):
    for x, top in ((8, 6), (11, 4), (14, 4.5), (17, 7)):
        p.drawLine(P(x, top), P(x, 12.5))
    path = QPainterPath(P(5, 12))
    path.lineTo(8, 15)
    path.lineTo(8, 12.5)
    path.moveTo(17, 12.5)
    path.cubicTo(P(17.5, 17), P(16, 21), P(12, 21))
    path.cubicTo(P(9, 21), P(7, 19), P(5, 15.5))
    path.lineTo(4, 13)
    p.drawPath(path)


def zoom(p, fill):
    p.drawEllipse(P(10, 10), 6, 6)
    pen = p.pen()
    pen.setWidthF(pen.widthF() * 1.6)
    p.setPen(pen)
    p.drawLine(P(14.5, 14.5), P(20, 20))


def dropper(p, fill):
    p.drawLine(P(5, 19), P(14, 10))
    p.drawLine(P(11.5, 7.5), P(16.5, 12.5))
    p.setBrush(fill)
    p.drawEllipse(P(17, 7), 3, 3)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(P(5, 19), P(3.5, 20.5))


def move(p, fill):
    p.drawLine(P(12, 3), P(12, 21))
    p.drawLine(P(3, 12), P(21, 12))
    for tip, ang in (((12, 3), -90), ((12, 21), 90), ((3, 12), 180), ((21, 12), 0)):
        _arrowhead(p, tip, ang, 3)


def pick(p, fill):
    p.setBrush(fill)
    p.drawPath(_path((6, 3), (6, 19), (10, 15), (13, 21), (15.5, 20), (12.5, 14), (18, 14), close=True))
    p.setBrush(Qt.BrushStyle.NoBrush)


def select_rect(p, fill):
    pen = p.pen()
    pen.setDashPattern([2, 1.6])
    p.setPen(pen)
    p.drawRect(QRectF(4, 6, 16, 12))


def lasso(p, fill):
    p.drawEllipse(P(13.5, 8.5), 7.5, 5)
    tail = QPainterPath(P(8.5, 12.3))
    tail.cubicTo(P(5.5, 15), P(9.5, 17), P(7.5, 19))
    tail.cubicTo(P(6, 20.5), P(4.5, 21), P(3.5, 22))
    p.drawPath(tail)


def wand(p, fill):
    pen = p.pen()
    pen.setWidthF(pen.widthF() * 1.4)
    p.setPen(pen)
    p.drawLine(P(4, 20), P(14, 10))
    pen.setWidthF(pen.widthF() / 1.4)
    p.setPen(pen)
    cx, cy = 17.5, 6.5
    for a in range(0, 360, 45):
        r0, r1 = (1.2, 4) if a % 90 == 0 else (1.2, 2.6)
        b = math.radians(a)
        p.drawLine(P(cx + r0 * math.cos(b), cy + r0 * math.sin(b)), P(cx + r1 * math.cos(b), cy + r1 * math.sin(b)))


def brush(p, fill):
    p.drawLine(P(20, 4), P(12, 12))
    p.setBrush(fill)
    tip = QPainterPath(P(11, 11))
    tip.cubicTo(P(14, 13), P(13, 16), P(10, 17))
    tip.cubicTo(P(8, 18.5), P(6, 19), P(4, 20.5))
    tip.cubicTo(P(5, 18), P(5.5, 15.5), P(7, 13.5))
    tip.cubicTo(P(8, 12), P(9.5, 10.5), P(11, 11))
    p.drawPath(tip)
    p.setBrush(Qt.BrushStyle.NoBrush)


def airbrush(p, fill):
    p.drawRoundedRect(QRectF(11, 8, 8, 13), 2, 2)
    p.drawLine(P(13, 8), P(13, 5.5))
    p.drawLine(P(13, 5.5), P(17, 5.5))
    p.setBrush(fill)
    p.setPen(Qt.PenStyle.NoPen)
    for x, y in ((8, 4), (6, 7), (8.5, 8), (4, 5), (5, 10), (3, 8)):
        p.drawEllipse(P(x, y), 0.9, 0.9)


def eraser(p, fill):
    p.drawPath(_path((4, 15), (13, 6), (20, 13), (11, 22), (7, 22), close=True))
    p.drawLine(P(8.5, 10.5), P(15.5, 17.5))
    p.drawLine(P(11, 22), P(20, 22))


def lighten_darken(p, fill):
    p.drawEllipse(P(12, 12), 8, 8)
    p.setBrush(fill)
    path = QPainterPath(P(12, 4))
    path.arcTo(QRectF(4, 4, 16, 16), 90, 180)
    path.closeSubpath()
    p.drawPath(path)


def _lollipop(p, fill, solid):
    # rond schijfje op een rechte steel (zoals de klassieke tegenhouden/doordrukken-iconen)
    p.drawLine(P(12, 13.5), P(12, 21.5))
    if solid:
        p.setBrush(fill)
    p.drawEllipse(P(12, 8), 5.5, 5.5)


def dodge(p, fill):
    _lollipop(p, fill, False)


def burn(p, fill):
    _lollipop(p, fill, True)


def smudge(p, fill):
    # vinger die schuin over het vlak veegt, met veegsporen erachter
    p.save()
    p.translate(14, 10)
    p.rotate(40)
    path = QPainterPath()
    path.addRoundedRect(QRectF(-3, -8, 6, 15), 3, 3)
    p.drawPath(path)
    p.drawArc(QRectF(-1.8, -6.8, 3.6, 3.2), 0, 180 * 16)
    p.restore()
    wave = QPainterPath(P(3, 21))
    wave.cubicTo(P(5, 18.5), P(7, 20.5), P(9, 18))
    p.drawPath(wave)
    wave = QPainterPath(P(3, 16.5))
    wave.cubicTo(P(4.5, 14.5), P(6, 16), P(7.5, 14))
    p.drawPath(wave)


def push(p, fill):
    p.drawRoundedRect(QRectF(3, 9, 12, 6), 3, 3)
    p.drawLine(P(15, 12), P(21, 12))
    _arrowhead(p, (21, 12), 0, 3)


def soften(p, fill):
    pen = p.pen()
    pen.setDashPattern([1.2, 1.6])
    p.setPen(pen)
    p.drawEllipse(P(12, 12), 8, 8)
    pen.setStyle(Qt.PenStyle.SolidLine)
    p.setPen(pen)
    p.drawEllipse(P(12, 12), 3.5, 3.5)


def sharpen(p, fill):
    p.drawEllipse(P(12, 12), 8, 8)
    p.setBrush(fill)
    p.drawEllipse(P(12, 12), 3.5, 3.5)


def emboss(p, fill):
    p.drawRect(QRectF(4, 4, 16, 16))
    p.drawLine(P(4, 20), P(20, 4))
    p.setBrush(fill)
    p.drawPath(_path((20, 4), (20, 20), (4, 20), close=True))


def saturation(p, fill):
    for r in (8.5, 6, 3.5):
        p.drawArc(QRectF(12 - r, 17 - r, 2 * r, 2 * r), 0, 180 * 16)
    p.drawLine(P(2.5, 17), P(21.5, 17))


def hue(p, fill):
    path = QPainterPath(P(12, 3.5))
    path.cubicTo(P(20, 3.5), P(22, 10), P(19.5, 13))
    path.cubicTo(P(17.5, 15), P(15, 13), P(14, 15.5))
    path.cubicTo(P(13, 18), P(16, 20.5), P(12, 20.5))
    path.cubicTo(P(5, 20.5), P(2.5, 15), P(2.5, 11.5))
    path.cubicTo(P(2.5, 7), P(6.5, 3.5), P(12, 3.5))
    p.drawPath(path)
    p.setBrush(fill)
    for x, y in ((7, 9), (11.5, 7), (16, 8.5), (6.5, 14)):
        p.drawEllipse(P(x, y), 1.3, 1.3)


def target(p, fill):
    for r in (8.5, 5, 1.5):
        p.drawEllipse(P(12, 12), r, r)


def replace(p, fill):
    p.drawArc(QRectF(4, 4, 16, 16), 30 * 16, 150 * 16)
    p.drawArc(QRectF(4, 4, 16, 16), 210 * 16, 150 * 16)
    _arrowhead(p, (18.9, 8), -60, 3)
    _arrowhead(p, (5.1, 16), 120, 3)


def scratch(p, fill):
    p.drawRoundedRect(QRectF(3, 8, 18, 10), 3, 3)
    p.setBrush(fill)
    p.setPen(Qt.PenStyle.NoPen)
    for x, y in ((7, 11.5), (11, 14.5), (15, 11), (17.5, 15)):
        p.drawEllipse(P(x, y), 1.1, 1.1)


def clone(p, fill):
    p.drawEllipse(P(12, 6), 3, 3)
    p.drawLine(P(12, 9), P(12, 13))
    p.drawRoundedRect(QRectF(5, 13, 14, 4), 1.5, 1.5)
    p.drawLine(P(6, 20.5), P(18, 20.5))


def fill_tool(p, fill):
    p.drawPath(_path((4, 11), (11, 4), (19, 12), (12, 19), close=True))
    p.drawLine(P(8, 8), P(5, 5))
    p.setBrush(fill)
    drop = QPainterPath(P(20, 15))
    drop.cubicTo(P(22, 18), P(22, 20.5), P(20, 20.5))
    drop.cubicTo(P(18, 20.5), P(18, 18), P(20, 15))
    p.drawPath(drop)


def crayon(p, fill):
    p.drawPath(_path((17, 3), (21, 7), (9, 19), (5, 15), close=True))
    p.setBrush(fill)
    p.drawPath(_path((5, 15), (9, 19), (3, 21), close=True))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(P(14, 6), P(18, 10))


def eye(p, fill):
    path = QPainterPath(P(2.5, 12))
    path.cubicTo(P(7, 5), P(17, 5), P(21.5, 12))
    path.cubicTo(P(17, 19), P(7, 19), P(2.5, 12))
    p.drawPath(path)
    p.setBrush(fill)
    p.drawEllipse(P(12, 12), 3, 3)


def straighten(p, fill):
    p.drawPath(_path((4, 20), (20, 20), (4, 4), close=True))
    p.drawPath(_path((8, 16.5), (12.5, 16.5), (8, 12), close=True))
    for k in range(3):
        x = 9 + k * 3.5
        p.drawLine(P(x, 20), P(x, 18.3))


def perspective(p, fill):
    # schuine vierhoek met hoekgrepen en een hulplijn: rechttrekken van perspectief
    p.drawPath(_path((7, 5), (17, 5), (21, 19), (3, 19), close=True))
    p.drawLine(P(12, 5), P(12, 19))
    p.setBrush(fill)
    for x, y in ((7, 5), (17, 5), (21, 19), (3, 19)):
        p.drawRect(QRectF(x - 1.6, y - 1.6, 3.2, 3.2))
    p.setBrush(Qt.BrushStyle.NoBrush)


def scratch_remover(p, fill):
    # schuin kadertje over een kronkelige kras
    p.save()
    p.translate(12, 12)
    p.rotate(-35)
    p.drawRoundedRect(QRectF(-9.5, -3.5, 19, 7), 1.5, 1.5)
    path = QPainterPath(P(-7, 0.8))
    path.cubicTo(P(-4, -2), P(-2, 2.5), P(0.5, 0))
    path.cubicTo(P(3, -2.5), P(5, 2), P(7, -0.5))
    p.drawPath(path)
    p.restore()


def _stick(p, fill, length, width, tip, band=False):
    """Schuin staand stiftje (krijt, pastel, kleurkrijt, potlood) met de punt linksonder."""
    p.save()
    p.translate(13, 11)
    p.rotate(-45)
    h = width / 2
    body = QPainterPath(P(-length / 2, -h))
    body.lineTo(length / 2, -h)
    body.lineTo(length / 2, h)
    body.lineTo(-length / 2, h)
    if tip:
        body.lineTo(-length / 2 - tip, 0)
    body.closeSubpath()
    p.drawPath(body)
    if band:
        p.drawLine(P(length / 6, -h), P(length / 6, h))
        p.drawLine(P(length / 6 + 2.5, -h), P(length / 6 + 2.5, h))
    p.restore()


def oil(p, fill):
    # platte kwast met een klodder verf
    p.save()
    p.translate(14, 10)
    p.rotate(-45)
    p.drawLine(P(2, 0), P(10, 0))
    p.drawRoundedRect(QRectF(-3, -3, 5, 6), 1, 1)
    p.setBrush(fill)
    tuft = QPainterPath(P(-3, -3.5))
    tuft.lineTo(-9, -3)
    tuft.cubicTo(P(-11, -1), P(-11, 1), P(-9, 3))
    tuft.lineTo(-3, 3.5)
    tuft.closeSubpath()
    p.drawPath(tuft)
    p.restore()
    p.setBrush(fill)
    p.drawEllipse(P(5.5, 19.5), 2.6, 1.6)


def chalk(p, fill):
    _stick(p, fill, 13, 6, 0)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(fill)
    for x, y in ((3, 21), (5.5, 20), (8, 21.5), (4.5, 18), (7, 18.5)):
        p.drawEllipse(P(x, y), 0.9, 0.9)


def pastel(p, fill):
    _stick(p, fill, 10, 6.5, 1.5)
    wave = QPainterPath(P(2.5, 21))
    wave.cubicTo(P(5, 18), P(7, 22.5), P(10, 20))
    p.drawPath(wave)


def crayon_wax(p, fill):
    _stick(p, fill, 14, 5.5, 3.5, band=True)


def pencil(p, fill):
    _stick(p, fill, 15, 4, 4.5)
    p.setBrush(fill)
    p.save()
    p.translate(13, 11)
    p.rotate(-45)
    p.drawPath(_path((-7.5 - 3.2, -0.9), (-7.5 - 4.5, 0), (-7.5 - 3.2, 0.9), close=True))
    p.restore()


def makeover(p, fill):
    # lippenstift met een glinstering
    p.save()
    p.translate(11, 13)
    p.rotate(-30)
    p.drawRect(QRectF(-3.5, 1, 7, 8))
    p.drawLine(P(-3.5, 3.5), P(3.5, 3.5))
    tip = QPainterPath(P(-2.5, 1))
    tip.lineTo(-2.5, -5)
    tip.lineTo(2.5, -8)
    tip.lineTo(2.5, 1)
    p.setBrush(fill)
    p.drawPath(tip)
    p.restore()
    p.setBrush(Qt.BrushStyle.NoBrush)
    for cx, cy, r in ((18.5, 6, 2.6), (20.5, 12.5, 1.6)):
        p.drawLine(P(cx - r, cy), P(cx + r, cy))
        p.drawLine(P(cx, cy - r), P(cx, cy + r))


def object_remover(p, fill):
    # gestippelde lijn om een vorm, met een bronkader ernaast
    pen = p.pen()
    dashed = QPen(pen)
    dashed.setStyle(Qt.PenStyle.DashLine)
    dashed.setDashPattern([2, 1.6])
    p.setPen(dashed)
    blob = QPainterPath(P(9, 4))
    blob.cubicTo(P(15, 3.5), P(16, 10), P(14, 13))
    blob.cubicTo(P(12, 17), P(4, 17), P(3.5, 11))
    blob.cubicTo(P(3, 7), P(5, 4.5), P(9, 4))
    p.drawPath(blob)
    p.setPen(pen)
    p.drawRect(QRectF(13.5, 13.5, 7.5, 7.5))
    _arrowhead(p, (13.5, 13.5), -135, 3)
    p.drawLine(P(13.5, 13.5), P(10.5, 10.5))


def marker(p, fill):
    # viltstift met schuine punt en een doorschijnende streep
    p.save()
    p.translate(13.5, 10.5)
    p.rotate(-45)
    p.drawRoundedRect(QRectF(-4, -3.5, 13, 7), 1.5, 1.5)
    p.drawLine(P(4, -3.5), P(4, 3.5))
    nib = QPainterPath(P(-4, -2.5))
    nib.lineTo(-8, -1.5)
    nib.lineTo(-8, 1.8)
    nib.lineTo(-4, 2.5)
    p.setBrush(fill)
    p.drawPath(nib)
    p.restore()
    c = QColor(fill.color() if isinstance(fill, QBrush) else fill)
    c.setAlpha(110)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QRectF(2, 18.5, 11, 3.5), 1.5, 1.5)


def knife(p, fill):
    # paletmes: handvat, geknikte steel en een plat, rond blad
    p.drawLine(P(20.5, 3.5), P(15.5, 8.5))
    p.save()
    p.translate(19, 5)
    p.rotate(-45)
    p.drawRoundedRect(QRectF(-1.5, -2, 7, 4), 1.5, 1.5)
    p.restore()
    p.drawLine(P(15.5, 8.5), P(13, 9.5))
    blade = QPainterPath(P(13, 9.5))
    blade.lineTo(5, 17.5)
    blade.cubicTo(P(3, 19.5), P(3.5, 21), P(5.5, 20.5))
    blade.lineTo(14.5, 12)
    blade.closeSubpath()
    p.setBrush(fill)
    p.drawPath(blade)


def warp(p, fill):
    # spiraal: pixels draaien en vervormen
    path = QPainterPath(P(12, 12))
    for k in range(1, 60):
        a = k * 0.3
        r = 0.16 * k
        path.lineTo(12 + r * math.cos(a), 12 + r * math.sin(a))
    p.drawPath(path)


def mesh(p, fill):
    # gebogen raster
    for k in (0, 1, 2):
        y = 5 + k * 7
        path = QPainterPath(P(3, y))
        path.cubicTo(P(9, y - 3 + k * 2), P(15, y + 3 - k), P(21, y))
        p.drawPath(path)
        x = 5 + k * 7
        path = QPainterPath(P(x, 3))
        path.cubicTo(P(x + 3 - k * 2, 9), P(x - 3 + k, 15), P(x, 21))
        p.drawPath(path)


def crop(p, fill):
    p.drawPolyline(QPolygonF([P(7, 3), P(7, 17), P(21, 17)]))
    p.drawPolyline(QPolygonF([P(3, 7), P(17, 7), P(17, 21)]))


def rect(p, fill):
    p.drawRect(QRectF(3.5, 6, 17, 12))


def ellipse(p, fill):
    p.drawEllipse(P(12, 12), 9, 6.5)


def star(p, fill):
    pts = []
    for k in range(10):
        r = 9 if k % 2 == 0 else 4
        a = math.radians(-90 + k * 36)
        pts.append((12 + r * math.cos(a), 12.5 + r * math.sin(a)))
    p.drawPath(_path(*pts, close=True))


def bubble(p, fill):
    path = QPainterPath()
    path.addRoundedRect(QRectF(3, 4, 18, 12), 4, 4)
    p.drawPath(path)
    p.drawPolyline(QPolygonF([P(8, 16), P(7, 21), P(12, 16)]))


def pen_tool(p, fill):
    p.drawPath(_path((12, 21), (6, 12), (12, 3), (18, 12), close=True))
    p.drawLine(P(12, 21), P(12, 13))
    p.setBrush(fill)
    p.drawEllipse(P(12, 11.5), 1.4, 1.4)


def text(p, fill):
    p.drawPolyline(QPolygonF([P(5, 20), P(12, 4), P(19, 20)]))
    p.drawLine(P(8, 14), P(16, 14))


# ---------------------------------------------------------------- standaardwerkbalk
def new_doc(p, fill):
    p.drawPath(_path((5, 3), (14, 3), (19, 8), (19, 21), (5, 21), close=True))
    p.drawPolyline(QPolygonF([P(14, 3), P(14, 8), P(19, 8)]))


def open_doc(p, fill):
    p.drawPath(_path((3, 19), (3, 5), (9, 5), (11, 7), (18, 7), (18, 10)))
    p.drawPath(_path((3, 19), (6.5, 10), (21.5, 10), (18, 19), close=True))


def save(p, fill):
    p.drawPath(_path((4, 4), (17, 4), (20, 7), (20, 20), (4, 20), close=True))
    p.drawRect(QRectF(8, 4, 8, 5))
    p.drawRect(QRectF(7, 13, 10, 7))


def save_as(p, fill):
    p.drawPath(_path((4, 4), (17, 4), (20, 7), (20, 11)))
    p.drawPath(_path((4, 4), (4, 20), (12, 20)))
    p.drawRect(QRectF(8, 4, 8, 5))
    p.drawLine(P(14, 21), P(21, 14))
    p.drawLine(P(19, 12.5), P(22.5, 16))


def printer(p, fill):
    p.drawRect(QRectF(7, 3, 10, 6))
    p.drawRoundedRect(QRectF(3, 9, 18, 8), 1.5, 1.5)
    p.drawRect(QRectF(7, 14, 10, 7))


def _curved(p, left):
    path = QPainterPath()
    if left:
        path.moveTo(19, 17)
        path.cubicTo(P(19, 9), P(13, 7), P(6, 9))
        p.drawPath(path)
        _arrowhead(p, (5.5, 9.2), 175, 4)
    else:
        path.moveTo(5, 17)
        path.cubicTo(P(5, 9), P(11, 7), P(18, 9))
        p.drawPath(path)
        _arrowhead(p, (18.5, 9.2), 5, 4)


def undo(p, fill):
    _curved(p, True)


def redo(p, fill):
    _curved(p, False)


def resize(p, fill):
    p.drawLine(P(5, 19), P(19, 5))
    _arrowhead(p, (19, 5), -45, 4)
    _arrowhead(p, (5, 19), 135, 4)
    p.drawRect(QRectF(3, 3, 18, 18))


def _rotate(p, clockwise):
    r = 7
    if clockwise:
        p.drawArc(QRectF(12 - r, 12 - r, 2 * r, 2 * r), 100 * 16, 260 * 16)
        tip = (12 + r * math.cos(math.radians(100)), 12 - r * math.sin(math.radians(100)))
        _arrowhead(p, (tip[0] + 2.2, tip[1] + 0.4), 10, 3.5)
        p.drawLine(P(*tip), P(tip[0] + 2.2, tip[1] + 0.4))
    else:
        p.drawArc(QRectF(12 - r, 12 - r, 2 * r, 2 * r), 80 * 16, -260 * 16)
        tip = (12 + r * math.cos(math.radians(80)), 12 - r * math.sin(math.radians(80)))
        _arrowhead(p, (tip[0] - 2.2, tip[1] + 0.4), 170, 3.5)
        p.drawLine(P(*tip), P(tip[0] - 2.2, tip[1] + 0.4))


def rotate_cw(p, fill):
    _rotate(p, True)


def rotate_ccw(p, fill):
    _rotate(p, False)



# ---------------------------------------------------------------- paletten
def layer_new(p, fill):
    for y in (6, 10.5, 15):
        p.drawLine(P(3, y), P(13, y))
    p.drawRect(QRectF(3, 4, 10, 13))
    p.drawLine(P(18, 12), P(18, 22))
    p.drawLine(P(13, 17), P(23, 17))


def delete(p, fill):
    p.drawLine(P(6, 6), P(18, 18))
    p.drawLine(P(18, 6), P(6, 18))


def gear(p, fill):
    path = QPainterPath()
    n = 8
    for k in range(2 * n):
        a = math.radians(k * 180 / n - 90)
        r = 9 if k % 2 == 0 else 6.8
        # elke tand is een klein plateau: twee punten op dezelfde straal
        for da in (-7, 7):
            b = a + math.radians(da)
            pt = P(12 + r * math.cos(b), 12 + r * math.sin(b))
            path.moveTo(pt) if path.elementCount() == 0 else path.lineTo(pt)
    path.closeSubpath()
    p.drawPath(path)
    p.drawEllipse(P(12, 12), 2.8, 2.8)


def up(p, fill):
    p.drawPolyline(QPolygonF([P(5, 15), P(12, 8), P(19, 15)]))


def down(p, fill):
    p.drawPolyline(QPolygonF([P(5, 9), P(12, 16), P(19, 9)]))


def merge_down(p, fill):
    p.drawLine(P(12, 3), P(12, 14))
    _arrowhead(p, (12, 14), 90, 4)
    p.drawLine(P(4, 19.5), P(20, 19.5))


def opacity(p, fill):
    p.drawRect(QRectF(4, 4, 16, 16))
    p.setBrush(fill)
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(4):
        for j in range(4):
            if (i + j) % 2 == 0:
                p.drawRect(QRectF(4 + i * 4, 4 + j * 4, 4, 4))


def lock(p, fill):
    p.drawRoundedRect(QRectF(5, 11, 14, 10), 1.5, 1.5)
    p.drawArc(QRectF(8, 4, 8, 12), 0, 180 * 16)
    p.drawLine(P(8, 10), P(8, 11))
    p.drawLine(P(16, 10), P(16, 11))
    p.drawLine(P(12, 15), P(12, 17))


def eye_off(p, fill):
    path = QPainterPath(P(2.5, 12))
    path.cubicTo(P(7, 17), P(17, 17), P(21.5, 12))
    p.drawPath(path)
    p.drawLine(P(7, 15.5), P(5.5, 18))
    p.drawLine(P(12, 16.8), P(12, 19.5))
    p.drawLine(P(17, 15.5), P(18.5, 18))


def folder(p, fill):
    p.drawPath(_path((3, 19), (3, 5), (9, 5), (11, 7.5), (21, 7.5), (21, 19), close=True))
    p.drawLine(P(3, 10), P(21, 10))


def mask(p, fill):
    p.drawRect(QRectF(3.5, 3.5, 17, 17))
    p.setBrush(fill)
    p.drawEllipse(P(12, 12), 5, 5)


def chevron_right(p, fill):
    p.drawPolyline(QPolygonF([P(9, 5), P(16, 12), P(9, 19)]))


def chevron_down(p, fill):
    p.drawPolyline(QPolygonF([P(5, 9), P(12, 16), P(19, 9)]))


def solid_color(p, fill):
    p.setBrush(fill)
    p.drawEllipse(P(12, 12), 7, 7)


def gradient(p, fill):
    p.drawRect(QRectF(4, 4, 16, 16))
    p.setBrush(fill)
    p.setPen(Qt.PenStyle.NoPen)
    for k, w in enumerate((4, 3, 2, 1)):
        p.drawRect(QRectF(4 + k * 4, 4, w, 16))


def pattern(p, fill):
    p.setBrush(fill)
    for i in range(2):
        for j in range(2):
            p.drawRoundedRect(QRectF(4.5 + i * 8.5, 4.5 + j * 8.5, 6.5, 6.5), 1, 1)


def none(p, fill):
    p.drawEllipse(P(12, 12), 8, 8)
    p.drawLine(P(6.3, 17.7), P(17.7, 6.3))


def link(p, fill):
    p.save()
    p.translate(12, 12)
    p.rotate(-45)
    p.drawRoundedRect(QRectF(-9, -3.5, 10, 7), 3.5, 3.5)
    p.drawRoundedRect(QRectF(-1, -3.5, 10, 7), 3.5, 3.5)
    p.restore()


def swap(p, fill):
    p.drawLine(P(8, 4), P(8, 19))
    _arrowhead(p, (8, 4), -90, 3.5)
    p.drawLine(P(16, 5), P(16, 20))
    _arrowhead(p, (16, 20), 90, 3.5)

ICONS = {
    "✋": pan, "🔍": zoom, "💧": dropper, "✥": move, "➚": pick, "⬚": select_rect, "➰": lasso, "✨": wand,
    "🖌": brush, "💨": airbrush, "⌫": eraser, "◐": lighten_darken, "◯": dodge, "●": burn, "☝": smudge,
    "👉": push, "◌": soften, "◉": sharpen, "▦": emboss, "🌈": saturation, "🎨": hue, "🎯": target,
    "🔁": replace, "🧽": scratch, "⎘": clone, "🪣": fill_tool, "🖍": crayon, "👁": eye, "📐": straighten, "⏢": perspective, "〰": scratch_remover, "oil": oil, "chalk": chalk, "pastel": pastel, "crayon_wax": crayon_wax, "pencil": pencil, "warp": warp, "mesh": mesh, "makeover": makeover, "object_remover": object_remover, "marker": marker, "knife": knife,
    "⛶": crop, "▭": rect, "⬭": ellipse, "✶": star, "💬": bubble, "✒": pen_tool, "A": text,
    # standaardwerkbalk
    "new": new_doc, "open": open_doc, "💾": save, "save_as": save_as, "🖨": printer, "↶": undo, "↷": redo,
    "⤢": resize, "↻": rotate_cw, "↺": rotate_ccw,
    # paletten
    "layer_new": layer_new, "delete": delete, "gear": gear, "up": up, "down": down, "merge_down": merge_down,
    "opacity": opacity, "lock": lock, "eye": eye, "eye_off": eye_off, "folder": folder, "mask": mask,
    "adjust": lighten_darken, "chevron_right": chevron_right, "chevron_down": chevron_down,
    "color": solid_color, "gradient": gradient, "pattern": pattern, "none": none, "swap": swap, "link": link,
}


def set_button(button, name, size=16, tooltip=None):
    """Knop een getekend icoon geven in plaats van een teken."""
    ic = icon(name)
    if ic is None:
        return
    button.setText("")
    button.setIcon(ic)
    from PySide6.QtCore import QSize
    button.setIconSize(QSize(size, size))
    if tooltip:
        button.setToolTip(tooltip)


def label_pixmap(name, size=16, color=None):
    return render(name, size, QColor(color) if color is not None else icon_color())


def text_color():
    """Tekstkleur van het thema: voor iconen op een plek die zelf de accentkleur kan krijgen
    (zoals een geselecteerde laag), zodat ze daar niet wegvallen."""
    return QApplication.palette().windowText().color()


def render(name, size, color, enabled=True):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if not enabled:
        p.setOpacity(0.35)
    p.scale(size / 24, size / 24)
    # iets dikkere lijnen bij kleine iconen, zodat ze even zwaar ogen
    width = 1.7 if size >= 24 else 1.9 if size >= 20 else 2.1
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    ICONS[name](p, QBrush(color))
    p.end()
    return pm


def icon(name, enabled=True, color=None):
    """QIcon van een getekend icoon, of None als er geen tekening voor die naam is."""
    if name not in ICONS:
        return None
    c = QColor(color) if color is not None else icon_color()
    ic = QIcon()
    for s in SIZES:
        ic.addPixmap(render(name, s, c, enabled))
    return ic
