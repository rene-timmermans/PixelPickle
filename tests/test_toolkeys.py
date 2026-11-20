"""Tool shortcuts (letters from the keyboard layout): every letter selects its tool,
and no shortcut occurs twice (then it does not work at all in Qt):
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
assert not dupes, f"duplicate shortcuts: {dupes}"
print("1 no duplicate shortcuts (", len(count), "in total )")
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
print("2 all", n, "tool letters choose their tool")
fired = []
for cid in (0x80d5, 0xe102):
    w.actions_by_id[cid].triggered.connect(lambda _=False, c=cid: fired.append(c))
w.actions_by_id[0xe102].triggered.disconnect()  # do not really close
w.actions_by_id[0xe102].triggered.connect(lambda _=False: fired.append(0xe102))
QTest.keyClick(cv, Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier); app.processEvents()
QTest.keyClick(cv, Qt.Key.Key_F4, Qt.KeyboardModifier.ControlModifier); app.processEvents()
assert 0x80d5 in fired and 0xe102 in fired, fired
print("3 Ctrl+W (fit to image) and Ctrl+F4 (close) work")
d.set_modified(False)
print("ALL OK")
