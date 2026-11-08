"""Alle vertalingen: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_languages.py
Per taal: catalogus compleet, invulplekken kloppen, handleiding aanwezig, en na het starten in die taal
staat er geen Nederlandse tekst meer in de menu's, de optiebalk en een effectvenster."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "pixelpickle", "data")
sys.path.insert(0, ROOT)

if len(sys.argv) > 1:  # één taal in een eigen proces (de taal wordt bij het starten gekozen)
    import tempfile
    os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QAbstractButton, QApplication, QLabel, QWidget
    lang = sys.argv[1]
    app = QApplication(sys.argv)
    from pixelpickle import i18n
    assert i18n.load(lang) == lang
    if i18n.is_rtl():
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    i18n.install(app)
    from pixelpickle.document import Document
    from pixelpickle.mainwindow import MainWindow
    cat = json.load(open(os.path.join(DATA, f"lang_{lang}.json"), encoding="utf-8"))
    # alles wat in deze taal een andere tekst heeft, mag niet meer in de oorspronkelijke vorm te zien zijn
    dutch = {k for k, v in cat.items() if v and v != k and k.replace("&", "") != v.replace("&", "")}
    left = set()
    w = MainWindow(); w.show(); app.processEvents()
    doc = Document(120, 80); w.add_document(doc); app.processEvents()

    def check(text, where):
        if text and text in dutch:
            left.add((text, where))

    def walk(m, path):
        m.popup(w.mapToGlobal(w.rect().center())); app.processEvents(); m.hide()
        for a in m.actions():
            if not a.isSeparator():
                check(a.text(), path)
                if a.menu():
                    walk(a.menu(), path + " > " + a.text())
    for a in w.menuBar().actions():
        walk(a.menu(), a.text())
    from PySide6.QtWidgets import QComboBox
    for t in [t for t in w.tools.values() if t.available]:
        w.select_tool(t); app.processEvents()
        check(t.name, "gereedschap")
        for c in w.opt_bar.findChildren(QWidget):
            if isinstance(c, (QLabel, QAbstractButton)):
                check(c.text(), "optiebalk " + t.name)
            if isinstance(c, QComboBox):
                for i in range(c.count()):
                    check(c.itemText(i), "keuzelijst " + t.name)
    for pal in (w.materials, w.layers, w.history):
        for c in pal.findChildren(QWidget):
            check(c.toolTip(), "palet")
            if isinstance(c, (QLabel, QAbstractButton)):
                check(c.text(), "palet")
    from pixelpickle.effectdialog import EffectDialog
    dlg = EffectDialog(w, doc, w.effects[0x809e]); dlg.show(); app.processEvents()
    for c in dlg.findChildren(QWidget):
        if isinstance(c, (QLabel, QAbstractButton)):
            check(c.text(), "effectvenster")
    dlg.reject()
    html = w.manual_html()
    assert "{tools}" not in html and os.path.exists(os.path.join(DATA, f"manual_{lang}.html")), lang
    print(lang, "menu Bestand:", w.menuBar().actions()[0].text(), "| richting:",
          "rtl" if app.layoutDirection() == Qt.LayoutDirection.RightToLeft else "ltr", "| Nederlands over:", len(left))
    for t_, wh in sorted(left)[:10]:
        print("   ", repr(t_), "@", wh)
    doc.set_modified(False)
    sys.exit(1 if left else 0)

from pixelpickle.i18n import LANGUAGES  # noqa: E402
en = json.load(open(os.path.join(DATA, "lang_en.json"), encoding="utf-8"))
# alle teksten van alle effecten (naam, labels, keuzes) moeten in de catalogus staan
from pixelpickle.effects import load_all  # noqa: E402
gaps = set()
for e in load_all().values():
    for t in [e.name] + [p["label"] for p in e.params] + [o for p in e.params for o in p.get("options", [])]:
        if t not in en and t.replace("&", "") not in en:  # precies zoals het op het scherm komt
            gaps.add(t)
assert not gaps, f"effectteksten zonder vertaling: {sorted(gaps)}"
print("effectteksten: alle namen, labels en keuzes staan in de catalogus")
failed = []
for code, name in LANGUAGES:
    if code in ("nl", "en"):
        continue
    path = os.path.join(DATA, f"lang_{code}.json")
    assert os.path.exists(path), f"ontbreekt: {path}"
    cat = json.load(open(path, encoding="utf-8"))
    missing = set(en) - set(cat)
    bad = [k for k in en if k in cat and (en[k].count("{}") != cat[k].count("{}") or not cat[k])]
    assert not missing and not bad, (code, len(missing), bad[:5])
    r = subprocess.run([sys.executable, __file__, code], capture_output=True, text=True,
                       env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    out = [l for l in r.stdout.splitlines() if l.strip()]
    print("\n".join(out))
    if r.returncode != 0:
        failed.append(code)
        print(r.stderr[-800:])
print("ALLES OK" if not failed else f"LET OP: {failed}")
