"""Bewerkbare tekstlagen: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_text.py"""
import os, sys, tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QPointF, Qt, QEvent
from PySide6.QtGui import QMouseEvent, QColor
from PySide6.QtWidgets import QApplication, QMessageBox
app = QApplication(sys.argv)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
import numpy as np
from pigment.mainwindow import MainWindow
from pigment.document import Document
from pigment import imageops as ops
from pigment.textlayer import bounds

w = MainWindow(); w.show()
doc = Document(400, 300); cv = w.add_document(doc).canvas; app.processEvents()
T = w.tools
def ev(t, pt, btn=Qt.MouseButton.LeftButton):
    pos = cv.to_widget(pt)
    return QMouseEvent(t, pos, pos, btn, btn if t != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)
def drag(tool, a, b):
    w.select_tool(tool)
    tool.press(cv, a, ev(QEvent.Type.MouseButtonPress, a)); tool.move(cv, b, ev(QEvent.Type.MouseMove, b))
    tool.release(cv, b, ev(QEvent.Type.MouseButtonRelease, b)); app.processEvents()
def ink(layer):
    a = ops.qimage_to_rgba(layer.image)[..., 3] > 0
    ys, xs = np.nonzero(a)
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())) if len(xs) else None

text = T[0xd0f0]; w.select_tool(text)
w.opts.update(font_size=40, text_units=1, text_stroke=0)
w.set_color(QColor(200, 0, 0), False)          # vulling = achtergrondkleur
text.press(cv, QPointF(50, 120), ev(QEvent.Type.MouseButtonPress, QPointF(50, 120)))
text.dlg.edit.setPlainText("Hallo"); text.dlg.accept(); app.processEvents()
L = doc.layer(); assert L.text and L.text["text"] == "Hallo" and L.name == "Hallo"
b0 = ink(L); print("1 nieuwe tekst", b0, "kleur", L.image.pixelColor(b0[0] + 3, b0[3] - 5).name())

# bewerken: klik op de tekst, andere tekst en grootte
text.press(cv, QPointF(b0[0] + 5, b0[1] + 5), ev(QEvent.Type.MouseButtonPress, QPointF(b0[0] + 5, b0[1] + 5)))
assert text.dlg.text() == "Hallo", "bewerken opent de bestaande tekst"
w.opts["font_size"] = 30; text.dlg.edit.setPlainText("Hallo wereld"); text.dlg.accept(); app.processEvents()
assert len(doc.layers) == 2 and doc.layer().text["text"] == "Hallo wereld" and doc.layer().text["size"] == 30
b1 = ink(doc.layer()); print("2 bewerkt", b1)

# verplaatsen (M) houdt het tekst
drag(T[0xd012], QPointF(100, 100), QPointF(130, 110))
b2 = ink(doc.layer()); assert doc.layer().text is not None and b2[0] - b1[0] in (29, 30, 31), (b1, b2)
print("3 verplaatst", b2)
# schalen met Selecteren (K) via rechter zijgreep
pick = T[0xd011]; w.select_tool(pick); pts, mids, c, rot = pick._handles(cv)
drag(pick, mids[1], QPointF(mids[1].x() + 60, mids[1].y()))
b3 = ink(doc.layer()); assert doc.layer().text is not None and (b3[2] - b3[0]) > (b2[2] - b2[0]) + 30, (b2, b3)
print("4 geschaald", b3)
# bewerken na schalen behoudt de schaal
text.press(cv, QPointF((b3[0] + b3[2]) / 2, (b3[1] + b3[3]) / 2), ev(QEvent.Type.MouseButtonPress, QPointF((b3[0] + b3[2]) / 2, (b3[1] + b3[3]) / 2)))
text.dlg.edit.setPlainText("Hi"); text.dlg.accept(); app.processEvents()
assert doc.layer().text["matrix"][0] > 1.05, "schaal blijft na bewerken"
print("5 bewerkt na schalen, matrix", [round(v, 2) for v in doc.layer().text["matrix"]])

# afbeelding bewerkingen
for name, fn in (("formaat", lambda: doc.resize_image(200, 150)), ("roteren", lambda: doc.rotate(90)),
                 ("bijsnijden", lambda: doc.crop(doc.rect().adjusted(10, 10, -10, -10))),
                 ("spiegelen", lambda: doc.mirror_layer(True)), ("canvas", lambda: doc.canvas_size(300, 300, 20, 20, QColor("white"))),
                 ("vrij roteren", lambda: doc.rotate_free(15, False, QColor("white")))):
    fn(); l = doc.layers[-1]
    r = bounds(l.text, doc.px_per_pt); bi = ink(l)
    assert l.text is not None and bi and abs(r.center().x() - (bi[0] + bi[2]) / 2) < 6, (name, r, bi)
    print("6", name, "blijft tekst, kader past:", bi)

# ongedaan maken herstelt tekst
n = len(doc.undo_stack)
for _ in range(6): doc.undo()
assert doc.layers[-1].text is not None and doc.layers[-1].text["text"] == "Hi"
print("7 ongedaan maken OK")
# schilderen vraagt omzetten
w.select_tool(T[0xd091]); doc.active = len(doc.layers) - 1
cv.mousePressEvent(ev(QEvent.Type.MouseButtonPress, QPointF(150, 150))); cv.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(150, 150)))
assert doc.layer().text is None, "omgezet naar raster"
print("8 schilderen zet om naar raster")
# annuleren van nieuwe tekst haalt laag weg
n = len(doc.layers); w.select_tool(text)
text.press(cv, QPointF(10, 250), ev(QEvent.Type.MouseButtonPress, QPointF(10, 250))); text.dlg.reject(); app.processEvents()
assert len(doc.layers) == n, "geannuleerde tekst verwijderd"
print("ALLES OK")
for s in w.mdi.subWindowList(): s.canvas.doc.set_modified(False)
