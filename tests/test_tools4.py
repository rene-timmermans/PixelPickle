"""Makeover, Object verwijderen, Markering en Paletmes:
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_tools4.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from pixelpickle.document import Document  # noqa: E402
from pixelpickle.mainwindow import MainWindow  # noqa: E402

w = MainWindow(); w.show()
LB, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton


def ev(kind, btn=LB):
    t = {"press": QEvent.Type.MouseButtonPress, "move": QEvent.Type.MouseMove, "release": QEvent.Type.MouseButtonRelease}[kind]
    return QMouseEvent(t, QPointF(), QPointF(), btn, LB if kind != "release" else NB, Qt.KeyboardModifier.NoModifier)


def stroke(cv, pts):
    t = w.tool
    t.press(cv, QPointF(*pts[0]), ev("press"))
    for q in pts[1:]:
        t.move(cv, QPointF(*q), ev("move"))
    t.release(cv, QPointF(*pts[-1]), ev("release"))
    app.processEvents()


def newdoc(color=QColor(200, 160, 130)):
    d = Document(160, 120, color)
    cv = w.add_document(d).canvas
    app.processEvents()
    return d, cv


for cid in (0xd070, 0xd083, 0xd136, 0xd137):
    assert w.tools[cid].available, hex(cid)
print("1 alle vier beschikbaar op de gereedschapsbalk")

# Makeover: vlek verwijderen
d, cv = newdoc()
p = QPainter(d.layers[0].image); p.setBrush(QColor(120, 40, 40)); p.setPen(Qt.PenStyle.NoPen)
p.drawEllipse(QPointF(50, 50), 4, 4); p.end()
w.select_tool(w.tools[0xd070]); w.opts["mk_mode"] = 0; w.opts["mk_size"] = 14; w.opts["mk_strength"] = 100
stroke(cv, [(50, 50)])
c = d.layers[0].image.pixelColor(50, 50)
assert abs(c.red() - 200) < 25 and abs(c.green() - 160) < 25, c.getRgb()
print("2 Makeover vlekken verwijderen: vlek opgevuld met de huidkleur", c.getRgb()[:3])

# Tandenborstel: gelige tand wordt witter, rode lip blijft
p = QPainter(d.layers[0].image); p.fillRect(90, 20, 20, 10, QColor(225, 205, 150)); p.fillRect(90, 30, 20, 10, QColor(190, 60, 70)); p.end()
w.opts["mk_mode"] = 1
stroke(cv, [(92, 25), (108, 25), (108, 35), (92, 35)])
tooth, lip = d.layers[0].image.pixelColor(100, 24), d.layers[0].image.pixelColor(100, 36)
assert tooth.hslSaturation() < 90 and tooth.lightness() > 190, tooth.getRgb()
assert lip.red() > 160 and lip.green() < 90, lip.getRgb()
print("3 Tandenborstel: tand witter", tooth.getRgb()[:3], "lip blijft", lip.getRgb()[:3])

# Zonnebruin: warmer en iets donkerder
w.opts["mk_mode"] = 3
before = d.layers[0].image.pixelColor(30, 100)
stroke(cv, [(20, 100), (40, 100)])
after = d.layers[0].image.pixelColor(30, 100)
assert after.lightness() < before.lightness() and 10 <= after.hslHue() <= 40, (before.getRgb(), after.getRgb())
print("4 Zonnebruin:", before.getRgb()[:3], "->", after.getRgb()[:3])

# Slanker maken: een verticale streep in het midden blijft, eentje opzij schuift naar het midden
d2, cv2 = newdoc(QColor(255, 255, 255))
p = QPainter(d2.layers[0].image); p.fillRect(40, 0, 2, 120, QColor(0, 0, 0)); p.fillRect(80, 0, 1, 120, QColor(255, 0, 0)); p.end()
w.opts["mk_mode"] = 4
w.tool.press(cv2, QPointF(80.5, 60), ev("press"))
row = [d2.layers[0].image.pixelColor(x, 60) for x in range(160)]
dark = [x for x, c in enumerate(row) if c.red() < 128]
red = [x for x, c in enumerate(row) if c.red() > 200 and c.green() < 100]
assert dark and dark[0] > 41 and red and abs(red[0] - 80) <= 1, (dark, red)
assert row[0] == QColor(255, 255, 255)
print("5 Slanker maken: zijkant schuift naar het midden", dark[:2], "midden blijft", red[:1])

# Object verwijderen: blauw blokje op een verloop verdwijnt naadloos
d3, cv3 = newdoc(QColor(255, 255, 255))
p = QPainter(d3.layers[0].image)
for x in range(160):
    p.fillRect(x, 0, 1, 120, QColor(60 + x, 120, 200 - x // 2))
p.fillRect(100, 50, 16, 16, QColor(0, 0, 255)); p.end()
w.select_tool(w.tools[0xd083]); w.opts["or_mode"] = 0
stroke(cv3, [(96, 46), (120, 46), (120, 70), (96, 70)])
assert w.opts["or_mode"] == 1 and w.tool.src is not None
w.tool.src = w.tool.src.translated(0, 0)  # standaard bron (links ernaast)
w.tool.apply()
c = d3.layers[0].image.pixelColor(108, 58)
expect = QColor(60 + 108, 120, 200 - 108 // 2)
assert abs(c.red() - expect.red()) < 12 and abs(c.blue() - expect.blue()) < 12, (c.getRgb(), expect.getRgb())
assert w.tool.poly == [] and w.opts["or_mode"] == 0
print("6 Object verwijderen: object weg, kleur sluit aan", c.getRgb()[:3], "verwacht", expect.getRgb()[:3])
# Enter past ook toe, Esc gooit weg
stroke(cv3, [(10, 10), (30, 10), (30, 30), (10, 30)])
assert w.tool.key(cv3, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
assert w.tool.poly == [] and w.tool.src is None
print("7 Esc gooit de omtrek weg")

# Markering: doorschijnend; tweede streek eroverheen wordt donkerder; binnen één streek niet
d4, cv4 = newdoc(QColor(255, 255, 255))
w.select_tool(w.tools[0xd136]); w.fg = QColor(255, 220, 0)
stroke(cv4, [(20, 40), (140, 40), (20, 40)])  # heen en terug in één streek
one = d4.layers[0].image.pixelColor(80, 40)
stroke(cv4, [(80, 10), (80, 70)])
two = d4.layers[0].image.pixelColor(80, 40)
assert one.blue() > 60 and one.blue() < 230, one.getRgb()
assert two.blue() < one.blue() - 20, (one.getRgb(), two.getRgb())
print("8 Markering: één laag", one.getRgb()[:3], "overlap donkerder", two.getRgb()[:3])

# Paletmes: dikke verf, smeert de kleur eronder mee
d5, cv5 = newdoc(QColor(255, 255, 255))
p = QPainter(d5.layers[0].image); p.fillRect(0, 0, 60, 120, QColor(0, 0, 200)); p.end()
w.select_tool(w.tools[0xd137]); w.fg = QColor(230, 30, 30)
stroke(cv5, [(20, 60), (60, 60), (120, 60)])
mid = d5.layers[0].image.pixelColor(110, 60)
assert mid != QColor(255, 255, 255) and mid.red() > 80, mid.getRgb()
print("9 Paletmes: verf aangebracht", mid.getRgb()[:3])

for x in (d, d2, d3, d4, d5):
    x.set_modified(False)
print("ALLES OK")
