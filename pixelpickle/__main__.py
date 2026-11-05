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


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PixelPickle")
    app.setDesktopFileName("pixelpickle")
    app.setStyle("Fusion")
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
