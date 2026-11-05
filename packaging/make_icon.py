"""Tekent het PixelPickle icoon (een augurk van pixels) als PNG in meerdere formaten."""
import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

# 16 x 16 pixelkunst: . = leeg, D = donkergroen (rand), G = groen, L = lichtgroen, S = glans, B = bobbel
ART = [
    "................",
    "..........DDD...",
    "........DDGGGD..",
    ".......DGGLSGD..",
    "......DGGBLSLD..",
    ".....DGGGGLLGD..",
    "....DGGBGGGLD...",
    "...DGGGGGBGGD...",
    "...DGBGGGGGD....",
    "..DGGGGBGGGD....",
    "..DGGGGGGGD.....",
    ".DGGBGGGGD......",
    ".DGGGGGGD.......",
    ".DDGGGDD........",
    "..DDDD..........",
    "................",
]
COLORS = {"D": QColor(46, 94, 32), "G": QColor(104, 170, 60), "L": QColor(150, 205, 95),
          "S": QColor(220, 245, 190), "B": QColor(70, 130, 40)}

app = QGuiApplication(sys.argv)
out = sys.argv[1]
for size in (16, 32, 48, 64, 128, 256):
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    cell = size / 16
    for y, row in enumerate(ART):
        for x, ch in enumerate(row):
            if ch in COLORS:
                p.fillRect(QRectF(x * cell, y * cell, cell + 0.01, cell + 0.01), COLORS[ch])
    if size >= 48:  # fijne pixelrasterlijntjes geven het 'pixel' karakter
        p.setPen(QPen(QColor(0, 0, 0, 28), 1))
        for y, row in enumerate(ART):
            for x, ch in enumerate(row):
                if ch in COLORS:
                    p.drawRect(QRectF(x * cell, y * cell, cell, cell))
    p.end()
    img.save(f"{out}/pixelpickle-{size}.png")
