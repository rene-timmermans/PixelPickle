"""Auto-scroll at the edge: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_autoscroll.py"""
import os, sys, tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QPointF, QPoint, Qt, QEvent
from PySide6.QtGui import QMouseEvent, QCursor
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from pixelpickle.mainwindow import MainWindow
from pixelpickle.document import Document
import pixelpickle.canvas as cvmod

w = MainWindow(); w.resize(1000, 700); w.show()
doc = Document(2000, 1500); cv = w.add_document(doc).canvas; app.processEvents()
cv.set_zoom(3.0); app.processEvents()
fake = {"pos": QPoint(0, 0)}
QCursor.pos = staticmethod(lambda: cv.mapToGlobal(fake["pos"]))  # set the mouse position in the test
def move(p, buttons=Qt.MouseButton.NoButton):
    fake["pos"] = p.toPoint()
    cv.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, p, cv.mapToGlobal(p.toPoint()), Qt.MouseButton.NoButton, buttons, Qt.KeyboardModifier.NoModifier))
def click(p):
    cv.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, p, cv.mapToGlobal(p.toPoint()), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    cv.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, p, cv.mapToGlobal(p.toPoint()), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))

lasso = w.tools[0xd022]; w.opts["lasso_type"] = 1; w.select_tool(lasso)
H = cv.height()
# without an active selection: nothing happens at the edge
oy0 = cv.oy; move(QPointF(300, H - 5)); [cv._autoscroll_tick() for _ in range(5)]
assert cv.oy == oy0 and not cv.autoscroll.isActive(), "scrolls while nothing is happening"
print("1 no operation: no scrolling")
# point-to-point in progress: in the bottom edge zone the view scrolls up (so down in the image)
click(QPointF(300, 200)); click(QPointF(400, 260))
move(QPointF(400, H - 30)); assert cv.autoscroll.isActive()
oy = cv.oy; cv._autoscroll_tick(); slow = oy - cv.oy
move(QPointF(400, H - 2)); oy = cv.oy; cv._autoscroll_tick(); mid = oy - cv.oy
fake["pos"] = QPoint(400, H + 120); oy = cv.oy; cv._autoscroll_tick(); fast = oy - cv.oy
assert 0 < slow < mid < fast, (slow, mid, fast)
print(f"2 point to point, bottom edge: {slow:.1f} -> {mid:.1f} -> {fast:.1f} px per tick (faster the further out)")
# the line to the mouse follows along: the last preview point lies further in the image
last = lasso.preview[-1] if lasso.preview else None
print("3 preview line follows the mouse up to y =", round(last.y()) if last else None, "(image height 1500)")
# finish and check that it stops
lasso.double_click(cv, cv.to_doc(QPointF(400, 300)), None); move(QPointF(400, H - 5)); cv._autoscroll_tick()
assert not cv.autoscroll.isActive(); print("4 after closing the selection: stops")
# other tools (brush, rectangle selection, freehand drag): do not scroll along
for tool, lt in ((w.tools[0xd091], 1), (w.tools[0xd021], 1), (lasso, 0)):
    w.opts["lasso_type"] = lt; w.select_tool(tool)
    cv.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(300, 300), cv.mapToGlobal(QPoint(300, 300)), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    ox = cv.ox; move(QPointF(cv.width() - 3, 300), Qt.MouseButton.LeftButton); cv._autoscroll_tick()
    assert cv.ox == ox and not cv.autoscroll.isActive(), tool.name
    cv.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(cv.width() - 3, 300), cv.mapToGlobal(QPoint(cv.width() - 3, 300)), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
print("5 brush, rectangle selection and freehand drag: does not scroll along")
for s in w.mdi.subWindowList(): s.canvas.doc.set_modified(False)
print("ALL OK")
