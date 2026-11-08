import sys

from PySide6.QtWidgets import QApplication


def selftest(app):
    """Opstartcontrole zonder scherm (voor de pakkettesten): pixelpickle --selftest"""
    from .mainwindow import MainWindow
    from .document import Document
    w = MainWindow()
    w.show()
    w.add_document(Document(64, 48))
    app.processEvents()
    n_menu, n_tools, n_fx = len(w.actions_by_id), len(w.tools), len(w.effects)
    print(f"PixelPickle selftest: {n_menu} menu-items, {n_tools} gereedschappen, {n_fx} effecten")
    for s in w.mdi.subWindowList():
        s.canvas.doc.set_modified(False)
    ok = n_menu > 200 and n_tools >= 50 and n_fx >= 140
    # alle menu's openen en een effectvenster tonen (met het vertalen actief)
    for a in w.menuBar().actions():
        m = a.menu()
        if m is not None:
            m.popup(w.mapToGlobal(w.rect().center()))
            app.processEvents()
            m.hide()
    from .effectdialog import EffectDialog
    dlg = EffectDialog(w, w.doc(), w.effects[0x809e])
    dlg.show()
    app.processEvents()
    dlg.reject()
    english = w.menuBar().actions()[0].text() == "&File"
    print("Engels:", "OK" if english else "FOUT")
    ok = ok and english
    print("OK" if ok else "FOUT")
    return 0 if ok else 1


def app_icon():
    """Het PixelPickle icoon (augurk van pixels), meegeleverd in alle formaten."""
    import os
    from PySide6.QtGui import QIcon
    icon = QIcon()
    folder = os.path.join(os.path.dirname(__file__), "data", "icons")
    for size in (16, 32, 48, 64, 128, 256):
        path = os.path.join(folder, f"pixelpickle-{size}.png")
        if os.path.exists(path):
            icon.addFile(path)
    return icon


def _qt_translations(app, lang):
    """Standaardvensters en -knoppen van Qt (Ja/Nee, kleur- en bestandskiezer) in dezelfde taal."""
    from PySide6.QtCore import QLibraryInfo, QTranslator
    if lang == "en":
        return
    t = QTranslator(app)
    name = {"zh": "zh_CN"}.get(lang, lang)  # Qt kent vereenvoudigd Chinees als zh_CN
    if t.load(f"qtbase_{name}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(t)


def _crash_log():
    """Bij een harde crash (Qt) de Python-stapel wegschrijven, zodat de oorzaak te vinden is:
    ~/.cache/PixelPickle/crash.log"""
    import faulthandler
    import os
    import time
    folder = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "PixelPickle")
    try:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "crash.log")
        big = os.path.exists(path) and os.path.getsize(path) > 256 * 1024
        f = open(path, "w" if big else "a", encoding="utf-8")
        f.write(f"\n=== start {time.strftime('%Y-%m-%d %H:%M:%S')} pid {os.getpid()}\n")
        f.flush()
        faulthandler.enable(f, all_threads=False)
        return f
    except OSError:
        return None


def main():
    _log = _crash_log()  # noqa: F841 (bestand moet open blijven)
    app = QApplication(sys.argv)
    app.setApplicationName("PixelPickle")
    # alleen als het menu-item geïnstalleerd is; anders klaagt de desktop-portal bij afsluiten
    from PySide6.QtCore import QStandardPaths
    if QStandardPaths.locate(QStandardPaths.StandardLocation.ApplicationsLocation, "pixelpickle.desktop"):
        app.setDesktopFileName("pixelpickle")
    app.setWindowIcon(app_icon())  # titelbalk en taakbalk, ook zonder geïnstalleerd menu-item
    app.setStyle("Fusion")
    from . import i18n
    # de selftest start zoals een eerste start: Engels, met automatisch vertalen al actief
    lang = i18n.load("en" if "--selftest" in sys.argv[1:] else None)
    _qt_translations(app, lang)
    if i18n.is_rtl():  # Arabisch: hele venster van rechts naar links
        from PySide6.QtCore import Qt
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    i18n.install(app)
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest(app))
    from .mainwindow import MainWindow
    w = MainWindow()
    w.show()
    for path in sys.argv[1:]:
        w.open_path(path)
    from PySide6.QtCore import QTimer
    QTimer.singleShot(400, w.offer_recovery)
    code = app.exec()
    # Het opruimen van Qt-objecten door Python bij het afsluiten kan crashen (bekend PySide-probleem);
    # alles is dan al opgeslagen, dus direct stoppen.
    w.settings.sync()
    sys.stdout.flush()
    sys.stderr.flush()
    import os
    os._exit(code)


if __name__ == "__main__":
    main()
