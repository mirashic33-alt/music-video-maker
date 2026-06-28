from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QLineEdit, QPushButton, QFrame
)
from PySide6.QtCore import Qt
import src.state as state
from src.ui.icons import apply as ico, IC_COPY


class TabYouTube(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self._load_state()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 16, 28, 20)
        lay.setSpacing(14)

        head = QHBoxLayout()
        title = QLabel("YouTube")
        title.setObjectName("label_h1")
        head.addWidget(title)
        head.addStretch()

        hint = QLabel("Подготовь текст, скопируй и вставь на YouTube вручную")
        hint.setObjectName("label_dim")
        head.addWidget(hint)
        lay.addLayout(head)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        lay.addWidget(sep)

        cols = QHBoxLayout()
        cols.setSpacing(20)
        lay.addLayout(cols, 1)

        # Левая колонка
        left = QVBoxLayout()
        left.setSpacing(10)
        cols.addLayout(left, 1)

        left.addWidget(self._section("Название видео"))
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Например: Relaxing Bird Music — AI Generated")
        self._title_edit.textChanged.connect(self._save_state)
        left.addWidget(self._title_edit)

        row_t = QHBoxLayout()
        row_t.addStretch()
        copy_t = QPushButton(" Копировать")
        ico(copy_t, IC_COPY)
        copy_t.setMinimumWidth(130)
        copy_t.setCursor(Qt.PointingHandCursor)
        copy_t.clicked.connect(lambda: self._copy_to_clipboard(self._title_edit.text()))
        row_t.addWidget(copy_t)
        left.addLayout(row_t)

        left.addWidget(self._section("Описание"))
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText(
            "Шаблонное описание канала...\n\nМожно редактировать перед каждым видео."
        )
        self._desc_edit.textChanged.connect(self._save_state)
        left.addWidget(self._desc_edit, 1)

        row_d = QHBoxLayout()
        row_d.addStretch()
        copy_d = QPushButton(" Копировать")
        ico(copy_d, IC_COPY)
        copy_d.setMinimumWidth(130)
        copy_d.setCursor(Qt.PointingHandCursor)
        copy_d.clicked.connect(lambda: self._copy_to_clipboard(self._desc_edit.toPlainText()))
        row_d.addWidget(copy_d)
        left.addLayout(row_d)

        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        cols.addWidget(vline)

        # Правая колонка
        right = QVBoxLayout()
        right.setSpacing(10)
        cols.addLayout(right, 1)

        right.addWidget(self._section("Теги"))
        self._tags_edit = QTextEdit()
        self._tags_edit.setPlaceholderText(
            "relaxing music, ai music, bird sounds, ambient, meditation"
        )
        self._tags_edit.setMaximumHeight(160)
        self._tags_edit.textChanged.connect(self._save_state)
        right.addWidget(self._tags_edit)

        row_tg = QHBoxLayout()
        row_tg.addStretch()
        copy_tg = QPushButton(" Копировать")
        ico(copy_tg, IC_COPY)
        copy_tg.setMinimumWidth(130)
        copy_tg.setCursor(Qt.PointingHandCursor)
        copy_tg.clicked.connect(lambda: self._copy_to_clipboard(self._tags_edit.toPlainText()))
        row_tg.addWidget(copy_tg)
        right.addLayout(row_tg)

        right.addWidget(self._section("Чеклист перед публикацией"))
        checklist = QLabel(
            "  Название заполнено\n"
            "  Описание готово\n"
            "  Теги вставлены\n"
            "  Язык видео: указан\n"
            "  Не для детей: галочка стоит\n"
            "  AI-контент: галочка стоит\n"
            "  Музыкальная категория\n"
            "  Дата публикации: задана\n"
            "  YouTube не нашёл ничего подозрительного"
        )
        checklist.setObjectName("yt_checklist")
        checklist.setWordWrap(True)
        right.addWidget(checklist)
        right.addStretch()

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section_title")
        return lbl

    def _copy_to_clipboard(self, text: str):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    def _save_state(self):
        s = state.load()
        s["youtube"] = {
            "title": self._title_edit.text(),
            "description": self._desc_edit.toPlainText(),
            "tags": self._tags_edit.toPlainText(),
        }
        state.save(s)

    def _load_state(self):
        s = state.load()
        yt = s.get("youtube", {})
        self._title_edit.blockSignals(True)
        self._desc_edit.blockSignals(True)
        self._tags_edit.blockSignals(True)

        self._title_edit.setText(yt.get("title", ""))
        self._desc_edit.setPlainText(yt.get("description", ""))
        self._tags_edit.setPlainText(yt.get("tags", ""))

        self._title_edit.blockSignals(False)
        self._desc_edit.blockSignals(False)
        self._tags_edit.blockSignals(False)
