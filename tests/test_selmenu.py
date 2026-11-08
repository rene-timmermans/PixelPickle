"""Menu Selecties: vanuit vectorobject, dezelfde kleur, kleurbereik, doezelen, anti-alias, stippen en gaten,
vloeiend, selectieranden, laden/opslaan op schijf, selectie bewerken, zwevend:
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_selmenu.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtGui import QColor, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

app = QApplication(sys.argv)
from pixelpickle import dialogs, imageops as ops, vectorlayer as V  # noqa: E402
from pixelpickle.document import Document  # noqa: E402
from pixelpickle.mainwindow import MainWindow  # noqa: E402

answers = []
dialogs.ask_form = lambda *a, **k: answers.pop(0)
import pixelpickle.mainwindow as mw  # noqa: E402
w = MainWindow(); w.show()
d = Document(100, 80, QColor(255, 255, 255)); cv = w.add_document(d).canvas; app.processEvents()
p = QPainter(d.layers[0].image)
p.fillRect(10, 10, 20, 20, QColor(255, 0, 0)); p.fillRect(60, 10, 20, 20, QColor(250, 5, 5)); p.fillRect(40, 50, 10, 10, QColor(0, 0, 255))
p.end()
run = lambda cid: w.actions_by_id[cid].trigger()  # noqa: E731
sel = lambda: ops.qimage_to_mask(d.sel) if d.sel is not None else None  # noqa: E731
rect = lambda x, y, ww, hh: d.set_selection(ops.mask_to_qimage(  # noqa: E731
    np.pad(np.full((hh, ww), 255, np.uint8), ((y, 80 - y - hh), (x, 100 - x - ww)))))

rect(12, 12, 5, 5)
answers.append({"tol": 10, "cont": False, "merged": False}); run(0x8114)
m = sel(); assert m[15, 65] == 255 and m[15, 20] == 255 and m[55, 45] == 0 and m[5, 5] == 0
answers.append({"tol": 10, "cont": True, "merged": False}); rect(12, 12, 5, 5); run(0x8114)
m = sel(); assert m[15, 20] == 255 and m[15, 65] == 0
print("1 Alles met dezelfde kleur: overal, en aaneengesloten alleen het eigen vlak")
d.set_selection(None)
answers.append({"color": QColor(0, 0, 255), "tol": 10, "soft": 0, "mode": 0, "merged": False}); run(0x81eb)
m = sel(); assert m[55, 45] == 255 and m[15, 20] == 0
print("2 Kleurbereik selecteren")
rect(20, 20, 40, 30)
answers.append({"n": 6, "side": 0}); run(0x8193)
m = sel(); assert 0 < m[20, 40] < 255 and m[35, 40] == 255 and m[15, 40] == 0
answers.append({"t": 50}); run(0x81ee)
assert set(np.unique(sel())) <= {0, 255}
print("3 Binnen doezelen en doezelen opheffen")
answers.append({"w": 1}); run(0x81e8); assert len(np.unique(sel())) > 2
run(0x81e7)
print("4 Op vorm gebaseerde anti-alias en anti-alias herstellen")
mm = np.zeros((80, 100), np.uint8); mm[20:50, 20:60] = 255; mm[30:33, 30:33] = 0; mm[70, 90] = 255
d.set_selection(ops.mask_to_qimage(mm))
answers.append({"what": 2, "size": 20}); run(0x81f6)
m = sel(); assert m[31, 31] == 255 and m[70, 90] == 0
answers.append({"n": 4}); run(0x81f5)
answers.append({"w": 4, "side": 0, "aa": False}); run(0x81ec)
m = sel(); assert m[21, 40] == 255 and m[35, 40] == 0
print("5 Stippen en gaten, Vloeiend, Selectieranden")
run(0x8283); assert d.sel is not None
# laden en opslaan op schijf
path = os.path.join(tempfile.mkdtemp(), "sel.png")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (path, ""))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (path, ""))
before = sel().copy()
run(0x80df); assert os.path.exists(path)
d.set_selection(None); run(0x80de)
assert np.array_equal(sel() > 127, before > 127)
print("6 Selectie opslaan op schijf en weer laden")
# selectie bewerken: rood tonen, op de laag schilderen, terug naar selectie
rect(10, 10, 20, 20)
run(0x81f4)
lay = d.seledit_layer(); assert lay is not None and d.sel is None and w.actions_by_id[0x81f4].isChecked()
assert cv._ruby() is not None
c = d.composite(); assert c.pixelColor(15, 15) == QColor(255, 0, 0), "de bewerklaag zit niet in de afbeelding zelf"
q = QPainter(lay.image); q.fillRect(50, 50, 10, 10, QColor(255, 255, 255)); q.end()
run(0x81f4)
m = sel(); assert d.seledit_layer() is None and m[15, 15] == 255 and m[55, 55] == 255 and m[40, 40] == 0
print("7 Selectie bewerken: wit erbij geschilderd wordt geselecteerd")
# zwevend en niet-zwevend
d.active = 0
rect(10, 10, 20, 20)
n = len(d.layers)
run(0x80e4)
assert len(d.layers) == n + 1 and d.layer().role == "floating"
assert d.layers[0].image.pixelColor(15, 15) == QColor(255, 255, 255), "gat in de achtergrond gevuld met achtergrondkleur"
assert d.layer().image.pixelColor(15, 15) == QColor(255, 0, 0)
run(0x80e5)
assert len(d.layers) == n and d.layers[0].image.pixelColor(15, 15) == QColor(255, 0, 0)
print("8 Zwevend en niet-zwevend")
# vanuit vectorobject
vl = d.new_vector_layer("v", undo=False)
vl.vector.append(V.make_object([[QPointF(5, 5), None, None], [QPointF(40, 5), None, None], [QPointF(40, 40), None, None]],
                               True, None, [0, 0, 0, 255], 1))
d.set_selection(None); run(0x8001)
m = sel(); assert m[10, 30] == 255 and m[35, 10] == 0
print("9 Selectie vanuit vectorobject")
d.set_modified(False)
print("ALLES OK")
