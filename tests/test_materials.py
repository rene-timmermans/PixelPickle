"""Verloop en patroon: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_materials.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QEvent, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from pixelpickle import material as M
from pixelpickle.document import Document
from pixelpickle.mainwindow import MainWindow
from pixelpickle.materials import MaterialDialog

w = MainWindow(); w.show(); app.processEvents()
doc = Document(200, 100); sw = w.add_document(doc); app.processEvents()
cv = sw.canvas
P = QPointF
LB = Qt.MouseButton.LeftButton


def ev(t, pos, btn=LB):
    return QMouseEvent(t, P(pos), P(pos), btn, btn if t != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)


def drag(tool, pts):
    w.select_tool(tool)
    tool.press(cv, pts[0], ev(QEvent.Type.MouseButtonPress, cv.to_widget(pts[0])))
    for p in pts[1:]:
        tool.move(cv, p, ev(QEvent.Type.MouseMove, cv.to_widget(p)))
    tool.release(cv, pts[-1], ev(QEvent.Type.MouseButtonRelease, cv.to_widget(pts[-1])))
    app.processEvents()


px = lambda x, y: doc.layers[0].image.pixelColor(x, y)

# 1. renderen: lineair 90 graden = links zwart, rechts wit
g = dict(M.default_gradient(), preset="Zwart-wit", angle=90)
img = M.render(g, QRect(0, 0, 100, 10))
assert img.pixelColor(0, 5).lightness() < 10 and img.pixelColor(99, 5).lightness() > 245
g0 = dict(g, angle=0)  # hoek 0: boven naar beneden
img = M.render(g0, QRect(0, 0, 10, 100))
assert img.pixelColor(5, 0).lightness() < 10 and img.pixelColor(5, 99).lightness() > 245
for st in range(4):
    for inv in (False, True):
        assert not M.render(dict(g, style=st, invert=inv, repeats=2), QRect(5, 5, 40, 30)).isNull()
sb = M.render(dict(g, style=2), QRect(0, 0, 100, 100))
assert sb.pixelColor(50, 50).lightness() < 15 and sb.pixelColor(0, 0).lightness() > 240, "zonnestraal"
print("1 renderen OK")

# 2. alle patronen
for name in M.PATTERNS:
    im = M.pattern_image(name)
    assert not im.isNull() and im.width() > 0, name
pat = M.default_pattern()
a = M.render(pat, QRect(0, 0, 64, 64)); b = M.render(pat, QRect(32, 0, 32, 64))
assert a.pixelColor(40, 10) == b.pixelColor(8, 10), "patroon ligt vast t.o.v. het document"
print("2 patronen OK")

# 2b. PSP verloopbestand (zelf gemaakt) en wat er in de PSP installatie staat
import struct
def stop(loc, rgb, typ=0, mid=50):
    return struct.pack(">IIHHHHHH", loc, mid, 0, rgb[0] * 257, rgb[1] * 257, rgb[2] * 257, 0, typ)
body = bytes([4]) + b"Test" + struct.pack(">H", 3) + stop(0, (255, 0, 0)) + stop(2048, (0, 255, 0)) + stop(4096, (0, 0, 0), 2)
body += struct.pack(">H", 2) + struct.pack(">IIH", 0, 50, 255) + struct.pack(">IIH", 4096, 50, 0) + bytes(6)
fn = os.path.join(tempfile.mkdtemp(), "t.PspGradient"); open(fn, "wb").write(b"8BGR" + struct.pack(">HH", 3, 1) + body)
(name, cs, al), = M.read_grd(fn)
assert name == "Test" and cs[1][0] == 0.5 and cs[2][3] == 2 and al[1][2] == 0
M.psp_gradients()["psp:Test"] = (cs, al)
lut = M.gradient_lut("psp:Test", QColor(0, 0, 0), QColor(0, 0, 255))
assert tuple(lut[0].round()) == (255, 0, 0, 255) and lut[128][1] > 250 and lut[255][2] > 250 and lut[255][3] < 1, lut[[0, 128, 255]]
print("2b PSP verloop OK; uit installatie:", len(M.psp_gradients()) - 1, "verlopen,", len(M.psp_patterns()), "patronen")

# 3. vulemmer met verloop
w.set_color(QColor(255, 0, 0), True); w.set_color(QColor(0, 0, 255), False)
w.set_material(True, dict(M.default_gradient(), angle=90))  # rood -> blauw van links naar rechts
drag(w.tools[0xd0d1], [P(100, 50)])
l, r = px(2, 50), px(197, 50)
assert l.red() > 240 and l.blue() < 15 and r.blue() > 240 and r.red() < 15, (l.name(), r.name())
print("3 vulemmer verloop OK", l.name(), px(100, 50).name(), r.name())

# 4. penseel met patroon
w.set_material(True, dict(M.default_pattern(), name="Schaakbord", image=M.pattern_image("Schaakbord")))
w.opts["size"] = 30; w.opts["hardness"] = 100; w.opts["opacity"] = 100
doc.layers[0].image.fill(QColor(0, 200, 0))
drag(w.tools[0xd091], [P(20, 50), P(180, 50)])
cols = {px(x, 50).name() for x in range(30, 170)}
assert "#000000" in cols and "#ffffff" in cols, cols
print("4 penseel patroon OK")

# 5. rechthoek: vulling met verloop, rand effen
w.set_material(True, None)
w.set_color(QColor(0, 0, 0), True); w.set_color(QColor(255, 255, 255), False)
w.set_material(False, dict(M.default_gradient(), preset="Zwart-wit", angle=90))
doc.layers[0].image.fill(QColor(0, 200, 0))
w.opts["line_width"] = 1; w.opts["shape_vector"] = False
drag(w.tools[0xd102], [P(50, 20), P(150, 80)])
a, b = px(55, 50), px(145, 50)
assert a.lightness() < 40 and b.lightness() > 215, (a.name(), b.name())
print("5 rechthoek verloop OK", a.name(), b.name())

# 6. venster: tabbladen werken en geven het materiaal terug
dlg = MaterialDialog(w, QColor(10, 20, 30), mat=None, fg=w.fg, bg=w.bg, documents=w.pattern_sources())
assert all(dlg.tabs.isTabEnabled(i) for i in range(3))
assert dlg.material() is None
dlg.tabs.setCurrentIndex(1); dlg.glist.setCurrentRow(4); dlg.gsp["angle"].setValue(45); dlg.gstyle.button(2).click()
m = dlg.material(); assert m["kind"] == "gradient" and m["preset"] == list(M.GRADIENTS)[4] and m["angle"] == 45 and m["style"] == 2, m
dlg.tabs.setCurrentIndex(2); dlg.plist.setCurrentRow(3); dlg.psp["scale"].setValue(50)
m = dlg.material(); assert m["kind"] == "pattern" and m["scale"] == 50 and not m["image"].isNull(), m
assert dlg.plist.count() == len(M.PATTERNS) + len(M.psp_patterns()) + 1, "open afbeelding als patroon"
dlg.reject()
dlg = MaterialDialog(w, QColor(10, 20, 30), mat=w.bg_mat, fg=w.fg, bg=w.bg)
assert dlg.tabs.currentIndex() == 1
dlg.reject()
print("6 venster OK")

# 7. stijlknopjes, wisselen, standaard
w.set_material_kind(True, 2); assert w.fg_mat["kind"] == "pattern"
w.swap_colors(); assert w.bg_mat["kind"] == "pattern" and w.fg_mat["kind"] == "gradient"
w.materials.fgbox.kinds.button(0).click(); assert w.fg_mat is None
w.reset_colors(); assert w.fg_mat is None and w.bg_mat is None
print("7 knopjes OK")
for s in w.mdi.subWindowList():
    s.canvas.doc.set_modified(False)
print("ALLES OK")
