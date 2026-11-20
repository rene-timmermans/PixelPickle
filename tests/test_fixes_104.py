"""Improvements after 1.0.3: mirroring in place, Transition to goal does not build up, Ctrl = eyedropper with brushes,
opacity in the layers palette with slider, compact tabs in Materials, one-pixel-wide selections:
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_fixes_104.py"""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from pixelpickle import imageops as ops  # noqa: E402
from pixelpickle.document import Document, Layer, new_image  # noqa: E402
from pixelpickle.mainwindow import MainWindow  # noqa: E402
from pixelpickle.tools import SliderSpinBox  # noqa: E402

w = MainWindow(); w.show()
d = Document(200, 120, QColor(200, 150, 120)); cv = w.add_document(d).canvas; app.processEvents()
L, R = Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton


def ev(kind, btn=L, mods=Qt.KeyboardModifier.NoModifier):
    held = btn if kind != QEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    return QMouseEvent(kind, QPointF(), QPointF(), btn, held, mods)


def stroke(tool, a, b, btn=L, mods=Qt.KeyboardModifier.NoModifier):
    tool.press(cv, QPointF(*a), ev(QEvent.Type.MouseButtonPress, btn, mods))
    tool.move(cv, QPointF(*b), ev(QEvent.Type.MouseMove, btn, mods))
    tool.release(cv, QPointF(*b), ev(QEvent.Type.MouseButtonRelease, btn, mods))
    app.processEvents()


# 1. mirror around own content
lay = Layer("figuur", new_image(200, 120)); d.add_layer(lay)
p = QPainter(lay.image); p.fillRect(20, 30, 30, 40, QColor(255, 0, 0)); p.fillRect(20, 30, 5, 40, QColor(0, 0, 255)); p.end()
w.actions_by_id[0x800d].trigger()
a = ops.qimage_to_rgba(d.layer().image)
xs = np.nonzero((a[..., 3] > 0).any(0))[0]
assert (xs.min(), xs.max()) == (20, 49) and a[50, 47, 2] > 200, (xs.min(), xs.max())
print("1 mirror: the figure stays in place and flips about its own axis")
d.active = 0
# 2. Transition to goal: two strokes = one stroke
t = w.tools[0xd0ab]; w.select_tool(t)
w.opts.update(size=30, hardness=100, opacity=50, step=10, target_mode=0, continuous=False)
w.fg = QColor(0, 200, 0)
stroke(t, (10, 100), (190, 100)); one = d.layers[0].image.pixelColor(100, 100).getRgb()
stroke(t, (10, 100), (190, 100)); two = d.layers[0].image.pixelColor(100, 100).getRgb()
assert one == two and one != (200, 150, 120, 255), (one, two)
print("2 Move toward target: a second stroke over the same spot does not make it stronger")
# 3. Ctrl = eyedropper with the color replacer and the brush
for cid in (0xd0ac, 0xd091):
    tool = w.tools[cid]; w.select_tool(tool)
    before = ops.qimage_to_rgba(d.layers[0].image).copy()
    w.fg = QColor(1, 2, 3)
    tool.press(cv, QPointF(5, 5), ev(QEvent.Type.MouseButtonPress, L, Qt.KeyboardModifier.ControlModifier))
    tool.release(cv, QPointF(5, 5), ev(QEvent.Type.MouseButtonRelease, L, Qt.KeyboardModifier.ControlModifier))
    assert w.fg.getRgb()[:3] == (200, 150, 120), w.fg.getRgb()
    assert np.array_equal(before, ops.qimage_to_rgba(d.layers[0].image)), "Ctrl+click does not paint"
