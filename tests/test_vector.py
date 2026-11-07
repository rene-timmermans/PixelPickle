"""Vectorlagen: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_vector.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication(sys.argv)
from pixelpickle import fileio
from pixelpickle.document import Document
from pixelpickle.mainwindow import MainWindow

QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
w = MainWindow(); w.show()
doc = Document(300, 200, QColor(255, 255, 255)); cv = w.add_document(doc).canvas; app.processEvents()
P, LB = QPointF, Qt.MouseButton.LeftButton
w.set_color(QColor(0, 0, 0), True); w.set_color(QColor(255, 0, 0), False)


def ev(t, p, mods=Qt.KeyboardModifier.NoModifier):
    return QMouseEvent(t, cv.to_widget(p), cv.to_widget(p), LB, LB if t != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton, mods)


def drag(tool, pts):
    tool.press(cv, pts[0], ev(QEvent.Type.MouseButtonPress, pts[0]))
    for q in pts[1:]:
        tool.move(cv, q, ev(QEvent.Type.MouseMove, q))
    tool.release(cv, pts[-1], ev(QEvent.Type.MouseButtonRelease, pts[-1]))
    app.processEvents()


def comp(x, y):
    return doc.composite().pixelColor(x, y)


# 1. pen met 'Op vector maken': nieuwe vectorlaag, achtergrond blijft schoon
pen = w.tools[0xd110]; w.select_tool(pen)
w.opts.update(pen_mode=1, pen_vector=True, line_width=4, antialias=False, pen_style=0)
drag(pen, [P(20, 30), P(200, 30)]); pen.apply()
assert len(doc.layers) == 2 and doc.layer().vector is not None and len(doc.layer().vector) == 1
assert doc.layers[0].image.pixelColor(100, 30) == QColor(255, 255, 255) and comp(100, 30) == QColor(0, 0, 0)
vlayer = doc.layer()
print("1 pen maakt een vectorlaag OK")

# 2. rechthoek op dezelfde vectorlaag: tweede object, gevuld met achtergrondkleur
rect = w.tools[0xd102]; w.select_tool(rect); w.opts.update(line_width=2, shape_vector=True)
drag(rect, [P(60, 80), P(160, 160)])
assert len(doc.layers) == 2 and len(vlayer.vector) == 2, len(vlayer.vector)
assert comp(110, 120) == QColor(255, 0, 0) and comp(60, 120) == QColor(0, 0, 0)
print("2 rechthoek als vectorobject OK")

# 3. later bewerken: rechthoek oppakken, hoek verslepen, kleur en breedte wijzigen, toepassen
w.select_tool(pen); w.opts["pen_mode"] = 0
drag(pen, [P(110, 120)])  # klik in de gevulde rechthoek: oppakken
assert pen.picked is not None and len(pen.paths) == 1 and len(vlayer.vector) == 1
assert w.opts["line_width"] == 2 and w.bg == QColor(255, 0, 0), "instellingen van het object overgenomen"
nodes = pen.paths[0]["nodes"]
corner = min(range(len(nodes)), key=lambda i: (nodes[i][0].x() - 160) ** 2 + (nodes[i][0].y() - 160) ** 2)
drag(pen, [nodes[corner][0], P(220, 190)])
w.set_color(QColor(0, 0, 255), False)
pen.apply()
assert len(vlayer.vector) == 2 and comp(200, 180) == QColor(0, 0, 255), comp(200, 180).name()
print("3 object opnieuw bewerkt (vorm en kleur) OK")

# 4. Esc na oppakken zet ongewijzigd terug; Delete verwijdert het object
drag(pen, [P(120, 130)]); assert pen.picked is not None
pen.key(cv, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
assert len(vlayer.vector) == 2 and comp(200, 180) == QColor(0, 0, 255)
drag(pen, [P(120, 130)])
pen.key(cv, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier))
assert len(vlayer.vector) == 1 and comp(120, 130) == QColor(255, 255, 255)
doc.undo(); vlayer = doc.layer(); assert len(vlayer.vector) == 2, "ongedaan maken herstelt het object"
print("4 Esc, Delete en ongedaan maken OK")

# 5. verplaatsen, spiegelen en formaat wijzigen houden het bewerkbaar
w.select_tool(w.tools[0xd012])  # verplaatsen
drag(w.tools[0xd012], [P(100, 100), P(110, 100)])
assert doc.layer().vector is not None and abs(doc.layer().vector[0]["nodes"][0][0][0] - 30) < 1e-6
doc.resize_image(600, 400)
v = doc.layer().vector
assert v is not None and abs(v[0]["nodes"][0][0][0] - 60) < 1e-6 and abs(v[0]["width"] - 8) < 1e-6
print("5 verplaatsen en formaat wijzigen: nog steeds vector OK")

# 6. schilderen op een vectorlaag vraagt om omzetten; daarna rasterlaag
brush = w.tools[0xd091]; w.select_tool(brush)
cv.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, cv.to_widget(P(10, 10)), cv.to_widget(P(10, 10)), LB, LB, Qt.KeyboardModifier.NoModifier))
cv.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, cv.to_widget(P(10, 10)), cv.to_widget(P(10, 10)), LB, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
assert doc.layer().vector is None, "omgezet in rasterlaag"
doc.undo(); doc.undo()
print("6 schilderen zet om in rasterlaag OK")

# 7. .ora bewaart de vectoren bewerkbaar
path = os.path.join(tempfile.mkdtemp(), "v.ora")
fileio.save(doc, path)
d2 = fileio.load(path)
vl = [l for l in d2.layers if l.vector is not None]
assert vl and len(vl[0].vector) == len(doc.layers[-1].vector or vl[0].vector), vl
print("7 .ora bewaart vectoren OK")

# 8. menu Lagen > Nieuwe vectorlaag
n = len(doc.layers); w.actions_by_id[0x8141].trigger(); app.processEvents()
assert len(doc.layers) == n + 1 and doc.layer().vector == []
doc.set_modified(False)
print("ALLES OK")
