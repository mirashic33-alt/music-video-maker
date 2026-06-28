import logging
import re
import subprocess
import sys

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabBar, QTabWidget, QStatusBar, QLabel, QFrame,
    QMessageBox, QPushButton, QFileDialog, QApplication
)
from PySide6.QtCore import Qt, QTimer
from src.logger import get_logger, register_status_callback, status_text
from src.ui.icons import mdl2
from src.theme import current as cur_theme
from src.ui.tabs.tab_home     import TabHome
from src.ui.tabs.tab_clip     import TabClip
from src.ui.tabs.tab_slide    import TabSlide
from src.ui.tabs.tab_youtube  import TabYouTube
from src.ui.tabs.tab_videogen import TabVideoGen

log = get_logger()

_VERSION = "1.0"
_TAB_NAMES = ["Главная", "Клип", "Слайды", "YouTube", "Grok Video"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"SongBird  v{_VERSION}")
        self.setMinimumSize(900, 600)
        self.resize(1280, 720)
        self._build()
        self._center()
        register_status_callback(self._on_log)

    def _center(self):
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.x() + (screen.width()  - self.width())  // 2,
            screen.y() + (screen.height() - self.height()) // 2,
        )

    def _build(self):
        root = QWidget()
        root.setObjectName("root_widget")
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Полоса вкладок
        self.tab_bar = QTabBar()
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setCursor(Qt.PointingHandCursor)
        for name in _TAB_NAMES:
            self.tab_bar.addTab(name)

        bar_container = QWidget()
        bar_container.setObjectName("tab_bar_container")
        bar_lay = QHBoxLayout(bar_container)
        bar_lay.setContentsMargins(12, 6, 12, 0)
        bar_lay.setSpacing(0)
        bar_lay.addWidget(self.tab_bar)
        bar_lay.addStretch()

        from PySide6.QtCore import QSize
        theme_btn = QPushButton()
        theme_btn.setIcon(mdl2(chr(0xE7EF), cur_theme()["text"], 18))
        theme_btn.setIconSize(QSize(18, 18))
        theme_btn.setFixedSize(32, 28)
        theme_btn.setToolTip("Выбрать тему")
        theme_btn.setCursor(Qt.PointingHandCursor)
        theme_btn.clicked.connect(self._on_theme_select)
        bar_lay.addWidget(theme_btn)

        layout.addWidget(bar_container)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        layout.addWidget(line)

        # Содержимое вкладок
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().hide()

        self.tab_bar.currentChanged.connect(self.tabs.setCurrentIndex)
        self.tabs.currentChanged.connect(self.tab_bar.setCurrentIndex)

        self.tab_home     = TabHome()
        self.tab_clip     = TabClip()
        self.tab_slide    = TabSlide()
        self.tab_youtube  = TabYouTube()
        self.tab_videogen = TabVideoGen()

        self.tabs.addTab(self.tab_home,     "")
        self.tabs.addTab(self.tab_clip,     "")
        self.tabs.addTab(self.tab_slide,    "")
        self.tabs.addTab(self.tab_youtube,  "")
        self.tabs.addTab(self.tab_videogen, "")

        layout.addWidget(self.tabs)

        # Строка статуса
        self.status_bar = QStatusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.setStatusBar(self.status_bar)

        self._log_lbl = QLabel("Готово")
        self._log_lbl.setObjectName("status_log")
        self.status_bar.addWidget(self._log_lbl, 1)

        self._err_lbl = QLabel("")
        self._err_lbl.setObjectName("status_err")
        self.status_bar.addPermanentWidget(self._err_lbl)

        self._err_timer = QTimer()
        self._err_timer.setSingleShot(True)
        self._err_timer.timeout.connect(lambda: self._err_lbl.setText(""))

    _EMOJI_RE = re.compile(r'[\U0001F000-\U0001FFFF☀-➿]+')

    def _on_log(self, level: int, msg: str):
        short = self._EMOJI_RE.sub('', status_text(msg)).strip()
        if level >= logging.ERROR:
            QTimer.singleShot(0, lambda: self._show_err(short))
        else:
            QTimer.singleShot(0, lambda: self._log_lbl.setText(short))

    def _show_err(self, msg: str):
        self._err_lbl.setText(f"X {msg}")
        self._err_timer.start(12_000)

    def _on_theme_select(self):
        from pathlib import Path
        import json
        themes_dir = str(Path(__file__).resolve().parent.parent.parent / "themes")
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать тему", themes_dir, "Темы (*.json)"
        )
        if not path:
            return
        try:
            state_file = Path(__file__).resolve().parent.parent.parent / "state.json"
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
            except Exception:
                state = {}
            state["theme_path"] = path
            state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить тему:\n{e}")
            return
        subprocess.Popen([sys.executable] + sys.argv)
        QApplication.instance().quit()

    def closeEvent(self, event):
        if getattr(self.tab_clip, "_running", False) or getattr(self.tab_slide, "_running", False):
            mb = QMessageBox(self)
            mb.setWindowTitle("Рендеринг не завершён")
            mb.setText("Сейчас идёт монтаж клипа. Если закрыть — файл не сохранится.\nВсё равно закрыть?")
            mb.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            mb.setDefaultButton(QMessageBox.No)
            mb.button(QMessageBox.Yes).setText("Закрыть")
            mb.button(QMessageBox.No).setText("Отмена")
            if mb.exec() == QMessageBox.No:
                event.ignore()
                return
        event.accept()