print("3 Ctrl+click with color replacer and brush picks up the color (dropper) and does not paint")
# 4. opacity in the layers palette: input field with slider, no separate slider
assert isinstance(w.layers.spin, SliderSpinBox) and not hasattr(w.layers, "slider")
w.layers.spin.set_fraction(0.5); assert abs(d.layer().opacity - 0.5) < 0.011
print("4 opacity with slider below the input field")
# 5. compact tabs above the color picker
assert max(w.materials.tabs.tabBar().tabRect(i).width() for i in range(2)) <= 40
print("5 compact tabs")
# 6. one-pixel-wide selection
sel = w.tools[0xd021]; w.select_tool(sel); w.opts.update(sel_shape=0, feather=0, antialias=True, sel_mode=0)
cv.zoom = 8
stroke(sel, (10.3, 5.2), (10.8, 60.6))
m = ops.qimage_to_mask(d.sel)
assert np.nonzero((m > 0).any(0))[0].tolist() == [10] and m[20, 10] == 255
stroke(sel, (50, 50), (50.1, 50.1)); assert d.sel is None
print("6 dragging within one pixel column selects exactly that column; clicking clears the selection")
# 7. Select on a layer group: frame around the group's content, everything moves together
d.sel = None
base_bg = QImage(d.layers[0].image)
circles = []
for i in range(3):
    d.add_layer(); circles.append(d.layer()); p = QPainter(d.layer().image); p.setBrush(QColor(0, 0, 255)); p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(30 + 40 * i, 30), 8, 8); p.end()
d.active = d.layers.index(circles[0]); d.new_group()
g = d.layer()
for l in circles:
    l.group = g
d.normalize(); d.active = d.layers.index(g)
pick = w.tools[0xd011]; w.select_tool(pick); cv.zoom = 1
box = pick._bbox(d)
assert abs(box.left() - 22) <= 1 and abs(box.right() - 118) <= 1, box
stroke(pick, (30, 30), (40, 50))
assert all(l.image.pixelColor(40 + 40 * i, 50).alpha() == 255 for i, l in enumerate(circles))
assert all(l.image.pixelColor(30 + 40 * i, 30).alpha() == 0 for i, l in enumerate(circles))
assert d.layers[0].image == base_bg, "background must not move along"
names = [l.name for l in circles]
d.undo()
by_name = {l.name: l for l in d.layers}
assert all(by_name[n].image.pixelColor(30 + 40 * i, 30).alpha() == 255 for i, n in enumerate(names)), "undo"

print("7 Selecting on a layer group moves all layers in it together, the background stays put")
# 8. Distribute and align on a layer group: each layer is an object
grp = [l for l in d.layers if l.kind == "group"][-1]
d.active = d.layers.index(grp)
kids = [l for l in d.children(grp)]
bb = lambda l: ops.mask_bbox(ops.qimage_to_rgba(l.image)[..., 3] > 0)
p = QPainter(kids[1].image); p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear); p.fillRect(kids[1].image.rect(), Qt.GlobalColor.transparent); p.end()
p = QPainter(kids[1].image); p.setBrush(QColor(0, 0, 255)); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QPointF(50, 80), 8, 8); p.end()
w.all_handlers()[0x8164]()  # distribute vertically evenly (centers)
ys = sorted(bb(l).center().y() for l in kids)
assert abs((ys[1] - ys[0]) - (ys[2] - ys[1])) <= 1, ys
w.all_handlers()[0x8163]()  # align tops
assert len({bb(l).top() for l in kids}) == 1, [bb(l) for l in kids]
print("8 distribute and align work on the layers of a layer group")
# 9. click with Select on another layer makes that layer active
w.select_tool(pick)
for l in d.layers:
    if l.name == "figuur":
        l.visible = False
target = kids[0]
c = bb(target).center()
d.active = 0  # background active: frame around the whole background, so first another layer outside the group
d.add_layer(); other = d.layer()
p = QPainter(other.image); p.fillRect(150, 90, 20, 20, QColor(0, 200, 0)); p.end()
pick._stale = True
stroke(pick, (c.x(), c.y()), (c.x(), c.y()))
assert d.layer() is target, d.layer().name
stroke(pick, (160, 100), (165, 100))
assert d.layer() is other and other.image.pixelColor(172, 100).alpha() == 255
print("9 clicking a layer with Select makes that layer active and drags it right away")
# 10. adjustments and effects on a layer group: each raster layer in the group
from pixelpickle.effectdialog import EffectDialog
from pixelpickle import dialogs
d2 = Document(80, 60, QColor(255, 255, 255)); cv2 = w.add_document(d2).canvas; app.processEvents()
gl = []
for x in (10, 50):
    d2.add_layer(); gl.append(d2.layer())
    p = QPainter(d2.layer().image); p.fillRect(x, 10, 15, 15, QColor(0, 100, 200)); p.end()
