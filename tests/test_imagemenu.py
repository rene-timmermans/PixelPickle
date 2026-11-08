"""Menu Afbeelding: kleurdiepte verminderen, kanalen splitsen en combineren, berekeningen, fotolijst:
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_imagemenu.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from pixelpickle import dialogs, imageops as ops  # noqa: E402
from pixelpickle.document import Document  # noqa: E402
from pixelpickle.mainwindow import MainWindow  # noqa: E402

answers = []
dialogs.ask_form = lambda *a, **k: answers.pop(0)
w = MainWindow(); w.show()


def gradient_doc(wd=120, ht=80):
    d = Document(wd, ht, QColor(255, 255, 255))
    yy, xx = np.mgrid[0:ht, 0:wd]
    a = np.dstack([xx * 255 // wd, yy * 255 // ht, 255 - xx * 255 // wd, np.full_like(xx, 255)]).astype(np.uint8)
    d.layers[0].image = ops.rgba_to_qimage(a)
    w.add_document(d); app.processEvents()
    return d


run = lambda cid: w.actions_by_id[cid].trigger()  # noqa: E731
cols = lambda d: len(np.unique(ops.qimage_to_rgba(d.layers[0].image)[..., :3].reshape(-1, 3), axis=0))  # noqa: E731
d = gradient_doc()
n0 = cols(d)
answers.append({"pal": 0, "m": 1}); run(0x8059)
assert cols(d) <= 16, cols(d)
d.undo(); answers.append({"n": 8, "pal": 0, "m": 0}); run(0x805d); assert cols(d) <= 8
d.undo(); answers.append({"m": 1}); run(0x8058); assert cols(d) == 2
d.undo(); answers.append({"m": 0}); run(0x805b); assert cols(d) < n0
d.undo(); answers.append({"pal": 1, "m": 2}); run(0x805a); assert cols(d) <= 256
print("1 Kleurdiepte verminderen: 16, X (8), 2, 32.000 en 256 kleuren (van", n0, "kleuren)")
before = ops.qimage_to_rgba(d.layers[0].image).copy()
nd = len(w.mdi.subWindowList())
run(0x80f3)
assert len(w.mdi.subWindowList()) == nd + 3
answers.append({"0": nd, "1": nd + 1, "2": nd + 2}); run(0x80f4)
res = ops.qimage_to_rgba(w.doc().layers[0].image)
assert np.array_equal(res[..., :3], before[..., :3])
print("2 Splitsen in RGB en weer combineren geeft hetzelfde beeld")
w.mdi.setActiveSubWindow(w.mdi.subWindowList()[0])
run(0x8118); docs = [s.canvas.doc for s in w.mdi.subWindowList()]
answers.append({str(k): len(docs) - 4 + k for k in range(4)}); run(0x8123)
res = ops.qimage_to_rgba(w.doc().layers[0].image).astype(int)
assert np.abs(res[..., :3] - before[..., :3]).max() <= 2
print("3 CMYK splitsen en combineren (afwijking hoogstens 2)")
docs = [s.canvas.doc for s in w.mdi.subWindowList()]
answers.append({"a": 0, "b": 0, "f": 3, "c": 0, "div": 1, "bias": 0, "clip": True}); run(0x80f2)
assert ops.qimage_to_rgba(w.doc().layers[0].image)[..., :3].max() == 0, "verschil met zichzelf is zwart"
answers.append({"a": 0, "b": 0, "f": 0, "c": 1, "div": 2, "bias": 10, "clip": True}); run(0x80f2)
print("4 Berekeningen")
for s in w.mdi.subWindowList():
    s.canvas.doc.set_modified(False)
# fotolijsten
S = "/tmp/claude-1000/-home-deck/229d952d-2ed1-4a89-a046-e18bd43cc32f/scratchpad"
tiles = []
for style in range(7):
    fd = gradient_doc(160, 110)
    answers.append({"s": style, "t": 14, "c": QColor(70, 45, 25), "out": 1 if style in (5,) else 0}); run(0x012f)
    assert len(fd.undo_stack) == 1, "fotolijst is één stap ongedaan maken"
    tiles.append(ops.qimage_to_rgba(fd.flattened(QColor(255, 255, 255))))
    if style == 5:
        assert fd.h == 110 + 14 * 4 and fd.w == 160 + 28
    fd.set_modified(False)
from PIL import Image  # noqa: E402
H = max(t.shape[0] for t in tiles)
canvas = np.full((H, sum(t.shape[1] + 6 for t in tiles), 4), 90, np.uint8)
x = 0
for t in tiles:
    canvas[:t.shape[0], x:x + t.shape[1]] = t
    x += t.shape[1] + 6
if os.path.isdir(S):
    Image.fromarray(canvas).save(S + "/frames.png")
print("5 Fotolijsten: alle zeven stijlen, polaroid buiten de afbeelding")
print("ALLES OK")
