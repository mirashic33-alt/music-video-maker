import os
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QFont

import src.state as state
from src.theme import current as cur_theme
from src.ui.icons import mdl2

_IMG_DIR = Path(__file__).resolve().parent.parent.parent.parent / "img"
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


class TabHome(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._images: list[str] = []
        self._index: int = 0
        self._build()
        self._scan_images()
        self._load_state()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        t = cur_theme()

        # Картинка — на весь экран
        self._img_lbl = QLabel()
        self._img_lbl.setObjectName("home_img")
        self._img_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self._img_lbl, 1)

        # Нижняя панель с навигацией и названием
        bar = QWidget()
        bar.setObjectName("home_bar")
        bar.setFixedHeight(56)
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(24, 0, 24, 0)
        bar_lay.setSpacing(16)

        self._prev_btn = QPushButton()
        self._prev_btn.setObjectName("home_nav_btn")
        self._prev_btn.setIcon(mdl2(chr(0xE76B), t["accent"], 22))
        self._prev_btn.setFixedSize(36, 36)
        self._prev_btn.setCursor(Qt.PointingHandCursor)
        self._prev_btn.setToolTip("Предыдущая картинка")
        self._prev_btn.clicked.connect(self._prev)
        bar_lay.addWidget(self._prev_btn)

        self._counter_lbl = QLabel("")
        self._counter_lbl.setObjectName("home_counter")
        self._counter_lbl.setAlignment(Qt.AlignCenter)
        bar_lay.addWidget(self._counter_lbl)

        self._next_btn = QPushButton()
        self._next_btn.setObjectName("home_nav_btn")
        self._next_btn.setIcon(mdl2(chr(0xE76C), t["accent"], 22))
        self._next_btn.setFixedSize(36, 36)
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.setToolTip("Следующая картинка")
        self._next_btn.clicked.connect(self._next)
        bar_lay.addWidget(self._next_btn)

        bar_lay.addStretch()

        title = QLabel("SongBird")
        title.setObjectName("home_title")
        title.setFont(QFont("Gabriola", 52))
        bar_lay.addWidget(title)

        bar_lay.addStretch()

        self._name_lbl = QLabel("")
        self._name_lbl.setObjectName("home_name")
        self._name_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bar_lay.addWidget(self._name_lbl)

        root.addWidget(bar)

    def _scan_images(self):
        self._images = []
        if not _IMG_DIR.exists():
            return
        for f in sorted(_IMG_DIR.iterdir()):
            if f.suffix.lower() in _IMG_EXTS:
                self._images.append(str(f))

    def _load_state(self):
        s = state.load()
        saved = s.get("home_image", "")
        if saved and saved in self._images:
            self._index = self._images.index(saved)
        else:
            self._index = 0
        self._show()

    def _show(self):
        if not self._images:
            self._img_lbl.setText("Нет картинок в папке img/")
            self._counter_lbl.setText("")
            self._name_lbl.setText("")
            return

        path = self._images[self._index]
        pm = QPixmap(path)
        if not pm.isNull():
            size = self._img_lbl.size()
            if size.width() > 10 and size.height() > 10:
                pm = pm.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._img_lbl.setPixmap(pm)

        self._counter_lbl.setText(f"{self._index + 1} / {len(self._images)}")
        self._name_lbl.setText(os.path.basename(path))

        s = state.load()
        s["home_image"] = path
        state.save(s)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._show()

    def _prev(self):
        if not self._images:
            return
        self._index = (self._index - 1) % len(self._images)
        self._show()

    def _next(self):
        if not self._images:
            return
        self._index = (self._index + 1) % len(self._images)
        self._show()
