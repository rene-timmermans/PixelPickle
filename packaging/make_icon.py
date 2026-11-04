"""Tekent het Pigment icoon (penseel op een palet) als PNG in meerdere formaten."""
import sys
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen

app = QGuiApplication(sys.argv)
out = sys.argv[1]
for size in (16, 32, 48, 64, 128, 256):
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 256, size / 256)
    # palet
    pal = QPainterPath()
    pal.addEllipse(QRectF(16, 40, 210, 180))
    hole = QPainterPath()
    hole.addEllipse(QRectF(150, 150, 34, 30))
    pal = pal.subtracted(hole)
    g = QLinearGradient(0, 40, 0, 220)
    g.setColorAt(0, QColor(236, 200, 140))
    g.setColorAt(1, QColor(196, 150, 90))
    p.setPen(QPen(QColor(120, 80, 40), 6))
    p.setBrush(QBrush(g))
    p.drawPath(pal)
    for (x, y), c in zip([(62, 90), (110, 72), (160, 88), (60, 145), (100, 170)],
                         ["#e53935", "#fdd835", "#43a047", "#1e88e5", "#8e24aa"]):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c))
        p.drawEllipse(QPointF(x, y), 20, 17)
    # penseel
    p.save()
    p.translate(150, 140)
    p.rotate(-40)
    p.setPen(QPen(QColor(60, 40, 20), 4))
    p.setBrush(QColor(140, 90, 40))
    p.drawRoundedRect(QRectF(-9, -120, 18, 120), 8, 8)
    p.setBrush(QColor(190, 190, 200))
    p.drawRect(QRectF(-11, 0, 22, 26))
    tip = QPainterPath(QPointF(-11, 26))
    tip.cubicTo(-14, 60, 0, 80, 0, 92)
    tip.cubicTo(0, 80, 14, 60, 11, 26)
    p.setBrush(QColor(229, 57, 53))
    p.drawPath(tip)
    p.restore()
    p.end()
    img.save(f"{out}/pigment-{size}.png")
