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
from PySide6.QtGui import QColor, QMouseEvent, QPainter  # noqa: E402
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
d.set_modified(False)
print("ALLES OK")
