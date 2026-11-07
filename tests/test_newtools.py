"""Nieuwe en herstelde gereedschappen: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_newtools.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPolygonF
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from pixelpickle import imageops as ops
from pixelpickle.document import Document
from pixelpickle.mainwindow import MainWindow

w = MainWindow(); w.show()
P, LB = QPointF, Qt.MouseButton.LeftButton


def ev(cv, t, p):
    return QMouseEvent(t, cv.to_widget(p), cv.to_widget(p), LB, LB if t != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)


def drag(cv, tool, pts):
    tool.press(cv, pts[0], ev(cv, QEvent.Type.MouseButtonPress, pts[0]))
    for q in pts[1:]:
        tool.move(cv, q, ev(cv, QEvent.Type.MouseMove, q))
    tool.release(cv, pts[-1], ev(cv, QEvent.Type.MouseButtonRelease, pts[-1]))
    app.processEvents()


# ---- 1. Perspectiefcorrectie: een scheve vierhoek wordt een rechthoek
doc = Document(300, 200, QColor(255, 255, 255)); cv = w.add_document(doc).canvas; app.processEvents()
quad = [P(80, 40), P(220, 60), P(240, 170), P(60, 150)]
p = QPainter(doc.layers[0].image); p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(200, 0, 0))
p.drawPolygon(QPolygonF(quad)); p.end()
t = w.tools[0xd052]; assert t.available and 0xd052 in w.group_buttons
w.select_tool(t); app.processEvents()
assert len(t.quad) == 4 and t.quad[0] == P(45, 30), t.quad  # beginkader: 15% van de randen
for i, q in enumerate(quad):  # hoeken naar de vierhoek slepen
    drag(cv, t, [t.quad[i], q])
assert [(round(q.x()), round(q.y())) for q in t.quad] == [(80, 40), (220, 60), (240, 170), (60, 150)], t.quad
w.opts["persp_crop"] = True
t.double_click(cv, P(150, 100), None)  # binnen het kader: toepassen
a = ops.qimage_to_rgba(doc.layers[0].image)
red = (a[..., 0] > 150) & (a[..., 1] < 80)
print("1 perspectief bijgesneden tot", doc.w, "x", doc.h, "| rood:", round(red.mean() * 100), "%")
assert 130 < doc.w < 190 and 90 < doc.h < 140 and red[3:-3, 3:-3].mean() > 0.97
doc.undo(); assert doc.w == 300
w.opts["persp_crop"] = False
t.reset(cv); t.quad = [QPointF(q) for q in quad]; t.apply(cv)
assert doc.w == 300 and doc.h == 200
a = ops.qimage_to_rgba(doc.layers[0].image); red = (a[..., 0] > 150) & (a[..., 1] < 80)
ys, xs = np.nonzero(red)
# na correctie is het rode vlak (vrijwel) een rechthoek: het vult zijn omhullende bijna helemaal
fill = red.sum() / ((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1))
print("2 zonder bijsnijden: rode vlak vult", round(fill * 100), "% van zijn omhullende rechthoek")
assert fill > 0.95
doc.set_modified(False)

# ---- 2. Bosseleren: overlappende stempels stapelen het effect niet op
doc2 = Document(200, 120, QColor(120, 120, 120)); cv2 = w.add_document(doc2).canvas; app.processEvents()
p = QPainter(doc2.layers[0].image); p.fillRect(100, 0, 100, 120, QColor(180, 180, 180)); p.end()
e = w.tools[0xd0a8]; w.select_tool(e); w.opts.update(size=60, hardness=100, step=5, opacity=100)
# één streek heen en weer: vele overlappende stempels op dezelfde plek
drag(cv2, e, [P(x, 60) for x in list(range(30, 171, 4)) + list(range(170, 29, -4)) * 2])
a = ops.qimage_to_rgba(doc2.layers[0].image).astype(int)
flat = a[60, 50, :3]; edge = a[60, 100, :3]
print("3 bosseleren: vlak", flat, "| rand", edge)
assert all(abs(v - 128) <= 2 for v in flat), "egaal vlak wordt middengrijs"
assert 40 <= abs(int(edge[0]) - 128) <= 70, "rand geeft reliëf, niet opgestapeld"
stripes = np.abs(np.diff(a[40:80, 40:90, 0].astype(int), axis=1)).max()
assert stripes <= 3, f"geen strepen in een egaal vlak ({stripes})"
doc2.set_modified(False)
# ---- 3. Krasjes verwijderen: een donkere kras op een verloop verdwijnt
doc3 = Document(200, 120, QColor(0, 0, 0)); cv3 = w.add_document(doc3).canvas; app.processEvents()
img = doc3.layers[0].image
for y in range(120):
    for x in range(200):
        img.setPixelColor(x, y, QColor(60 + x // 2, 100 + y // 2, 150))
p = QPainter(img); p.setPen(QColor(10, 10, 10)); p.drawLine(20, 30, 180, 90); p.end()
s_ = w.tools[0xd082]; assert s_.available and 0xd082 in w.group_buttons
w.select_tool(s_); w.opts["scratch_width"] = 8
for ends in (0, 1):
    w.opts["scratch_ends"] = ends
    drag(cv3, s_, [P(20, 30), P(100, 60), P(180, 90)])
    a = ops.qimage_to_rgba(doc3.layers[0].image).astype(int)
    on = a[60, 100, :3]; expect = np.array([60 + 50, 100 + 30, 150])
    print(f"4 kras ({['recht', 'puntig'][ends]}): op de lijn", on, "verwacht ongeveer", expect)
    assert np.abs(on - expect).max() <= 6, "kras niet weg"
    assert np.abs(a[5, 5, :3] - [62, 102, 150]).max() <= 1, "buiten het kader onveranderd"
    doc3.undo()
doc3.set_modified(False)
# ---- 4. Kunstmedia: elk tekent, krijt laat korrel zien, potlood is dun, olieverf mengt
doc4 = Document(400, 200, QColor(255, 255, 255)); cv4 = w.add_document(doc4).canvas; app.processEvents()
w.set_color(QColor(0, 0, 0), True)
res = {}
for i, cid in enumerate((0xd131, 0xd132, 0xd133, 0xd134, 0xd135)):
    t = w.tools[cid]; assert t.available and cid in w.group_buttons, hex(cid)
    w.select_tool(t)
    y = 20 + i * 35
    drag(cv4, t, [P(x, y) for x in range(20, 381, 3)])
    a = ops.qimage_to_rgba(doc4.layers[0].image).astype(np.float32)
    band = 255 - a[y - 15:y + 16, 60:340, 0]
    rows = (band.max(axis=1) > 40).sum()
    core = band[15]
    res[t.name] = (rows, round(float(core.mean())), round(float(core.std()), 1))
for k, v in res.items():
    print(f"5 {k}: dikte {v[0]} px, gem. dekking {v[1]}, spreiding {v[2]}")
vals = list(res.values())
assert all(v[1] > 60 for v in vals), "elk medium tekent"
assert vals[4][0] <= 8 < vals[1][0], "potlood dun, krijt breed"
assert vals[1][2] > vals[2][2] > 0, "krijt korreliger dan pastel"
# olieverf neemt kleur op van wat eronder ligt
doc5 = Document(300, 60, QColor(0, 0, 255)); cv5 = w.add_document(doc5).canvas; app.processEvents()
w.set_color(QColor(255, 255, 0), True); w.select_tool(w.tools[0xd131])
drag(cv5, w.tools[0xd131], [P(x, 30) for x in range(10, 291, 3)])
a = ops.qimage_to_rgba(doc5.layers[0].image).astype(int)
start, end = a[30, 30, :3], a[30, 270, :3]
print("6 olieverf geel over blauw: begin", start, "eind", end)
assert start[0] > 150 and end[2] > start[2], "verf mengt met blauw en raakt op"
# ---- 5. Penseel Verwringen: duwen verplaatst inhoud, gladstrijken zet terug
doc6 = Document(240, 160, QColor(255, 255, 255)); cv6 = w.add_document(doc6).canvas; app.processEvents()
p = QPainter(doc6.layers[0].image); p.fillRect(100, 60, 40, 40, QColor(0, 0, 0)); p.end()
orig = ops.qimage_to_rgba(doc6.layers[0].image).copy()
wb = w.tools[0xd121]; assert wb.available and 0xd121 in w.group_buttons
w.select_tool(wb); w.opts.update(size=60, hardness=50, step=10, warp_strength=80, warp_mode=0)
drag(cv6, wb, [P(110 + k, 80) for k in range(0, 41, 2)])  # naar rechts duwen
a = ops.qimage_to_rgba(doc6.layers[0].image)
dark = a[..., 0] < 128
xs = np.nonzero(dark.any(axis=0))[0]
print("7 duwen: zwart vlak liep van x=100..139, nu", xs.min(), "..", xs.max())
assert xs.max() > 145, "inhoud is meegeduwd"
for mode, name in ((1, "uitzetten"), (2, "samentrekken"), (3, "rechtsom"), (4, "linksom"), (5, "ruis")):
    w.opts["warp_mode"] = mode; drag(cv6, wb, [P(120, 80), P(122, 80)])
w.opts.update(warp_mode=6, warp_strength=100)
for _ in range(12):
    drag(cv6, wb, [P(x, y) for y in range(40, 121, 15) for x in (60, 200)])
a = ops.qimage_to_rgba(doc6.layers[0].image)
diff = np.abs(a[..., :3].astype(int) - orig[..., :3].astype(int)).mean()
print("8 gladstrijken: gemiddeld verschil met het origineel", round(float(diff), 2))
assert diff < 3, "gladstrijken zet terug"
doc6.set_modified(False)

# ---- 6. Maasvormig verwringen: knooppunt verslepen buigt de afbeelding
doc7 = Document(240, 160, QColor(255, 255, 255)); cv7 = w.add_document(doc7).canvas; app.processEvents()
for x in range(0, 240, 20):
    p = QPainter(doc7.layers[0].image); p.fillRect(x, 0, 2, 160, QColor(0, 0, 0)); p.end()
mw = w.tools[0xd122]; assert mw.available and 0xd122 in w.group_buttons
w.opts.update(mesh_cols=3, mesh_rows=3); w.select_tool(mw); mw._ensure(cv7)
i, j = 2, 2; node = QPointF(float(mw.nodes[i, j, 0]), float(mw.nodes[i, j, 1]))
drag(cv7, mw, [node, node + QPointF(25, 0)])
a = ops.qimage_to_rgba(doc7.layers[0].image)
row = a[int(node.y()), :, 0]
lines = np.nonzero(row < 100)[0]
print("9 maas: zwarte lijn bij x=120 ligt nu rond", [int(v) for v in lines if 125 <= v <= 160][:3])
assert any(135 <= v <= 150 for v in lines), "lijn is meegebogen"
doc7.undo(); assert ops.qimage_to_rgba(doc7.layers[0].image)[int(node.y()), 120, 0] < 100
# ---- 7. Retoucheerpenselen stapelen niet op binnen een streek (tenzij Doorlopend)
doc8 = Document(200, 120, QColor(120, 120, 120)); cv8 = w.add_document(doc8).canvas; app.processEvents()
p = QPainter(doc8.layers[0].image); p.fillRect(100, 0, 100, 120, QColor(160, 160, 160)); p.end()
orig8 = ops.qimage_to_rgba(doc8.layers[0].image).astype(int)
w.opts.update(size=50, hardness=100, step=5, opacity=100, continuous=False)
results = {}
for cid in (0xd0a7, 0xd0a6, 0xd0a1, 0xd0a2, 0xd0a3, 0xd0a9, 0xd0aa):
    t = w.tools[cid]; w.select_tool(t)
    once = None
    for passes in (1, 3):
        doc8.layers[0].image = ops.rgba_to_qimage(orig8.astype(np.uint8))
        drag(cv8, t, [P(x, 60) for x in (list(range(40, 161, 3)) + list(range(160, 39, -3))) * passes])
        a = ops.qimage_to_rgba(doc8.layers[0].image).astype(int)
        if once is None:
            once = a
    results[t.name] = int(np.abs(a - once).max())
print("10 heen en weer binnen één streek, verschil met één keer:", results)
assert all(v <= 1 for v in results.values()), results
# verscherpen: geen ontploffing; egaal vlak blijft egaal
t = w.tools[0xd0a7]; w.select_tool(t)
doc8.layers[0].image = ops.rgba_to_qimage(orig8.astype(np.uint8))
drag(cv8, t, [P(x, 60) for x in list(range(40, 161, 2)) * 4])
a = ops.qimage_to_rgba(doc8.layers[0].image).astype(int)
assert np.abs(a[40:80, 50:90, :3] - 120).max() <= 1 and 0 < a[60, 100, 0] < 255, "verscherpen ontploft niet"
# Doorlopend: bouwt wel op
t = w.tools[0xd0a1]; w.select_tool(t)
vals = {}
for cont in (False, True):
    w.opts["continuous"] = cont
    doc8.layers[0].image = ops.rgba_to_qimage(orig8.astype(np.uint8))
    drag(cv8, t, [P(x, 60) for x in list(range(40, 161, 3)) * 3])
    vals[cont] = int(ops.qimage_to_rgba(doc8.layers[0].image)[60, 60, 0])
print("11 lichter maken, 3x heen en weer: zonder Doorlopend", vals[False], "| met", vals[True], "(begin 120)")
assert 120 < vals[False] < vals[True], vals
w.opts["continuous"] = False
doc8.set_modified(False)
for d_ in (doc4, doc5, doc7):
    d_.set_modified(False)
print("ALLES OK")
