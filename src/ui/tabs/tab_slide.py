import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QProgressBar, QTextEdit,
    QFileDialog, QComboBox, QDoubleSpinBox, QSpinBox,
    QScrollArea, QFrame, QCheckBox, QSizePolicy, QMessageBox, QLineEdit,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap

import src.state as state
from src.logger import get_logger
from src.theme import current as cur_theme
from src.ui.icons import apply as ico, IC_FOLDER, IC_PLAY, IC_DELETE, IC_UP, IC_DOWN

log = get_logger()

_BIN_DIR    = Path(__file__).resolve().parent.parent.parent.parent / "bin"
_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "output"

_MODE_HINTS = {
    0: "Делит длину трека поровну между всеми слайдами",
    1: "Каждый слайд показывается указанное время, потом по кругу",
}

# (display_name, font_filename) — ищем в C:/Windows/Fonts/
_FONTS = [
    ("Arial",        "arial.ttf"),
    ("Verdana",      "verdana.ttf"),
    ("Trebuchet",    "trebuc.ttf"),
    ("Georgia",      "georgia.ttf"),
    ("Impact",       "impact.ttf"),
    ("Calibri",      "calibri.ttf"),
    ("Segoe UI",     "segoeui.ttf"),
]


class _ElidedLabel(QLabel):
    """QLabel с многоточием когда текст не помещается."""
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self._full = text
        super().setText(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        elided = self.fontMetrics().elidedText(self._full, Qt.ElideRight, self.width())
        super().setText(elided)


def _ffprobe_bin() -> str:
    local = _BIN_DIR / "ffprobe.exe"
    return str(local) if local.exists() else "ffprobe"


def _kw() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def _probe_dur(path: str) -> float:
    try:
        r = subprocess.run(
            [_ffprobe_bin(), "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10, **_kw()
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


# ── поток рендера ───────────────────────────────────────────────────────────
class _RenderThread(QThread):
    log_msg  = Signal(str)
    progress = Signal(int)
    done     = Signal(bool, str)

    def __init__(self, images, tracks, settings, out_dir):
        super().__init__()
        self.images   = images
        self.tracks   = tracks
        self.settings = settings
        self.out_dir  = out_dir

    def run(self):
        from src.slide_render import render_slideshow
        ok, result = render_slideshow(
            self.images, self.tracks, self.settings, self.out_dir,
            on_log=self.log_msg.emit,
            on_progress=self.progress.emit,
        )
        self.done.emit(ok, result)


# ── карточка одного слайда ──────────────────────────────────────────────────
class _SlideCard(QWidget):
    def __init__(self, path: str, on_up, on_down, on_del, parent=None):
        super().__init__(parent)
        self.path = path
        self.setObjectName("media_card")
        self.setFixedHeight(84)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(8)

        thumb = QLabel()
        thumb.setFixedSize(120, 68)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setObjectName("thumb_lbl")
        pm = QPixmap(path)
        if not pm.isNull():
            thumb.setPixmap(pm.scaled(120, 68, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            thumb.setText("?")
        lay.addWidget(thumb)

        name = _ElidedLabel(Path(path).name)
        name.setObjectName("card_name")
        name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(name, 1)

        t = cur_theme()
        dim = t.get("dim", "#606060")
        for icon, cb in ((IC_UP, on_up), (IC_DOWN, on_down)):
            btn = QPushButton()
            btn.setFixedSize(26, 26)
            btn.setCursor(Qt.PointingHandCursor)
            ico(btn, icon, dim, 14)
            btn.clicked.connect(lambda _, c=cb: c(self))
            lay.addWidget(btn)

        del_btn = QPushButton()
        del_btn.setFixedSize(26, 26)
        del_btn.setCursor(Qt.PointingHandCursor)
        ico(del_btn, IC_DELETE, dim, 14)
        del_btn.clicked.connect(lambda: on_del(self))
        lay.addWidget(del_btn)


# ── главный виджет вкладки ──────────────────────────────────────────────────
class TabSlide(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._slide_cards: list[_SlideCard] = []
        self._tracks: list[str] = []
        self._running = False
        self._thread: _RenderThread | None = None
        self._build()
        self._load_state()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ── левая панель ────────────────────────────────────────────────────
        left_w = QWidget()
        left_w.setObjectName("clip_left_panel")
        left_lay = QVBoxLayout(left_w)
        left_lay.setContentsMargins(10, 10, 10, 10)
        left_lay.setSpacing(6)

        left_lay.addLayout(self._build_tracks_panel())
        left_lay.addLayout(self._build_settings_block())

        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        left_lay.addWidget(self.progress)

        # строка статуса + кнопки
        bot = QHBoxLayout()
        bot.setSpacing(6)

        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("label_dim")
        bot.addWidget(self.status_lbl, 1)

        self.open_btn = QPushButton("  Открыть папку")
        ico(self.open_btn, IC_FOLDER)
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.clicked.connect(self._on_open_output)
        bot.addWidget(self.open_btn)

        self.render_btn = QPushButton("  Смонтировать")
        ico(self.render_btn, IC_PLAY)
        self.render_btn.setObjectName("accent_btn")
        self.render_btn.setCursor(Qt.PointingHandCursor)
        self.render_btn.clicked.connect(self._start_render)
        bot.addWidget(self.render_btn)

        self.cancel_btn = QPushButton("Стоп")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._cancel_render)
        bot.addWidget(self.cancel_btn)

        left_lay.addLayout(bot)

        self.log_box = QTextEdit()
        self.log_box.setObjectName("clip_log")
        self.log_box.setReadOnly(True)
        left_lay.addWidget(self.log_box, 1)

        # ── разделитель ─────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)

        # ── правая панель ───────────────────────────────────────────────────
        right_w = QWidget()
        right_w.setObjectName("clip_right_panel")
        right_lay = QVBoxLayout(right_w)
        right_lay.setContentsMargins(10, 10, 10, 10)
        right_lay.setSpacing(6)
        right_lay.addLayout(self._build_slides_panel())

        root.addWidget(left_w, 6)
        root.addWidget(sep)
        root.addWidget(right_w, 4)

    def _build_tracks_panel(self) -> QVBoxLayout:
        lay = QVBoxLayout()
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        title = QLabel("Треки")
        title.setObjectName("panel_title")
        hdr.addWidget(title)
        hdr.addStretch()
        self.track_total_lbl = QLabel("Длина: —")
        self.track_total_lbl.setObjectName("label_dim")
        hdr.addWidget(self.track_total_lbl)
        hdr.addStretch()
        add_btn = QPushButton("  Добавить")
        ico(add_btn, IC_FOLDER)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_tracks)
        hdr.addWidget(add_btn)
        lay.addLayout(hdr)

        self.track_list = QListWidget()
        self.track_list.setDragDropMode(QListWidget.NoDragDrop)
        self.track_list.setSelectionMode(QListWidget.SingleSelection)
        lay.addWidget(self.track_list)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        dim = cur_theme().get("dim", "#606060")
        for icon, cb in ((IC_UP, self._track_up), (IC_DOWN, self._track_down)):
            b = QPushButton()
            b.setFixedSize(28, 28)
            b.setCursor(Qt.PointingHandCursor)
            ico(b, icon, dim, 16)
            b.clicked.connect(cb)
            btn_row.addWidget(b)
        del_b = QPushButton()
        del_b.setFixedSize(28, 28)
        del_b.setCursor(Qt.PointingHandCursor)
        ico(del_b, IC_DELETE, dim, 16)
        del_b.clicked.connect(self._track_delete)
        btn_row.addWidget(del_b)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        return lay

    def _build_settings_block(self) -> QVBoxLayout:
        wrap = QVBoxLayout()
        wrap.setSpacing(4)

        # строка 1: режим + длительность + чекбоксы (как было)
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(QLabel("Длит.:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Авто (по треку)",    "auto")
        self.mode_combo.addItem("Фикс. (сек/слайд)",  "loop")
        self.mode_combo.setFixedWidth(148)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_change)
        row1.addWidget(self.mode_combo)
        self.dur_spin = QDoubleSpinBox()
        self.dur_spin.setRange(5, 120)
        self.dur_spin.setValue(20)
        self.dur_spin.setSuffix(" с")
        self.dur_spin.setFixedWidth(68)
        row1.addWidget(self.dur_spin)
        row1.addStretch()
        self.kenburns_cb = QCheckBox("Ken Burns")
        self.kenburns_cb.setChecked(True)
        row1.addWidget(self.kenburns_cb)
        self.particles_cb = QCheckBox("Частицы")
        self.particles_cb.setChecked(True)
        row1.addWidget(self.particles_cb)
        wrap.addLayout(row1)

        # подсказка под режимом
        self.hint_lbl = QLabel()
        self.hint_lbl.setObjectName("label_dim")
        wrap.addWidget(self.hint_lbl)

        # строка 2: канал — поле + шрифт + размер в одну строку
        row_ch = QHBoxLayout()
        row_ch.setSpacing(6)
        row_ch.addWidget(QLabel("Канал:"))
        self.channel_edit = QLineEdit()
        self.channel_edit.setPlaceholderText("название канала (всегда внизу)")
        row_ch.addWidget(self.channel_edit, 1)
        row_ch.addWidget(QLabel("Шрифт:"))
        self.ch_font_combo = QComboBox()
        for name, _ in _FONTS:
            self.ch_font_combo.addItem(name)
        self.ch_font_combo.setFixedWidth(90)
        row_ch.addWidget(self.ch_font_combo)
        row_ch.addWidget(QLabel("Размер:"))
        self.ch_size_spin = QSpinBox()
        self.ch_size_spin.setRange(16, 200)
        self.ch_size_spin.setValue(28)
        self.ch_size_spin.setSuffix("px")
        self.ch_size_spin.setFixedWidth(72)
        row_ch.addWidget(self.ch_size_spin)
        wrap.addLayout(row_ch)

        # строка 3: трек — поле + шрифт + размер в одну строку
        row_tr = QHBoxLayout()
        row_tr.setSpacing(6)
        row_tr.addWidget(QLabel("Трек:"))
        self.track_edit = QLineEdit()
        self.track_edit.setPlaceholderText("название трека (30 сек, потом исчезает)")
        row_tr.addWidget(self.track_edit, 1)
        row_tr.addWidget(QLabel("Шрифт:"))
        self.tr_font_combo = QComboBox()
        for name, _ in _FONTS:
            self.tr_font_combo.addItem(name)
        self.tr_font_combo.setFixedWidth(90)
        row_tr.addWidget(self.tr_font_combo)
        row_tr.addWidget(QLabel("Размер:"))
        self.tr_size_spin = QSpinBox()
        self.tr_size_spin.setRange(16, 200)
        self.tr_size_spin.setValue(42)
        self.tr_size_spin.setSuffix("px")
        self.tr_size_spin.setFixedWidth(72)
        row_tr.addWidget(self.tr_size_spin)
        wrap.addLayout(row_tr)

        # сохраняем при любом изменении настроек
        self.kenburns_cb.toggled.connect(lambda _: self._save_state())
        self.particles_cb.toggled.connect(lambda _: self._save_state())
        self.channel_edit.textChanged.connect(lambda _: self._save_state())
        self.ch_font_combo.currentIndexChanged.connect(lambda _: self._save_state())
        self.ch_size_spin.valueChanged.connect(lambda _: self._save_state())
        self.track_edit.textChanged.connect(lambda _: self._save_state())
        self.tr_font_combo.currentIndexChanged.connect(lambda _: self._save_state())
        self.tr_size_spin.valueChanged.connect(lambda _: self._save_state())
        self.mode_combo.currentIndexChanged.connect(lambda _: self._save_state())
        self.dur_spin.valueChanged.connect(lambda _: self._save_state())

        self._on_mode_change(0)
        return wrap

    def _build_slides_panel(self) -> QVBoxLayout:
        lay = QVBoxLayout()
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        title = QLabel("Слайды")
        title.setObjectName("panel_title")
        hdr.addWidget(title)
        hdr.addStretch()
        self.slide_count_lbl = QLabel("")
        self.slide_count_lbl.setObjectName("label_dim")
        hdr.addWidget(self.slide_count_lbl)
        hdr.addStretch()
        clr_btn = QPushButton("  Очистить")
        ico(clr_btn, IC_DELETE)
        clr_btn.setCursor(Qt.PointingHandCursor)
        clr_btn.clicked.connect(self._clear_slides)
        hdr.addWidget(clr_btn)
        add_btn = QPushButton("  Добавить")
        ico(add_btn, IC_FOLDER)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_slides)
        hdr.addWidget(add_btn)
        lay.addLayout(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._cards_container = QWidget()
        self._cards_container.setObjectName("media_cards_bg")
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(4, 4, 4, 4)
        self._cards_layout.setSpacing(4)
        self._cards_layout.addStretch()

        scroll.setWidget(self._cards_container)
        lay.addWidget(scroll, 1)
        return lay

    # ── режим ───────────────────────────────────────────────────────────────
    def _on_mode_change(self, idx: int):
        loop = idx == 1
        self.dur_spin.setVisible(loop)
        self.hint_lbl.setText(_MODE_HINTS.get(idx, ""))

    # ── треки ───────────────────────────────────────────────────────────────
    def _add_tracks(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Добавить треки", "",
            "Аудио (*.mp3 *.wav *.flac *.m4a *.ogg);;Все файлы (*)"
        )
        for f in files:
            if f not in self._tracks:
                self._tracks.append(f)
                self.track_list.addItem(Path(f).name)
        self._recalc_tracks()
        self._save_state()

    def _track_up(self):
        row = self.track_list.currentRow()
        if row > 0:
            self._tracks.insert(row - 1, self._tracks.pop(row))
            item = self.track_list.takeItem(row)
            self.track_list.insertItem(row - 1, item)
            self.track_list.setCurrentRow(row - 1)
            self._save_state()

    def _track_down(self):
        row = self.track_list.currentRow()
        if 0 <= row < self.track_list.count() - 1:
            self._tracks.insert(row + 1, self._tracks.pop(row))
            item = self.track_list.takeItem(row)
            self.track_list.insertItem(row + 1, item)
            self.track_list.setCurrentRow(row + 1)
            self._save_state()

    def _track_delete(self):
        row = self.track_list.currentRow()
        if row >= 0:
            self._tracks.pop(row)
            self.track_list.takeItem(row)
            self._recalc_tracks()
            self._save_state()

    def _recalc_tracks(self):
        total = sum(_probe_dur(t) for t in self._tracks)
        if total > 0:
            m, s = divmod(int(total), 60)
            self.track_total_lbl.setText(f"Длина: {m}:{s:02d}")
        else:
            self.track_total_lbl.setText("Длина: —")

    # ── слайды ──────────────────────────────────────────────────────────────
    def _add_slides(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Добавить слайды", "",
            "Изображения (*.jpg *.jpeg *.png *.webp *.bmp);;Все файлы (*)"
        )
        for f in files:
            self._add_card(f)
        self._recalc_slides()
        self._save_state()

    def _add_card(self, path: str):
        card = _SlideCard(path, self._card_up, self._card_down, self._card_del)
        self._slide_cards.append(card)
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

    def _card_up(self, card: _SlideCard):
        idx = self._slide_cards.index(card)
        if idx > 0:
            self._slide_cards.insert(idx - 1, self._slide_cards.pop(idx))
            self._rebuild_cards_layout()
            self._save_state()

    def _card_down(self, card: _SlideCard):
        idx = self._slide_cards.index(card)
        if idx < len(self._slide_cards) - 1:
            self._slide_cards.insert(idx + 1, self._slide_cards.pop(idx))
            self._rebuild_cards_layout()
            self._save_state()

    def _card_del(self, card: _SlideCard):
        self._slide_cards.remove(card)
        card.setParent(None)
        card.deleteLater()
        self._recalc_slides()
        self._save_state()

    def _clear_slides(self):
        mb = QMessageBox(self)
        mb.setWindowTitle("Очистить слайды?")
        mb.setText("Удалить все слайды из списка?")
        mb.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        mb.setDefaultButton(QMessageBox.No)
        mb.button(QMessageBox.Yes).setText("Очистить")
        mb.button(QMessageBox.No).setText("Отмена")
        if mb.exec() != QMessageBox.Yes:
            return
        for card in list(self._slide_cards):
            card.setParent(None)
            card.deleteLater()
        self._slide_cards.clear()
        self._recalc_slides()
        self._save_state()

    def _rebuild_cards_layout(self):
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        for card in self._slide_cards:
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

    def _recalc_slides(self):
        n = len(self._slide_cards)
        if n == 0:
            self.slide_count_lbl.setText("")
        elif n % 10 == 1 and n % 100 != 11:
            self.slide_count_lbl.setText(f"{n} слайд")
        elif 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
            self.slide_count_lbl.setText(f"{n} слайда")
        else:
            self.slide_count_lbl.setText(f"{n} слайдов")

    # ── рендер ──────────────────────────────────────────────────────────────
    def _start_render(self):
        if not self._tracks:
            self._set_status("err", "Добавь хотя бы один трек")
            return
        if not self._slide_cards:
            self._set_status("err", "Добавь слайды")
            return

        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        mode = self.mode_combo.currentData()
        settings = {
            "mode":           mode,
            "dur_per_img":    self.dur_spin.value(),
            "transition":     "fade",
            "trans_duration": 0.8,
            "fade_in":        1.0,
            "fade_out":       2.0,
            "kenburns":       self.kenburns_cb.isChecked(),
            "particles":      self.particles_cb.isChecked(),
            "width":          1920,
            "height":         1080,
            "fps":            25,
            "channel":        self.channel_edit.text().strip(),
            "ch_font":        _FONTS[self.ch_font_combo.currentIndex()][1],
            "ch_size":        self.ch_size_spin.value(),
            "track_name":     self.track_edit.text().strip(),
            "tr_font":        _FONTS[self.tr_font_combo.currentIndex()][1],
            "tr_size":        self.tr_size_spin.value(),
        }

        self._running = True
        self.render_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log_box.clear()
        self.progress.setValue(0)
        self._set_status("", "Монтирую...")

        images = [c.path for c in self._slide_cards]
        self._thread = _RenderThread(images, self._tracks, settings, str(_OUTPUT_DIR))
        self._thread.log_msg.connect(self._log)
        self._thread.progress.connect(self.progress.setValue)
        self._thread.done.connect(self._on_done)
        self._thread.start()

    def _cancel_render(self):
        if self._thread and self._thread.isRunning():
            self._thread.terminate()
        self._running = False
        self.render_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._set_status("", "Отменено")

    def _on_done(self, ok: bool, result: str):
        self._running = False
        self.render_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        if ok:
            self._set_status("ok", f"Готово: {Path(result).name}")
        else:
            self._set_status("err", result)

    def _on_open_output(self):
        if _OUTPUT_DIR.exists():
            os.startfile(str(_OUTPUT_DIR))

    def _set_status(self, kind: str, text: str):
        obj = {"ok": "label_ok", "err": "label_err"}.get(kind, "label_dim")
        self.status_lbl.setObjectName(obj)
        self.status_lbl.setText(text)
        self.status_lbl.style().polish(self.status_lbl)

    def _log(self, msg: str):
        self.log_box.append(msg)
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ── состояние ───────────────────────────────────────────────────────────
    def _save_state(self):
        s = state.load()
        s["slide"] = {
            "tracks":    self._tracks,
            "images":    [c.path for c in self._slide_cards],
            "mode":      self.mode_combo.currentIndex(),
            "dur_per":   self.dur_spin.value(),
            "kenburns":  self.kenburns_cb.isChecked(),
            "particles": self.particles_cb.isChecked(),
            "channel":      self.channel_edit.text().strip(),
            "ch_font_idx":  self.ch_font_combo.currentIndex(),
            "ch_size":      self.ch_size_spin.value(),
            "track_name":   self.track_edit.text().strip(),
            "tr_font_idx":  self.tr_font_combo.currentIndex(),
            "tr_size":      self.tr_size_spin.value(),
        }
        state.save(s)

    def _load_state(self):
        s = state.load().get("slide", {})
        for t in s.get("tracks", []):
            if os.path.exists(t):
                self._tracks.append(t)
                self.track_list.addItem(Path(t).name)
        for img in s.get("images", []):
            if os.path.exists(img):
                self._add_card(img)
        self.mode_combo.setCurrentIndex(s.get("mode", 0))
        self.dur_spin.setValue(s.get("dur_per", 20.0))
        self.kenburns_cb.setChecked(s.get("kenburns", True))
        self.particles_cb.setChecked(s.get("particles", True))
        self.channel_edit.setText(s.get("channel", ""))
        self.ch_font_combo.setCurrentIndex(s.get("ch_font_idx", 0))
        self.ch_size_spin.setValue(s.get("ch_size", 28))
        self.track_edit.setText(s.get("track_name", ""))
        self.tr_font_combo.setCurrentIndex(s.get("tr_font_idx", 0))
        self.tr_size_spin.setValue(s.get("tr_size", 42))
        self._recalc_tracks()
        self._recalc_slides()
