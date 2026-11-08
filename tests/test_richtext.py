"""Tekst met opmaak per woord, en verloop/patroon in tekst:
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_richtext.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QMouseEvent, QTextCursor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from pixelpickle import imageops as ops, material as M  # noqa: E402
from pixelpickle.document import Document  # noqa: E402
from pixelpickle.mainwindow import MainWindow  # noqa: E402

w = MainWindow(); w.show()
doc = Document(500, 200, QColor(255, 255, 255)); cv = w.add_document(doc).canvas; app.processEvents()
text = w.tools[0xd0f0]
w.select_tool(text)
w.opts.update(font_size=40, text_units=1, text_stroke=0, bold=False, italic=False, underline=False)
w.set_color(QColor(0, 0, 0), False)  # vulling zwart


def press(pt):
    pos = cv.to_widget(pt)
    text.press(cv, pt, QMouseEvent(QEvent.Type.MouseButtonPress, pos, pos, Qt.MouseButton.LeftButton,
                                   Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))


def select(dlg, start, end):
    c = dlg.edit.textCursor()
    c.setPosition(start); c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    dlg.edit.setTextCursor(c)


def ink_cols(img, y0, y1, color_test):
    a = ops.qimage_to_rgba(img)[y0:y1]
    return np.nonzero(color_test(a).any(axis=0))[0]


press(QPointF(20, 100))
dlg = text.dlg
dlg.edit.setPlainText("Hallo mooie wereld")
plain = text.layer.text
assert not plain.get("runs"), "zonder losse opmaak geen opmaakdelen"
select(dlg, 6, 11)  # "mooie"
dlg._merge(bold=True)
dlg._merge(color=QColor(220, 0, 0))
t = text.layer.text
assert t.get("runs") and len(t["runs"]) == 3, t.get("runs")
mid = t["runs"][1]
assert mid[3] == "mooie" and mid[0]["bold"] is True and tuple(mid[2]) == (220, 0, 0)
assert t["runs"][0][0]["bold"] is False and tuple(t["runs"][0][2]) == (0, 0, 0)
red = ink_cols(text.layer.image, 60, 110, lambda a: (a[..., 0] > 150) & (a[..., 1] < 80) & (a[..., 3] > 200))
black = ink_cols(text.layer.image, 60, 110, lambda a: (a[..., 0] < 60) & (a[..., 3] > 200))
assert len(red) > 20 and len(black) > 40 and red.min() > black.min() and red.max() < black.max()
print("1 'mooie' vet en rood, de rest zwart:", "rood x", red.min(), "..", red.max())
dlg.accept(); app.processEvents()
L = doc.layer(); assert L.text["text"] == "Hallo mooie wereld" and L.name == "Hallo mooie wereld"

# opnieuw bewerken: de opmaak komt terug in de editor
press(QPointF(60, 90))
dlg = text.dlg
assert dlg.edit.toPlainText() == "Hallo mooie wereld"
r = dlg.runs(text.layer.text)
assert r and r[1][3] == "mooie" and r[1][0]["bold"] and tuple(r[1][2]) == (220, 0, 0)
print("2 opnieuw bewerken: opmaak per woord blijft behouden")
# grootte en lettertype per woord, en de optiebalk blijft de basis voor de rest
select(dlg, 0, 5)
dlg._merge(size=60)
t = text.layer.text
assert t["runs"][0][3] == "Hallo" and t["runs"][0][0]["size"] == 60.0
w.opts["font_size"] = 30; text.refresh()
t = text.layer.text
assert t["runs"][0][0]["size"] == 60.0 and t["runs"][-1][0]["size"] == 30.0
print("3 grootte per woord; de optiebalk past de rest aan")
# opmaak wissen
select(dlg, 0, len("Hallo mooie wereld"))
dlg._clear_format()
assert not text.layer.text.get("runs")
print("4 opmaak wissen: weer één opmaak")
dlg.reject(); app.processEvents()

# verloop in de vulling
g = M.default_gradient(); g.update(preset="Zwart-wit", angle=90)  # van links (zwart) naar rechts (wit)
w.set_color(QColor(0, 0, 0), True); w.set_material(False, g)
press(QPointF(20, 180))
text.dlg.edit.setPlainText("IIIIIIIIIIIIIIIIIIIIIII")
img = text.layer.image
a = ops.qimage_to_rgba(img)
ys, xs = np.nonzero(a[..., 3] > 200)
left = a[ys[xs < xs.min() + 15], xs[xs < xs.min() + 15], 0].mean()
right = a[ys[xs > xs.max() - 15], xs[xs > xs.max() - 15], 0].mean()
assert left < 80 and right > 170, (left, right)
print("5 verloop in de tekst: links", round(left), "rechts", round(right))
text.dlg.accept(); app.processEvents()
# terug bewerken zet het materiaal terug in het palet
w.set_material(False, None)
press(QPointF(60, 165))
assert w.material(False) is not None and w.material(False)["preset"] == "Zwart-wit"
text.dlg.reject(); app.processEvents()
# patroon
w.set_material(False, M.default_pattern())
press(QPointF(20, 60))
text.dlg.edit.setPlainText("WWWW")
a = ops.qimage_to_rgba(text.layer.image)
cols = a[a[..., 3] > 200][:, :3]
assert len(np.unique(cols, axis=0)) > 3, "patroon geeft meerdere kleuren"
print("6 patroon in de tekst")
text.dlg.accept(); app.processEvents()
# ongedaan maken / kopiëren werkt met materiaal in de tekst
doc.undo(); doc.redo()
doc.set_modified(False)
print("ALLES OK")
