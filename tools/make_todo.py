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

# bewust niet bouwen: deze komen niet meer op de lijst
NOT_PLANNED = {0xd0e0, 0xd138, 0xd139,  # Plaatjespenseel, Uitsmeren (kunstmedia), Tekeningwisser
               0x81e9, 0x80d7, 0x80d8,  # scanner/camera en TWAIN
               0x61c8, 0x8124,  # FotoUitwisseling, Plaatjespenseel exporteren
               0x8026, 0x8025, 0x801c, 0x8024,  # scriptopname starten, pauzeren, annuleren, opslaan
               0x82fa, 0x8157,  # Lexar actief geheugensysteem, Voorbeeld in webbrowser
               0x8027, 0x821b,  # werkbalken Script en Web
               0x8029, 0x82cc, 0x800a}  # Studiecentrum, Menger, Scriptuitvoer

rows_tools = []
for i, group in enumerate(TOOLBAR, 1):
    for cid in group:
        t = w.tools.get(cid)
        if t is not None and not t.available and cid not in NOT_PLANNED:
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
        elif it["id"] and it["id"] not in handlers and it["id"] != 0xe110 and it["id"] not in NOT_PLANNED:
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

{table(rows_tools) if rows_tools else "Alle gereedschappen zijn gebouwd."}

## Menu-opdrachten

{table(rows_menu)}

## Bekende beperkingen van wat er al is

- [ ] Tekstlagen: één opmaak per tekst (geen losse woorden vet of in een andere kleur)
- [ ] .pspimage: alleen Curven als PSP aanpassingslaag; andere aanpassingslagen worden bij opslaan weggelaten
- [ ] Effect Lampen: 2 lampen in plaats van 5
- [ ] Textuur en Sculptuur: eigen patronen in plaats van de PSP patroonbestanden
- [ ] Rode ogen verwijderen (menu): herkent geen ogen, maakt alle sterk rode vlakken donkerder
- [ ] Materialen: verloop en patroon werken nog niet bij tekst, en zelf verlopen samenstellen (verloopbewerker) kan nog niet
- [ ] Inhoud van de snelmenu's (rechtsklik) precies gelijk aan PSP maken

## Afgerond

Wat al gebouwd is, met de versie waarin het verscheen.

- [x] Laatste gereedschappen: Makeover (vlekken, tanden, oogwit, zonnebruin, slanker maken), Object verwijderen,
  Markering en Paletmes; Kleurwisselaar werkt op alle gelijkende kleuren; pijltoetsen met versnelling;
  spiegelen en omdraaien met een selectie op dezelfde plek; schuifbalk onder de invoervelden
  van de optiebalk; Penseel Verwringen zonder scheuren (0.10.0)
- [x] Zeven extra talen (Duits, Frans, Spaans, Italiaans, Russisch, Chinees, Arabisch), handleiding in elke taal;
  .ora als standaardformaat met lagen; broncirkel bij Klonen; uitgebreide handleiding in alle talen;
  selectie verschuiven met de pijltoetsen; Vervagen/Verzachten, Gemiddelde en Filmkorrel verbeterd (0.9.0)
- [x] Vernieuwde optiebalk: vaste hoogte, strak uitgelijnd, groot gereedschapsicoon, kleine vinkjes (0.8.0)
- [x] Vectorlagen: pen en vormen blijven bewerkbaar (oppakken met de Pen in Bewerken), ook in .ora (0.7.0)
- [x] Pen met modi Bewerken, Lijnen en polylijnen, Punt tot punt (Bézier) en Uit de vrije hand, met lijnstijl,
  verbinding, verstek, tracking en knooppunten (0.6.1)
- [x] Gereedschappen: Perspectiefcorrectie, Krasjes verwijderen, Penseel Verwringen, Maasvormig verwringen
  en de kunstmedia Olieverfpenseel, Krijt, Pastel, Kleurkrijt en Kleurpotlood; retoucheerpenselen
  (o.a. Verscherpen, Bosseleren) stapelen niet meer op, met de optie Doorlopend (0.6.0)
- [x] Meeschuiven bij de rand alleen bij puntsgewijs selecteren; vinkje bij Opties voor gereedschap (0.5.5)
- [x] Selectiemodus Toevoegen/Verwijderen werkt ook bij klikken binnen de selectie (0.5.4)
- [x] Eigen set van 45 verlopen en 43 patronen in het programma zelf (0.5.3)
- [x] Effectvenster meldt een actieve selectie (0.5.1)
- [x] Mengbereiken in Laageigenschappen (0.5.0)
- [x] Eigen lijniconen in de accentkleur van het thema voor werkbalken, paletten en aanwijzers (0.5.0)
- [x] Optiebalk strak uitgelijnd; zonder afbeelding grijs de instellingen van het laatste gereedschap (0.5.0)
- [x] Materialen: verloop en patroon voor vulemmer, penselen en vormen (0.4.0)
- [x] Bijsnijden met aanpasbaar kader, grepen, vaste verhoudingen en uitlijnen (0.4.0)
- [x] Automatisch opslaan naar een herstelmap (0.4.0)
- [x] Gebruikershandleiding, venster Info en schuifbare toetsenbordlayout (0.4.0)
- [x] Zonder afbeelding geen actief gereedschap; laatst gebruikte gereedschap komt terug (0.4.0)
- [x] Pen scrolt niet mee bij de rand van het venster (0.4.0)
- [x] Geen merknamen van het oorspronkelijke programma in beeld (0.4.0)
- [x] Eigen programma-icoon, zoomen en schuiven in het effectvoorbeeld, meeschuiven bij de rand (0.3.1)
- [x] Engels als tweede taal; pakketten voor Debian, Ubuntu en Fedora (0.3.0)
- [x] Eigen muisaanwijzer per gereedschap (0.2.0)
- [x] Lagengroepen, maskerlagen, aanpassingslagen, bewerkbare tekst en lezen/schrijven van .pspimage (0.1)
"""
open(OUT, "w", encoding="utf-8").write(text)
print(f"{OUT}: {len(rows_tools)} gereedschappen, {len(rows_menu)} menu-opdrachten")
