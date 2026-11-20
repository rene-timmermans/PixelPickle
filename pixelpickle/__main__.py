import sys

from PySide6.QtWidgets import QApplication


def selftest(app):
    """Startup check without a screen (for the package tests): pixelpickle --selftest"""
    from .mainwindow import MainWindow
    from .document import Document
    w = MainWindow()
    w.show()
    w.add_document(Document(64, 48))
    app.processEvents()
    n_menu, n_tools, n_fx = len(w.actions_by_id), len(w.tools), len(w.effects)
    print(f"PixelPickle selftest: {n_menu} menu items, {n_tools} tools, {n_fx} effects")
    for s in w.mdi.subWindowList():
        s.canvas.doc.set_modified(False)
    ok = n_menu > 200 and n_tools >= 50 and n_fx >= 140
    # open all menus and show an effect window (with translation active)
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
    print("English:", "OK" if english else "FAIL")
    ok = ok and english
    print("OK" if ok else "FAIL")
    return 0 if ok else 1


def app_icon():
    """The PixelPickle icon (pickle made of pixels), shipped in all formats."""
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
    """Standard Qt windows and buttons (Yes/No, color and file chooser) in the same language."""
    from PySide6.QtCore import QLibraryInfo, QTranslator
    if lang == "en":
        return
    t = QTranslator(app)
    name = {"zh": "zh_CN"}.get(lang, lang)  # Qt calls Simplified Chinese zh_CN
    if t.load(f"qtbase_{name}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(t)


def _crash_log():
    """On a hard crash (Qt) write out the Python stack so the cause can be found:
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
    _log = _crash_log()  # noqa: F841 (file must stay open)
    app = QApplication(sys.argv)
    app.setApplicationName("PixelPickle")
    # only if the menu item is installed; otherwise the desktop portal complains on exit
    from PySide6.QtCore import QStandardPaths
    if QStandardPaths.locate(QStandardPaths.StandardLocation.ApplicationsLocation, "pixelpickle.desktop"):
        app.setDesktopFileName("pixelpickle")
    app.setWindowIcon(app_icon())  # title bar and taskbar, even without an installed menu item
    app.setStyle("Fusion")
    from . import i18n
    # the selftest starts like a first start: English, with automatic translation already active
    lang = i18n.load("en" if "--selftest" in sys.argv[1:] else None)
    _qt_translations(app, lang)
    if i18n.is_rtl():  # Arabic: whole window right to left
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
    # Python cleaning up Qt objects at exit can crash (known PySide issue);
    # everything is already saved, so stop immediately.
    w.settings.sync()
    sys.stdout.flush()
    sys.stderr.flush()
    import os
    os._exit(code)


if __name__ == "__main__":
    main()
