"""Context menus (right click): QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_contextmenu.py"""
import os, sys, tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QPointF, QPoint, Qt, QEvent
from PySide6.QtGui import QMouseEvent, QColor, QContextMenuEvent
from PySide6.QtWidgets import QApplication, QMenu, QTabBar
app = QApplication(sys.argv)
shown = []
def fake_exec(self, *a, **k):
    def walk(m, depth=0):
        return [("  " * depth) + (x.text().replace("&", "") if not x.isSeparator() else "---") for x in m.actions()]
    shown.append(walk(self))
    return None
class RecordingMenu(QMenu):
    exec = fake_exec
import pixelpickle.mainwindow as mw, pixelpickle.palettes as pal
mw.QMenu = RecordingMenu; pal.QMenu = RecordingMenu
from pixelpickle.mainwindow import MainWindow
from pixelpickle.document import Document
w = MainWindow(); w.show()
doc = Document(300, 200); cv = w.add_document(doc).canvas; app.processEvents()
T = w.tools
R, L = Qt.MouseButton.RightButton, Qt.MouseButton.LeftButton
def mouse(kind, pt, btn):
    p = cv.to_widget(pt)
    held = btn if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    return QMouseEvent(kind, p, cv.mapToGlobal(p.toPoint()), btn, held, Qt.KeyboardModifier.NoModifier)
def click(pt, btn):
    cv.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, pt, btn)); cv.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, pt, btn))
def drag(a, b, btn):
    cv.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, a, btn))
    for k in range(1, 6):
        cv.mouseMoveEvent(mouse(QEvent.Type.MouseMove, QPointF(a.x() + (b.x() - a.x()) * k / 5, a.y() + (b.y() - a.y()) * k / 5), btn))
    cv.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, b, btn)); app.processEvents()

# 1. right click with Selection without a selection: the (short) menu
w.select_tool(T[0xd021]); n = len(shown); click(QPointF(50, 50), R)
items = [x for x in shown[-1] if x != "---"]
assert len(shown) == n + 1 and "Knippen" in items and "Plakken als nieuwe laag" in items, shown[-1:]
for gone in ("Samengevoegd kopiëren", "Wissen", "Alles selecteren", "Niets selecteren", "Selecties", "Lagen",
             "Afbeelding", "Aanpassen", "Effecten", "Inzoomen", "Uitzoomen"):
    assert gone not in items, gone
print("1 menu on the image:", items)
# 1b. with a selection a right click clears the selection (no menu)
doc.select_all(); n = len(shown); click(QPointF(50, 50), R)
assert len(shown) == n and doc.sel is None
print("1b selection tool: right click clears the selection")
# 2. right drag in a selection moves the frame (no menu)
drag(QPointF(20, 20), QPointF(80, 80), L); bb = doc.selection_bbox()
n = len(shown); drag(QPointF(50, 50), QPointF(70, 60), R)
assert len(shown) == n and doc.selection_bbox().x() == bb.x() + 20, (bb, doc.selection_bbox())
print("2 right drag moves the selection frame:", bb.x(), "->", doc.selection_bbox().x())
w.select_none()
# 3. brush: right drag paints with the background color, no menu
w.set_color(QColor(0, 200, 0), False); w.select_tool(T[0xd091]); n = len(shown)
drag(QPointF(100, 150), QPointF(200, 150), R)
assert len(shown) == n and doc.layer().image.pixelColor(150, 150) == QColor(0, 200, 0)
print("3 brush right still paints (", doc.layer().image.pixelColor(150, 150).name(), ")")
# 4. Menu key works with every tool
n = len(shown); cv.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Keyboard, QPoint(10, 10)))
assert len(shown) == n + 1; print("4 menu key with brush: menu")
# 5. point-to-point: right click closes the selection, no menu
w.opts["lasso_type"] = 1; w.select_tool(T[0xd022])
for q in (QPointF(10, 10), QPointF(100, 10), QPointF(60, 90)):
    click(q, L)
n = len(shown); click(QPointF(60, 90), R)
assert len(shown) == n and doc.sel is not None; print("5 point-to-point: right click closes selection")
w.select_none(); w.opts["lasso_type"] = 0
# 6. crop: own commands at the top
w.select_tool(T[0xd040]); drag(QPointF(10, 10), QPointF(100, 80), L); click(QPointF(50, 50), R)
assert shown[-1][0] == "Bijsnijden toepassen"; print("6 crop: ", shown[-1][:2])
# 7. text layer: Edit text
from pixelpickle.document import Layer, new_image
from pixelpickle.textlayer import new_text
lay = Layer("Hoi", new_image(300, 200)); lay.text = new_text("Hoi", 20, 100, w.opts, w.fg, w.bg); doc.add_layer(lay); doc.render_text(lay)
w.select_tool(T[0xd001]); click(QPointF(150, 100), R)
assert "Tekst bewerken" in shown[-1]; w.edit_text_layer(cv)
assert T[0xd0f0].dlg is not None and T[0xd0f0].dlg.text() == "Hoi"; T[0xd0f0].dlg.reject(); app.processEvents()
print("7 text layer: 'Tekst bewerken' opens the text")
# 8. tab and layers palette
bar = w.mdi.findChildren(QTabBar)[0]
bar.customContextMenuRequested.emit(QPoint(5, 5)); app.processEvents()
assert any("Sluiten" in x for x in shown[-1]); print("8 tab:", [x for x in shown[-1] if x != "---"])
w.layers.context_menu(QPoint(5, 5)); assert any("Dupliceren" in x for x in shown[-1]) and any("Eigenschappen" in x for x in shown[-1])
print("9 layer palette:", len([x for x in shown[-1] if x != "---"]), "items, including Dupliceren and Eigenschappen")
# 10. empty workspace
w.show_workspace_menu(QPoint(5, 5))
items = [x for x in shown[-1] if x != "---"]
assert items == ["Nieuw...", "Openen...", "Alles sluiten", "Plakken als nieuwe afbeelding", "Klembord leegmaken",
                 "Vergrootglas", "Algemene programmavoorkeuren..."], items
print("10 empty workspace:", items)
# 11. magnifier on and off, check mark follows
w.toggle_magnifier(); app.processEvents()
assert w.magnifier.isVisible() and w.actions_by_id[0x8216].isChecked()
w.toggle_magnifier(); app.processEvents()
assert not w.magnifier.isVisible() and not w.actions_by_id[0x8216].isChecked()
print("11 magnifier on and off")
# 12. text input window: only cut, copy, paste
w.select_tool(T[0xd0f0]); T[0xd0f0].press(cv, QPointF(200, 50), mouse(QEvent.Type.MouseButtonPress, QPointF(200, 50), L))
import PySide6.QtWidgets as QW
orig = QW.QMenu; QW.QMenu = RecordingMenu
T[0xd0f0].dlg._context_menu(QPoint(3, 3)); QW.QMenu = orig
assert [x for x in shown[-1] if x != "---"] == ["Knippen", "Kopiëren", "Plakken"], shown[-1]
T[0xd0f0].dlg.reject(); app.processEvents()
print("12 text input: Knippen, Kopiëren, Plakken")
print("ALL OK")
for s in w.mdi.subWindowList(): s.canvas.doc.set_modified(False)
