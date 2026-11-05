"""Rooktest zonder scherm: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/smoke.py"""
import os, sys, tempfile, time
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()  # echte instellingen niet aanraken
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QPointF, Qt, QEvent, QTimer, QRect
from PySide6.QtGui import QMouseEvent, QColor, QImage
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QInputDialog
app = QApplication(sys.argv)

# dialoogvensters automatisch bevestigen
QDialog.exec = lambda self: (self.accept() if hasattr(self, "accept") else None) or 1
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.about = staticmethod(lambda *a, **k: None)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
QInputDialog.getInt = staticmethod(lambda *a, **k: (3, True))
from PySide6.QtWidgets import QFileDialog
_TMP = tempfile.mkdtemp()
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (os.path.join(_TMP, "export"), ""))
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([], ""))
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("Hallo\nwereld", True))

from brushwork.mainwindow import MainWindow
from brushwork.document import Document
from brushwork import fileio, imageops as ops

w = MainWindow(); w.show(); app.processEvents()
doc = Document(400, 300); sw = w.add_document(doc); app.processEvents()
cv = sw.canvas
P = QPointF


def ev(t, pos, btn=Qt.MouseButton.LeftButton, mods=Qt.KeyboardModifier.NoModifier):
    buttons = btn if t != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    return QMouseEvent(t, QPointF(pos), QPointF(pos), btn, buttons, mods)


def drag(tool, pts, **kw):
    w.select_tool(tool)
    tool.press(cv, pts[0], ev(QEvent.Type.MouseButtonPress, cv.to_widget(pts[0]), **kw))
    for p in pts[1:]:
        tool.move(cv, p, ev(QEvent.Type.MouseMove, cv.to_widget(p), **kw))
    tool.release(cv, pts[-1], ev(QEvent.Type.MouseButtonRelease, cv.to_widget(pts[-1]), **kw))
    app.processEvents()


T = w.tools
t0 = time.time()
# --- kernscenario met controles
w.set_color(QColor(255, 0, 0))
drag(T[0xd091], [P(20, 20), P(200, 150), P(380, 20)])
assert doc.layers[0].image.pixelColor(110, 85) == QColor(255, 0, 0), doc.layers[0].image.pixelColor(110, 85).name()
drag(T[0xd021], [P(50, 50), P(150, 120)])
assert doc.selection_bbox().width() == 100
w.set_color(QColor(0, 0, 255))
drag(T[0xd0d1], [P(60, 60)])
assert doc.layers[0].image.pixelColor(60, 60) == QColor(0, 0, 255)
assert doc.layers[0].image.pixelColor(10, 200) == QColor(255, 255, 255)
drag(T[0xd021], [P(60, 60), P(80, 70)])          # binnen selectie slepen = pixels verplaatsen
assert doc.selection_bbox().x() == 70, doc.selection_bbox()
assert doc.layers[0].image.pixelColor(60, 55) == QColor(255, 255, 255)  # gat = achtergrondkleur
w.select_none()

# --- nieuwe functies
lasso = T[0xd022]
for typ in (1, 2, 3):
    w.opts["lasso_type"] = typ
    w.select_tool(lasso)
    for q in (P(60, 40), P(200, 60), P(220, 200), P(70, 210)):
        lasso.press(cv, q, ev(QEvent.Type.MouseButtonPress, cv.to_widget(q)))
        lasso.move(cv, q + P(5, 5), ev(QEvent.Type.MouseMove, cv.to_widget(q), btn=Qt.MouseButton.NoButton))
    lasso.double_click(cv, P(70, 210), None)
    assert doc.sel is not None, f"lasso type {typ}"
    w.select_none()
w.opts["lasso_type"] = 0
for mm in range(8):
    w.opts["match_mode"] = mm
    drag(T[0xd023], [P(300, 250)])
    assert doc.sel is not None, f"toverstaf modus {mm}"
    w.select_none()
w.opts["match_mode"] = 1
# alle mengmodi op een laag en op het penseel
from brushwork.document import BLEND_MODES, TOOL_BLEND_MODES
doc.add_layer(); drag(T[0xd091], [P(20, 20), P(300, 200)])
for i in range(len(BLEND_MODES)):
    doc.layer().mode = i; doc.changed.emit(QRect()); app.processEvents()
for i in range(len(TOOL_BLEND_MODES)):
    w.opts["blend"] = i; drag(T[0xd091], [P(30, 30), P(200, 100)]); drag(T[0xd0d1], [P(390, 290)])
