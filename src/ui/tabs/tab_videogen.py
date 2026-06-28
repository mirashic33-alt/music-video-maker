import time
import threading
import webbrowser
import requests
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QLineEdit, QPushButton, QFrame,
    QFileDialog, QProgressBar, QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap

import src.state as state


# ── Константы ─────────────────────────────────────────────────────────────────
_API_KEY      = ""   # вставьте свой ключ Grok (xAI) в настройках вкладки «Генерация видео»
_API_BASE     = "https://api.x.ai/v1"
_MODEL        = "grok-imagine-video"
_DURATION     = 10
_ASPECT_RATIO = "16:9"
_RESOLUTION   = "720p"
_POLL_SEC     = 5


# ── Поток генерации ───────────────────────────────────────────────────────────

def _has_cyrillic(text: str) -> bool:
    return any('Ѐ' <= c <= 'ӿ' for c in text)


def _translate_prompt(api_key: str, text: str) -> str:
    """Переводит промпт на английский через grok-build-0.1."""
    resp = requests.post(
        f"{_API_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "grok-build-0.1",
            "messages": [
                {"role": "system", "content": "Translate the following video generation prompt to English. Return only the translation, no explanations."},
                {"role": "user", "content": text},
            ],
            "temperature": 0.3,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


class _GenThread(QThread):
    status_msg = Signal(str)
    translated = Signal(str)   # переведённый промпт (для показа в UI)
    finished   = Signal(str)   # video url
    failed     = Signal(str)

    def __init__(self, api_key: str, prompt: str, image_source: str):
        super().__init__()
        self.api_key      = api_key
        self.prompt       = prompt
        self.image_source = image_source

    def run(self):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }

        # Перевод если кириллица
        prompt = self.prompt
        if _has_cyrillic(prompt):
            self.status_msg.emit("Перевожу промпт...")
            try:
                prompt = _translate_prompt(self.api_key, prompt)
                self.translated.emit(prompt)
            except Exception as e:
                self.failed.emit(f"Ошибка перевода:\n{e}")
                return

        payload = {
            "model":        _MODEL,
            "prompt":       prompt,
            "duration":     _DURATION,
            "aspect_ratio": _ASPECT_RATIO,
            "resolution":   _RESOLUTION,
        }

        # Картинка
        if self.image_source:
            src = self.image_source.strip()
            if src.startswith("http://") or src.startswith("https://"):
                payload["image"] = {"url": src}
            else:
                self.status_msg.emit("Загружаю картинку...")
                try:
                    with open(src, "rb") as f:
                        r = requests.post(
                            "https://catbox.moe/user/api.php",
                            data={"reqtype": "fileupload"},
                            files={"fileToUpload": f},
                            timeout=30,
                        )
                    url = r.text.strip()
                    if not url.startswith("https://"):
                        self.failed.emit(f"Не удалось загрузить картинку:\n{url}")
                        return
                    payload["image"] = {"url": url}
                except Exception as e:
                    self.failed.emit(f"Ошибка загрузки картинки:\n{e}")
                    return

        # Запрос
        self.status_msg.emit("Отправляю запрос...")
        try:
            resp = requests.post(
                f"{_API_BASE}/videos/generations",
                json=payload, headers=headers, timeout=30,
            )
        except Exception as e:
            self.failed.emit(f"Сетевая ошибка:\n{e}")
            return

        if resp.status_code != 200:
            self.failed.emit(f"Ошибка API {resp.status_code}:\n{resp.text}")
            return

        request_id = resp.json().get("request_id")
        if not request_id:
            self.failed.emit(f"Нет request_id:\n{resp.text}")
            return

        # Polling
        start = time.time()
        while True:
            elapsed = int(time.time() - start)
            self.status_msg.emit(f"Генерирую... {elapsed} сек")
            try:
                r    = requests.get(f"{_API_BASE}/videos/{request_id}", headers=headers, timeout=10)
                data = r.json()
                st   = data.get("status")
                if st == "done":
                    self.finished.emit(data.get("video", {}).get("url", ""))
                    return
                elif st in ("failed", "expired"):
                    self.failed.emit(f"Генерация не удалась: {st}\n{data}")
                    return
            except Exception:
                pass
            time.sleep(_POLL_SEC)


# ── Вкладка ───────────────────────────────────────────────────────────────────

