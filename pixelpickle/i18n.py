"""Talen. Nederlands is de brontaal; voor Engels staat er een catalogus in data/lang_en.json
({Nederlandse tekst: Engelse tekst}). Teksten met wisselende delen staan erin als patroon met {}:
"Opgeslagen: {}" -> "Saved: {}". De wisselende delen worden zelf ook vertaald (recursief).

Vertalen gebeurt op twee manieren:
- tr(tekst) in de code;
- automatisch voor alles wat op het scherm verschijnt (vensters, menu's, knoppen, keuzelijsten,
  tooltips, statusbalk), via een gebeurtenisfilter op de applicatie."""
import json
import os
import re

from PySide6.QtCore import QEvent, QObject, QSettings
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QDockWidget, QGroupBox, QLabel, QLineEdit, QMenu,
                               QMenuBar, QTabBar, QTabWidget, QToolBar, QWidget)

LANGUAGES = [("nl", "Nederlands"), ("en", "English")]
_lang = "nl"
_exact = {}
_patterns = []  # [(regex, engels sjabloon, aantal delen)]


def setting():
    return QSettings("PixelPickle", "PixelPickle").value("language", "")


def load(lang=None):
    """Kies de taal: de opgeslagen voorkeur, anders Engels (standaard bij de eerste start)."""
    global _lang, _exact, _patterns
    if lang is None:
        lang = setting() or "en"
    _lang = lang if lang in dict(LANGUAGES) else "nl"
    _exact, _patterns = {}, []
    if _lang == "nl":
        return _lang
    path = os.path.join(os.path.dirname(__file__), "data", f"lang_{_lang}.json")
    try:
        with open(path, encoding="utf-8") as f:
            cat = json.load(f)
    except (OSError, ValueError):
        return _lang
    for nl, other in cat.items():
        if not isinstance(other, str) or not other:
            continue
        if "{}" in nl and nl.replace("{}", "") and nl.count("{}") == other.count("{}"):
            rx = "^" + "(.+?)".join(re.escape(p) for p in nl.split("{}")) + "$"
            _patterns.append((re.compile(rx, re.S), other, nl.count("{}")))
        else:
            _exact[nl] = other
    # langere (specifiekere) patronen eerst
    _patterns.sort(key=lambda t: -len(t[0].pattern))
    return _lang


def language():
    return _lang


def tr(text, _depth=0):
    if _lang == "nl" or not text or not isinstance(text, str):
        return text
    hit = _exact.get(text)
    if hit is not None:
        return hit
    # menu-items met '&' of afsluitende '...' / ':' ook zonder die tekens proberen
    plain = text.replace("&", "")
    if plain != text and plain in _exact:
        return _exact[plain]
    if _depth < 3:
        for rx, other, n in _patterns:
            m = rx.match(text)
            if m:
                parts = [tr(g, _depth + 1) for g in m.groups()]
                try:
                    return other.format(*parts)
                except (IndexError, ValueError):
                    return text
        if "\n" in text:  # meerregelige teksten per regel
            lines = text.split("\n")
            out = [tr(l, _depth + 1) for l in lines]
            if out != lines:
                return "\n".join(out)
    return text


def _set(obj, getter, setter):
    try:
        v = getattr(obj, getter)()
        t = tr(v)
        if t != v:
            getattr(obj, setter)(t)
    except RuntimeError:
        pass


def translate_widget(w):
    """Vertaal één widget (niet de kinderen)."""
    if w.property("pp_notr"):
        return
    _set(w, "windowTitle", "setWindowTitle")
    _set(w, "toolTip", "setToolTip")
    _set(w, "statusTip", "setStatusTip")
    if isinstance(w, QLabel):
        _set(w, "text", "setText")
    elif isinstance(w, QAbstractButton):
        _set(w, "text", "setText")
    elif isinstance(w, QGroupBox):
        _set(w, "title", "setTitle")
    elif isinstance(w, QLineEdit):
        _set(w, "placeholderText", "setPlaceholderText")
    elif isinstance(w, QComboBox) and not w.isEditable():
        for i in range(w.count()):
            t = tr(w.itemText(i))
            if t != w.itemText(i):
                w.setItemText(i, t)
    elif isinstance(w, QTabWidget):
        for i in range(w.count()):
            w.setTabText(i, tr(w.tabText(i)))
    elif isinstance(w, QTabBar) and not w.property("pp_doc_tabs"):
        for i in range(w.count()):
            w.setTabText(i, tr(w.tabText(i)))
    elif isinstance(w, QDockWidget):
        _set(w, "windowTitle", "setWindowTitle")
    if isinstance(w, (QMenu, QMenuBar, QToolBar)) or w.actions():
        for a in w.actions():
            if a.property("pp_notr"):
                continue
            for g, s in (("text", "setText"), ("toolTip", "setToolTip"), ("statusTip", "setStatusTip"),
                         ("iconText", "setIconText")):
                _set(a, g, s)
            m = a.menu()
            if m is not None:
                _set(m, "title", "setTitle")


def translate_tree(w):
    for c in [w] + w.findChildren(QWidget):
        try:
            translate_widget(c)
        except RuntimeError:  # onderdeel is intussen door Qt opgeruimd
            continue


class _Filter(QObject):
    """Vertaalt wat verschijnt. Vertalen kan zelf weer iets laten verschijnen (bijvoorbeeld een
    menu); daarom niet opnieuw beginnen terwijl er al vertaald wordt. Een fout bij het vertalen
    mag het programma nooit laten stoppen."""
    busy = False

    def eventFilter(self, obj, ev):
        if _Filter.busy:
            return False
        t = ev.type()
        if t not in (QEvent.Type.Show, QEvent.Type.ToolTip):
            return False
        _Filter.busy = True
        try:
            if isinstance(obj, QWidget):
                if t == QEvent.Type.Show:
                    translate_tree(obj)
                else:
                    translate_widget(obj)
        except Exception:  # o.a. een onderdeel dat Qt al heeft opgeruimd
            pass
        finally:
            _Filter.busy = False
        return False


_filter = None


def install(app):
    """Automatisch vertalen van alles wat verschijnt (alleen nodig als de taal niet Nederlands is)."""
    global _filter
    if _lang == "nl" or _filter is not None:
        return
    _filter = _Filter()
    app.installEventFilter(_filter)
