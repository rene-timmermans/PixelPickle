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
    ok = n_menu > 400 and n_tools >= 50 and n_fx >= 140
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
    if t.load(f"qtbase_{lang}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(t)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PixelPickle")
    app.setDesktopFileName("pixelpickle")
    app.setWindowIcon(app_icon())  # titelbalk en taakbalk, ook zonder geïnstalleerd menu-item
    app.setStyle("Fusion")
    from . import i18n
    lang = i18n.load("nl" if "--selftest" in sys.argv[1:] else None)
    _qt_translations(app, lang)
    i18n.install(app)
    if "--selftest" in sys.argv[1:]:
        sys.exit(selftest(app))
    from .mainwindow import MainWindow
    w = MainWindow()
    w.show()
    for path in sys.argv[1:]:
        w.open_path(path)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
