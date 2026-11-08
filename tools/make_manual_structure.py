"""Maakt pixelpickle/data/manual/structure.json: de opbouw van de uitgebreide handleiding, rechtstreeks
uit het programma (gereedschappen met hun opties, effecten met hun instellingen, menu's). De uitleg zelf
staat per taal in pixelpickle/data/manual/prose_<taal>.json.
Gebruik: QT_QPA_PLATFORM=offscreen .venv/bin/python -I tools/make_manual_structure.py"""
import json
import os
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())
from PySide6.QtWidgets import (QAbstractButton, QApplication, QCheckBox, QComboBox, QLabel,  # noqa: E402
                               QSpinBox, QDoubleSpinBox)

app = QApplication(sys.argv)
from pixelpickle import i18n  # noqa: E402
i18n.load("nl")
from pixelpickle.mainwindow import MainWindow  # noqa: E402
from pixelpickle.psplayout import TOOLBAR, TOOL_NAMES  # noqa: E402
from pixelpickle.tools import recorded_keys  # noqa: E402

w = MainWindow()
out = {"tools": [], "effects": [], "menus": []}

for gi, group in enumerate(TOOLBAR, 1):
    for cid in group:
        t = w.tools.get(cid)
        if t is None or not t.available:
            continue
        widgets, _ = recorded_keys(t)
        opts, label = [], None
        for x in widgets:
            if isinstance(x, QLabel):
                label = x.text()
                continue
            o = {"label": label}
            if isinstance(x, QComboBox):
                o.update(type="choice", choices=[x.itemText(i) for i in range(x.count())])
            elif isinstance(x, (QSpinBox, QDoubleSpinBox)):
                o.update(type="number", range=[x.minimum(), x.maximum()])
            elif isinstance(x, QCheckBox):
                o.update(type="check", label=x.text())
            elif isinstance(x, QAbstractButton):
                o.update(type="button", label=x.text() or label)
            else:
                label = None
                continue
            if o.get("label"):
                opts.append(o)
            label = None
        out["tools"].append({"id": f"{cid:04x}", "name": TOOL_NAMES.get(cid, t.name), "group": gi,
                             "glyph": t.glyph, "key": w.tool_key(t), "options": opts})

menu_paths = {}


def walk(items, path):
    for it in items:
        if not it:
            continue
        if it["items"]:
            walk(it["items"], path + [it["text"].replace("&", "")])
        elif it["id"]:
            menu_paths[it["id"]] = path


walk(w.menu_tree, [])
for cid, e in sorted(w.effects.items(), key=lambda kv: (menu_paths.get(kv[0], ["~"]), kv[1].name)):
    params = []
    for p in e.params:
        q = {"label": p["label"], "type": p["type"]}
        if p["type"] == "int":
            q.update(range=[p["lo"], p["hi"]], default=p["default"])
        elif p["type"] == "choice":
            q.update(choices=list(p["options"]))
        params.append(q)
    out["effects"].append({"id": f"{cid:04x}", "name": e.name, "menu": menu_paths.get(cid, []), "params": params})

handlers = w.all_handlers()
effects = set(w.effects)
for top in w.menu_tree:
    items = []

    def collect(its, path):
        for it in its:
            if not it:
                continue
            if it["items"]:
                collect(it["items"], path + [it["text"].replace("&", "")])
            elif it["id"] in handlers and it["id"] not in effects:
                items.append({"id": f"{it['id']:04x}", "text": it["text"].replace("&", ""), "path": path})
    collect(top["items"], [])
    if items:
        out["menus"].append({"menu": top["text"].replace("&", ""), "items": items})

path = os.path.join(ROOT, "pixelpickle", "data", "manual", "structure.json")
json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(path, "gereedschappen:", len(out["tools"]), "effecten:", len(out["effects"]),
      "menu-opdrachten:", sum(len(m["items"]) for m in out["menus"]),
      "opties:", sum(len(t["options"]) for t in out["tools"]), "instellingen:", sum(len(e["params"]) for e in out["effects"]))
