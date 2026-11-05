"""Maakt of werkt TODO.md bij: alle PSP functies die PixelPickle (nog) niet heeft.
Ingevulde prioriteiten en notities blijven bewaard (gekoppeld aan de ID in de laatste kolom).
Gebruik: QT_QPA_PLATFORM=offscreen .venv/bin/python -I tools/make_todo.py"""
import json
import os
import re
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())
OUT = os.path.join(ROOT, "TODO.md")

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from pixelpickle.mainwindow import MainWindow  # noqa: E402
from pixelpickle.psplayout import TOOLBAR, TOOL_NAMES  # noqa: E402

w = MainWindow()
handlers = w.all_handlers()
en = json.load(open(os.path.join(ROOT, "pixelpickle", "data", "lang_en.json"), encoding="utf-8"))


def english(nl):
    return en.get(nl, en.get(nl.replace("&", ""), nl)).replace("&", "")  # gelijk in beide talen: zelfde woord


# bestaande prioriteiten en notities bewaren
keep = {}
if os.path.exists(OUT):
    for line in open(OUT, encoding="utf-8"):
        m = re.match(r"^\|\s*(.*?)\s*\|(.*)\|\s*`([^`]+)`\s*\|\s*$", line)
        if m:
            cells = [c.strip() for c in m.group(2).split("|")]
            keep[m.group(3)] = (m.group(1), cells[-1] if cells else "")

rows_tools = []
for i, group in enumerate(TOOLBAR, 1):
    for cid in group:
        t = w.tools.get(cid)
        if t is not None and not t.available:
            key = w.tool_key(t)
            nl = TOOL_NAMES[cid]
            rows_tools.append((f"knop {i}" + (f", sneltoets {key}" if key else ""), nl, english(nl), f"{cid:04x}"))

rows_menu = []


def walk(items, path):
    for it in items:
        if not it:
            continue
        name = it["text"].replace("&", "")
        if it["items"]:
            walk(it["items"], path + [name])
        elif it["id"] and it["id"] not in handlers and it["id"] != 0xe110:
            where = " > ".join(path)
            rows_menu.append((where, name, english(it["text"]), f"{it['id']:04x}"))


walk(w.menu_tree, [])


def table(rows):
    out = ["| Prioriteit | Functie | Engels | Plek | Notitie | ID |", "|---|---|---|---|---|---|"]
    for where, nl, eng, key in rows:
        prio, note = keep.get(key, ("", ""))
        out.append(f"| {prio} | {nl} | {eng} | {where} | {note} | `{key}` |")
    return "\n".join(out)


text = f"""# PixelPickle: takenlijst

Functies uit Paint Shop Pro XI die PixelPickle nog niet heeft. Ze staan (nog) niet in de menu's of op
de gereedschapsbalk; zodra een functie gebouwd is, verschijnt hij vanzelf op zijn PSP-plek en valt hij
bij de volgende update van deze lijst weg.

Vul de kolom **Prioriteit** in (bijvoorbeeld *hoog*, *middel*, *laag* of *nooit*) en gebruik **Notitie**
voor opmerkingen. Bijwerken: `QT_QPA_PLATFORM=offscreen .venv/bin/python -I tools/make_todo.py`
(ingevulde prioriteiten en notities blijven bewaard).

Totaal: {len(rows_tools)} gereedschappen en {len(rows_menu)} menu-opdrachten.

## Gereedschappen

{table(rows_tools)}

## Menu-opdrachten

{table(rows_menu)}

## Bekende beperkingen van wat er al is

- [ ] Tekstlagen: één opmaak per tekst (geen losse woorden vet of in een andere kleur)
- [ ] Tekst en vectorvormen blijven bij opslaan als .pspimage geen tekst/vector (worden een rasterlaag)
- [ ] Vectorvormen uit .pspimage (rechthoek, pijl, pen) worden nog niet ingelezen
- [ ] .pspimage: alleen Curven als PSP aanpassingslaag; andere aanpassingslagen worden bij opslaan weggelaten
- [ ] Laageigenschappen: tabblad Mengbereiken
- [ ] Effect Lampen: 2 lampen in plaats van 5
- [ ] Textuur en Sculptuur: eigen patronen in plaats van de PSP patroonbestanden
- [ ] Rode ogen verwijderen (menu): herkent geen ogen, maakt alle sterk rode vlakken donkerder
- [ ] Zwakke effecten: Wind (te subtiel), Fijn leer, Contour overtrekken
- [ ] Materialen: verloop en patroon als vulling (nu alleen effen kleur)
- [ ] Inhoud van de snelmenu's (rechtsklik) precies gelijk aan PSP maken
- [ ] Gentoo installer (ebuild)
"""
open(OUT, "w", encoding="utf-8").write(text)
print(f"{OUT}: {len(rows_tools)} gereedschappen, {len(rows_menu)} menu-opdrachten")
