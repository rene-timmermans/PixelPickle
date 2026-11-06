"""Selectiemodus Toevoegen/Verwijderen uit de optiebalk: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_selmode.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from pixelpickle.document import Document
from pixelpickle.mainwindow import MainWindow

w = MainWindow(); w.show()
doc = Document(200, 150, QColor(200, 150, 100)); sw = w.add_document(doc); app.processEvents()
cv = sw.canvas
P, LB = QPointF, Qt.MouseButton.LeftButton


def ev(t, p, btn=LB):
    return QMouseEvent(t, cv.to_widget(p), cv.to_widget(p), btn, btn if t != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)


def drag_rect(tool, a, b):
    tool.press(cv, a, ev(QEvent.Type.MouseButtonPress, a))
    tool.move(cv, b, ev(QEvent.Type.MouseMove, b))
    tool.release(cv, b, ev(QEvent.Type.MouseButtonRelease, b))


def sel(x, y):
    return doc.sel is not None and doc.sel.pixelColor(x, y).alpha() > 127


before = QColor(doc.layers[0].image.pixelColor(60, 60))
# 1. selectie: rechthoek 20..180 x 20..130
rect = w.tools[0xd021]; w.opts["sel_mode"] = 0; w.select_tool(rect)
drag_rect(rect, P(20, 20), P(180, 130)); assert sel(100, 75)
# 2. lasso punt tot punt, modus Verwijderen, alle klikken BINNEN de selectie
lasso = w.tools[0xd022]; w.opts["lasso_type"] = 1; w.opts["sel_mode"] = 2; w.select_tool(lasso)
assert lasso.hover_cursor(cv, P(60, 60)) is None, "geen verplaats-cursor bij Verwijderen"
for q in (P(50, 40), P(110, 40), P(110, 100), P(50, 100)):
    lasso.press(cv, q, ev(QEvent.Type.MouseButtonPress, q))
    lasso.release(cv, q, ev(QEvent.Type.MouseButtonRelease, q))
lasso.double_click(cv, P(50, 100), None)
assert not sel(80, 70) and sel(150, 70), "gebied binnen de lasso hoort uit de selectie"
assert doc.layers[0].image.pixelColor(60, 60) == before, "pixels mogen niet verplaatst zijn"
# 3. Toevoegen binnen de selectie: rechthoek die deels erbuiten valt breidt uit
w.opts["sel_mode"] = 1; w.select_tool(rect)
drag_rect(rect, P(150, 100), P(195, 145)); assert sel(190, 140) and sel(150, 70)
# 4. Vervangen: slepen binnen de selectie verplaatst nog steeds de pixels
w.opts["sel_mode"] = 0; w.select_tool(rect)
assert rect.hover_cursor(cv, P(160, 60)) == Qt.CursorShape.SizeAllCursor
doc.set_modified(False)
print("ALLES OK")