class TabVideoGen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread     = None
        self._video_url  = ""
        self._start_time = 0.0
        self._timer      = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._build()
        self._load_state()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 16, 28, 20)
        lay.setSpacing(14)

        # Заголовок
        head = QHBoxLayout()
        title = QLabel("Grok Video")
        title.setObjectName("label_h1")
        head.addWidget(title)
        head.addStretch()
        hint = QLabel(f"{_DURATION} сек  ·  {_ASPECT_RATIO}  ·  {_RESOLUTION}  ·  ~$0.50 / ролик")
        hint.setObjectName("label_dim")
        head.addWidget(hint)
        lay.addLayout(head)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        lay.addWidget(sep)

        # API Key
        lay.addWidget(self._section("API Key  (xAI)"))
        key_row = QHBoxLayout()
        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.Password)
        self._key_edit.setPlaceholderText("xai-...")
        self._key_edit.textChanged.connect(self._save_state)
        key_row.addWidget(self._key_edit)
        lay.addLayout(key_row)

        # Картинка + превью (две колонки)
        img_prompt_row = QHBoxLayout()
        img_prompt_row.setSpacing(16)
        lay.addLayout(img_prompt_row)

        # Левая колонка: картинка + промпт
        left_col = QVBoxLayout()
        left_col.setSpacing(10)
        img_prompt_row.addLayout(left_col, 1)

        left_col.addWidget(self._section("Референсная картинка  (необязательно)"))
        img_row = QHBoxLayout()
        self._img_edit = QLineEdit()
        self._img_edit.setPlaceholderText("путь к файлу  или  https://...")
        self._img_edit.textChanged.connect(self._on_img_changed)
        img_row.addWidget(self._img_edit, 1)
        btn_browse = QPushButton("Обзор...")
        btn_browse.setFixedWidth(90)
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.clicked.connect(self._pick_image)
        img_row.addWidget(btn_browse)
        left_col.addLayout(img_row)

        left_col.addWidget(self._section("Prompt  (English)"))
        self._prompt = QTextEdit()
        self._prompt.setPlaceholderText(
            "A woman walks slowly through a neon-lit cyberpunk street at night,\n"
            "rain reflecting colorful signs, cinematic atmosphere, slow motion..."
        )
        self._prompt.setFixedHeight(100)
        self._prompt.textChanged.connect(self._save_state)
        self._prompt.textChanged.connect(self._clear_translation)
        left_col.addWidget(self._prompt)

        self._translated_lbl = QLabel("")
        self._translated_lbl.setObjectName("label_dim")
        self._translated_lbl.setWordWrap(True)
        self._translated_lbl.setVisible(False)
        left_col.addWidget(self._translated_lbl)

        # Правая колонка: превью картинки
        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        img_prompt_row.addLayout(right_col)

        right_col.addWidget(self._section("Превью"))
        self._preview = QLabel()
        self._preview.setFixedSize(213, 120)   # 16:9 пропорция
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setObjectName("img_preview")
        self._preview.setStyleSheet(
            "QLabel#img_preview { border: 1px solid #444; border-radius: 4px; background: #1a1a1a; color: #555; }"
        )
        self._preview.setText("нет картинки")
        right_col.addWidget(self._preview)
        right_col.addStretch()

        # Кнопка
        self._gen_btn = QPushButton("Генерировать видео")
        self._gen_btn.setFixedHeight(36)
        self._gen_btn.setCursor(Qt.PointingHandCursor)
        self._gen_btn.clicked.connect(self._generate)
        lay.addWidget(self._gen_btn)

        # Прогресс
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        lay.addWidget(self._progress)

        # Статус
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("label_dim")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._status_lbl)

        # Результат
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        lay.addWidget(sep2)

        self._result_lbl = QLabel("")
        self._result_lbl.setWordWrap(True)
        self._result_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._result_lbl.setObjectName("label_dim")
        lay.addWidget(self._result_lbl)

        res_btns = QHBoxLayout()
        self._open_btn = QPushButton("Открыть в браузере")
        self._open_btn.setVisible(False)
        self._open_btn.setCursor(Qt.PointingHandCursor)
        self._open_btn.clicked.connect(self._open_video)
        self._save_lbl = QLabel("")
        self._save_lbl.setObjectName("label_dim")
        res_btns.addWidget(self._open_btn)
        res_btns.addStretch()
        res_btns.addWidget(self._save_lbl)
        lay.addLayout(res_btns)

        lay.addStretch()

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section_title")
        return lbl

    # ── Логика ────────────────────────────────────────────────────────────────

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбери референсную картинку", "",
            "Images (*.jpg *.jpeg *.png *.webp)"
        )
        if path:
            self._img_edit.setText(path)

    def _on_img_changed(self, text: str):
        text = text.strip()
        if not text:
            self._preview.setPixmap(QPixmap())
            self._preview.setText("нет картинки")
            return
        # Локальный файл
        if not text.startswith("http"):
            px = QPixmap(text)
            if not px.isNull():
                self._preview.setText("")
                self._preview.setPixmap(
                    px.scaled(self._preview.width(), self._preview.height(),
                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            else:
                self._preview.setPixmap(QPixmap())
                self._preview.setText("файл не найден")
        else:
            # URL — загружаем в фоне
            self._preview.setPixmap(QPixmap())
            self._preview.setText("загружаю...")
            def _fetch(url):
                try:
                    r = requests.get(url, timeout=10)
                    px = QPixmap()
                    px.loadFromData(r.content)
                    if not px.isNull():
                        scaled = px.scaled(self._preview.width(), self._preview.height(),
                                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        QTimer.singleShot(0, lambda: (
                            self._preview.setPixmap(scaled),
                            self._preview.setText(""),
                        ))
                    else:
                        QTimer.singleShot(0, lambda: self._preview.setText("не удалось"))
                except Exception:
                    QTimer.singleShot(0, lambda: self._preview.setText("ошибка загрузки"))
            threading.Thread(target=_fetch, args=(text,), daemon=True).start()

    def _generate(self):
        key    = self._key_edit.text().strip()
        prompt = self._prompt.toPlainText().strip()
        if not key:
            QMessageBox.warning(self, "Нет ключа", "Введи API ключ xAI")
            return
        if not prompt:
            QMessageBox.warning(self, "Нет промпта", "Напиши промпт на английском")
            return

        self._gen_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._open_btn.setVisible(False)
        self._result_lbl.setText("")
        self._save_lbl.setText("")
        self._start_time = time.time()
        self._timer.start()

        self._thread = _GenThread(key, prompt, self._img_edit.text())
        self._thread.status_msg.connect(self._on_status)
        self._thread.translated.connect(self._on_translated)
        self._thread.finished.connect(self._on_done)
        self._thread.failed.connect(self._on_error)
        self._thread.start()

    def _tick(self):
        elapsed = int(time.time() - self._start_time)
        self._status_lbl.setText(f"Генерирую... {elapsed} сек")

    def _on_translated(self, text: str):
        self._translated_lbl.setText(f"→ {text}")
        self._translated_lbl.setVisible(True)

    def _clear_translation(self):
        self._translated_lbl.setVisible(False)
        self._translated_lbl.setText("")

    def _on_status(self, msg: str):
        if not self._timer.isActive():
            self._status_lbl.setText(msg)

    def _on_done(self, url: str):
        self._timer.stop()
        self._progress.setVisible(False)
        self._gen_btn.setEnabled(True)
        elapsed = int(time.time() - self._start_time)
        self._status_lbl.setText(f"Готово за {elapsed} сек")
        self._video_url = url
        self._result_lbl.setText(url)
        self._open_btn.setVisible(True)
        self._download_video(url)

    def _on_error(self, msg: str):
        self._timer.stop()
        self._progress.setVisible(False)
        self._gen_btn.setEnabled(True)
        self._status_lbl.setText("")
        QMessageBox.critical(self, "Ошибка генерации", msg)

    def _download_video(self, url: str):
        def _do():
            try:
                r   = requests.get(url, timeout=120)
                out = Path(__file__).parent.parent.parent.parent / "output" / f"video_{int(time.time())}.mp4"
                out.parent.mkdir(exist_ok=True)
                out.write_bytes(r.content)
                self._save_lbl.setText(f"Сохранено: {out.name}")
            except Exception as e:
                self._save_lbl.setText(f"Не скачалось: {e}")
        threading.Thread(target=_do, daemon=True).start()

    def _open_video(self):
        if self._video_url:
            webbrowser.open(self._video_url)

    # ── State ─────────────────────────────────────────────────────────────────

    def _save_state(self):
        s = state.load()
        s["videogen"] = {
            "api_key": self._key_edit.text(),
            "prompt":  self._prompt.toPlainText(),
        }
        state.save(s)

    def _load_state(self):
        s = state.load()
        vg = s.get("videogen", {})
        self._key_edit.blockSignals(True)
        self._prompt.blockSignals(True)
        self._key_edit.setText(vg.get("api_key", _API_KEY))
        self._prompt.setPlainText(vg.get("prompt", ""))
        self._key_edit.blockSignals(False)
        self._prompt.blockSignals(False)
