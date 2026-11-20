"""New and restored tools: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_newtools.py"""
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


# ---- 1. Perspective correction: a skewed quadrilateral becomes a rectangle
doc = Document(300, 200, QColor(255, 255, 255)); cv = w.add_document(doc).canvas; app.processEvents()
quad = [P(80, 40), P(220, 60), P(240, 170), P(60, 150)]
p = QPainter(doc.layers[0].image); p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(200, 0, 0))
p.drawPolygon(QPolygonF(quad)); p.end()
t = w.tools[0xd052]; assert t.available and 0xd052 in w.group_buttons
w.select_tool(t); app.processEvents()
assert len(t.quad) == 4 and t.quad[0] == P(45, 30), t.quad  # initial frame: 15% from the edges
for i, q in enumerate(quad):  # drag corners to the quadrilateral
    drag(cv, t, [t.quad[i], q])
assert [(round(q.x()), round(q.y())) for q in t.quad] == [(80, 40), (220, 60), (240, 170), (60, 150)], t.quad
w.opts["persp_crop"] = True
t.double_click(cv, P(150, 100), None)  # inside the frame: apply
a = ops.qimage_to_rgba(doc.layers[0].image)
red = (a[..., 0] > 150) & (a[..., 1] < 80)
print("1 perspective cropped to", doc.w, "x", doc.h, "| red:", round(red.mean() * 100), "%")
assert 130 < doc.w < 190 and 90 < doc.h < 140 and red[3:-3, 3:-3].mean() > 0.97
doc.undo(); assert doc.w == 300
w.opts["persp_crop"] = False
t.reset(cv); t.quad = [QPointF(q) for q in quad]; t.apply(cv)
assert doc.w == 300 and doc.h == 200
a = ops.qimage_to_rgba(doc.layers[0].image); red = (a[..., 0] > 150) & (a[..., 1] < 80)
ys, xs = np.nonzero(red)
# after correction the red area is (almost) a rectangle: it nearly fills its bounding box
fill = red.sum() / ((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1))
print("2 without cropping: red area fills", round(fill * 100), "% of its bounding rectangle")
assert fill > 0.95
doc.set_modified(False)

# ---- 2. Emboss: overlapping stamps do not stack the effect
doc2 = Document(200, 120, QColor(120, 120, 120)); cv2 = w.add_document(doc2).canvas; app.processEvents()
p = QPainter(doc2.layers[0].image); p.fillRect(100, 0, 100, 120, QColor(180, 180, 180)); p.end()
e = w.tools[0xd0a8]; w.select_tool(e); w.opts.update(size=60, hardness=100, step=5, opacity=100)
# one stroke back and forth: many overlapping stamps in the same place
drag(cv2, e, [P(x, 60) for x in list(range(30, 171, 4)) + list(range(170, 29, -4)) * 2])
a = ops.qimage_to_rgba(doc2.layers[0].image).astype(int)
flat = a[60, 50, :3]; edge = a[60, 100, :3]
print("3 embossing: flat area", flat, "| edge", edge)
assert all(abs(v - 128) <= 2 for v in flat), "uniform area becomes mid grey"
assert 40 <= abs(int(edge[0]) - 128) <= 70, "edge gives relief, not piled up"
stripes = np.abs(np.diff(a[40:80, 40:90, 0].astype(int), axis=1)).max()
assert stripes <= 3, f"no stripes in a uniform area ({stripes})"
doc2.set_modified(False)
# ---- 3. Scratch remover: a dark scratch on a gradient disappears
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
    print(f"4 scratch ({['recht', 'puntig'][ends]}): on the line", on, "expected about", expect)
    assert np.abs(on - expect).max() <= 6, "scratch not gone"
    assert np.abs(a[5, 5, :3] - [62, 102, 150]).max() <= 1, "unchanged outside the frame"
    doc3.undo()
doc3.set_modified(False)
# ---- 4. Art media: each draws, chalk shows grain, pencil is thin, oil paint mixes
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
    print(f"5 {k}: thickness {v[0]} px, avg. opacity {v[1]}, spread {v[2]}")
vals = list(res.values())
assert all(v[1] > 60 for v in vals), "every medium draws"
assert vals[4][0] <= 8 < vals[1][0], "pencil thin, chalk wide"
assert vals[1][2] > vals[2][2] > 0, "chalk grainier than pastel"
# oil paint picks up color from what is underneath
doc5 = Document(300, 60, QColor(0, 0, 255)); cv5 = w.add_document(doc5).canvas; app.processEvents()
w.set_color(QColor(255, 255, 0), True); w.select_tool(w.tools[0xd131])
drag(cv5, w.tools[0xd131], [P(x, 30) for x in range(10, 291, 3)])
a = ops.qimage_to_rgba(doc5.layers[0].image).astype(int)
start, end = a[30, 30, :3], a[30, 270, :3]
print("6 oil paint yellow over blue: start", start, "end", end)
assert start[0] > 150 and end[2] > start[2], "paint mixes with blue and runs out"
# ---- 5. Warp brush: pushing moves content, smoothing puts it back
doc6 = Document(240, 160, QColor(255, 255, 255)); cv6 = w.add_document(doc6).canvas; app.processEvents()
p = QPainter(doc6.layers[0].image); p.fillRect(100, 60, 40, 40, QColor(0, 0, 0)); p.end()
orig = ops.qimage_to_rgba(doc6.layers[0].image).copy()
wb = w.tools[0xd121]; assert wb.available and 0xd121 in w.group_buttons
w.select_tool(wb); w.opts.update(size=60, hardness=50, step=10, warp_strength=80, warp_mode=0)
drag(cv6, wb, [P(110 + k, 80) for k in range(0, 41, 2)])  # push to the right
a = ops.qimage_to_rgba(doc6.layers[0].image)
dark = a[..., 0] < 128
xs = np.nonzero(dark.any(axis=0))[0]
print("7 push: black area ran from x=100..139, now", xs.min(), "..", xs.max())
assert xs.max() > 145, "content was pushed along"
for mode, name in ((1, "uitzetten"), (2, "samentrekken"), (3, "rechtsom"), (4, "linksom"), (5, "ruis")):
    w.opts["warp_mode"] = mode; drag(cv6, wb, [P(120, 80), P(122, 80)])