w.opts["blend"] = 0; doc.layer().mode = 0
from brushwork.materials import MaterialDialog
md = MaterialDialog(w, QColor(159, 254, 32)); md.html.setText("#123456"); md._from_html()
assert md.color() == QColor(0x12, 0x34, 0x56) and md.sp["r"].value() == 0x12
w.set_none(False, True); drag(T[0xd102], [P(10, 10), P(60, 60)]); w.set_none(False, False)
w.export_gif()
from PIL import Image
g = Image.open(os.path.join(_TMP, "export.gif")); assert g.format == "GIF"
doc.layers[0].lock_alpha = True; drag(T[0xd0b0], [P(10, 10), P(50, 50)]); doc.layers[0].lock_alpha = False
assert doc.layers[0].image.pixelColor(30, 30).alpha() == 255, "vergrendelde transparantie"
drag(T[0xd011], [P(200, 150), P(220, 160)])   # selecteren: verplaatsen
w.layers.refresh(); w.select_tool(T[0xd091])
# aanpassingslaag: helderheid/contrast, met masker
base_px = cv.cache.pixelColor(390, 290)
w.new_adjustment_layer(0x8052)
lay = doc.layer(); assert lay.adjust is not None
lay.adjust = (0x8052, {"brightness": 120, "contrast": 0}); doc.changed.emit(QRect()); app.processEvents()
assert cv.cache.pixelColor(390, 290).lightness() > base_px.lightness(), "aanpassingslaag werkt niet"
from brushwork.document import new_image as _ni
lay.image = _ni(doc.w, doc.h, QColor(0, 0, 0)); doc.changed.emit(QRect()); app.processEvents()
assert cv.cache.pixelColor(390, 290) == base_px, "zwart masker moet effect verbergen"
fileio.save(doc, os.path.join(_TMP, "adj.ora")); assert fileio.load(os.path.join(_TMP, "adj.ora")).layers[-1].adjust[0] == 0x8052
w.layer_properties(); doc.delete_layer()
# koppelingsset
doc.add_layer(); a1 = doc.layer(); a1.link_set = 1; doc.add_layer(); a2 = doc.layer(); a2.link_set = 1
from brushwork.document import new_image as ni
a1.image = ni(doc.w, doc.h); a1.image.setPixelColor(5, 5, QColor(255, 0, 0))
drag(T[0xd012], [P(100, 100), P(110, 100)])
assert a1.image.pixelColor(15, 5) == QColor(255, 0, 0), "gekoppelde laag beweegt niet mee"
w.new_raster_layer()

# --- voorinstellingen
from brushwork.effectdialog import EffectDialog
ed = EffectDialog(w, doc, w.effects[0x8091])
psp_items = [ed.presets.itemText(i) for i in range(ed.presets.count()) if "(PSP)" in ed.presets.itemText(i)]
print("PSP voorinstellingen Spiraal:", psp_items[:3])
if psp_items:
    ed._load_preset([ed.presets.itemText(i) for i in range(ed.presets.count())].index(psp_items[0]))
ed.reject()
w.select_tool(T[0xd091]); w._apply_tool_preset(T[0xd091], {"size": 77}); assert w.opts["size"] == 77

# --- elk gereedschap met links en rechts slepen
errors = []
line = [P(100, 100), P(140, 120), P(180, 160), P(220, 150)]
T[0xd081].source = None
for cid, tool in T.items():
    for btn in (Qt.MouseButton.RightButton, Qt.MouseButton.LeftButton):
        try:
            drag(tool, line, btn=btn)
            if hasattr(tool, "apply"):
                tool.apply(cv)
            tool.deactivate()
        except Exception as e:
            import traceback; traceback.print_exc()
            errors.append((tool.name, repr(e)))
print("gereedschappen getest:", len(T), "fouten:", errors)

# --- elke menuopdracht met een functie
skip = {0xe141, 0xe102, 0x80d3, 0x801d, 0xe101, 0xe104, 0xe10b, 0xe103}
doc.add_layer(); w.select_all()
from PySide6.QtWidgets import QApplication as QA
QA.clipboard().setImage(QImage(50, 40, QImage.Format.Format_ARGB32))
H = w.all_handlers(); failed = []
for cid, fn in H.items():
    if cid in skip:
        continue
    try:
        fn(); app.processEvents()
    except Exception as e:
        import traceback; traceback.print_exc()
        failed.append((hex(cid), repr(e)))
print("menuopdrachten getest:", len(H) - len(skip), "fouten:", failed)
n_menu = sum(1 for a in w.actions_by_id.values())
n_off = sum(1 for a in w.actions_by_id.values() if a.property("unavailable"))
print(f"menu-items: {n_menu}, werkend: {n_menu - n_off}, nog grijs: {n_off}")

cv = w.canvas(); doc = cv.doc
d = tempfile.mkdtemp(dir="/tmp/claude-1000") if os.path.isdir("/tmp/claude-1000") else tempfile.mkdtemp()
fileio.save(doc, d + "/t.ora"); d2 = fileio.load(d + "/t.ora")
assert len(d2.layers) == len(doc.layers)
for ext in ("png", "jpg", "tif", "bmp", "webp"):
    fileio.save(doc, f"{d}/t.{ext}"); assert fileio.load(f"{d}/t.{ext}").w == doc.w
w.grab().save(d + "/window.png")
print("OK" if not errors and not failed else "FOUTEN", "in", round(time.time() - t0, 2), "s;", d)
for s in list(w.mdi.subWindowList()): s.canvas.doc.set_modified(False)
w.close()
sys.exit(1 if errors or failed else 0)
