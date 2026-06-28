import sys
from PySide6.QtWidgets import QApplication
from src.theme import build_qss, load_theme, set_current
from src.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    t = load_theme()
    set_current(t)
    app.setStyleSheet(build_qss(t))
    win = MainWindow()
    win.setWindowTitle(f"SongBird  v1.0")
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
