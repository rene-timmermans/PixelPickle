"""English language: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_i18n.py
Starts PixelPickle in English and looks for Dutch texts that are still on screen."""
import json
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QAbstractButton, QComboBox, QMenu

app = QApplication(sys.argv)
from pixelpickle import i18n
assert i18n.load("en") == "en"
i18n.install(app)
from pixelpickle.mainwindow import MainWindow
from pixelpickle.document import Document

cat = json.load(open(os.path.join(os.path.dirname(__file__), "..", "pixelpickle", "data", "lang_en.json"), encoding="utf-8"))
dutch = {k for k, v in cat.items() if v and v != k}
left = set()


def check(text, where):
    if text and text in dutch:
        left.add((text, where))


w = MainWindow(); w.show(); app.processEvents()
doc = Document(200, 150); w.add_document(doc); app.processEvents()
print("menu bar:", [a.text() for a in w.menuBar().actions()])
assert w.menuBar().actions()[0].text() == "&File", w.menuBar().actions()[0].text()
assert doc.layers[0].name == "Background" and doc.untitled.startswith("Image")


def walk_menu(m, path):
    m.popup(w.mapToGlobal(w.rect().center())); app.processEvents(); m.hide()
    for a in m.actions():
        if a.isSeparator():
            continue
        check(a.text(), path)
        if a.menu():
            walk_menu(a.menu(), path + " > " + a.text())


for a in w.menuBar().actions():
    walk_menu(a.menu(), a.text())
# every tool: option bar and status bar
for t in [t for t in w.tools.values() if t.available]:
    w.select_tool(t); app.processEvents()
    for c in w.opt_bar.findChildren(QWidget):
        if isinstance(c, (QLabel, QAbstractButton)):
            check(c.text(), "optiebalk " + t.name)
        if isinstance(c, QComboBox):
            for i in range(c.count()):
                check(c.itemText(i), "keuzelijst " + t.name)
    check(t.name, "gereedschap")
    msg = w.statusBar().currentMessage()
    for part in msg.split(": ", 1):
        check(part, "status " + t.name)
# an effect window
from pixelpickle.effectdialog import EffectDialog
dlg = EffectDialog(w, doc, w.effects[0x809e]); dlg.show(); app.processEvents()
for c in dlg.findChildren(QWidget):
    if isinstance(c, (QLabel, QAbstractButton)):
        check(c.text(), "effectvenster")
print("effect dialog title:", dlg.windowTitle(), "| labels:", [c.text() for c in dlg.findChildren(QLabel) if c.text()][:6])
dlg.reject()
print("status bar Magic Wand:", (w.select_tool(w.tools[0xd023]), w.statusBar().currentMessage())[1])
print("NOT TRANSLATED on screen:", len(left))
for t, wh in sorted(left)[:40]:
    print("  ", repr(t), "@", wh)
for s in w.mdi.subWindowList():
    s.canvas.doc.set_modified(False)
print("ALL OK" if not left else "NOTE: untranslated texts")
