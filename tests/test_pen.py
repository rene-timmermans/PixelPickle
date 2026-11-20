"""Pen: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_pen.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from pixelpickle import imageops as ops
from pixelpickle.document import Document
from pixelpickle.mainwindow import MainWindow

w = MainWindow(); w.show()
doc = Document(300, 200, QColor(255, 255, 255)); cv = w.add_document(doc).canvas; app.processEvents()
P, LB = QPointF, Qt.MouseButton.LeftButton
pen = w.tools[0xd110]; w.select_tool(pen)
w.set_color(QColor(0, 0, 0), True); w.set_color(QColor(255, 0, 0), False)
w.opts.update(line_width=4, antialias=False, pen_vector=False)  # first: pixels on the layer


def ev(t, p):
    return QMouseEvent(t, cv.to_widget(p), cv.to_widget(p), LB, LB if t != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)


def drag(pts):
    pen.press(cv, pts[0], ev(QEvent.Type.MouseButtonPress, pts[0]))
    for q in pts[1:]:
        pen.move(cv, q, ev(QEvent.Type.MouseMove, q))
    pen.release(cv, pts[-1], ev(QEvent.Type.MouseButtonRelease, pts[-1]))


def px(x, y):
    return doc.layers[0].image.pixelColor(x, y)


def key(k):
    return pen.key(cv, QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier))


# 1. lines and polylines: two connected segments, not on the layer until Enter
w.opts["pen_mode"] = 1
drag([P(20, 20), P(120, 20)]); drag([P(120, 20), P(120, 100)])
assert len(pen.paths) == 1 and len(pen.paths[0]["nodes"]) == 3, pen.paths
assert px(70, 20) == QColor(255, 255, 255), "not applied yet"
assert key(Qt.Key.Key_Return)
assert px(70, 20) == QColor(0, 0, 0) and px(120, 60) == QColor(0, 0, 0) and not pen.paths
print("1 polyline OK")

# 2. point to point: curve with handles, close on the first point, filled with background color
w.opts["pen_mode"] = 2
drag([P(160, 120)]); drag([P(260, 120), P(280, 150)]); drag([P(210, 190)])
drag([P(160, 120)])  # click on the first point: close
sub = pen.paths[0]
assert sub["closed"] and len(sub["nodes"]) == 3 and sub["nodes"][1][2] is not None, sub
pen.apply()
assert px(210, 140) == QColor(255, 0, 0), px(210, 140).name()
print("2 bezier closed and filled OK")

# 3. edit: drag a node before applying, Delete removes, Esc discards
w.opts["pen_mode"] = 1
drag([P(20, 150), P(100, 150)])
w.opts["pen_mode"] = 0
drag([P(100, 150), P(100, 190)])
assert pen.paths[0]["nodes"][1][0] == P(100, 190)
key(Qt.Key.Key_Escape); assert not pen.paths
assert px(60, 150) == QColor(255, 255, 255), "discarded, nothing drawn"
print("3 editing and Esc OK")

# 4. freehand with tracking: many points become few; switching tools applies
w.opts.update(pen_mode=3, pen_tracking=10)
drag([P(20 + k, 60 + 10 * np.sin(k / 10)) for k in range(0, 200)])
n = len(pen.paths[0]["nodes"])
assert 3 <= n < 60, n
w.select_tool(w.tools[0xd001])
assert not pen.paths and (ops.qimage_to_rgba(doc.layers[0].image)[50:72, 20:220, 0] < 50).any()
print("4 freehand,", n, "nodes; applied on switching OK")

# 5. dashed line style and round join: gives a broken line
w.select_tool(pen); w.opts.update(pen_mode=1, pen_style=1, line_width=3)
drag([P(20, 120), P(140, 120)]); pen.apply()
row = ops.qimage_to_rgba(doc.layers[0].image)[120, 20:140, 0]
assert (row < 50).any() and (row > 200).any(), "dashes"
# 6. convert a corner point to a curve afterwards: Ctrl + drag, and via the context menu smooth/corner
w.opts.update(pen_mode=1, pen_style=0)
drag([P(20, 170), P(150, 170)]); drag([P(150, 170), P(280, 170)])
w.opts["pen_mode"] = 0
mid = pen.paths[0]["nodes"][1]
pen.press(cv, P(150, 170), QMouseEvent(QEvent.Type.MouseButtonPress, cv.to_widget(P(150, 170)), cv.to_widget(P(150, 170)), LB, LB, Qt.KeyboardModifier.ControlModifier))
pen.move(cv, P(190, 140), ev(QEvent.Type.MouseMove, P(190, 140))); pen.release(cv, P(190, 140), ev(QEvent.Type.MouseButtonRelease, P(190, 140)))
assert mid[0] == P(150, 170) and mid[2] == P(190, 140) and mid[1] == P(110, 200), mid
pen.make_corner(0, 1); assert mid[1] is None and mid[2] is None
pen.make_smooth(0, 1); assert mid[1].x() < 150 < mid[2].x() and abs(mid[1].y() - 170) < 1e-6
names = [a[0] for a in pen.context_actions(cv)]
assert "Vloeiend knooppunt" in names and "Hoekpunt" in names, names
key(Qt.Key.Key_Escape)
doc.set_modified(False)
print("ALL OK")
