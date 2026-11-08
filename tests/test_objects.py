"""Vectorobjecten: kiezen, uitlijnen, verdelen, even groot, schikken, groeperen, eigenschappen, tekst in
curven en tekst op een pad: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_objects.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QMenu  # noqa: E402

app = QApplication(sys.argv)
shown = []


class RecordingMenu(QMenu):
    def exec(self, *a, **k):
        shown.append([x.text() for x in self.actions() if not x.isSeparator()])


import pixelpickle.mainwindow as mw  # noqa: E402
mw.QMenu = RecordingMenu
from pixelpickle import dialogs, vectorlayer as V, vectorops as VO  # noqa: E402
from pixelpickle.document import Document, Layer, new_image  # noqa: E402
from pixelpickle.mainwindow import MainWindow  # noqa: E402
from pixelpickle.textlayer import new_text  # noqa: E402

w = MainWindow(); w.show()
doc = Document(400, 300, QColor(255, 255, 255)); cv = w.add_document(doc).canvas; app.processEvents()
assert "Objecten" in w.top_menus
lay = doc.new_vector_layer("Vormen", undo=False)


def rect(x, y, ww, hh, col=(255, 0, 0, 255)):
    pts = [QPointF(x, y), QPointF(x + ww, y), QPointF(x + ww, y + hh), QPointF(x, y + hh)]
    return V.make_object([[p, None, None] for p in pts], True, [0, 0, 0, 255], list(col), 1)


lay.vector += [rect(10, 10, 40, 30), rect(100, 60, 20, 20), rect(200, 120, 60, 50)]
doc.render_vector(lay)
pick = w.tools[0xd011]
w.select_tool(pick)
LB = Qt.MouseButton.LeftButton


def ev(kind, pt, mods=Qt.KeyboardModifier.NoModifier, btn=LB):
    p = cv.to_widget(pt)
    held = btn if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    return QMouseEvent(kind, p, cv.mapToGlobal(p.toPoint()), btn, held, mods)


def click(pt, mods=Qt.KeyboardModifier.NoModifier):
    pick.press(cv, pt, ev(QEvent.Type.MouseButtonPress, pt, mods))
    pick.release(cv, pt, ev(QEvent.Type.MouseButtonRelease, pt, mods))


def drag(a, b, mods=Qt.KeyboardModifier.NoModifier):
    pick.press(cv, a, ev(QEvent.Type.MouseButtonPress, a, mods))
    pick.move(cv, b, ev(QEvent.Type.MouseMove, b, mods))
    pick.release(cv, b, ev(QEvent.Type.MouseButtonRelease, b, mods))


# kiezen: klik, Shift+klik, kader
click(QPointF(30, 25)); assert doc.vsel == [0]
click(QPointF(110, 70), Qt.KeyboardModifier.ShiftModifier); assert doc.vsel == [0, 1]
click(QPointF(350, 280)); assert doc.vsel == []
drag(QPointF(5, 5), QPointF(130, 90)); assert sorted(doc.vsel) == [0, 1]
print("1 Kiezen: klik, Shift+klik, leeg vlak, kader", doc.vsel)
# verplaatsen van de gekozen objecten
b0 = VO.obj_bounds(lay.vector[1])
drag(QPointF(110, 70), QPointF(130, 80))
b1 = VO.obj_bounds(lay.vector[1])
assert round(b1.x() - b0.x()) == 20 and round(VO.obj_bounds(lay.vector[2]).x()) == 200
print("2 slepen verplaatst alleen de gekozen objecten")
run = lambda cid: w.actions_by_id[cid].trigger()  # noqa: E731
doc.vsel = [0, 1, 2]
run(0x8163)  # uitlijnen boven
assert len({round(VO.obj_bounds(o).top()) for o in lay.vector}) == 1
run(0x8162)  # horizontaal centreren
cx = {round(VO.obj_bounds(o).center().x()) for o in lay.vector}
assert len(cx) == 1, cx
doc.undo(); doc.undo()
lay = doc.layer()  # na ongedaan maken zijn de lagen nieuwe kopieën
print("3 Uitlijnen boven en horizontaal centreren")
doc.vsel = [0, 1, 2]
run(0x816f)  # horizontaal gelijkmatig verdelen
bs = sorted((VO.obj_bounds(o) for o in lay.vector), key=lambda b: b.left())
g1, g2 = bs[1].left() - bs[0].right(), bs[2].left() - bs[1].right()
assert abs(g1 - g2) < 0.01, (g1, g2)
print("4 Verdelen: gelijke tussenruimte", round(g1, 1))
doc.vsel = [2, 0]
run(0x816b)  # even groot (beide), maat = eerst gekozen (2)
assert round(VO.obj_bounds(lay.vector[0]).width()) == 60 and round(VO.obj_bounds(lay.vector[0]).height()) == 50
print("5 Even groot maken naar het eerst gekozen object")
doc.vsel = [0]
run(0x8139)  # vooraan
assert doc.vsel == [2] and round(VO.obj_bounds(lay.vector[2]).width()) == 60
print("6 Schikken: vooraan")
doc.vsel = [0, 1]
run(0x8154)  # groeperen
assert lay.vector[0].get("group") and lay.vector[0]["group"] == lay.vector[1]["group"]
doc.vsel = []; click(QPointF(VO.obj_bounds(lay.vector[0]).center()))
assert sorted(doc.vsel) == [0, 1]
run(0x8156); assert "group" not in lay.vector[0]
print("7 Groeperen: klik kiest de hele groep; groep opheffen")
# eigenschappen
orig_exec = dialogs.VectorPropertiesDialog.exec


def fake_exec(self):
    self.width.setValue(5)
    self.colors["fill"][2].setChecked(True)
    return QDialog.DialogCode.Accepted


dialogs.VectorPropertiesDialog.exec = fake_exec
doc.vsel = [0]
run(0x81e6)
assert lay.vector[0]["width"] == 5 and lay.vector[0]["fill"] is None
print("8 Eigenschappen: breedte en geen vulling")
# snelmenu bij Kiezen
cv.mousePressEvent(ev(QEvent.Type.MouseButtonPress, QPointF(390, 290), btn=Qt.MouseButton.RightButton))
cv.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(390, 290), btn=Qt.MouseButton.RightButton))
items = shown[-1]
assert "Knippen" in items and "Rasterselectie maken" in items and any("Uitlijnen" in x for x in items), items
print("9 snelmenu vectorobjecten:", items)
pick.object_edit("raster_selection", cv); assert doc.sel is not None
pick.object_edit("copy", cv); pick.object_edit("paste", cv); assert len(lay.vector) == 4
doc.set_selection(None)
# tekst in curven
tl = Layer("Tekst", new_image(400, 300))
w.opts.update(font_size=40, text_units=1, text_stroke=0)
tl.text = new_text("Ok", 20, 250, w.opts, QColor(0, 0, 0), QColor(0, 0, 200))
doc.add_layer(tl); doc.render_text(tl)
run(0x814d)  # als afzonderlijke lettervormen
assert tl.text is None and tl.vector is not None and len(tl.vector) == 2
assert tl.vector[0].get("more"), "de O heeft een gat (samengesteld object)"
inside_hole = V.qpath(tl.vector[0]).boundingRect().center()
assert not V.qpath(tl.vector[0]).contains(inside_hole), "het gat van de O blijft open"
doc.undo()
run(0x814c); assert len(doc.layer().vector) == 1
doc.undo()
lay = next(l for l in doc.layers if l.name == "Vormen")
print("10 Tekst omzetten in curven: per letter (O met gat) en als één vorm")
# tekst op een pad
doc.active = doc.layers.index(lay)
lay.vector.append(V.make_object([[QPointF(20, 200), None, QPointF(150, 100)], [QPointF(380, 200), QPointF(250, 100), None]],
                                False, [0, 0, 0, 255], None, 1))
doc.vsel = [len(lay.vector) - 1]
run(0x813d)
tl2 = next(l for l in doc.layers if l.text is not None)
assert tl2.text.get("on_path")
from pixelpickle.textlayer import bounds  # noqa: E402
r = bounds(tl2.text)
assert r.width() > 30 and r.top() < 200, r
doc.active = doc.layers.index(tl2)
run(0x1793); assert not tl2.text.get("on_path")
print("11 Tekst inpassen in pad en weer loskoppelen")
doc.set_modified(False)
print("ALLES OK")