d2.active = d2.layers.index(gl[0]); d2.new_group(); grp2 = d2.layer()
for l in gl:
    l.group = grp2
d2.normalize(); d2.active = d2.layers.index(grp2)
bg_before = QImage(d2.layers[0].image)
dlg = EffectDialog(w, d2, w.effects[0x8054])
assert not ops.qimage_to_rgba(dlg.region)[..., 3].max() == 0, "preview of the group is empty"
dlg.set_params({"red": 100, "green": 0, "blue": 0}); dlg.accept()
assert all(l.image.pixelColor(x + 5, 15).red() > 200 for l, x in zip(gl, (10, 50))), [l.image.pixelColor(15, 15).name() for l in gl]
assert d2.layers[0].image == bg_before
d2.undo()
names2 = [l.name for l in gl]
assert all(l.image.pixelColor(x + 5, 15).red() == 0 for l, x in zip([l for l in d2.layers if l.name in names2], (10, 50)))
d2.active = [l.kind for l in d2.layers].index("group")
w.all_handlers()[0x804b]()  # negative, without a window
neg = [l for l in d2.layers if l.name in names2]
assert all(l.image.pixelColor(x + 5, 15).red() == 255 for l, x in zip(neg, (10, 50)))
d2.undo(); d2.active = [l.kind for l in d2.layers].index("group")
ad = dialogs.AdjustDialog(w, d2, "Helderheid/contrast", ops.adj_brightness_contrast,
                          [("brightness", "Helderheid:", -100, 100, 60), ("contrast", "Contrast:", -100, 100, 0)])
ad.accept()
assert all(l.image.pixelColor(x + 5, 15).lightness() > QColor(0, 100, 200).lightness()
           for l, x in zip([l for l in d2.layers if l.name in names2], (10, 50)))
d2.set_modified(False)
print("10 adjustments and effects work on all raster layers of a layer group, with preview")
# 11. choosing another layer in the layers palette: the canvas redraws immediately (Select frame)
w.select_tool(w.tools[0xd011]); app.processEvents()
painted = []
cv2.paintEvent = lambda e, _orig=cv2.paintEvent: (painted.append(1), _orig(e))
row = [w.layers._index(r) for r in range(w.layers.list.count())].index([l.name for l in d2.layers].index(names2[0]))
w.layers.on_row(row); app.processEvents()
assert painted, "canvas not redrawn after layer switch"
print("11 choosing a layer in the layer palette updates the canvas immediately")
# 12. mirroring a layer group: as a whole, around the center of the group's content
d3 = Document(100, 50, QColor(255, 255, 255)); w.add_document(d3); app.processEvents()
ml = []
for x in (10, 40):
    d3.add_layer(); ml.append(d3.layer())
    p = QPainter(d3.layer().image); p.fillRect(x, 10, 10, 10, QColor(255, 0, 0)); p.end()
ml[1].image.setPixelColor(49, 10, QColor(0, 0, 255))  # marker at the top right of the right block
d3.active = d3.layers.index(ml[0]); d3.new_group(); g3 = d3.layer()
for l in ml:
    l.group = g3
d3.normalize(); d3.active = d3.layers.index(g3)
d3.mirror_layer(True)  # group spans x 10..49, center 30: blocks swap places
assert ml[0].image.pixelColor(45, 15) == QColor(255, 0, 0) and ml[0].image.pixelColor(15, 15).alpha() == 0
assert ml[1].image.pixelColor(15, 15) == QColor(255, 0, 0) and ml[1].image.pixelColor(10, 10) == QColor(0, 0, 255)
d3.set_modified(False)
print("12 mirroring a layer group happens as a whole, in the same place")
# 13. jumping in the history: in one go, with the same result as step by step
d4 = Document(60, 40, QColor(255, 255, 255)); w.add_document(d4); app.processEvents()
for i in range(5):
    d4.add_layer(Layer(f"L{i}", new_image(60, 40)), label=f"stap {i}")
