"""Beeld, Venster en Bewerken: linialen, hulplijnen, uitlijnen, rastereigenschappen, werkbalken Effecten en
Foto, paletten Histogram/Overzicht/Penseelvariantie, schermvullend, plakken als transparante en vectorselectie:
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_viewmenu.py"""
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
from pixelpickle import dialogs, imageops as ops, vectorlayer as V  # noqa: E402
from pixelpickle.document import Document  # noqa: E402
from pixelpickle.mainwindow import MainWindow  # noqa: E402

answers = []
dialogs.ask_form = lambda *a, **k: answers.pop(0)
w = MainWindow(); w.resize(900, 700); w.show()
d = Document(300, 200, QColor(255, 255, 255)); cv = w.add_document(d).canvas; app.processEvents()
run = lambda cid: w.actions_by_id[cid].trigger()  # noqa: E731
L = Qt.MouseButton.LeftButton


def mouse(kind, pos, btn=L):
    held = btn if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    return QMouseEvent(kind, pos, cv.mapToGlobal(pos.toPoint()), btn, held, Qt.KeyboardModifier.NoModifier)


run(0x810a); assert w.view_opts["rulers"] and w.actions_by_id[0x810a].isChecked()
# hulplijn uit de bovenste liniaal slepen tot y = 50 in de afbeelding
start = QPointF(cv.ox + 100 * cv.zoom, 5)
end = QPointF(cv.ox + 100 * cv.zoom, cv.oy + 50 * cv.zoom)
cv.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, start))
cv.mouseMoveEvent(mouse(QEvent.Type.MouseMove, end))
cv.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, end))
assert d.guides["h"] == [50], d.guides
print("1 linialen aan; hulplijn uit de liniaal gesleept op y =", d.guides["h"][0])
# uitlijnen op hulplijnen: een punt vlakbij trekt naar de hulplijn (alleen gereedschappen die uitlijnen)
w.select_tool(w.tools[0xd021])
p = cv.tool_point(QPointF(cv.ox + 120 * cv.zoom, cv.oy + 52.5 * cv.zoom))
assert abs(p.y() - 50) < 1e-6, p
run(0x817b)  # uit
p = cv.tool_point(QPointF(cv.ox + 120 * cv.zoom, cv.oy + 52.5 * cv.zoom)); assert abs(p.y() - 52.5) < 0.01
run(0x817a)  # uitlijnen op raster
answers.append({"grid_h": 40, "grid_v": 40, "grid_color": QColor(255, 0, 0), "guide_color": QColor(0, 200, 255), "snap_dist": 10})
run(0x8155)
p = cv.tool_point(QPointF(cv.ox + 82 * cv.zoom, cv.oy + 118 * cv.zoom)); assert (round(p.x()), round(p.y())) == (80, 120), p
print("2 uitlijnen op hulplijnen en op het raster (40 px)")
# hulplijn terug in de liniaal slepen: weg
g = QPointF(5, cv.oy + 50 * cv.zoom)
cv.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, g))
cv.mouseMoveEvent(mouse(QEvent.Type.MouseMove, QPointF(5, 6)))
cv.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, QPointF(5, 6)))
assert d.guides["h"] == [] and d.guides["v"] == [], d.guides
print("3 hulplijn terug naar de liniaal: verwijderd")
cv.repaint()
img = cv.grab().toImage()
assert img.pixelColor(cv.width() // 2, 5) != img.pixelColor(cv.width() // 2, cv.RULER + 30)
run(0x821d); run(0x821c); app.processEvents()
assert w.effects_toolbar.isVisible() and w.photo_toolbar.isVisible() and len(w.photo_toolbar.actions()) >= 8
print("4 werkbalken Effecten en Foto:", len(w.effects_toolbar.actions()), "en", len(w.photo_toolbar.actions()), "knoppen")
q = QPainter(d.layers[0].image); q.fillRect(0, 0, 150, 200, QColor(0, 0, 0)); q.end(); d.changed.emit(d.rect())
run(0x8022); run(0x8159); run(0x822d); app.processEvents()
w.histogram._key = None; w.histogram._poll()
assert w.histogram.hist is not None and w.histogram.hist[0][0] > 0 and w.histogram.hist[0][255] > 0
w.overview.resize(200, 160); w.overview._center_on(QPointF(100, 40)); assert not cv._auto
print("5 paletten Histogram (zwart en wit gevonden), Overzicht (klik verschuift) en Penseelvariantie")
# penseelvariantie: spreiding laat stempels buiten de lijn vallen
w.opts.update(var_spread=100, var_size=50, var_opacity=0, var_rotation=0)
br = w.tools[0xd091]; w.select_tool(br); w.opts.update(size=10, hardness=100, step=25, opacity=100)
w.set_color(QColor(255, 0, 0), True)
for kind, pt in ((QEvent.Type.MouseButtonPress, QPointF(170, 100)), (QEvent.Type.MouseMove, QPointF(290, 100)),
                 (QEvent.Type.MouseButtonRelease, QPointF(290, 100))):
    getattr(br, {QEvent.Type.MouseButtonPress: "press", QEvent.Type.MouseMove: "move",
                 QEvent.Type.MouseButtonRelease: "release"}[kind])(cv, pt, mouse(kind, cv.to_widget(pt)))
a = ops.qimage_to_rgba(d.layers[0].image)
rows = np.nonzero((a[:, 160:300, 1] < 100).any(axis=1))[0]
assert rows.max() - rows.min() > 12, (rows.min(), rows.max())
w.opts.update(var_spread=0, var_size=0)
print("6 penseelvariantie: streek spreidt", rows.max() - rows.min(), "pixels")
run(0x8202); run(0x80ef); app.processEvents()
assert w._preview.isVisible(); w._preview.close()
print("7 schermvullend maken en schermvullend voorbeeld")
# plakken als transparante selectie
clip = QImage(40, 30, QImage.Format.Format_ARGB32_Premultiplied); clip.fill(QColor(255, 255, 255))
q = QPainter(clip); q.fillRect(10, 10, 20, 10, QColor(0, 0, 255)); q.end()
QApplication.clipboard().setImage(clip)
w.bg = QColor(255, 255, 255)
run(0x80f0)
m = ops.qimage_to_mask(d.sel); lay = ops.qimage_to_rgba(d.layer().image)
assert m.sum() // 255 == 200 and lay[..., 3].max() == 255
print("8 plakken als transparante selectie: alleen het blauwe deel")
# plakken als nieuwe vectorselectie
from pixelpickle.tools import PickTool  # noqa: E402
PickTool.clipboard = [V.make_object([[QPointF(5, 5), None, None], [QPointF(50, 50), None, None]], False, [0, 0, 0, 255], None, 2)]
run(0x8023)
assert d.layer().vector is not None and d.vsel == [0] and w.tool is w.tools[0xd011]
print("9 plakken als nieuwe vectorselectie: op een nieuwe vectorlaag, meteen gekozen")
d.set_modified(False)
print("ALLES OK")
