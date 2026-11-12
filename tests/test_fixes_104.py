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
# 10. aanpassingen en effecten op een lagengroep: elke rasterlaag in de groep
from pixelpickle.effectdialog import EffectDialog
from pixelpickle import dialogs
d2 = Document(80, 60, QColor(255, 255, 255)); cv2 = w.add_document(d2).canvas; app.processEvents()
gl = []
for x in (10, 50):
    d2.add_layer(); gl.append(d2.layer())
    p = QPainter(d2.layer().image); p.fillRect(x, 10, 15, 15, QColor(0, 100, 200)); p.end()
d2.active = d2.layers.index(gl[0]); d2.new_group(); grp2 = d2.layer()
for l in gl:
    l.group = grp2
d2.normalize(); d2.active = d2.layers.index(grp2)
bg_before = QImage(d2.layers[0].image)
dlg = EffectDialog(w, d2, w.effects[0x8054])
assert not ops.qimage_to_rgba(dlg.region)[..., 3].max() == 0, "voorbeeld van de groep is leeg"
dlg.set_params({"red": 100, "green": 0, "blue": 0}); dlg.accept()
assert all(l.image.pixelColor(x + 5, 15).red() > 200 for l, x in zip(gl, (10, 50))), [l.image.pixelColor(15, 15).name() for l in gl]
assert d2.layers[0].image == bg_before
d2.undo()
names2 = [l.name for l in gl]
assert all(l.image.pixelColor(x + 5, 15).red() == 0 for l, x in zip([l for l in d2.layers if l.name in names2], (10, 50)))
d2.active = [l.kind for l in d2.layers].index("group")
w.all_handlers()[0x804b]()  # negatief, zonder venster
neg = [l for l in d2.layers if l.name in names2]
assert all(l.image.pixelColor(x + 5, 15).red() == 255 for l, x in zip(neg, (10, 50)))
d2.undo(); d2.active = [l.kind for l in d2.layers].index("group")
ad = dialogs.AdjustDialog(w, d2, "Helderheid/contrast", ops.adj_brightness_contrast,
                          [("brightness", "Helderheid:", -100, 100, 60), ("contrast", "Contrast:", -100, 100, 0)])
ad.accept()
assert all(l.image.pixelColor(x + 5, 15).lightness() > QColor(0, 100, 200).lightness()
           for l, x in zip([l for l in d2.layers if l.name in names2], (10, 50)))
d2.set_modified(False)
print("10 aanpassingen en effecten werken op alle rasterlagen van een lagengroep, met voorbeeld")
# 11. andere laag kiezen in het lagenpalet: het canvas tekent meteen opnieuw (kader van Selecteren)
w.select_tool(w.tools[0xd011]); app.processEvents()
painted = []
cv2.paintEvent = lambda e, _orig=cv2.paintEvent: (painted.append(1), _orig(e))
row = [w.layers._index(r) for r in range(w.layers.list.count())].index([l.name for l in d2.layers].index(names2[0]))
w.layers.on_row(row); app.processEvents()
assert painted, "canvas niet opnieuw getekend na laagwissel"
print("11 laag kiezen in het lagenpalet werkt het canvas meteen bij")
# 12. spiegelen van een lagengroep: als geheel, om het midden van de inhoud van de groep
d3 = Document(100, 50, QColor(255, 255, 255)); w.add_document(d3); app.processEvents()
ml = []
for x in (10, 40):
    d3.add_layer(); ml.append(d3.layer())
    p = QPainter(d3.layer().image); p.fillRect(x, 10, 10, 10, QColor(255, 0, 0)); p.end()
ml[1].image.setPixelColor(49, 10, QColor(0, 0, 255))  # markering rechtsboven in het rechter blok
d3.active = d3.layers.index(ml[0]); d3.new_group(); g3 = d3.layer()
for l in ml:
    l.group = g3
d3.normalize(); d3.active = d3.layers.index(g3)
d3.mirror_layer(True)  # groep beslaat x 10..49, midden 30: blokken wisselen van plek
assert ml[0].image.pixelColor(45, 15) == QColor(255, 0, 0) and ml[0].image.pixelColor(15, 15).alpha() == 0
assert ml[1].image.pixelColor(15, 15) == QColor(255, 0, 0) and ml[1].image.pixelColor(10, 10) == QColor(0, 0, 255)
d3.set_modified(False)
print("12 spiegelen van een lagengroep gebeurt als geheel, op dezelfde plek")
# 13. springen in de geschiedenis: in één keer, met hetzelfde resultaat als stap voor stap
d4 = Document(60, 40, QColor(255, 255, 255)); w.add_document(d4); app.processEvents()
for i in range(5):
    d4.add_layer(Layer(f"L{i}", new_image(60, 40)), label=f"stap {i}")
names_at = lambda: [l.name for l in d4.layers]
full = names_at()
d4.jump_history(2)
assert names_at() == full[:3] and len(d4.undo_stack) == 2 and len(d4.redo_stack) == 3, names_at()
assert [lab for lab, _ in d4.redo_stack] == ["stap 4", "stap 3", "stap 2"]
d4.redo(); assert names_at() == full[:4]
d4.jump_history(5); assert names_at() == full and not d4.redo_stack
d4.jump_history(0); assert names_at() == full[:1]
d4.undo(); assert names_at() == full[:1]  # niets meer ongedaan te maken
w.history.set_doc(d4); w.history.refresh()
w.history.jump(w.history.list.item(5)); assert names_at() == full
d4.set_modified(False)
print("13 springen in de geschiedenis gebeurt in één keer en klopt met stap voor stap")
d.set_modified(False)
print("ALLES OK")
