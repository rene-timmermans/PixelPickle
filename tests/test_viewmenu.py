"""View, Window and Edit: rulers, guides, snapping, grid properties, Effects and Photo toolbars,
Histogram/Overview/Brush variance palettes, full screen, paste as transparent and vector selection:
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
# drag a guide from the top ruler to y = 50 in the image
start = QPointF(cv.ox + 100 * cv.zoom, 5)
end = QPointF(cv.ox + 100 * cv.zoom, cv.oy + 50 * cv.zoom)
cv.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, start))
cv.mouseMoveEvent(mouse(QEvent.Type.MouseMove, end))
cv.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, end))
assert d.guides["h"] == [50], d.guides
print("1 rulers on; guide dragged from the ruler at y =", d.guides["h"][0])
# snap to guides: a nearby point pulls to the guide (only tools that snap)
w.select_tool(w.tools[0xd021])
p = cv.tool_point(QPointF(cv.ox + 120 * cv.zoom, cv.oy + 52.5 * cv.zoom))
assert abs(p.y() - 50) < 1e-6, p
run(0x817b)  # off
p = cv.tool_point(QPointF(cv.ox + 120 * cv.zoom, cv.oy + 52.5 * cv.zoom)); assert abs(p.y() - 52.5) < 0.01
run(0x817a)  # snap to grid
answers.append({"grid_h": 40, "grid_v": 40, "grid_color": QColor(255, 0, 0), "guide_color": QColor(0, 200, 255), "snap_dist": 10})
run(0x8155)
p = cv.tool_point(QPointF(cv.ox + 82 * cv.zoom, cv.oy + 118 * cv.zoom)); assert (round(p.x()), round(p.y())) == (80, 120), p
print("2 snapping to guides and to the grid (40 px)")
# drag guide back into the ruler: gone
g = QPointF(5, cv.oy + 50 * cv.zoom)
cv.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, g))
cv.mouseMoveEvent(mouse(QEvent.Type.MouseMove, QPointF(5, 6)))
cv.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, QPointF(5, 6)))
assert d.guides["h"] == [] and d.guides["v"] == [], d.guides
print("3 guide back to the ruler: removed")
cv.repaint()
img = cv.grab().toImage()
assert img.pixelColor(cv.width() // 2, 5) != img.pixelColor(cv.width() // 2, cv.RULER + 30)
run(0x821d); run(0x821c); app.processEvents()
assert w.effects_toolbar.isVisible() and w.photo_toolbar.isVisible() and len(w.photo_toolbar.actions()) >= 8
print("4 toolbars Effecten and Foto:", len(w.effects_toolbar.actions()), "and", len(w.photo_toolbar.actions()), "buttons")
q = QPainter(d.layers[0].image); q.fillRect(0, 0, 150, 200, QColor(0, 0, 0)); q.end(); d.changed.emit(d.rect())
run(0x8022); run(0x8159); run(0x822d); app.processEvents()
w.histogram._key = None; w.histogram._poll()
assert w.histogram.hist is not None and w.histogram.hist[0][0] > 0 and w.histogram.hist[0][255] > 0
w.overview.resize(200, 160); w.overview._center_on(QPointF(100, 40)); assert not cv._auto
print("5 palettes Histogram (black and white found), Overview (click shifts) and Brush variance")
# brush variance: spread makes stamps fall outside the line
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
print("6 brush variance: stroke spreads", rows.max() - rows.min(), "pixels")
run(0x8202); run(0x80ef); app.processEvents()
assert w._preview.isVisible(); w._preview.close()
print("7 full screen and full screen preview")
# paste as transparent selection
clip = QImage(40, 30, QImage.Format.Format_ARGB32_Premultiplied); clip.fill(QColor(255, 255, 255))
q = QPainter(clip); q.fillRect(10, 10, 20, 10, QColor(0, 0, 255)); q.end()
QApplication.clipboard().setImage(clip)
w.bg = QColor(255, 255, 255)
run(0x80f0)
m = ops.qimage_to_mask(d.sel); lay = ops.qimage_to_rgba(d.layer().image)
assert m.sum() // 255 == 200 and lay[..., 3].max() == 255
print("8 paste as transparent selection: only the blue part")
# paste as new vector selection
from pixelpickle.tools import PickTool  # noqa: E402
PickTool.clipboard = [V.make_object([[QPointF(5, 5), None, None], [QPointF(50, 50), None, None]], False, [0, 0, 0, 255], None, 2)]
run(0x8023)
assert d.layer().vector is not None and d.vsel == [0] and w.tool is w.tools[0xd011]
print("9 paste as new vector selection: on a new vector layer, chosen right away")
d.set_modified(False)
print("ALL OK")
