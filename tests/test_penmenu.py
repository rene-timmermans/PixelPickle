"""Snelmenu van de Pen (zoals PSP): QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_penmenu.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QInputDialog, QMenu  # noqa: E402

app = QApplication(sys.argv)
shown = []


class RecordingMenu(QMenu):
    def exec(self, *a, **k):
        def walk(m, depth=0):
            out = []
            for x in m.actions():
                if x.isSeparator():
                    continue
                out.append(("  " * depth) + x.text() + ("" if x.isEnabled() else " (uit)"))
                if x.menu():
                    out += walk(x.menu(), depth + 1)
            return out
        shown.append(walk(self))


import pixelpickle.mainwindow as mw  # noqa: E402
mw.QMenu = RecordingMenu
from pixelpickle.document import Document  # noqa: E402
from pixelpickle.mainwindow import MainWindow  # noqa: E402

w = MainWindow(); w.show()
doc = Document(300, 200, QColor(255, 255, 255)); cv = w.add_document(doc).canvas; app.processEvents()
pen = w.tools[0xd110]
w.select_tool(pen)
LB, RB = Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton


def ev(kind, pt, btn=LB, mods=Qt.KeyboardModifier.NoModifier):
    p = cv.to_widget(pt)
    held = btn if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    return QMouseEvent(kind, p, cv.mapToGlobal(p.toPoint()), btn, held, mods)


def click(pt, mods=Qt.KeyboardModifier.NoModifier):
    pen.press(cv, pt, ev(QEvent.Type.MouseButtonPress, pt, LB, mods))
    pen.release(cv, pt, ev(QEvent.Type.MouseButtonRelease, pt, LB, mods))


def drag(a, b, mods=Qt.KeyboardModifier.NoModifier):
    pen.press(cv, a, ev(QEvent.Type.MouseButtonPress, a, LB, mods))
    pen.move(cv, b, ev(QEvent.Type.MouseMove, b, LB, mods))
    pen.release(cv, b, ev(QEvent.Type.MouseButtonRelease, b, LB, mods))


# twee open lijnen tekenen (lijnen en polylijnen)
w.opts.update(pen_mode=1, pen_connect=True)
click(QPointF(20, 50)); click(QPointF(100, 50))
pen.cur = None
click(QPointF(140, 50)); click(QPointF(220, 50))
assert len(pen.paths) == 2, pen.paths
# rechtsklik: het menu van de Pen
cv.mousePressEvent(ev(QEvent.Type.MouseButtonPress, QPointF(150, 150), RB))
cv.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(150, 150), RB))
top = [x for x in shown[-1] if not x.startswith(" ")]
assert top[:3] == ["Be&werken", "&Tekenpunttype", "&Geselecteerde tekenpunten transformeren"], top
assert "  &Verbinden (uit)" in shown[-1], shown[-1]
print("1 rechtsklik met de Pen: eigen menu", top)

# Bewerken-modus: kader slepen selecteert de twee binnenste eindpunten
w.opts["pen_mode"] = 0
drag(QPointF(90, 40), QPointF(150, 60))
assert pen.nsel == {(0, 1), (1, 0)}, pen.nsel
pen.pen_command("join")
assert len(pen.paths) == 1 and len(pen.paths[0]["nodes"]) == 4
print("2 kader selecteert twee eindpunten; Verbinden maakt één pad van vier punten")
# Shift+klik op knooppunten, samenvoegen tot één punt
pen.paths = []
w.opts["pen_mode"] = 1
click(QPointF(20, 100)); click(QPointF(100, 100)); pen.cur = None
click(QPointF(110, 100)); click(QPointF(200, 100)); pen.cur = None
w.opts["pen_mode"] = 0
click(QPointF(100, 100)); click(QPointF(110, 100), Qt.KeyboardModifier.ShiftModifier)
assert pen.nsel == {(0, 1), (1, 0)}
pen.pen_command("merge")
xs = [round(n[0].x()) for n in pen.paths[0]["nodes"]]
assert len(pen.paths) == 1 and xs == [20, 105, 200], xs
print("3 Shift+klik en Samenvoegen: één punt halverwege", xs)
# onderbreken, sluiten
pen.nsel = {(0, 1)}
pen.pen_command("break")
assert len(pen.paths) == 2
pen.pen_command("select_all"); assert len(pen.nsel) == 4
pen.pen_command("invert"); assert pen.nsel == set()
print("4 Onderbreken, Alles selecteren, Selectie omkeren")
# knooppunttype en transformeren
pen.paths = [{"nodes": [[QPointF(0, 0), None, None], [QPointF(50, 0), None, None], [QPointF(100, 50), None, None]],
              "closed": False, "types": {}}]
pen.nsel = {(0, 1)}
pen.pen_command("sym")
n = pen.paths[0]["nodes"][1]
assert n[1] is not None and n[2] is not None and abs((n[1] - n[0]).manhattanLength() - (n[2] - n[0]).manhattanLength()) < 1e-6
pen.pen_command("to_line")
assert n[1] is None and n[2] is None
pen.nsel = {(0, 0), (0, 2)}
pen.pen_command("mirror")
assert round(pen.paths[0]["nodes"][0][0].x()) == 100 and round(pen.paths[0]["nodes"][2][0].x()) == 0
QInputDialog.getDouble = staticmethod(lambda *a, **k: (90.0, True))
pen.pen_command("rotate")
print("5 Symmetrisch, Omzetten in lijn, Spiegelen, Roteren")
# kopiëren en plakken, dupliceren
pen.pen_command("select_all"); pen.pen_command("copy"); pen.pen_command("paste")
assert len(pen.paths) == 2
pen.pen_command("duplicate_offset"); assert len(pen.paths) == 3
pen.pen_command("delete"); assert len(pen.paths) == 2
pen.pen_command("cut"); assert len(pen.paths) == 0 and pen.clipboard
print("6 Kopiëren, Plakken, Dupliceren en verschuiven, Verwijderen, Knippen")
# handvat slepen volgt het type: asymmetrisch houdt de eigen lengte
pen.paths = [{"nodes": [[QPointF(0, 0), None, None], [QPointF(50, 0), QPointF(40, 0), QPointF(70, 0)],
                         [QPointF(100, 0), None, None]], "closed": False, "types": {1: "asym"}}]
pen.nsel = set()
drag(QPointF(70, 0), QPointF(70, 20))
n = pen.paths[0]["nodes"][1]
assert abs((n[1] - n[0]).manhattanLength() - 10) < 0.5 or abs(((n[1] - n[0]).x() ** 2 + (n[1] - n[0]).y() ** 2) ** 0.5 - 10) < 0.5
print("7 asymmetrisch handvat: het andere houdt zijn eigen lengte")
pen.apply(); app.processEvents()
doc.set_modified(False)
# dezelfde opdrachten via het hoofdmenu Objecten
pen.paths = [{"nodes": [[QPointF(0, 0), None, None], [QPointF(50, 0), None, None]], "closed": False, "types": {}}]
w.update_node_actions()
assert w.actions_by_id[0x1774].isEnabled() and not w.actions_by_id[0x1777].isEnabled()
w.actions_by_id[0x1774].trigger(); assert len(pen.nsel) == 2
w.update_node_actions(); w.actions_by_id[0x1789].trigger(); assert round(pen.paths[0]["nodes"][0][0].x()) == 50
print("8 Objecten > Bewerken / transformeren werkt op de lijnen van de Pen")
pen.apply()
assert "Objecten" in w.top_menus
print("ALLES OK")