names_at = lambda: [l.name for l in d4.layers]
full = names_at()
d4.jump_history(2)
assert names_at() == full[:3] and len(d4.undo_stack) == 2 and len(d4.redo_stack) == 3, names_at()
assert [lab for lab, _ in d4.redo_stack] == ["stap 4", "stap 3", "stap 2"]
d4.redo(); assert names_at() == full[:4]
d4.jump_history(5); assert names_at() == full and not d4.redo_stack
d4.jump_history(0); assert names_at() == full[:1]
d4.undo(); assert names_at() == full[:1]  # nothing left to undo
w.history.set_doc(d4); w.history.refresh()
w.history.jump(w.history.list.item(5)); assert names_at() == full
d4.set_modified(False)
print("13 jumping in the history happens at once and matches step by step")
# 14. color swatch in effect windows: the color picker does not take over the swatch color
from PySide6.QtWidgets import QColorDialog
from pixelpickle.effectdialog import ColorButton
sw = ColorButton((89, 255, 60)); sw.show(); app.processEvents()
assert sw.grab().toImage().pixelColor(sw.width() // 2, sw.height() // 2) == QColor(89, 255, 60)
cdlg = QColorDialog(sw); cdlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog); cdlg.show(); app.processEvents()
assert cdlg.grab().toImage().pixelColor(5, 5) != QColor(89, 255, 60), "color picker was drawn in the swatch color"
cdlg.close(); sw.close()
print("14 color swatch shows the exact color and does not tint the color picker")
# 15. Undo and Redo gray when there is nothing to undo or redo
d5 = Document(40, 30, QColor(255, 255, 255)); w.add_document(d5); app.processEvents()
U, R = w.actions_by_id[0xe12b], w.actions_by_id[0xe12c]
assert not U.isEnabled() and not R.isEnabled(), "new image: both greyed out"
d5.add_layer(); app.processEvents()
assert U.isEnabled() and not R.isEnabled()
U.trigger(); app.processEvents()
assert not U.isEnabled() and R.isEnabled(), "after undoing back to the start"
R.trigger(); app.processEvents()
assert U.isEnabled() and not R.isEnabled()
d6 = Document(40, 30, QColor(255, 255, 255)); w.add_document(d6); app.processEvents()
assert not U.isEnabled() and not R.isEnabled(), "other image without history"
w.mdi.setActiveSubWindow([sw for sw in w.mdi.subWindowList() if sw.canvas.doc is d5][0]); app.processEvents()
assert U.isEnabled(), "back to the image with history"
d5.set_modified(False); d6.set_modified(False)
print("15 Undo and Redo are greyed out when there is nothing left to do, also when switching images")
# 16. effect window: exact preview at full resolution, and Preview on image never shows an intermediate state
import time as _time
d7 = Document(400, 300, QColor(255, 255, 255)); w.add_document(d7); app.processEvents()
arr = np.zeros((300, 400, 4), np.uint8); arr[..., 3] = 255
arr[::7, :, :3] = 200; arr[:, ::11, 1] = 120; arr[100:200, 150:250, 0] = 255
d7.layers[0].image = ops.rgba_to_qimage(arr)
ed = EffectDialog(w, d7, w.effects[0x80a7]); ed.show(); ed.fit_preview(); app.processEvents()
ed.on_image.setChecked(True)
def _wait(cond, sec=20):
    t0 = _time.time()
    while not cond() and _time.time() - t0 < sec:
        app.processEvents()
for val in (10, 40, 70):  # drag quickly in succession
    ed.widgets[next(iter(ed.widgets))][1].setValue(val) if ed.widgets[next(iter(ed.widgets))][0] == "int" else None
    app.processEvents()
_wait(lambda: ed._full is not None and ed._full[0] == ed._pkey() and ed._job is None)
_wait(lambda: False, 0.6)
want = ed.result_image(ed.origs[0])
assert d7.layers[0].image == want, "image does not show the result of the last settings"
from PySide6.QtCore import Qt as _Qt
from pixelpickle.effectdialog import checker_pixmap
cx, cy, _, _ = ed._view(); full = want.copy(ed.rect)
sc = full.scaled(round(full.width() * ed.zoom), round(full.height() * ed.zoom), _Qt.AspectRatioMode.IgnoreAspectRatio,
                 _Qt.TransformationMode.SmoothTransformation)