w.opts.update(warp_mode=6, warp_strength=100)
for _ in range(12):
    drag(cv6, wb, [P(x, y) for y in range(40, 121, 15) for x in (60, 200)])
a = ops.qimage_to_rgba(doc6.layers[0].image)
diff = np.abs(a[..., :3].astype(int) - orig[..., :3].astype(int)).mean()
print("8 smudge smoothing: average difference with the original", round(float(diff), 2))
assert diff < 3, "smoothing restores"
# contract with hardness 100, often back and forth: the image must not fold over anywhere (no tears or streaks)
w.opts.update(warp_mode=2, size=95, hardness=100, warp_strength=50, step=10)
for k in range(8):
    drag(cv6, wb, [P(40 + x, 80 + 20 * np.sin(x / 20 + k)) for x in range(0, 160, 3)])
gx = 1 + np.diff(wb.fx, axis=1)
gy = 1 + np.diff(wb.fy, axis=0)
print("8b pinch, hardness 100: smallest stretch factor x", round(float(gx.min()), 2), "y", round(float(gy.min()), 2))
assert gx.min() > 0 and gy.min() > 0, "the image folds over"
assert wb.weights[wb.weights.shape[0] // 2, 1] < 0.05, "the effect tapers off toward the edge to (almost) zero"
doc6.set_modified(False)

# ---- 6. Mesh warp: dragging a node bends the image
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
print("9 mesh: black line at x=120 now lies around", [int(v) for v in lines if 125 <= v <= 160][:3])
assert any(135 <= v <= 150 for v in lines), "line was bent along"
doc7.undo(); assert ops.qimage_to_rgba(doc7.layers[0].image)[int(node.y()), 120, 0] < 100
# ---- 7. Retouch brushes do not stack within a stroke (unless Continuous)
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
print("10 back and forth within one stroke, difference with once:", results)
assert all(v <= 1 for v in results.values()), results
# sharpen: no blow-up; a flat area stays flat
t = w.tools[0xd0a7]; w.select_tool(t)
doc8.layers[0].image = ops.rgba_to_qimage(orig8.astype(np.uint8))
drag(cv8, t, [P(x, 60) for x in list(range(40, 161, 2)) * 4])
a = ops.qimage_to_rgba(doc8.layers[0].image).astype(int)
assert np.abs(a[40:80, 50:90, :3] - 120).max() <= 1 and 0 < a[60, 100, 0] < 255, "sharpening does not blow up"
# Continuous: does build up
t = w.tools[0xd0a1]; w.select_tool(t)
vals = {}
for cont in (False, True):
    w.opts["continuous"] = cont
    doc8.layers[0].image = ops.rgba_to_qimage(orig8.astype(np.uint8))
    drag(cv8, t, [P(x, 60) for x in list(range(40, 161, 3)) * 3])
    vals[cont] = int(ops.qimage_to_rgba(doc8.layers[0].image)[60, 60, 0])
print("11 lighten, 3x back and forth: without Doorlopend", vals[False], "| with", vals[True], "(start 120)")
assert 120 < vals[False] < vals[True], vals
w.opts["continuous"] = False
doc8.set_modified(False)
# ---- 8. Clone: choosing a new source during a running stroke gives no error
doc9 = Document(200, 150, QColor(200, 150, 120)); cv9 = w.add_document(doc9).canvas; app.processEvents()
cl = w.tools[0xd081]; w.select_tool(cl); w.opts.update(size=20, clone_aligned=True)
RB = Qt.MouseButton.RightButton
def rev(t, p):
    return QMouseEvent(t, cv9.to_widget(p), cv9.to_widget(p), RB, RB if t != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
cl.press(cv9, P(30, 30), rev(QEvent.Type.MouseButtonPress, P(30, 30)))          # source
cl.press(cv9, P(100, 80), ev(cv9, QEvent.Type.MouseButtonPress, P(100, 80)))   # stroke starts
cl.move(cv9, P(110, 80), ev(cv9, QEvent.Type.MouseMove, P(110, 80)))
cl.press(cv9, P(40, 40), rev(QEvent.Type.MouseButtonPress, P(40, 40)))          # new source in the middle of the stroke
cl.move(cv9, P(130, 80), ev(cv9, QEvent.Type.MouseMove, P(130, 80)))           # used to give an error
cl.release(cv9, P(130, 80), ev(cv9, QEvent.Type.MouseButtonRelease, P(130, 80)))
assert not cl.active and cl.source == P(40, 40)
drag(cv9, cl, [P(120, 100), P(140, 100)])  # just continuing to clone works
print("12 cloning: new source during a stroke OK")
doc9.set_modified(False)
for d_ in (doc4, doc5, doc7):
    d_.set_modified(False)
print("ALL OK")
