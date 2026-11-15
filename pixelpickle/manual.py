"""Uitgebreide gebruikershandleiding (Help > Gebruikershandleiding).

De opbouw komt uit data/manual/structure.json (gemaakt door tools/make_manual_structure.py uit het
programma zelf: gereedschappen met hun opties, effecten met hun instellingen, menu's). De uitleg staat per
taal in data/manual/prose_<taal>.json; ontbreekt een taal of een stukje, dan wordt het Engels gebruikt.
Namen van gereedschappen, opties en menu's worden vertaald met de gewone vertalingen (i18n.tr), zodat de
handleiding altijd dezelfde woorden gebruikt als het programma."""
import base64
import html
import json
import os
from bisect import bisect_right

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPoint, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QShortcut, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser,
                               QTextEdit, QVBoxLayout)

from . import i18n
from .i18n import tr

DATA = os.path.join(os.path.dirname(__file__), "data", "manual")

SECTIONS = [("workspace", "De werkruimte"), ("files", "Bestanden openen, maken en opslaan"),
            ("navigation", "Zoomen en navigeren"), ("selections", "Selecties"), ("layers", "Lagen"),
            ("materials", "Materialen: kleur, verloop en patroon"), ("vector", "De pen en vectorlagen"),
            ("adjust_effects", "Aanpassen en effecten"), ("undo", "Ongedaan maken"),
            ("preferences", "Voorkeuren"), ("tips", "Handige tips")]


