"""Effectvenster met actieve selectie: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_effect_selection.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from pixelpickle.document import Document, new_image
from pixelpickle.effectdialog import EffectDialog
from pixelpickle.mainwindow import MainWindow

w = MainWindow()
doc = Document(400, 300, QColor(255, 255, 255)); w.add_document(doc); doc.add_layer()
lay = doc.layer(); lay.image = new_image(400, 300)
p = QPainter(lay.image); p.fillRect(150, 80, 150, 120, QColor(200, 120, 60)); p.end()
eff = w.effects[0x8052]
d = EffectDialog(w, doc, eff); assert not hasattr(d, "sel_note"), "geen selectie: geen melding"; d.reject()
m = QImage(400, 300, QImage.Format.Format_Alpha8)


def select(x, y, ww, hh):
    m.fill(0)
    q = QPainter(m); q.fillRect(x, y, ww, hh, QColor(0, 0, 0, 255)); q.end()
    doc.set_selection(QImage(m))


select(10, 220, 200, 70)  # selectie naast de inhoud van de laag (zoals bij de gebruiker)
d = EffectDialog(w, doc, eff); assert "buiten de inhoud" in d.sel_note.text(); d.reject()
select(100, 50, 150, 100)  # selectie over de inhoud
d = EffectDialog(w, doc, eff); assert d.sel_note.text().startswith("Alleen binnen de selectie"); d.reject()
doc.set_modified(False)
print("ALLES OK")
