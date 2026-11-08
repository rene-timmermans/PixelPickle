"""Sneltoetsen van de gereedschappen (letters uit de toetsenbordindeling): elke letter kiest zijn gereedschap,
en geen enkele sneltoets komt dubbel voor (dan werkt hij in Qt helemaal niet):
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_toolkeys.py"""
import os
import sys
import tempfile
from collections import Counter
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QAction, QColor  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from pixelpickle.document import Document  # noqa: E402
from pixelpickle.mainwindow import MainWindow  # noqa: E402

w = MainWindow(); w.show()
d = Document(50, 50, QColor(255, 255, 255)); cv = w.add_document(d).canvas; app.processEvents()
cv.setFocus(); app.processEvents()
count = Counter(s.toString() for a in w.findChildren(QAction) for s in a.shortcuts())
dupes = [k for k, n in count.items() if n > 1]
assert not dupes, f"dubbele sneltoetsen: {dupes}"
print("1 geen dubbele sneltoetsen (", len(count), "in totaal )")
bad, n = [], 0
for cid, keys in w.tool_keys.items():
    t = w.tools.get(cid)
    if t is None or not t.available:
        continue
    n += 1
    QTest.keyClick(cv, getattr(Qt.Key, "Key_" + keys[0])); app.processEvents()
    if w.tool is not t:
        bad.append((keys[0], t.name, w.tool.name))
assert not bad, bad
print("2 alle", n, "gereedschapsletters kiezen hun gereedschap")
fired = []
for cid in (0x80d5, 0xe102):
    w.actions_by_id[cid].triggered.connect(lambda _=False, c=cid: fired.append(c))
w.actions_by_id[0xe102].triggered.disconnect()  # niet echt sluiten
w.actions_by_id[0xe102].triggered.connect(lambda _=False: fired.append(0xe102))
QTest.keyClick(cv, Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier); app.processEvents()
QTest.keyClick(cv, Qt.Key.Key_F4, Qt.KeyboardModifier.ControlModifier); app.processEvents()
assert 0x80d5 in fired and 0xe102 in fired, fired
print("3 Ctrl+W (aanpassen aan afbeelding) en Ctrl+F4 (sluiten) werken")
d.set_modified(False)
print("ALLES OK")
