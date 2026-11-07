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
w.opts.update(line_width=4, antialias=False, pen_vector=False)  # eerst: pixels op de laag


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


# 1. lijnen en polylijnen: twee aaneengesloten segmenten, nog niet op de laag tot Enter
w.opts["pen_mode"] = 1
drag([P(20, 20), P(120, 20)]); drag([P(120, 20), P(120, 100)])
assert len(pen.paths) == 1 and len(pen.paths[0]["nodes"]) == 3, pen.paths
assert px(70, 20) == QColor(255, 255, 255), "nog niet toegepast"
assert key(Qt.Key.Key_Return)
assert px(70, 20) == QColor(0, 0, 0) and px(120, 60) == QColor(0, 0, 0) and not pen.paths
print("1 polylijn OK")

# 2. punt tot punt: kromme met handvatten, sluiten op het eerste punt, gevuld met achtergrondkleur
w.opts["pen_mode"] = 2
drag([P(160, 120)]); drag([P(260, 120), P(280, 150)]); drag([P(210, 190)])
drag([P(160, 120)])  # klik op het eerste punt: sluiten
sub = pen.paths[0]
assert sub["closed"] and len(sub["nodes"]) == 3 and sub["nodes"][1][2] is not None, sub
pen.apply()
assert px(210, 140) == QColor(255, 0, 0), px(210, 140).name()
print("2 bézier gesloten en gevuld OK")

# 3. bewerken: knooppunt verslepen voor het toepassen, Delete verwijdert, Esc gooit weg
w.opts["pen_mode"] = 1
drag([P(20, 150), P(100, 150)])
w.opts["pen_mode"] = 0
drag([P(100, 150), P(100, 190)])
assert pen.paths[0]["nodes"][1][0] == P(100, 190)
key(Qt.Key.Key_Escape); assert not pen.paths
assert px(60, 150) == QColor(255, 255, 255), "weggegooid, niets getekend"
print("3 bewerken en Esc OK")

# 4. uit de vrije hand met tracking: veel punten worden er weinig; wisselen van gereedschap past toe
w.opts.update(pen_mode=3, pen_tracking=10)
drag([P(20 + k, 60 + 10 * np.sin(k / 10)) for k in range(0, 200)])
n = len(pen.paths[0]["nodes"])
assert 3 <= n < 60, n
w.select_tool(w.tools[0xd001])
assert not pen.paths and (ops.qimage_to_rgba(doc.layers[0].image)[50:72, 20:220, 0] < 50).any()
print("4 vrije hand,", n, "knooppunten; toegepast bij wisselen OK")

# 5. lijnstijl streepjes en ronde verbinding: geeft onderbroken lijn
w.select_tool(pen); w.opts.update(pen_mode=1, pen_style=1, line_width=3)
drag([P(20, 120), P(140, 120)]); pen.apply()
row = ops.qimage_to_rgba(doc.layers[0].image)[120, 20:140, 0]
assert (row < 50).any() and (row > 200).any(), "streepjes"
# 6. hoekpunt achteraf omzetten naar kromme: Ctrl + slepen, en via het snelmenu vloeiend/hoekpunt
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
print("ALLES OK")