def _load(name):
    try:
        with open(os.path.join(DATA, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _merge(base, over):
    """Taalspecifieke tekst over de Engelse heen leggen (diep), zodat ontbrekende stukjes Engels blijven."""
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        elif v:
            out[k] = v
    return out


def prose(lang=None):
    lang = lang or i18n.language()
    base = _load("prose_en.json")
    return base if lang == "en" else _merge(base, _load(f"prose_{lang}.json"))


def _icon(glyph, size=22):
    from . import icons
    if glyph not in icons.ICONS:
        return html.escape(glyph)
    pm = icons.render(glyph, size, icons.icon_color())
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    return f'<img src="data:image/png;base64,{base64.b64encode(bytes(ba)).decode()}" width="{size}" height="{size}">'


def _clean(label):
    return tr(label or "").replace("&", "").rstrip(": ").strip()


def _choices(o):
    if o.get("type") == "choice" and o.get("choices") and len(o["choices"]) <= 8:  # lange lijsten: zie de uitleg
        return " <i>(" + ", ".join(html.escape(_clean(c)) for c in o["choices"]) + ")</i>"
    if o.get("range"):
        lo, hi = o["range"][0], o["range"][1]
        return f" <i>({lo} … {hi})</i>"
    return ""


def _anchor(name, title):
    """Kop met een anker eromheen (een leeg anker laat Qt soms vallen; zo blijft de kop vindbaar)."""
    return f'<a name="{name}">{title}</a>'


def build(main=None, with_topics=False):
    """De hele handleiding als HTML, met genummerde hoofdstukken en een klikbare inhoudsopgave.
    with_topics: geeft ook de onderwerpen terug als [(anker, niveau)] in leesvolgorde (voor Vorige/Volgende)."""
    s = _load("structure.json")
    p = prose()
    T = lambda t: html.escape(tr(t))  # noqa: E731
    sec = p.get("sections", {})
    tp, mp, ep = p.get("tools", {}), p.get("menus", {}), p.get("effects", {})

    # hoofdstukken en onderwerpen: (anker, titel, niveau)
    chapters = []
    n = 0
    for key, title in SECTIONS:
        if sec.get(key):
            n += 1
            chapters.append((f"s-{key}", f"{n}. {T(title)}", 2, []))
    n += 1
    sub = [(f"t-{t['id']}", f"{n}.{i}. {T(t['name'])}") for i, t in enumerate(s.get("tools", []), 1)]
    chapters.append(("tools", f"{n}. {T('Gereedschappen')}", 2, sub))
    tool_no = n
    n += 1
    sub = [(f"m-{k}", f"{n}.{k}. {html.escape(_clean(m['menu']))}") for k, m in enumerate(s.get("menus", []), 1)]
    chapters.append(("menus", f"{n}. {T('Menu-opdrachten')}", 2, sub))
    menu_no = n
    n += 1
    groups = []
    for e in s.get("effects", []):
        g = " › ".join(_clean(x) for x in e.get("menu", [])) or tr("Overige")
        if g not in groups:
            groups.append(g)
    sub = [(f"g-{k}", f"{n}.{k}. {html.escape(g)}") for k, g in enumerate(groups, 1)]
    chapters.append(("effects", f"{n}. {T('Effecten en aanpassingen')}", 2, sub))
    effect_no = n
    topics = [("contents", 2)]
    for a, _, lvl, subs in chapters:
        topics.append((a, lvl))
        topics += [(sa, 3) for sa, _ in subs]

    out = [f"<h1>{T('PixelPickle: gebruikershandleiding')}</h1>", p.get("intro", ""),
           f"<p>{T(NAV_INTRO)}</p>"]
    # inhoudsopgave
    out.append(f"<h2>{_anchor('contents', T('Inhoudsopgave'))}</h2><p><i>{T(CONTENTS_HINT)}</i></p><ul>")
    for a, title, _, subs in chapters:
        out.append(f'<li><a href="#{a}">{title}</a>')
        if subs:
            out.append("<ul>" + "".join(f'<li><a href="#{sa}">{st}</a></li>' for sa, st in subs) + "</ul>")
        out.append("</li>")
    out.append("</ul>")
    # algemene hoofdstukken
    k = 0
    for key, title in SECTIONS:
        if sec.get(key):
            k += 1
            out.append(f"<h2>{_anchor('s-' + key, f'{k}. ' + T(title))}</h2>{sec[key]}")
    # gereedschappen
    out.append(f"<h2>{_anchor('tools', f'{tool_no}. ' + T('Gereedschappen'))}</h2>")
    for i, t in enumerate(s.get("tools", []), 1):
        info = tp.get(t["id"], {})
        key = f' &nbsp; <span style="color:gray">{T("Sneltoets")}: <b>{html.escape(t["key"])}</b></span>' if t.get("key") else ""
        out.append(f"<h3>{_icon(t['glyph'])} &nbsp;{_anchor('t-' + t['id'], f'{tool_no}.{i}. ' + T(t['name']))}{key}</h3>")
        out.append(info.get("about", ""))
        if info.get("use"):
            out.append(f"<p><b>{T('Gebruik')}</b></p>{info['use']}")
        if t.get("options"):
            out.append(f"<p><b>{T('Opties')}</b></p><ul>")
            expl = info.get("options", {})
            for o in t["options"]:
                out.append(f"<li><b>{html.escape(_clean(o['label']))}</b>{_choices(o)}: {expl.get(o['label'], '')}</li>")
            out.append("</ul>")
        if info.get("tips"):
            out.append(f"<p><b>{T('Tips')}</b></p>{info['tips']}")
    # menu's
    out.append(f"<h2>{_anchor('menus', f'{menu_no}. ' + T('Menu-opdrachten'))}</h2>")
    for i, m in enumerate(s.get("menus", []), 1):
        out.append(f"<h3>{_anchor(f'm-{i}', f'{menu_no}.{i}. ' + html.escape(_clean(m['menu'])))}</h3><ul>")
        for it in m["items"]:
            path = " › ".join(_clean(x) for x in it.get("path", []) + [it["text"]])
            out.append(f"<li><b>{html.escape(path)}</b>: {mp.get(it['id'], '')}</li>")
        out.append("</ul>")
    # effecten, gegroepeerd per menu
    out.append(f"<h2>{_anchor('effects', f'{effect_no}. ' + T('Effecten en aanpassingen'))}</h2>")
    last = None
    for e in s.get("effects", []):
        group = " › ".join(_clean(x) for x in e.get("menu", [])) or tr("Overige")
        if group != last:
            gi = groups.index(group) + 1
            out.append(f"<h3>{_anchor(f'g-{gi}', f'{effect_no}.{gi}. ' + html.escape(group))}</h3>")
            last = group
        info = ep.get(e["id"], {})
        out.append(f'<p><a name="e-{e["id"]}"></a><b>{html.escape(_clean(e["name"]))}</b><br>{info.get("about", "")}</p>')
        if e.get("params"):
            out.append("<ul>")
            expl = info.get("params", {})
            for q in e["params"]:
                out.append(f"<li><b>{html.escape(_clean(q['label']))}</b>{_choices(q)}: {expl.get(q['label'], '')}</li>")
            out.append("</ul>")
    page = "\n".join(out)
    if i18n.is_rtl():
        page = f'<div dir="rtl">{page}</div>'
    return (page, topics) if with_topics else page


NAV_INTRO = ("Zoek met Ctrl+F of in de zoekbalk bovenaan; F3 gaat naar de volgende treffer en Shift+F3 naar de vorige. "
             "Vorige en Volgende springen naar het vorige of volgende onderwerp, Inhoud brengt je terug naar de "
             "inhoudsopgave. Het venster kan naast je werk open blijven staan.")
CONTENTS_HINT = ("Klik op een onderwerp om er direct naartoe te gaan. Inhoud brengt je terug; Vorige en Volgende "
                 "bladeren door de onderwerpen.")
STATUS_HINT = "Ctrl+F: zoeken · F3: volgende treffer · Shift+F3: vorige treffer"


class ManualWindow(QDialog):
    """Doorzoekbare handleiding die naast het werk open kan blijven, met Inhoud, Vorige en Volgende."""

    def __init__(self, parent=None):
        super().__init__(parent)
        if parent is None:  # zelfstandig venster: met minimaliseren/maximaliseren, ook achter het hoofdvenster
            self.setWindowFlags(Qt.WindowType.Window)
        self.setWindowTitle(tr("Gebruikershandleiding") + " - PixelPickle")
        self.setSizeGripEnabled(True)
        self.resize(900, 820)
        v = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Zoeken in de handleiding…"))
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(lambda: self.find())
        self.search.textChanged.connect(self._highlight_all)
        bar.addWidget(self.search, 1)
        self.contents_btn = QPushButton(tr("Inhoud"))
        self.contents_btn.setToolTip(tr("Terug naar de inhoudsopgave"))
        self.prev_btn = QPushButton(tr("Vorige"))
        self.prev_btn.setToolTip(tr("Vorig onderwerp"))
        self.next_btn = QPushButton(tr("Volgende"))
        self.next_btn.setToolTip(tr("Volgend onderwerp"))
        for b in (self.contents_btn, self.prev_btn, self.next_btn):
            b.setAutoDefault(False)
            bar.addWidget(b)
        self.contents_btn.clicked.connect(lambda: self.go("contents"))
        self.prev_btn.clicked.connect(lambda: self.step(-1))
        self.next_btn.clicked.connect(lambda: self.step(1))
        v.addLayout(bar)
        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self.open_link)
        self.browser.verticalScrollBar().valueChanged.connect(self._track)
        v.addWidget(self.browser, 1)
        self.status = QLabel(tr(STATUS_HINT))
        self.status.setProperty("pp_notr", True)
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.button(QDialogButtonBox.StandardButton.Close).setAutoDefault(False)
        bb.rejected.connect(self.close)
        v.addWidget(bb)
        for keys, fn in (("Ctrl+F", self.focus_search), ("F3", lambda: self.find()),
                         ("Shift+F3", lambda: self.find(True))):
            QShortcut(QKeySequence(keys), self, activated=fn)
        self.topics, self.positions, self.index = [], [], -1
        self._jumping = False
        self.reload()

    def reload(self):
        """Handleiding (opnieuw) opbouwen in de huidige taal en de plek van elk onderwerp bepalen."""
        page, topics = build(with_topics=True)
        self._jumping = True
        self.browser.setHtml(page)
        self.browser.setLayoutDirection(Qt.LayoutDirection.RightToLeft if i18n.is_rtl() else Qt.LayoutDirection.LeftToRight)
        found = {}
        block = self.browser.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    for name in frag.charFormat().anchorNames():
                        found.setdefault(name, block.position())
                it += 1
            block = block.next()
        pairs = [(a, found[a]) for a, _ in topics if a in found and a != "contents"]
        pairs.sort(key=lambda x: x[1])
        self.topics = [a for a, _ in pairs]
        self.positions = [pos for _, pos in pairs]
        self._jumping = False
        self.index = -1
        self._buttons()

    def focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    def _track(self, *_):
        """Bij scrollen bijhouden in welk onderwerp je bent (voor Vorige en Volgende)."""
        if self._jumping:
            return
        pos = self.browser.cursorForPosition(QPoint(0, 0)).position()
        self.index = bisect_right(self.positions, pos) - 1
        sb = self.browser.verticalScrollBar()
        if sb.maximum() and sb.value() >= sb.maximum():
            self.index = len(self.topics) - 1
        self._buttons()

    def _buttons(self):
        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setEnabled(self.index + 1 < len(self.topics))

    def go(self, anchor):
        self._jumping = True
        self.browser.scrollToAnchor(anchor)
        self._jumping = False
        self.index = self.topics.index(anchor) if anchor in self.topics else -1
        self._buttons()

    def step(self, d):
        i = self.index + d
        if 0 <= i < len(self.topics):
            self.go(self.topics[i])

    def open_link(self, url: QUrl):
        if url.isRelative() and url.fragment():
            self.go(url.fragment())
        elif url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)

    def _highlight_all(self, *_):
        """Alle treffers van de zoekterm licht markeren."""
        term = self.search.text().strip()
        sels = []
        if len(term) >= 2:
            doc = self.browser.document()
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(255, 210, 0, 110))
            c = doc.find(term, 0)
            while not c.isNull() and len(sels) < 2000:
                sel = QTextEdit.ExtraSelection()
                sel.cursor, sel.format = c, fmt
                sels.append(sel)
                c = doc.find(term, c)
        self.browser.setExtraSelections(sels)
        if not term:
            self.status.setText(tr(STATUS_HINT))

    def find(self, backwards=False):
        term = self.search.text().strip()
        if not term:
            self.focus_search()
            return
        flags = QTextDocument.FindFlag.FindBackward if backwards else QTextDocument.FindFlag(0)
        found = self.browser.find(term, flags)
        if not found:  # aan het eind: verder vanaf het begin (of andersom)
            self.browser.moveCursor(QTextCursor.MoveOperation.End if backwards else QTextCursor.MoveOperation.Start)
            found = self.browser.find(term, flags)
        n = len(self.browser.extraSelections())
        if found:
            self.status.setText(tr("Gevonden: {} ({} treffers)").format(term, n) if n > 1 else tr("Gevonden: {}").format(term))
        else:
            self.status.setText(tr("Niet gevonden: {}").format(term))
