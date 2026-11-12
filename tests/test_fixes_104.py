"""Verbeteringen na 1.0.3: spiegelen op zijn plek, Naar doel overgaan bouwt niet op, Ctrl = pipet bij penselen,
dekking in het lagenpalet met schuifbalk, compacte tabs in Materialen, selecties van één pixel breed:
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_fixes_104.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from pixelpickle import imageops as ops  # noqa: E402
from pixelpickle.document import Document, Layer, new_image  # noqa: E402
from pixelpickle.mainwindow import MainWindow  # noqa: E402
from pixelpickle.tools import SliderSpinBox  # noqa: E402

w = MainWindow(); w.show()
d = Document(200, 120, QColor(200, 150, 120)); cv = w.add_document(d).canvas; app.processEvents()
L, R = Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton


def ev(kind, btn=L, mods=Qt.KeyboardModifier.NoModifier):
    held = btn if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    return QMouseEvent(kind, QPointF(), QPointF(), btn, held, mods)


def stroke(tool, a, b, btn=L, mods=Qt.KeyboardModifier.NoModifier):
    tool.press(cv, QPointF(*a), ev(QEvent.Type.MouseButtonPress, btn, mods))
    tool.move(cv, QPointF(*b), ev(QEvent.Type.MouseMove, btn, mods))
    tool.release(cv, QPointF(*b), ev(QEvent.Type.MouseButtonRelease, btn, mods))
    app.processEvents()


# 1. spiegelen om de eigen inhoud
lay = Layer("figuur", new_image(200, 120)); d.add_layer(lay)
p = QPainter(lay.image); p.fillRect(20, 30, 30, 40, QColor(255, 0, 0)); p.fillRect(20, 30, 5, 40, QColor(0, 0, 255)); p.end()
w.actions_by_id[0x800d].trigger()
a = ops.qimage_to_rgba(d.layer().image)
xs = np.nonzero((a[..., 3] > 0).any(0))[0]
assert (xs.min(), xs.max()) == (20, 49) and a[50, 47, 2] > 200, (xs.min(), xs.max())
print("1 spiegelen: de figuur blijft op zijn plek en draait om zijn eigen as")
d.active = 0
# 2. Naar doel overgaan: twee streken = één streek
t = w.tools[0xd0ab]; w.select_tool(t)
w.opts.update(size=30, hardness=100, opacity=50, step=10, target_mode=0, continuous=False)
w.fg = QColor(0, 200, 0)
stroke(t, (10, 100), (190, 100)); one = d.layers[0].image.pixelColor(100, 100).getRgb()
stroke(t, (10, 100), (190, 100)); two = d.layers[0].image.pixelColor(100, 100).getRgb()
assert one == two and one != (200, 150, 120, 255), (one, two)
print("2 Naar doel overgaan: een tweede streek over dezelfde plek maakt het niet sterker")
# 3. Ctrl = pipet bij de kleurvervanger en het penseel
for cid in (0xd0ac, 0xd091):
    tool = w.tools[cid]; w.select_tool(tool)
    before = ops.qimage_to_rgba(d.layers[0].image).copy()
    w.fg = QColor(1, 2, 3)
    tool.press(cv, QPointF(5, 5), ev(QEvent.Type.MouseButtonPress, L, Qt.KeyboardModifier.ControlModifier))
    tool.release(cv, QPointF(5, 5), ev(QEvent.Type.MouseButtonRelease, L, Qt.KeyboardModifier.ControlModifier))
    assert w.fg.getRgb()[:3] == (200, 150, 120), w.fg.getRgb()
    assert np.array_equal(before, ops.qimage_to_rgba(d.layers[0].image)), "Ctrl+klik schildert niet"
print("3 Ctrl+klik met kleurvervanger en penseel neemt de kleur over (pipet) en schildert niet")
# 4. dekking in het lagenpalet: invoerveld met schuifbalk, geen los schuifje
assert isinstance(w.layers.spin, SliderSpinBox) and not hasattr(w.layers, "slider")
w.layers.spin.set_fraction(0.5); assert abs(d.layer().opacity - 0.5) < 0.011
print("4 dekking met schuifbalk onder het invoerveld")
# 5. compacte tabbladen boven de kleurkiezer
assert max(w.materials.tabs.tabBar().tabRect(i).width() for i in range(2)) <= 40
print("5 compacte tabbladen")
# 6. selectie van één pixel breed
sel = w.tools[0xd021]; w.select_tool(sel); w.opts.update(sel_shape=0, feather=0, antialias=True, sel_mode=0)
cv.zoom = 8
stroke(sel, (10.3, 5.2), (10.8, 60.6))
m = ops.qimage_to_mask(d.sel)
assert np.nonzero((m > 0).any(0))[0].tolist() == [10] and m[20, 10] == 255
stroke(sel, (50, 50), (50.1, 50.1)); assert d.sel is None
print("6 slepen binnen één pixelkolom selecteert precies die kolom; klikken heft de selectie op")
# 7. Selecteren op een lagengroep: kader om de inhoud van de groep, alles verplaatst samen
d.sel = None
base_bg = QImage(d.layers[0].image)
circles = []
for i in range(3):
    d.add_layer(); circles.append(d.layer()); p = QPainter(d.layer().image); p.setBrush(QColor(0, 0, 255)); p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(30 + 40 * i, 30), 8, 8); p.end()
d.active = d.layers.index(circles[0]); d.new_group()
g = d.layer()
for l in circles:
    l.group = g
d.normalize(); d.active = d.layers.index(g)
pick = w.tools[0xd011]; w.select_tool(pick); cv.zoom = 1
box = pick._bbox(d)
assert abs(box.left() - 22) <= 1 and abs(box.right() - 118) <= 1, box
stroke(pick, (30, 30), (40, 50))
assert all(l.image.pixelColor(40 + 40 * i, 50).alpha() == 255 for i, l in enumerate(circles))
assert all(l.image.pixelColor(30 + 40 * i, 30).alpha() == 0 for i, l in enumerate(circles))
assert d.layers[0].image == base_bg, "achtergrond mag niet meebewegen"
names = [l.name for l in circles]
d.undo()
by_name = {l.name: l for l in d.layers}
assert all(by_name[n].image.pixelColor(30 + 40 * i, 30).alpha() == 255 for i, n in enumerate(names)), "ongedaan maken"

print("7 Selecteren op een lagengroep verplaatst alle lagen erin samen, de achtergrond blijft staan")
# 8. Verdelen en uitlijnen op een lagengroep: elke laag is een object
grp = [l for l in d.layers if l.kind == "group"][-1]
d.active = d.layers.index(grp)
kids = [l for l in d.children(grp)]
bb = lambda l: ops.mask_bbox(ops.qimage_to_rgba(l.image)[..., 3] > 0)
p = QPainter(kids[1].image); p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear); p.fillRect(kids[1].image.rect(), Qt.GlobalColor.transparent); p.end()
p = QPainter(kids[1].image); p.setBrush(QColor(0, 0, 255)); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QPointF(50, 80), 8, 8); p.end()
w.all_handlers()[0x8164]()  # verticaal gelijkmatig verdelen (middens)
ys = sorted(bb(l).center().y() for l in kids)
assert abs((ys[1] - ys[0]) - (ys[2] - ys[1])) <= 1, ys
w.all_handlers()[0x8163]()  # bovenkanten uitlijnen
assert len({bb(l).top() for l in kids}) == 1, [bb(l) for l in kids]
print("8 verdelen en uitlijnen werken op de lagen van een lagengroep")
# 9. klik met Selecteren op een andere laag maakt die laag actief
w.select_tool(pick)
for l in d.layers:
    if l.name == "figuur":
        l.visible = False
target = kids[0]
c = bb(target).center()
d.active = 0  # achtergrond actief: kader om de hele achtergrond, dus eerst een andere laag buiten de groep
d.add_layer(); other = d.layer()
p = QPainter(other.image); p.fillRect(150, 90, 20, 20, QColor(0, 200, 0)); p.end()
pick._stale = True
stroke(pick, (c.x(), c.y()), (c.x(), c.y()))
assert d.layer() is target, d.layer().name
stroke(pick, (160, 100), (165, 100))
assert d.layer() is other and other.image.pixelColor(172, 100).alpha() == 255
print("9 klikken op een laag met Selecteren maakt die laag actief en sleept haar meteen")
d.set_modified(False)
print("ALLES OK")
