"""Bijsnijden zoals PSP: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_crop.py"""
import os, sys, tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QPointF, QPoint, QRect, Qt, QEvent
from PySide6.QtGui import QMouseEvent, QColor
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from pixelpickle.mainwindow import MainWindow
from pixelpickle.document import Document, Layer, new_image

w = MainWindow(); w.resize(1100, 800); w.show()
doc = Document(400, 300); cv = w.add_document(doc).canvas; app.processEvents()
crop = w.tools[0xd040]; w.select_tool(crop)
L = Qt.MouseButton.LeftButton
def ev(kind, pt, held=L):
    p = cv.to_widget(pt)
    return QMouseEvent(kind, p, cv.mapToGlobal(p.toPoint()), L, held if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
def drag(a, b):
    crop.press(cv, a, ev(QEvent.Type.MouseButtonPress, a)); crop.move(cv, b, ev(QEvent.Type.MouseMove, b))
    crop.release(cv, b, ev(QEvent.Type.MouseButtonRelease, b)); app.processEvents()
def handle(i):
    return cv.to_doc(crop._handles(cv)[i])

drag(QPointF(50, 40), QPointF(250, 190)); assert crop.r == QRect(50, 40, 200, 150), crop.r
cv.repaint(); app.processEvents()
bar = crop.bars[id(cv)]; assert bar.isVisible(), "zwevend balkje"
print("1 nieuw kader", crop.r, "| balkje onder het kader zichtbaar")
drag(handle(2), QPointF(300, 250)); assert crop.r == QRect(50, 40, 250, 210), crop.r
drag(handle(7), QPointF(20, 120)); assert crop.r.x() == 20 and crop.r.width() == 280, crop.r
print("2 hoek- en zijgreep:", crop.r)
drag(QPointF(100, 100), QPointF(130, 110)); assert crop.r.topLeft() == QPoint(50, 50), crop.r
print("3 verplaatsen binnen kader:", crop.r)
crop.set_ratio(cv, 1.0); assert crop.r.width() == crop.r.height(); print("4 verhouding 1 × 1:", crop.r)
drag(QPointF(10, 10), QPointF(200, 60)); assert crop.r.width() == crop.r.height(), crop.r
print("5 nieuw kader met 1 × 1 blijft vierkant:", crop.r)
crop.set_ratio(cv, 4 / 3); r0 = QRect(crop.r); crop.rotate_frame(cv)
assert (crop.r.width(), crop.r.height()) == (r0.height(), r0.width()), (r0, crop.r)
print("6 kantelen:", r0.size().toTuple(), "->", crop.r.size().toTuple())
crop.set_ratio(cv, None)
lay = Layer("blok", new_image(400, 300)); lay.image.fill(Qt.GlobalColor.transparent)
from PySide6.QtGui import QPainter
p = QPainter(lay.image); p.fillRect(120, 80, 60, 40, QColor(255, 0, 0)); p.end(); doc.add_layer(lay)
crop.snap("layer"); assert crop.r == QRect(120, 80, 60, 40), crop.r
crop.snap("image"); assert crop.r == doc.rect()
print("7 uitlijnen op laag:", QRect(120, 80, 60, 40), "| op afbeelding:", crop.r)
w.select_tool(crop); crop.spins["w"].setValue(100); crop.spins["h"].setValue(80); crop.spins["l"].setValue(30); crop.spins["t"].setValue(20)
# Links/Boven zijn randen (zoals PSP): de linkerrand schuift op, de rechterrand blijft staan
assert crop.r == QRect(30, 20, 70, 60), crop.r
crop.spins["w"].setValue(100); assert crop.r == QRect(30, 20, 100, 60), crop.r
print("8 maten intypen (randen en breedte):", crop.r)
crop.double_click(cv, QPointF(5, 5), None); assert (doc.w, doc.h) == (400, 300), "dubbelklik buiten mag niet bijsnijden"
crop.double_click(cv, QPointF(60, 50), None); assert (doc.w, doc.h) == (100, 60), (doc.w, doc.h)
print("9 dubbelklik buiten: niets | binnen: bijgesneden tot", doc.w, "×", doc.h)
# Pen: geen automatisch scrollen
w.select_tool(w.tools[0xd110]); cv._as_buttons = L
assert not cv._autoscroll_wanted(); w.select_tool(w.tools[0xd021]); assert not cv._autoscroll_wanted()
w.opts["lasso_type"] = 1; w.select_tool(w.tools[0xd022]); assert cv._autoscroll_wanted()  # alleen punt tot punt
print("10 Pen en rechthoekselectie scrollen niet mee, punt tot punt wel")
for s in w.mdi.subWindowList(): s.canvas.doc.set_modified(False)
print("ALLES OK")
