"""Help-vensters en automatisch opslaan: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_help.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QTextBrowser

app = QApplication(sys.argv)
from pixelpickle import autosave
from pixelpickle.document import Document
from pixelpickle.mainwindow import MainWindow

shown = []
QDialog.exec = lambda self: (shown.append(self), self.accept())[1] or 1
w = MainWindow(); w.show(); app.processEvents()

# 1. menu: handleiding, info en toetsenbordlayout zijn verschillende vensters
names = {cid: w.actions_by_id[cid].text() for cid in (0xe142, 0xe140, 0x8028, 0x8151)}
print(names)
assert names[0xe142] == "&Gebruikershandleiding..." and all(w.actions_by_id[c].isEnabled() for c in names)
w.actions_by_id[0x8028].trigger(); keys = shown[-1]
tb = keys.findChild(QTextBrowser); assert tb and "Ctrl+N" in tb.toPlainText() and keys.isSizeGripEnabled()
w.actions_by_id[0xe140].trigger(); about = shown[-1]
from PySide6.QtWidgets import QLabel
txt = " ".join(l.text() for l in about.findChildren(QLabel))
assert "René Timmermans" in txt and "GNU General Public License" in txt and "github.com" in txt, txt
html = w.manual_html(); assert "{tools}" not in html and "<table" in html and "Penseel" in html
w.show_manual(); app.processEvents()
assert type(about) is not type(keys)
print("1 help OK")

# 2. instellingen automatisch opslaan
w.autosave_settings(); dlg = shown[-1]
assert not dlg.enabled.isChecked() and dlg.minutes.value() == 5 and not w.autosaver.timer.isActive()
w.settings.setValue("autosave/enabled", "true"); w.settings.setValue("autosave/minutes", 2); w.autosaver.apply_settings()
assert w.autosaver.timer.isActive() and w.autosaver.timer.interval() == 120000
print("2 instellingen OK")

# 3. bewaren, opruimen, herstellen
d1 = Document(60, 40, QColor(255, 0, 0)); w.add_document(d1); d1.set_modified(True)
d2 = Document(30, 30); w.add_document(d2)
w.autosaver.tick()
files = os.listdir(w.autosaver.dir); assert len([f for f in files if f.endswith(".ora")]) == 1, files
d1.set_modified(False); w.autosaver.tick(); assert not [f for f in os.listdir(w.autosaver.dir) if f.endswith(".ora")]
d1.set_modified(True); w.autosaver.tick()
# doen alsof dit proces gecrasht is: map onder een niet-bestaand procesnummer
crashed = os.path.join(autosave.base_dir(), "999999")
os.rename(w.autosaver.dir, crashed); w.autosaver.saved.clear()
found = autosave.leftovers(); assert len(found) == 1 and found[0][1][0]["title"] == d1.untitled, found
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
n = len(w.mdi.subWindowList()); w.offer_recovery(); app.processEvents()
assert len(w.mdi.subWindowList()) == n + 1 and not os.path.exists(crashed)
rec = w.canvas().doc; assert rec.modified and rec.layers[0].image.pixelColor(5, 5) == QColor(255, 0, 0)
print("3 herstel OK")
for s in w.mdi.subWindowList():
    s.canvas.doc.set_modified(False)
w.close(); assert not os.path.exists(w.autosaver.dir)
print("ALLES OK")
