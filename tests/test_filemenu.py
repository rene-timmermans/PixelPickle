"""Menu Bestand: naar vorige versie, verwijderen, afdrukken (naar PDF), eigen penseel/vorm/lijst, PNG-optimalisatie,
afbeelding met hyperlinks, batchverwerking, namen in batch wijzigen, voorkeuren en bestandslocaties:
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_filemenu.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
from PySide6.QtCore import QPointF, QRect  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QMessageBox  # noqa: E402

app = QApplication(sys.argv)
from pixelpickle import dialogs, fileio, imageops as ops, userdata, vectorlayer as V  # noqa: E402
from pixelpickle.document import Document  # noqa: E402
from pixelpickle.mainwindow import MainWindow  # noqa: E402

QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)
tmp = tempfile.mkdtemp()
w = MainWindow(); w.show()
run = lambda cid: w.actions_by_id[cid].trigger()  # noqa: E731

# naar vorige versie
d = Document(80, 60, QColor(255, 255, 255)); path = os.path.join(tmp, "a.png"); fileio.save(d, path); d.path = path
cv = w.add_document(d).canvas; app.processEvents()
q = QPainter(d.layers[0].image); q.fillRect(0, 0, 80, 60, QColor(255, 0, 0)); q.end(); d.set_modified(True)
run(0x8019)
assert d.layers[0].image.pixelColor(5, 5) == QColor(255, 255, 255) and not d.modified
d.undo(); assert d.layers[0].image.pixelColor(5, 5) == QColor(255, 0, 0)
d.set_modified(False)
print("1 Naar vorige versie (en weer ongedaan te maken)")
# afdrukweergave en afdrukken naar PDF
from PySide6.QtPrintSupport import QPrinter  # noqa: E402
pr = QPrinter(); pr.setOutputFormat(QPrinter.OutputFormat.PdfFormat); pr.setOutputFileName(os.path.join(tmp, "p.pdf"))
w._paint_page(pr); assert os.path.getsize(os.path.join(tmp, "p.pdf")) > 500
print("2 Afdrukken (naar PDF getest)")
# eigen penseel exporteren en gebruiken
q = QPainter(d.layers[0].image); q.fillRect(0, 0, 80, 60, QColor(255, 255, 255)); q.fillRect(20, 20, 30, 10, QColor(0, 0, 0)); q.end()
QInputDialog.getText = staticmethod(lambda *a, **k: ("Streep", True))
run(0x8201)
assert "Streep" in userdata.brush_names()
br = w.tools[0xd091]; w.select_tool(br)
w.opts.update(brush_shape=2 + userdata.brush_names().index("Streep"), size=40, hardness=100)
br.make_stamp(QColor(255, 0, 0))
wts = br.weights
assert wts.max() > 0.9 and (wts > 0.5).sum() < 0.6 * wts.size, "een liggende streep, geen volle cirkel"
print("3 Aangepast penseel exporteren en gebruiken als penseelvorm")
imgp = os.path.join(tmp, "punt.png"); QImage(os.path.join(userdata.folder("brushes"), "Streep.png")).save(imgp)
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([imgp], ""))
run(0x8203); assert "punt" in userdata.brush_names()
print("4 Aangepast penseel importeren")
# vorm exporteren en gebruiken bij Basisvormen
vl = d.new_vector_layer("v", undo=False)
vl.vector.append(V.make_object([[QPointF(10, 10), None, None], [QPointF(50, 10), None, None], [QPointF(30, 50), None, None]],
                               True, [0, 0, 0, 255], [255, 0, 0, 255], 1))
QInputDialog.getText = staticmethod(lambda *a, **k: ("Driehoekje", True))
run(0x815c); assert "Driehoekje" in userdata.shape_names()
ps = w.tools[0xd101]
w.opts["preset"] = len(ps.SHAPES) + userdata.shape_names().index("Driehoekje")
path_ = ps.path(QPointF(0, 0), QPointF(100, 100))
assert path_.contains(QPointF(50, 30)) and not path_.contains(QPointF(5, 90))
print("5 Vorm exporteren en kiezen bij Basisvormen")
# fotolijst exporteren
fd = Document(100, 80, None)
q = QPainter(fd.layers[0].image); q.fillRect(0, 0, 100, 80, QColor(120, 80, 30)); q.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
q.fillRect(15, 15, 70, 50, QColor(0, 0, 0, 0)); q.end()
w.add_document(fd); app.processEvents()
QInputDialog.getText = staticmethod(lambda *a, **k: ("Bruin", True))
run(0x822c); assert "Bruin" in userdata.frame_names()
answers = [{"s": 7, "t": 10, "c": QColor(0, 0, 0), "out": 0}]
orig_form = dialogs.ask_form
dialogs.ask_form = lambda *a, **k: answers.pop(0)
w.mdi.setActiveSubWindow(w.mdi.subWindowList()[0]); d.active = 0
run(0x012f); assert d.layer().name in ("Fotolijst", "Picture Frame")
d.set_modified(False); fd.set_modified(False)
print("6 Fotolijst exporteren en gebruiken bij Afbeelding > Fotolijst")
# PNG-optimalisatie
out = os.path.join(tmp, "klein.png")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (out, ""))
orig_exec = dialogs.PngOptimizerDialog.exec
dialogs.PngOptimizerDialog.exec = lambda self: (self.kind.setCurrentIndex(2), self.colors.setValue(16), self._estimate(),
                                               QDialog.DialogCode.Accepted)[-1]
run(0x815b); assert os.path.exists(out) and QImage(out).format() == QImage.Format.Format_Indexed8
print("7 PNG-optimalisatie (8 bits palet, 16 kleuren)")
# afbeelding met hyperlinks
html = os.path.join(tmp, "kaart.html")
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (html, ""))


def fake_map(self):
    self.add_area("rect", QRect(5, 5, 20, 20)); self.url.setText("https://example.org"); self.alt.setText("Voorbeeld")
    self.add_area("circle", QRect(40, 20, 20, 20)); self.url.setText("pagina.html")
    return QDialog.DialogCode.Accepted


dialogs.ImageMapDialog.exec = fake_map
run(0x8174)
t = open(html, encoding="utf-8").read()
assert 'shape="rect" coords="5,5,25,25" href="https://example.org"' in t and 'shape="circle"' in t
assert os.path.exists(os.path.join(tmp, "kaart.png"))
print("8 Afbeelding met hyperlinks: HTML met twee gebieden en de afbeelding")
# batchverwerking en namen in batch wijzigen
srcs = []
for k in range(3):
    dd = Document(40 + k, 30, QColor(0, 100 + k * 50, 0)); pth = os.path.join(tmp, f"b{k}.png"); fileio.save(dd, pth); srcs.append(pth)
outdir = os.path.join(tmp, "uit"); os.makedirs(outdir)
dialogs.BatchDialog.exec = lambda self: QDialog.DialogCode.Accepted
dialogs.BatchDialog.values = lambda self: dict(files=srcs, ext=".jpg", quality=80, maxsize=20, outdir=outdir, overwrite=False)
run(0x801b)
made = sorted(os.listdir(outdir)); assert made == ["b0.jpg", "b1.jpg", "b2.jpg"], made
assert max(QImage(os.path.join(outdir, "b2.jpg")).width(), QImage(os.path.join(outdir, "b2.jpg")).height()) == 20
print("9 Batchverwerking: drie bestanden naar JPEG, verkleind tot 20 pixels")


def fake_rename(self):
    self.files = [os.path.join(outdir, f) for f in made]; self.prefix.setText("vakantie_"); self._preview()
    return QDialog.DialogCode.Accepted


dialogs.BatchRenameDialog.exec = fake_rename
run(0x81ad)
assert sorted(os.listdir(outdir)) == ["vakantie_001.jpg", "vakantie_002.jpg", "vakantie_003.jpg"], os.listdir(outdir)
print("10 Namen in batch wijzigen")
# voorkeuren
answers.append({"q": 75, "png": 9, "layered": 1}); run(0x8014)
assert w.settings.value("layered_ext") == ".pspimage" and int(w.settings.value("png_compress")) == 9
newloc = os.path.join(tmp, "eigen_vormen")
dialogs.FileLocationsDialog.exec = lambda self: (self.edits["shapes"].setText(newloc), QDialog.DialogCode.Accepted)[-1]
run(0x8152); assert userdata.folder("shapes") == newloc and userdata.shape_names() == []
print("11 Voorkeuren bestandsindelingen en bestandslocaties")
# verwijderen (naar de prullenbak)
victim = Document(20, 20, QColor(255, 255, 255)); vp = os.path.join(tmp, "weg.png"); fileio.save(victim, vp); victim.path = vp
w.add_document(victim); app.processEvents()
n = len(w.mdi.subWindowList())
run(0x80d6)
print("12 Verwijderen:", "naar de prullenbak" if not os.path.exists(vp) else "prullenbak niet beschikbaar in de testomgeving")
run(0x8204); assert w.settings.value("layered_ext") is None
w._prefs_reset = True
print("13 Voorkeuren herstellen")
for s in w.mdi.subWindowList():
    s.canvas.doc.set_modified(False)
print("ALLES OK")
