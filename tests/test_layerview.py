"""Lagen > Beeld (welke lagen zichtbaar zijn): QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_layerview.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from pixelpickle.document import Document, Layer, new_image  # noqa: E402
from pixelpickle.mainwindow import MainWindow  # noqa: E402

w = MainWindow(); w.show()
d = Document(20, 10, QColor(255, 255, 255))
w.add_document(d); app.processEvents()
for name in ("a", "b", "c"):
    d.add_layer(Layer(name, new_image(20, 10, QColor(255, 0, 0))))
# b in een groep
d.active = 2; d.new_group()
names = lambda: {l.name: l.visible for l in d.layers}  # noqa: E731
b = next(l for l in d.layers if l.name == "b"); g = b.group
assert g is not None


def run(cid):
    w.actions_by_id[cid].trigger(); app.processEvents()


d.active = d.layers.index(b)
run(0x80ff)
vis = names()
assert vis["b"] and g.visible and not vis["a"] and not vis["c"] and not d.layers[0].visible, vis
print("1 Alleen huidige laag: alleen b (en zijn groep) zichtbaar", vis)
run(0x8176)
assert d.layers[0].visible and names()["a"] and names()["c"] and not b.visible and g.visible
print("2 Omkeren: de rest aan, b uit; groepen blijven aan")
run(0x8177); assert not any(l.visible for l in d.layers)
run(0x8100); assert all(l.visible for l in d.layers)
print("3 Geen en Alle lagen")
# koppelingsset: a en c
for l in d.layers:
    if l.name in ("a", "c"):
        l.link_set = 1
d.active = next(i for i, l in enumerate(d.layers) if l.name == "a")
run(0x8179)
assert not names()["a"] and not names()["c"] and b.visible and d.layers[0].visible
run(0x8178)
assert names()["a"] and names()["c"]
print("4 Koppelingset verbergen en weergeven: a en c samen")
n = len(d.undo_stack)
run(0x8100)  # alles al zichtbaar: geen extra stap
assert len(d.undo_stack) == n
d.undo(); assert not names()["a"] and not names()["c"]
print("5 ongedaan maken werkt, geen lege stap als er niets verandert")
assert all(cid in w.actions_by_id and w.actions_by_id[cid].isEnabled() for cid in (0x80ff, 0x8100, 0x8177, 0x8176, 0x8178, 0x8179))
d.set_modified(False)
print("ALLES OK")