exp = checker_pixmap(ed._draw(sc, cx * ed.zoom, cy * ed.zoom, 1.0)).toImage()
diff = np.abs(ops.qimage_to_rgba(ed.after.pixmap().toImage().convertToFormat(ops.FMT)).astype(int)
              - ops.qimage_to_rgba(exp.convertToFormat(ops.FMT)).astype(int)).mean()
assert diff < 1, diff
ed.reject(); d7.set_modified(False)
print("16 exact preview equals the result; preview on image follows the last settings")
# 17. windows with Preview on image: not modal for the window manager (KDE otherwise makes the main window
#     dark and dull), but clicks and keys in the main window are still blocked
from PySide6.QtCore import QTimer as _QT
from PySide6.QtGui import QMouseEvent as _ME
from pixelpickle import dialogs as _dlgs
d8 = Document(80, 60, QColor(200, 30, 30)); cv8 = w.add_document(d8).canvas; app.processEvents()
ed8 = EffectDialog(w, d8, w.effects[0x82d8])
seen = {}
def _probe():
    seen["modal"] = ed8.isModal() or ed8.windowModality() != Qt.WindowModality.NonModal
    seen["visible"] = ed8.isVisible()
    before = len(d8.undo_stack)
    w.select_tool(w.tools[0xd091])
    pos = QPointF(cv8.width() / 2, cv8.height() / 2)
    for t in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        app.sendEvent(cv8, _ME(t, pos, pos, Qt.MouseButton.LeftButton,
                               Qt.MouseButton.LeftButton if t == QEvent.Type.MouseButtonPress else Qt.MouseButton.NoButton,
                               Qt.KeyboardModifier.NoModifier))
    seen["painted"] = len(d8.undo_stack) != before
    ed8.accept()
_QT.singleShot(200, _probe)
res = _dlgs.exec_live(ed8, w)
assert seen == {"modal": False, "visible": True, "painted": False}, seen
assert res == 1 and len(d8.undo_stack) == 1, (res, len(d8.undo_stack))
cv8.mousePressEvent  # canvas then works normally again
d8.set_modified(False)
print("17 effect dialog not modal (no KDE dimming), main window blocked; OK works")
# 18. default toolbar without Enhance photo/Palettes, with full screen; Enhance photo in Adjust;
#     check marks at View > Toolbars
from PySide6.QtWidgets import QToolButton as _TB
A = w.actions_by_id
assert not [b for b in w.std_toolbar.findChildren(_TB) if b.menu() is not None and b.popupMode() == _TB.ToolButtonPopupMode.InstantPopup]
assert A[0x801d] in w.std_toolbar.actions() and A[0x801d].isCheckable()
A[0x801d].trigger(); app.processEvents()
assert w.isFullScreen() and A[0x801d].isChecked()
A[0x801d].trigger(); app.processEvents()
assert not w.isFullScreen() and not A[0x801d].isChecked()
adj = w.top_menus["Aanpassen"]
from PySide6.QtWidgets import QMenu as _QM
fv = [x for x in adj.findChildren(_QM) if x.title().replace("&", "") == "Foto verbeteren"]
assert fv and adj.actions()[0].text().replace("&", "") == "Foto verbeteren", "Foto verbeteren is at the top in Aanpassen"
ids = {cid for cid, act in A.items() if act in fv[0].actions()}
assert ids == {0x8240, 0x82d8, 0x82f1, 0x82c1, 0x82dc, 0x806a, 0x82db}, sorted(map(hex, ids))
assert sum(1 for a in adj.actions() if a in (A[0x8240], A[0x82d8])) == 0, "separate items no longer at the top"
for cid, bar in ((0xe800, w.std_toolbar), (0x81f9, w.tools_toolbar)):
    assert A[cid].isCheckable() and A[cid].isChecked()
    A[cid].trigger(); app.processEvents(); assert bar.isHidden() and not A[cid].isChecked()
    A[cid].trigger(); app.processEvents(); assert not bar.isHidden() and A[cid].isChecked()
