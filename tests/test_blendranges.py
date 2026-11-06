"""Mengbereiken: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_blendranges.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QEvent, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QApplication, QDialog

app = QApplication(sys.argv)
from pixelpickle import fileio
from pixelpickle.dialogs import LayerPropertiesDialog
from pixelpickle.document import Document, FULL_RANGE, new_image, range_weight
import numpy as np

# 1. weging
v = np.array([0, 50, 100, 150, 200, 255], np.float32)
w = range_weight(v, (50, 100, 150, 200))
assert list(np.round(w, 2)) == [0, 0, 1, 1, 0, 0], w
w = range_weight(np.array([75.0, 175.0]), (50, 100, 150, 200)); assert np.allclose(w, [0.5, 0.5])
print("1 weging OK")

# 2. samenvoegen: onderliggend links zwart, rechts wit; bovenlaag rood
doc = Document(100, 10, QColor(0, 0, 0))
p_img = doc.layers[0].image
for x in range(50, 100):
    for y in range(10):
        p_img.setPixelColor(x, y, QColor(255, 255, 255))
doc.add_layer(); top = doc.layer(); top.image = new_image(100, 10, QColor(255, 0, 0))
assert doc.composite().pixelColor(10, 5) == QColor(255, 0, 0)
# alleen tonen waar het onderliggende licht is
top.blend_ranges = {"Grijs": (FULL_RANGE, (128, 200, 255, 255))}
c = doc.composite()
assert c.pixelColor(10, 5) == QColor(0, 0, 0) and c.pixelColor(90, 5) == QColor(255, 0, 0), (c.pixelColor(10, 5).name(), c.pixelColor(90, 5).name())
# deze laag: rood kanaal hoog wegfilteren -> laag verdwijnt overal
top.blend_ranges = {"Rood": ((0, 0, 100, 120), FULL_RANGE)}
c = doc.composite(); assert c.pixelColor(90, 5) == QColor(255, 255, 255)
# deelrechthoek (zoals het canvas bijwerkt) geeft hetzelfde
part = doc.composite(QRect(80, 0, 20, 10)); assert part.pixelColor(10, 5) == QColor(255, 255, 255)
print("2 samenvoegen OK")

# 3. opslaan en laden (.ora en .pspimage), klonen, omlaag samenvoegen
top.blend_ranges = {"Grijs": (FULL_RANGE, (128, 200, 255, 255))}
d = tempfile.mkdtemp()
for ext in ("ora", "pspimage"):
    fileio.save(doc, f"{d}/t.{ext}")
    d2 = fileio.load(f"{d}/t.{ext}")
    br = d2.layers[-1].blend_ranges
    assert br and tuple(br["Grijs"][1]) == (128, 200, 255, 255), (ext, br)
    c = d2.composite(); assert c.pixelColor(10, 5) == QColor(0, 0, 0) and c.pixelColor(90, 5) == QColor(255, 0, 0), ext
assert doc.layers[-1].clone().blend_ranges == top.blend_ranges
doc.merge_down()
m = doc.layers[0].image; assert m.pixelColor(10, 5) == QColor(0, 0, 0) and m.pixelColor(90, 5) == QColor(255, 0, 0)
print("3 opslaan en samenvoegen OK")

# 4. venster: tabblad actief, schuif verandert de laag live, Annuleren herstelt, OK geeft de waarde
doc = Document(100, 10, QColor(0, 0, 0)); doc.add_layer(); lay = doc.layer(); lay.image = new_image(100, 10, QColor(255, 0, 0))
dlg = LayerPropertiesDialog(None, lay, doc)
from PySide6.QtWidgets import QTabWidget
tw = dlg.findChild(QTabWidget); assert tw.isTabEnabled(1) and tw.tabText(1) == "Mengbereiken"
pg = dlg.ranges; pg.spins[0][2].setValue(100); pg.spins[0][3].setValue(120)
assert lay.blend_ranges and tuple(lay.blend_ranges["Grijs"][0]) == (0, 0, 100, 120), lay.blend_ranges
pg.channel.setCurrentIndex(1); assert pg.spins[0][2].value() == 255  # ander kanaal: standaard
sl = pg.sliders[1]; sl.resize(300, 46); sl.show(); app.processEvents()
x = sl._x(0) + 1
for t, pos in ((QEvent.Type.MouseButtonPress, x), (QEvent.Type.MouseMove, sl._x(80)), (QEvent.Type.MouseButtonRelease, sl._x(80))):
    btn = Qt.MouseButton.LeftButton
    ev = QMouseEvent(t, QPointF(pos, 30), QPointF(pos, 30), btn, btn if t != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    {QEvent.Type.MouseButtonPress: sl.mousePressEvent, QEvent.Type.MouseMove: sl.mouseMoveEvent, QEvent.Type.MouseButtonRelease: sl.mouseReleaseEvent}[t](ev)
# vallen twee driehoekjes samen, dan schuift naar rechts slepen het binnenste (zachte overgang 0..80)
assert sl.v[0] == 0 and 75 <= sl.v[1] <= 85 and pg.spins[1][1].value() == sl.v[1], sl.v
vals = dlg.values(); assert vals["blend_ranges"]["Rood"][1][1] == sl.v[1]
dlg.reject(); assert lay.blend_ranges is None, "Annuleren herstelt"
pg2 = LayerPropertiesDialog(None, lay, doc); pg2.ranges._reset(); assert pg2.values()["blend_ranges"] is None; pg2.reject()
print("4 venster OK")
print("ALLES OK")
