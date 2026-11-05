import sys

from PySide6.QtWidgets import QApplication


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Brushwork")
    app.setDesktopFileName("brushwork")
    app.setStyle("Fusion")
    from .mainwindow import MainWindow
    w = MainWindow()
    w.show()
    for path in sys.argv[1:]:
        w.open_path(path)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
