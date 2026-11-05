"""Snelmenu's (rechtsklik): QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_contextmenu.py"""
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

# 1. rechtsklik met Selectie: menu
w.select_tool(T[0xd021]); n = len(shown); click(QPointF(50, 50), R)
assert len(shown) == n + 1 and "Knippen" in shown[-1] and "Lagen" in shown[-1], shown[-1:]
print("1 selectie: menu ->", [x for x in shown[-1] if x != "---"][:8], "...")
# 2. rechts slepen in een selectie verplaatst het kader (geen menu)
drag(QPointF(20, 20), QPointF(80, 80), L); bb = doc.selection_bbox()
n = len(shown); drag(QPointF(50, 50), QPointF(70, 60), R)
assert len(shown) == n and doc.selection_bbox().x() == bb.x() + 20, (bb, doc.selection_bbox())
print("2 rechts slepen verplaatst het selectiekader:", bb.x(), "->", doc.selection_bbox().x())
w.select_none()
# 3. penseel: rechts slepen schildert met achtergrondkleur, geen menu
w.set_color(QColor(0, 200, 0), False); w.select_tool(T[0xd091]); n = len(shown)
drag(QPointF(100, 150), QPointF(200, 150), R)
assert len(shown) == n and doc.layer().image.pixelColor(150, 150) == QColor(0, 200, 0)
print("3 penseel rechts schildert nog steeds (", doc.layer().image.pixelColor(150, 150).name(), ")")
# 4. Menu-toets werkt bij elk gereedschap
n = len(shown); cv.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Keyboard, QPoint(10, 10)))
assert len(shown) == n + 1; print("4 menutoets bij penseel: menu")
# 5. punt-tot-punt: rechtsklik sluit de selectie, geen menu
w.opts["lasso_type"] = 1; w.select_tool(T[0xd022])
for q in (QPointF(10, 10), QPointF(100, 10), QPointF(60, 90)):
    click(q, L)
n = len(shown); click(QPointF(60, 90), R)
assert len(shown) == n and doc.sel is not None; print("5 punt-tot-punt: rechtsklik sluit selectie")
w.select_none(); w.opts["lasso_type"] = 0
# 6. bijsnijden: eigen opdrachten bovenaan
w.select_tool(T[0xd040]); drag(QPointF(10, 10), QPointF(100, 80), L); click(QPointF(50, 50), R)
assert shown[-1][0] == "Bijsnijden toepassen"; print("6 bijsnijden: ", shown[-1][:2])
# 7. tekstlaag: Tekst bewerken
from pixelpickle.document import Layer, new_image
from pixelpickle.textlayer import new_text
lay = Layer("Hoi", new_image(300, 200)); lay.text = new_text("Hoi", 20, 100, w.opts, w.fg, w.bg); doc.add_layer(lay); doc.render_text(lay)
w.select_tool(T[0xd001]); click(QPointF(150, 100), R)
assert "Tekst bewerken" in shown[-1]; w.edit_text_layer(cv)
assert T[0xd0f0].dlg is not None and T[0xd0f0].dlg.text() == "Hoi"; T[0xd0f0].dlg.reject(); app.processEvents()
print("7 tekstlaag: 'Tekst bewerken' opent de tekst")
# 8. tabblad en lagenpalet
bar = w.mdi.findChildren(QTabBar)[0]
bar.customContextMenuRequested.emit(QPoint(5, 5)); app.processEvents()
assert any("Sluiten" in x for x in shown[-1]); print("8 tabblad:", [x for x in shown[-1] if x != "---"])
w.layers.context_menu(QPoint(5, 5)); assert any("Dupliceren" in x for x in shown[-1]) and any("Eigenschappen" in x for x in shown[-1])
print("9 lagenpalet:", len([x for x in shown[-1] if x != "---"]), "items, o.a. Dupliceren en Eigenschappen")
print("ALLES OK")
for s in w.mdi.subWindowList(): s.canvas.doc.set_modified(False)
