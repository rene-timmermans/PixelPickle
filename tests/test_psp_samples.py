"""Reads all sample files (.pspimage and related) from a local installation of the original
program. Those files are not shipped; if they are not there, this test is skipped."""
import sys, glob, collections, struct, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
base = os.path.expanduser("~/.var/app/com.usebottles.bottles/data/bottles/bottles/pspxi/drive_c/Program Files/"
                          "Corel/Corel Paint Shop Pro Photo XI/")
if not os.path.isdir(base):
    print("skipped: no local sample files")
    print("ALL OK")
    sys.exit(0)
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from pixelpickle import psp
files = [f for f in glob.glob(glob.escape(base) + "**/*", recursive=True) if f.lower().endswith((".pspimage",".psptube",".pspframe",".pspmask",".tub",".msk",".psp"))]
ok, fail, kinds = collections.Counter(), [], collections.Counter()
samples = {}
for f in files:
    d = open(f, "rb").read(36)
    if d[:25] != b"Paint Shop Pro Image File": continue
    v = struct.unpack_from("<H", d, 32)[0]
    try:
        doc = psp.load(f); ok[v] += 1
        for l in doc.layers: kinds[l.kind] += 1
        samples.setdefault(os.path.splitext(f)[1].lower(), (f, doc))
    except Exception as e:
        fail.append((v, f.split("/")[-1], repr(e)[:120]))
print("succeeded per version:", dict(ok), "layer kinds:", dict(kinds)); print("failed:", len(fail))
for x in fail[:8]: print(x)
from PySide6.QtGui import QImage, QPainter, QColor
sheet = QImage(1200, 300, QImage.Format.Format_ARGB32); sheet.fill(QColor(200, 200, 200))
p = QPainter(sheet); x = 0
for ext, (f, doc) in samples.items():
    im = doc.composite().scaled(230, 260, aspectMode=__import__("PySide6.QtCore").QtCore.Qt.AspectRatioMode.KeepAspectRatio)
    p.drawImage(x, 30, im); p.drawText(x, 15, f"{ext} {len(doc.layers)} lagen"); x += 240
p.end(); sheet.save(os.path.join(tempfile.gettempdir(), "psp_sheet.png"))
assert files and not fail, f"{len(fail)} files could not be opened"
print("ALL OK")
