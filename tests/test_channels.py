"""Alfakanalen: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_channels.py
Selectie en masker opslaan in en laden uit een alfakanaal, verwijderen, ongedaan maken, meedraaien met de
afbeelding en bewaren in .ora."""
import os
import sys
import tempfile
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

app = QApplication(sys.argv)
from pixelpickle import dialogs, fileio, imageops as ops  # noqa: E402
from pixelpickle.document import Document  # noqa: E402
from pixelpickle.mainwindow import MainWindow  # noqa: E402

w = MainWindow(); w.show()
d = Document(40, 20, QColor(255, 255, 255)); w.add_document(d); app.processEvents()
m = np.zeros((20, 40), np.uint8); m[:, :10] = 255
d.set_selection(ops.mask_to_qimage(m))

# vensters automatisch bevestigen met wat de test wil
answers = []
orig_exec = dialogs.AlphaChannelDialog.exec


def fake_exec(self):
    a = answers.pop(0)
    if self.mode == "save":
        self.name.setText(a)
    elif self.mode == "load":
        row, op, inv = a
        self.list.setCurrentRow(row)
        if self.op is not None:
            self.op.setCurrentIndex(["replace", "add", "sub"].index(op))
        self.invert.setChecked(inv)
    else:
        if a == "all":
            self.all.setChecked(True)
        else:
            self.list.clearSelection(); self.list.item(a).setSelected(True)
    return QDialog.DialogCode.Accepted


dialogs.AlphaChannelDialog.exec = fake_exec
run = lambda cid: w.actions_by_id[cid].trigger()  # noqa: E731

answers.append("Links"); run(0x810f)
assert d.channel_names() == ["Links"] and d.channel_mask(0)[5, 2] == 255 and d.channel_mask(0)[5, 30] == 0
print("1 selectie opgeslagen in alfakanaal 'Links'")
d.set_selection(None)
answers.append((0, "replace", True)); run(0x810e)
sel = ops.qimage_to_mask(d.sel)
assert sel[5, 2] == 0 and sel[5, 30] == 255
print("2 selectie geladen (omgekeerd): rechterdeel geselecteerd")
# masker uit kanaal, en weer opslaan als tweede kanaal
d.set_selection(None)
answers.append((0, "replace", False)); run(0x8110)
assert d.layer().kind == "mask"
assert d.mask_values()[5, 2] == 255 and d.mask_values()[5, 30] == 0
c = d.composite()
answers.append("Masker 1"); run(0x8111)
assert d.channel_names() == ["Links", "Masker 1"]
print("3 masker geladen uit kanaal en opgeslagen als 'Masker 1'")
# overschrijven met dezelfde naam
d.set_selection(ops.mask_to_qimage(255 - m))
answers.append("Links"); run(0x810f)
assert d.channel_names() == ["Links", "Masker 1"] and d.channel_mask(0)[5, 2] == 0
print("4 bestaand kanaal overschreven")
d.undo()
assert d.channel_mask(0)[5, 2] == 255
print("5 ongedaan maken zet het kanaal terug")
# meedraaien met de afbeelding
d.rotate(90)
assert d.channels[0][1].width() == 20 and d.channels[0][1].height() == 40
d.undo()
d.crop(QRect(5, 0, 20, 20))
assert d.channels[0][1].size() == d.rect().size() and d.channel_mask(0)[5, 2] == 255 and d.channel_mask(0)[5, 8] == 0
print("6 kanalen draaien en snijden mee met de afbeelding")
# .ora
path = os.path.join(tempfile.mkdtemp(), "k.ora")
fileio.save_ora(d, path)
d2 = fileio.load_ora(path)
assert d2.channel_names() == ["Links", "Masker 1"] and np.array_equal(d2.channel_mask(0), d.channel_mask(0))
print("7 bewaard en teruggelezen in .ora")
# verwijderen
answers.append(1); run(0x81e4)
assert d.channel_names() == ["Links"]
answers.append("all"); run(0x81e4)
assert d.channels == []
d.undo(); assert d.channel_names() == ["Links"]
print("8 verwijderen (een kanaal, alle kanalen) en ongedaan maken")
# venster zelf opbouwen (voorbeeld, knoppen)
dialogs.AlphaChannelDialog.exec = orig_exec
dlg = dialogs.AlphaChannelDialog(w, "x", d, "load", selection_ops=True)
assert dlg.preview.pixmap() is not None and not dlg.preview.pixmap().isNull() and dlg.ok.isEnabled()
dlg2 = dialogs.AlphaChannelDialog(w, "x", d, "save", "Selectie 2"); dlg2.show(); app.processEvents()
assert dlg2.ok.isEnabled() and dlg2.name.text() == "Selectie 2", "standaardnaam mag niet vanzelf een bestaand kanaal worden"
dlg2.name.setText(""); assert not dlg2.ok.isEnabled()
print("9 vensters: voorbeeld en OK-knop")
d.set_modified(False)
print("ALLES OK")
