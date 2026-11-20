"""Layer groups and masks: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_groups.py"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
app = QApplication(sys.argv)
from pixelpickle.document import Document, Layer, new_image
from pixelpickle import fileio

RED, BLUE, WHITE = QColor(255, 0, 0), QColor(0, 0, 255), QColor(255, 255, 255)
d = Document(20, 10)                                  # white
d.add_layer(Layer("rood", new_image(20, 10, RED)))
d.select_all()
from pixelpickle import imageops as ops
import numpy as np
m = np.zeros((10, 20), np.uint8); m[:, :10] = 255      # left half selected
d.set_selection(ops.mask_to_qimage(m))
d.add_mask("show_sel")                                 # red visible only on the left
assert [l.kind for l in d.layers] == ["raster", "raster", "mask", "group"], [l.kind for l in d.layers]
c = d.composite()
assert c.pixelColor(2, 5) == RED and c.pixelColor(15, 5) == WHITE, (c.pixelColor(2, 5).name(), c.pixelColor(15, 5).name())
print("mask in group hides only within the group: OK")

g = d.layers[3]; g.opacity = 0.5
c = d.composite(); assert c.pixelColor(2, 5).green() > 100, "group opacity"
g.opacity = 1.0
d.active = 2; d.invert_mask()
c = d.composite(); assert c.pixelColor(2, 5) == WHITE and c.pixelColor(15, 5) == RED
print("invert mask and group opacity: OK")

# add layer while the group header is active -> goes into the group
d.active = 3; d.add_layer(Layer("blauw", new_image(20, 10, BLUE)))
blue = d.layer(); assert blue.group is g
print("new layer in active group: OK", [l.name for l in d.layers])

# save and load preserves structure
p = os.path.join(tempfile.mkdtemp(), "g.ora"); fileio.save(d, p); d2 = fileio.load(p)
assert [l.kind for l in d2.layers] == [l.kind for l in d.layers], ([l.kind for l in d2.layers], [l.kind for l in d.layers])
assert d2.composite().pixelColor(15, 5) == d.composite().pixelColor(15, 5)
print("OpenRaster save/load with group and mask: OK")

# undo with group references
n = len(d.layers); d.ungroup(); assert all(l.group is None for l in d.layers) and len(d.layers) == n - 1
d.undo(); assert len(d.layers) == n and d.layers[-1].kind == "group"
assert all(l.group is None or l.group in d.layers for l in d.layers), "group reference after undo"
print("ungroup + undo: OK")

d.active = len(d.layers) - 1; d.merge_group(); assert d.layer().kind == "raster" and len(d.layers) == 2
print("merge group: OK")
d.active = 1; d.duplicate_layer(); d.move_layer(-1); d.arrange_layer("top"); d.delete_layer()
d.flatten(); assert len(d.layers) == 1
print("ALL OK")
