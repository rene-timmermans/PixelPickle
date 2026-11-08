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
doc.set_modified(False)
print("ALLES OK")
