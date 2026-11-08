"""Algemene programmavoorkeuren (taal, transparantie en arcering, lettertypen) en de schuifbalken rond de afbeelding:
QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_prefs.py"""
import os
import sys
import tempfile
import time
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

app = QApplication(sys.argv)
from pixelpickle import corefonts, dialogs  # noqa: E402
from pixelpickle.document import Document  # noqa: E402
from pixelpickle.mainwindow import MainWindow  # noqa: E402

w = MainWindow(); w.resize(900, 700); w.show()
d = Document(2000, 1500, QColor(255, 255, 255)); sw = w.add_document(d); cv = sw.canvas; app.processEvents()
view = sw.widget()
# schuifbalken: passend in het venster geen balken; op 100% wel, en ze verschuiven het beeld
cv.fit(); cv.repaint(); app.processEvents()
assert not view.hbar.isVisible() and not view.vbar.isVisible()
cv.actual_size(); cv.repaint(); app.processEvents()
assert view.hbar.isVisible() and view.vbar.isVisible()
assert view.hbar.maximum() == int(2000 * cv.zoom - cv.width())
view.hbar.setValue(300); app.processEvents()
assert round(-cv.ox) == 300 and not cv._auto
cv.ox = -500; cv.repaint(); app.processEvents()
assert view.hbar.value() == 500
print("1 schuifbalken: verborgen als het past, zichtbaar op 100%, en ze lopen mee in beide richtingen")
# voorkeurenvenster: pagina's, ruitjespatroon en arcering bewaren
dlg = dialogs.PreferencesDialog(w, "nl")
titles = [dlg.pages.item(i).text() for i in range(dlg.pages.count())]
assert titles == ["Taal", "Transparantie en arcering", "Lettertypen"], titles
dlg.csize.setCurrentIndex(2); dlg.scheme.setCurrentIndex(2)
dlg.shade_op.setValue(60); dlg.crop_bar.setChecked(False)
dlg.save_view_settings()
cv.apply_view_settings()
assert cv.view["checker_size"] == 2 and cv.view["checker_c1"] == "#444444" and cv.view["shade_opacity"] == 60
assert cv.checker.texture().width() == 32 and not cv.view["crop_bar"]
dlg.c1.set_color(QColor(255, 0, 0)); dlg._custom()
assert dlg.scheme.currentIndex() == len(dialogs.CHECKER_SCHEMES)
print("2 voorkeuren: drie onderwerpen; ruitjespatroon, arcering en zwevende bijsnijbalk worden bewaard en toegepast")
# lettertypen: installatie nagebootst (geen echte download)
import shutil  # noqa: E402
fake_src = tempfile.mkdtemp()
font = next((p for p in ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
                          "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") if os.path.exists(p)), None)
calls = []


class FakeResp:
    def __init__(self, data): self.data = data
    def read(self, n=-1):
        d, self.data = self.data, b""
        return d
    def __enter__(self): return self
    def __exit__(self, *a): return False


corefonts.urllib.request.urlopen = lambda req, timeout=60: (calls.append(req.full_url), FakeResp(b"x"))[1]


def fake_extract(tool, exe, dest):  # in plaats van cabextract: een lettertype "uitpakken"
    if font:
        shutil.copy(font, os.path.join(dest, os.path.basename(exe).replace(".exe", ".TTF")))


corefonts._extract = fake_extract
corefonts.extractor = lambda: "cabextract"
inst = corefonts.Installer(); inst.start()
for _ in range(100):
    if inst.done:
        break
    time.sleep(0.05)
assert inst.done and inst.error is None, inst.error
assert len(calls) == len(corefonts.FILES) and calls[0].startswith("https://downloads.sourceforge.net/corefonts/")
assert inst.result and all(p.endswith(".ttf") for p in inst.result)
assert inst.result[0].startswith(corefonts.target_dir())
if font:
    assert corefonts.register(inst.result[:1]) == 1
print("3 lettertypen: download van de bron en uitpakken naar de eigen lettertypemap (nagebootst)")
corefonts.extractor = lambda: None
dlg2 = dialogs.PreferencesDialog(w, "nl")
if not corefonts.installed():
    assert not dlg2.font_btn.isEnabled() and "cabextract" in dlg2.font_state.text()
print("4 zonder uitpakprogramma: duidelijke melding, knop uit")
d.set_modified(False)
print("ALLES OK")
