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

from PySide6.QtCore import QBuffer, QByteArray, QIODevice

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


def build(main=None):
    s = _load("structure.json")
    p = prose()
    T = lambda t: html.escape(tr(t))  # noqa: E731
    out = [f"<h1>{T('PixelPickle: gebruikershandleiding')}</h1>", p.get("intro", "")]
    # inhoudsopgave
    toc = [f"<h2>{T('Inhoud')}</h2><ul>"]
    for key, title in SECTIONS:
        toc.append(f'<li><a href="#s-{key}">{T(title)}</a></li>')
    toc.append(f'<li><a href="#tools">{T("Gereedschappen")}</a><ul>')
    for t in s.get("tools", []):
        toc.append(f'<li><a href="#t-{t["id"]}">{T(t["name"])}</a></li>')
    toc.append(f'</ul></li><li><a href="#menus">{T("Menu-opdrachten")}</a></li>')
    toc.append(f'<li><a href="#effects">{T("Effecten en aanpassingen")}</a></li></ul>')
    out += toc
    # algemene hoofdstukken
    sec = p.get("sections", {})
    for key, title in SECTIONS:
        if sec.get(key):
            out.append(f'<a name="s-{key}"></a><h2>{T(title)}</h2>{sec[key]}')
    # gereedschappen
    out.append(f'<a name="tools"></a><h2>{T("Gereedschappen")}</h2>')
    tp = p.get("tools", {})
    for t in s.get("tools", []):
        info = tp.get(t["id"], {})
        key = f' &nbsp; <span style="color:gray">{T("Sneltoets")}: <b>{html.escape(t["key"])}</b></span>' if t.get("key") else ""
        out.append(f'<a name="t-{t["id"]}"></a><h3>{_icon(t["glyph"])} &nbsp;{T(t["name"])}{key}</h3>')
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
    out.append(f'<a name="menus"></a><h2>{T("Menu-opdrachten")}</h2>')
    mp = p.get("menus", {})
    for m in s.get("menus", []):
        out.append(f"<h3>{T(m['menu'])}</h3><ul>")
        for it in m["items"]:
            path = " › ".join(_clean(x) for x in it.get("path", []) + [it["text"]])
            out.append(f"<li><b>{html.escape(path)}</b>: {mp.get(it['id'], '')}</li>")
        out.append("</ul>")
    # effecten, gegroepeerd per menu
    out.append(f'<a name="effects"></a><h2>{T("Effecten en aanpassingen")}</h2>')
    ep = p.get("effects", {})
    last = None
    for e in s.get("effects", []):
        group = " › ".join(_clean(x) for x in e.get("menu", [])) or T("Overige")
        if group != last:
            out.append(f"<h3>{html.escape(group)}</h3>")
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
    return page