w.std_toolbar.hide(); app.processEvents(); assert not A[0xe800].isChecked(), "closing via toolbar menu: checkmark gone"
w.std_toolbar.show(); app.processEvents()
A[0xe801].trigger(); app.processEvents(); assert w.statusBar().isHidden() and not A[0xe801].isChecked()
A[0xe801].trigger(); app.processEvents(); assert A[0xe801].isChecked()
print("18 toolbar cleaned up with full screen button, Foto verbeteren in Aanpassen, checkmarks under Werkbalken")
# 19. drag and drop from other programs
from PySide6.QtCore import QMimeData, QUrl, QPoint
from PySide6.QtGui import QDragEnterEvent, QDropEvent
tmpd = tempfile.mkdtemp()
pngp = os.path.join(tmpd, "gesleept.png"); QImage(30, 20, QImage.Format.Format_ARGB32).save(pngp)
txtp = os.path.join(tmpd, "notitie.txt"); open(txtp, "w").write("x")
def _drag(mime):
    ev = QDragEnterEvent(QPoint(50, 50), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    w.dragEnterEvent(ev); return ev.isAccepted()
def _drop(mime):
    ev = QDropEvent(QPointF(50, 50), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    w.dropEvent(ev); app.processEvents(); return ev.isAccepted()
mf = QMimeData(); mf.setUrls([QUrl.fromLocalFile(pngp)])
mt = QMimeData(); mt.setUrls([QUrl.fromLocalFile(txtp)])
mi = QMimeData(); img = QImage(12, 9, QImage.Format.Format_ARGB32); img.fill(QColor(0, 200, 0)); mi.setImageData(img)
assert w.acceptDrops() and _drag(mf) and _drag(mi) and not _drag(mt), "file and image yes, text file no"
n = len(w.mdi.subWindowList())
assert _drop(mf) and w.doc().path == pngp and len(w.mdi.subWindowList()) == n + 1
assert _drop(mi) and (w.doc().w, w.doc().h) == (12, 9) and w.doc().layers[0].image.pixelColor(3, 3) == QColor(0, 200, 0)
assert not _drop(mt) and len(w.mdi.subWindowList()) == n + 2
assert not w.mdi.viewport().acceptDrops() and not w.canvas().acceptDrops(), "canvas must not intercept the drag action"
for sw in w.mdi.subWindowList():
    sw.canvas.doc.set_modified(False)
print("19 dropping files and images from other programs opens them; other files do not")
# 20. drop with Ctrl on an open image: new layer, centered on the drop position
d9 = Document(200, 150, QColor(255, 255, 255)); cv9 = w.add_document(d9).canvas
w.resize(1200, 800); app.processEvents()
red = QImage(20, 10, QImage.Format.Format_ARGB32); red.fill(QColor(255, 0, 0))
redp = os.path.join(tmpd, "rood.png"); red.save(redp)
mr = QMimeData(); mr.setUrls([QUrl.fromLocalFile(redp)])
target = cv9.to_widget(QPointF(60, 40)).toPoint()
gpos = cv9.mapTo(w, target)
assert w._canvas_at(gpos) is cv9, "canvas under the mouse found"
n_win, n_lay = len(w.mdi.subWindowList()), len(d9.layers)
ev = QDropEvent(QPointF(gpos), Qt.DropAction.CopyAction, mr, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier)
w.dropEvent(ev); app.processEvents()
assert ev.isAccepted() and len(w.mdi.subWindowList()) == n_win and len(d9.layers) == n_lay + 1
nl = d9.layer()
assert nl.name == "rood" and nl.image.pixelColor(60, 40) == QColor(255, 0, 0) and nl.image.pixelColor(50, 35) == QColor(255, 0, 0)
assert nl.image.pixelColor(49, 40).alpha() == 0 and nl.image.pixelColor(70, 40).alpha() == 0
mi2 = QMimeData(); mi2.setImageData(red)
ev = QDropEvent(QPointF(gpos), Qt.DropAction.CopyAction, mi2, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier)
w.dropEvent(ev); app.processEvents()
assert len(d9.layers) == n_lay + 2 and len(w.mdi.subWindowList()) == n_win
ev = QDropEvent(QPointF(gpos), Qt.DropAction.CopyAction, mr, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
w.dropEvent(ev); app.processEvents()
assert len(w.mdi.subWindowList()) == n_win + 1, "without Ctrl: open as its own image"
for sw in w.mdi.subWindowList():
    sw.canvas.doc.set_modified(False)
print("20 dropping with Ctrl on an image adds a layer at the drop position")
d.set_modified(False)
print("ALL OK")
