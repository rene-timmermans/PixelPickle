"""Extensive manual: QT_QPA_PLATFORM=offscreen .venv/bin/python tests/test_manual.py
- the stored structure still matches the program (otherwise: run tools/make_manual_structure.py)
- the English text covers every tool, every option, every effect, every setting and every menu command
- per language the manual builds and contains all tools"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "pixelpickle", "data", "manual")
sys.path.insert(0, ROOT)
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()

# 1. structure still current?
saved = json.load(open(os.path.join(DATA, "structure.json"), encoding="utf-8"))
tmp = tempfile.mkdtemp()
env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
script = open(os.path.join(ROOT, "tools", "make_manual_structure.py"), encoding="utf-8").read()
script = script.replace('path = os.path.join(ROOT, "pixelpickle", "data", "manual", "structure.json")',
                        f'path = {os.path.join(tmp, "s.json")!r}')
r = subprocess.run([sys.executable, "-c", script.replace('os.path.dirname(os.path.abspath(__file__))', repr(os.path.join(ROOT, "tools")))],
                   capture_output=True, text=True, env=env)
fresh = json.load(open(os.path.join(tmp, "s.json"), encoding="utf-8"))
assert fresh == saved, "structure.json is outdated: run tools/make_manual_structure.py and complete the explanation"
print("1 structure matches the program")

# 2. English text complete
en = json.load(open(os.path.join(DATA, "prose_en.json"), encoding="utf-8"))
miss = []
for t in saved["tools"]:
    i = en["tools"].get(t["id"], {})
    miss += [t["id"]] if not i.get("about") else []
    miss += [f"{t['id']}:{o['label']}" for o in t["options"] if not i.get("options", {}).get(o["label"])]
for e in saved["effects"]:
    i = en["effects"].get(e["id"], {})
    miss += [e["id"]] if not i.get("about") else []
    miss += [f"{e['id']}:{q['label']}" for q in e["params"] if not i.get("params", {}).get(q["label"])]
miss += [m["id"] for mm in saved["menus"] for m in mm["items"] if not en["menus"].get(m["id"])]
assert not miss, miss[:20]
print("2 explanation complete:", len(saved["tools"]), "tools,", len(saved["effects"]), "effects,",
      sum(len(m["items"]) for m in saved["menus"]), "menu commands")

# 3. build per language
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication(sys.argv)
from pixelpickle import i18n, manual  # noqa: E402
for code, _ in i18n.LANGUAGES:
    i18n.load(code)
    page = manual.build()
    names = [i18n.tr(t["name"]) for t in saved["tools"]]
    import html as _h
    absent = [n for n in names if _h.escape(n.replace("&", "")) not in page and n.replace("&", "") not in page]
    has_prose = os.path.exists(os.path.join(DATA, f"prose_{code}.json")) or code == "en"
    assert not absent and len(page) > 100000, (code, absent[:5], len(page))
    print(f"3 {code}: {len(page)} chars, own explanation: {'yes' if has_prose else 'no (English)'}")
# 4. window: every topic findable, Previous/Next/Contents and search work, in every language
for code, _ in i18n.LANGUAGES:
    i18n.load(code)
    page, topics = manual.build(with_topics=True)
    win = manual.ManualWindow()
    want = [a for a, _ in topics if a != "contents"]
    assert win.topics == want, (code, set(want) - set(win.topics))
    assert not win.prev_btn.isEnabled() and win.next_btn.isEnabled()
    win.step(1); assert win.index == 0 and win.topics[0].startswith("s-")
    win.go("tools"); win.step(1); assert win.topics[win.index].startswith("t-")
    win.go(win.topics[-1]); assert not win.next_btn.isEnabled()
    win.go("contents"); assert win.index == -1 and not win.prev_btn.isEnabled()
    word = i18n.tr("Gereedschappen")
    win.search.setText(word); win.find()
    assert win.browser.textCursor().hasSelection() and len(win.browser.extraSelections()) >= 2, code
    win.close()
print("4 window with contents, previous, next and search works in every language")
# 5. standalone window: not attached to the main window (otherwise it always stays on top)
from pixelpickle.mainwindow import MainWindow  # noqa: E402
i18n.load("nl")
mw = MainWindow(); mw.show(); mw.show_manual(); app.processEvents()
mwin = mw._manual_win
assert mwin.parent() is None and mwin.windowFlags() & Qt.WindowType.Window and mwin.isVisible()
mw.show_manual(); assert mw._manual_win is mwin  # second time: the same window comes to the front
mw.close(); app.processEvents()
try:
    still_open = mwin.isVisible()
except RuntimeError:  # closed and cleaned up
    still_open = False
assert not still_open, "manual must close along with the main window"
print("5 manual is an independent window and closes along with the main window")
print("ALL OK")
