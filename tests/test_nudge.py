"""Pijltoetsen verschuiven een selectie: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_nudge.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtGui import QColor, QImage, QKeyEvent, QPainter
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from pixelpickle.document import Document
from pixelpickle.mainwindow import MainWindow

w = MainWindow(); w.show()
doc = Document(100, 80, QColor(255, 255, 255)); cv = w.add_document(doc).canvas; app.processEvents()
p = QPainter(doc.layers[0].image); p.fillRect(20, 20, 10, 10, QColor(255, 0, 0)); p.end()
m = QImage(100, 80, QImage.Format.Format_Alpha8); m.fill(0)
q = QPainter(m); q.fillRect(20, 20, 10, 10, QColor(0, 0, 0, 255)); q.end()
doc.set_selection(m)
w.select_tool(w.tools[0xd021])  # Selectie


def key(k, mods=Qt.KeyboardModifier.NoModifier):
    cv.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, k, mods))
    app.processEvents()


def px(x, y):
    return doc.layers[0].image.pixelColor(x, y)


n0 = len(doc.undo_stack)
key(Qt.Key.Key_Right); key(Qt.Key.Key_Right); key(Qt.Key.Key_Down)
assert px(22, 21) == QColor(255, 0, 0) and px(31, 30) == QColor(255, 0, 0) and px(21, 20) == QColor(255, 255, 255)
assert doc.selection_bbox() == QRect(22, 21, 10, 10), doc.selection_bbox()
assert len(doc.undo_stack) == n0 + 1, "een reeks duwtjes is één stap"
key(Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
assert px(32, 21) == QColor(255, 0, 0) and doc.selection_bbox().x() == 32
print("1 pijltoetsen en Shift (10) verschuiven de pixels OK")
key(Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier)
assert doc.selection_bbox().x() == 31 and px(32, 21) == QColor(255, 0, 0) and px(31, 21) == QColor(255, 255, 255)
print("2 Ctrl + pijltoets verschuift alleen het kader OK")
doc.undo(); doc.undo()
assert px(20, 20) == QColor(255, 0, 0) and px(32, 21) == QColor(255, 255, 255), "ongedaan maken in twee stappen"
print("3 ongedaan maken OK")
# Verplaatsen zonder selectie: hele laag
doc.set_selection(None); doc.add_layer(); lay = doc.layer()
p = QPainter(lay.image); p.fillRect(50, 50, 4, 4, QColor(0, 0, 255)); p.end()
w.select_tool(w.tools[0xd012])
key(Qt.Key.Key_Up)
assert lay.image.pixelColor(50, 49) == QColor(0, 0, 255) and lay.image.pixelColor(50, 53).alpha() == 0
# penseel: pijltoetsen doen niets met de afbeelding
w.select_tool(w.tools[0xd091]); n = len(doc.undo_stack); key(Qt.Key.Key_Up); assert len(doc.undo_stack) == n
print("4 Verplaatsen zonder selectie schuift de laag OK")

# versnelling bij ingedrukt houden
w.select_tool(w.tools[0xd012])
x0 = next(x for x in range(100) if lay.image.pixelColor(x, 49).alpha())
cv.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier))
for _ in range(25):
    cv.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier, "", True))
app.processEvents()
x1 = next(x for x in range(100) if lay.image.pixelColor(x, 49).alpha())
expect = 1 + sum(cv.nudge_speed(i) for i in range(1, 26))
assert x1 - x0 == expect and expect > 26, (x0, x1, expect)
print("5 ingedrukt houden versnelt:", expect, "pixels na 26 toetsaanslagen OK")

# focus op het lagenpalet (na het aanklikken van een laag): pijltoetsen schuiven toch de laag
w.layers.list.setFocus(); app.processEvents()
w.layers.list.setFocus()
ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
before = next(y for y in range(80) if lay.image.pixelColor(x1, y).alpha())
QApplication.sendEvent(w.layers.list, ev) if QApplication.focusWidget() is w.layers.list else \
    w.eventFilter(w.layers.list, ev)
app.processEvents()
after = next(y for y in range(80) if lay.image.pixelColor(x1, y).alpha())
assert after == before + 1 and doc.layer() is lay, (before, after)
print("6 pijltoetsen werken ook met de focus op het lagenpalet OK")

# vectorlaag blijft vector bij verschuiven
vl = doc.new_vector_layer("Vector", undo=False)
from PySide6.QtCore import QPointF  # noqa: E402
from pixelpickle.vectorlayer import make_object  # noqa: E402
vl.vector.append(make_object([[QPointF(10, 10), None, None], [QPointF(30, 30), None, None]], False,
                             [0, 0, 0, 255], None, 2))
key(Qt.Key.Key_Right)
assert doc.layer().vector is not None and doc.layer().vector[0]["nodes"][0][0] == [11.0, 10.0], "vectorlaag niet omgezet"
print("7 vectorlaag blijft vector OK")

# spiegelen met selectie: op dezelfde plek
d2 = Document(100, 80, QColor(255, 255, 255)); w.add_document(d2); app.processEvents()
p = QPainter(d2.layers[0].image); p.fillRect(60, 10, 5, 10, QColor(255, 0, 0)); p.end()
m = QImage(100, 80, QImage.Format.Format_Alpha8); m.fill(0)
q = QPainter(m); q.fillRect(60, 10, 20, 10, QColor(0, 0, 0, 255)); q.end()
d2.set_selection(m)
d2.mirror_layer(True)
im = d2.layers[0].image
assert im.pixelColor(79, 15) == QColor(255, 0, 0) and im.pixelColor(75, 15) == QColor(255, 0, 0)
assert im.pixelColor(60, 15) != QColor(255, 0, 0) and im.pixelColor(20, 15) == QColor(255, 255, 255)
assert d2.selection_bbox() == QRect(60, 10, 20, 10)
d2.mirror_layer(False)
assert d2.selection_bbox() == QRect(60, 10, 20, 10)
d2.undo(); d2.undo()
assert d2.layers[0].image.pixelColor(60, 15) == QColor(255, 0, 0)
print("8 spiegelen en omdraaien met selectie blijven op hun plek OK")
for d_ in (doc, d2):
    d_.set_modified(False)
print("ALLES OK")
