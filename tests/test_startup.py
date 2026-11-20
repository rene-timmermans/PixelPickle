"""Starting without an image: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_startup.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from pixelpickle.document import Document
from pixelpickle.mainwindow import MainWindow

w = MainWindow(); w.show(); app.processEvents()
assert w.tool is None and not w.tools_toolbar.isEnabled() and not w.opt_bar.isEnabled()
assert not any(b.isChecked() for b in w.group_buttons.values())
from PySide6.QtWidgets import QLabel
names = [l.toolTip() for l in w.opt_bar.findChildren(QLabel)]  # name is in the icon's tooltip
assert w.tools[0xd001].name in names and len(w.opt_bar.actions()) >= 2, names  # first start: Pan, gray
w.select_tool(w.tools[0xd040])  # shortcut without an image: just remember
assert w.tool is None and w.tools[0xd040].name in [l.toolTip() for l in w.opt_bar.findChildren(QLabel)]
sw = w.add_document(Document(100, 80)); app.processEvents()
assert w.tool is w.tools[0xd040] and w.tools_toolbar.isEnabled() and w.group_buttons[0xd040].isChecked()
w.select_tool(w.tools[0xd022])
sw.canvas.doc.set_modified(False); sw.close(); app.processEvents()
from PySide6.QtCore import QEvent; app.sendPostedEvents(None, QEvent.Type.DeferredDelete); app.processEvents()
assert w.tool is None and not w.tools_toolbar.isEnabled(), "after closing the last image"
print("1 without image OK")
w.close()
w2 = MainWindow(); w2.show(); app.processEvents()  # restart: last used tool
assert w2.tool is None
sw = w2.add_document(Document(50, 50)); app.processEvents()
assert w2.tool is w2.tools[0xd022], w2.tool.name
sw.canvas.doc.set_modified(False)
print("2 after restart OK")
a = w2.actions_by_id[0x81ba]  # Palettes > Tool options: check mark like the palettes
assert a.isCheckable() and a.isChecked()
a.trigger(); app.processEvents(); assert not w2.opt_bar.isVisible() and not a.isChecked()
a.trigger(); app.processEvents(); assert w2.opt_bar.isVisible() and a.isChecked()
print("3 options bar checkmark OK")
print("ALL OK")
