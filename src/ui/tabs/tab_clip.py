import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QFrame,
    QFileDialog, QComboBox, QDoubleSpinBox,
    QProgressBar, QTextEdit, QAbstractItemView,
    QScrollArea
)
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QPixmap, QCursor

import src.state as state
from src.logger import get_logger
from src.theme import current as cur_theme
from src.ui.icons import apply as ico, IC_FOLDER, IC_PLAY, IC_DELETE, IC_PREV, IC_NEXT, IC_REFRESH, IC_UP, IC_DOWN

log = get_logger()

_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}

_BIN_DIR = Path(__file__).resolve().parent.parent.parent.parent / "bin"
_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "output"
_THUMB_W, _THUMB_H = 128, 72


def _ffmpeg_bin() -> str:
    local = _BIN_DIR / "ffmpeg.exe"
    return str(local) if local.exists() else "ffmpeg"


def _ffprobe_bin() -> str:
    local = _BIN_DIR / "ffprobe.exe"
    return str(local) if local.exists() else "ffprobe"


def _kw() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def _probe_duration(path: str) -> float:
    try:
        r = subprocess.run(
            [_ffprobe_bin(), "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=10, **_kw()
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _make_thumb(path: str) -> QPixmap | None:
    try:
        dur = _probe_duration(path)
        seek = max(0.5, dur / 2) if dur > 1 else 0.5
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp = f.name
        subprocess.run(
            [_ffmpeg_bin(), "-y", "-ss", f"{seek:.2f}", "-i", path,
             "-frames:v", "1", "-q:v", "3", tmp],
            capture_output=True, timeout=15, **_kw()
        )
        pm = QPixmap(tmp)
        try:
            os.unlink(tmp)
        except Exception:
            pass
        if pm.isNull():
            return None
        return pm.scaled(_THUMB_W, _THUMB_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    except Exception:
        return None


def _fmt(secs: float) -> str:
    if secs <= 0:
        return "—"
    m, s = int(secs) // 60, int(secs) % 60
    if m >= 60:
        return f"{m // 60}:{m % 60:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class _Sig(QObject):
    finished    = Signal(bool, str)
    progress    = Signal(int)
    log_line    = Signal(str)
    dur_ready   = Signal(str, float)
    thumb_ready = Signal(str, object)


class _MediaCard(QWidget):
    request_up          = Signal(object)
    request_dn          = Signal(object)
    request_add_version = Signal(object)
    request_remove      = Signal(object)
    request_probe       = Signal(object)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._versions: list[str] = [path]
        self._current: int = 0
        self._thumb_cache: dict[str, QPixmap] = {}
        self._dur_cache:   dict[str, float]   = {}
        self._build()

    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(6)
        self.setObjectName("media_card")
        self.setAutoFillBackground(False)

        # Кнопки перемещения (вверх/вниз)
        move_col = QVBoxLayout()
        move_col.setSpacing(1)
        _dim = cur_theme()["dim"]
        up_btn = QPushButton()
        ico(up_btn, IC_UP, _dim, 16)
        up_btn.setFixedSize(28, 28)
        up_btn.setCursor(Qt.PointingHandCursor)
        up_btn.setToolTip("Переместить вверх")
        up_btn.clicked.connect(lambda: self.request_up.emit(self))
        dn_btn = QPushButton()
        ico(dn_btn, IC_DOWN, _dim, 16)
        dn_btn.setFixedSize(28, 28)
        dn_btn.setCursor(Qt.PointingHandCursor)
        dn_btn.setToolTip("Переместить вниз")
        dn_btn.clicked.connect(lambda: self.request_dn.emit(self))
        move_col.addWidget(up_btn)
        move_col.addWidget(dn_btn)
        lay.addLayout(move_col)

        # Превью с кнопками версий
        thumb_row = QHBoxLayout()
        thumb_row.setSpacing(1)

        self.prev_ver_btn = QPushButton("<")
        self.prev_ver_btn.setObjectName("ver_btn")
        self.prev_ver_btn.setFixedSize(18, _THUMB_H)
        self.prev_ver_btn.setCursor(Qt.PointingHandCursor)
        self.prev_ver_btn.setToolTip("Предыдущая версия")
        self.prev_ver_btn.clicked.connect(self._prev_version)
        thumb_row.addWidget(self.prev_ver_btn)

        self.thumb_lbl = QLabel()
        self.thumb_lbl.setObjectName("thumb_lbl")
        self.thumb_lbl.setFixedSize(_THUMB_W, _THUMB_H)
        self.thumb_lbl.setAlignment(Qt.AlignCenter)
        self.thumb_lbl.setText("...")
        self.thumb_lbl.setCursor(QCursor(Qt.PointingHandCursor))
        self.thumb_lbl.setToolTip("Открыть файл")
        self.thumb_lbl.mousePressEvent = lambda _e: self._open_file()
        thumb_row.addWidget(self.thumb_lbl)

        self.next_ver_btn = QPushButton(">")
        self.next_ver_btn.setObjectName("ver_btn")
        self.next_ver_btn.setFixedSize(18, _THUMB_H)
        self.next_ver_btn.setCursor(Qt.PointingHandCursor)
        self.next_ver_btn.setToolTip("Следующая версия")
        self.next_ver_btn.clicked.connect(self._next_version)
        thumb_row.addWidget(self.next_ver_btn)

        lay.addLayout(thumb_row)

        # Инфо
        info = QVBoxLayout()
        info.setSpacing(2)
        self.name_lbl = QLabel(os.path.basename(self._versions[0]))
        self.name_lbl.setObjectName("card_name")
        self.name_lbl.setWordWrap(True)
        self.dur_lbl = QLabel("...")
        self.dur_lbl.setObjectName("label_dim")
        self.ver_lbl = QLabel("")
        self.ver_lbl.setObjectName("card_ver")
        info.addWidget(self.name_lbl)
        info.addWidget(self.dur_lbl)
        info.addWidget(self.ver_lbl)
        info.addStretch()
        lay.addLayout(info, 1)

        # Действия
        actions = QVBoxLayout()
        actions.setSpacing(2)
        add_btn = QPushButton()
        ico(add_btn, IC_FOLDER)
        add_btn.setFixedSize(28, 30)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setToolTip("Загрузить другой файл как новую версию")
        add_btn.clicked.connect(lambda: self.request_add_version.emit(self))
        del_btn = QPushButton()
        ico(del_btn, IC_DELETE)
        del_btn.setFixedSize(28, 30)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setToolTip("Удалить позицию")
        del_btn.clicked.connect(lambda: self.request_remove.emit(self))
        actions.addWidget(add_btn)
        actions.addWidget(del_btn)
        lay.addLayout(actions)

        self._refresh_display()

    def add_version(self, new_path: str):
        self._versions.append(new_path)
        self._current = len(self._versions) - 1
        self._refresh_display()
        self.request_probe.emit(self)

    def _prev_version(self):
        if len(self._versions) < 2:
            return
        self._current = (self._current - 1) % len(self._versions)
        self._refresh_display()
        self._load_cached()

    def _next_version(self):
        if len(self._versions) < 2:
            return
        self._current = (self._current + 1) % len(self._versions)
        self._refresh_display()
        self._load_cached()

    def _refresh_display(self):
        p = self._versions[self._current]
        self.name_lbl.setText(os.path.basename(p))
        n = len(self._versions)
        self.ver_lbl.setText(f"версия {self._current + 1}/{n}" if n > 1 else "")
        self.prev_ver_btn.setEnabled(n > 1)
        self.next_ver_btn.setEnabled(n > 1)

    def _load_cached(self):
        p = self._versions[self._current]
        if p in self._thumb_cache:
            self.thumb_lbl.setPixmap(self._thumb_cache[p])
            self.thumb_lbl.setText("")
        else:
            self.thumb_lbl.clear()
            self.thumb_lbl.setText("...")
            self.request_probe.emit(self)
        if p in self._dur_cache:
            self.dur_lbl.setText(_fmt(self._dur_cache[p]))
        else:
            self.dur_lbl.setText("...")

    def receive_thumb(self, path: str, pm: QPixmap | None):
        if pm:
            self._thumb_cache[path] = pm
        if path == self._versions[self._current]:
            if pm:
                self.thumb_lbl.setPixmap(pm)
                self.thumb_lbl.setText("")
            else:
                self.thumb_lbl.setText("нет")

    def receive_duration(self, path: str, dur: float):
        self._dur_cache[path] = dur
        if path == self._versions[self._current]:
            self.dur_lbl.setText(_fmt(dur))

    def _open_file(self):
        p = self._versions[self._current]
        if os.path.exists(p):
            os.startfile(p)

    @property
    def path(self) -> str:
        return self._versions[self._current]


class TabClip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sig = _Sig()
        self._sig.finished.connect(self._on_finished)
        self._sig.progress.connect(self._on_progress)
        self._sig.log_line.connect(self._append_log)
        self._sig.dur_ready.connect(self._on_dur_ready)
        self._sig.thumb_ready.connect(self._on_thumb_ready)
        self._running = False
        self._durations: dict[str, float] = {}
        self._media_cards: list[_MediaCard] = []
        self._build()
        self._load_state()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Левая панель: треки + настройки + лог ─────────
        left_w = QWidget()
        left_w.setObjectName("clip_left_panel")
        left = QVBoxLayout(left_w)
        left.setContentsMargins(12, 10, 12, 10)
        left.setSpacing(8)
        root.addWidget(left_w, 1)

        left.addLayout(self._build_tracks_panel())

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        left.addWidget(sep)

        left.addLayout(self._build_settings_block())

        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine)
        left.addWidget(sep2)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        left.addWidget(self.progress_bar)

        self.log_box = QTextEdit()
        self.log_box.setObjectName("clip_log")
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(80)
        left.addWidget(self.log_box, 1)

        bot = QHBoxLayout()
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("label_dim")
        bot.addWidget(self.status_lbl, 1)

        self.open_btn = QPushButton(" Открыть папку")
        ico(self.open_btn, IC_FOLDER)
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.clicked.connect(self._on_open_output)
        bot.addWidget(self.open_btn)

        self.render_btn = QPushButton(" Смонтировать")
        ico(self.render_btn, IC_PLAY)
        self.render_btn.setObjectName("accent_btn")
        self.render_btn.setCursor(Qt.PointingHandCursor)
        self.render_btn.clicked.connect(self._on_render)
        bot.addWidget(self.render_btn)
        left.addLayout(bot)

        # ── Разделитель ───────────────────────────────────
        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        root.addWidget(vline)

        # ── Правая панель: только видеоряд ────────────────
        right_w = QWidget()
        right_w.setObjectName("clip_right_panel")
        right = QVBoxLayout(right_w)
        right.setContentsMargins(12, 10, 12, 10)
        right.setSpacing(6)
        root.addWidget(right_w, 1)

        right.addLayout(self._build_media_panel())

    def _build_tracks_panel(self) -> QVBoxLayout:
        v = QVBoxLayout()
        v.setSpacing(6)

        # Строка: [Треки] [stretch] [Длина: —] [stretch] [Добавить]
        hdr = QHBoxLayout()
        lbl = QLabel("Треки")
        lbl.setObjectName("panel_title")
        hdr.addWidget(lbl)
        hdr.addStretch()
        self.track_total_lbl = QLabel("Длина: —")
        self.track_total_lbl.setObjectName("label_dim")
        hdr.addWidget(self.track_total_lbl)
        hdr.addStretch()
        add_t = QPushButton(" Добавить")
        ico(add_t, IC_FOLDER)
        add_t.setMinimumWidth(110)
        add_t.setCursor(Qt.PointingHandCursor)
        add_t.clicked.connect(self._on_add_tracks)
        hdr.addWidget(add_t)
        v.addLayout(hdr)

        self.track_list = QListWidget()
        self.track_list.setMinimumHeight(140)
        self.track_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.track_list.model().rowsMoved.connect(self._recalc)
        v.addWidget(self.track_list)

        # Строка: [↑] [↓] [🗑] [stretch] [Разрешение:] [combo]
        btns = QHBoxLayout()
        btns.setSpacing(4)
        for icon, tip, fn in [
            (IC_PREV,   "Вверх",   lambda: self._move_track(-1)),
            (IC_NEXT,   "Вниз",    lambda: self._move_track(1)),
            (IC_DELETE, "Удалить", self._del_track),
        ]:
            b = QPushButton()
            ico(b, icon)
            b.setFixedWidth(32)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            btns.addWidget(b)
        btns.addStretch()
        btns.addWidget(QLabel("Разрешение:"))
        self.res_combo = QComboBox()
        self.res_combo.setMinimumWidth(145)
        for val, label in [
            ("1920x1080", "1920x1080 Full HD"),
            ("1280x720",  "1280x720 HD"),
            ("1080x1920", "1080x1920 Reels"),
            ("1080x1080", "1080x1080 Square"),
        ]:
            self.res_combo.addItem(label, val)
        btns.addWidget(self.res_combo)
        v.addLayout(btns)

        return v

    def _build_media_panel(self) -> QVBoxLayout:
        v = QVBoxLayout()
        v.setSpacing(6)

        # Заголовок + Очистить + Добавить — всё в одну строку
        hdr = QHBoxLayout()
        lbl = QLabel("Видеоряд")
        lbl.setObjectName("panel_title")
        hdr.addWidget(lbl)
        hdr.addStretch()

        clr_btn = QPushButton(" Очистить")
        ico(clr_btn, IC_REFRESH)
        clr_btn.setMinimumWidth(100)
        clr_btn.setCursor(Qt.PointingHandCursor)
        clr_btn.clicked.connect(self._clear_media)
        hdr.addWidget(clr_btn)

        add_m = QPushButton(" Добавить")
        ico(add_m, IC_FOLDER)
        add_m.setMinimumWidth(100)
        add_m.setCursor(Qt.PointingHandCursor)
        add_m.clicked.connect(self._on_add_media)
        hdr.addWidget(add_m)
        v.addLayout(hdr)

        self.media_scroll = QScrollArea()
        self.media_scroll.setWidgetResizable(True)
        self.media_scroll.setFrameShape(QFrame.NoFrame)

        self._cards_widget = QWidget()
        self._cards_widget.setObjectName("media_cards_bg")
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setSpacing(4)
        self._cards_layout.setContentsMargins(2, 2, 2, 2)
        self._cards_layout.addStretch()

        self.media_scroll.setWidget(self._cards_widget)
        v.addWidget(self.media_scroll, 1)

        self.media_cover_lbl = QLabel("Добавь видеофрагменты")
        self.media_cover_lbl.setObjectName("label_dim")
        self.media_cover_lbl.setWordWrap(True)
        v.addWidget(self.media_cover_lbl)
        return v

    def _build_settings_block(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(QLabel("Переход:"))
        self.trans_combo = QComboBox()
        self.trans_combo.setMinimumWidth(100)
        for val, lbl in [
            ("fade",      "Fade"),
            ("dissolve",  "Dissolve"),
            ("wipeleft",  "Wipe Left"),
            ("wiperight", "Wipe Right"),
            ("pixelize",  "Pixelize"),
            ("hblur",     "HBlur"),
            ("none",      "Нет"),
        ]:
            self.trans_combo.addItem(lbl, val)
        row.addWidget(self.trans_combo)

        row.addSpacing(6)
        row.addWidget(QLabel("Длит.:"))
        self.trans_dur = QDoubleSpinBox()
        self.trans_dur.setRange(0.1, 2.0)
        self.trans_dur.setSingleStep(0.1)
        self.trans_dur.setValue(0.5)
        self.trans_dur.setSuffix(" с")
        self.trans_dur.setFixedWidth(68)
        row.addWidget(self.trans_dur)

        row.addSpacing(6)
        row.addWidget(QLabel("Fade in:"))
        self.fade_in = QDoubleSpinBox()
        self.fade_in.setRange(0, 10)
        self.fade_in.setValue(0.5)
        self.fade_in.setSuffix(" с")
        self.fade_in.setFixedWidth(68)
        row.addWidget(self.fade_in)

        row.addWidget(QLabel("Fade out:"))
        self.fade_out = QDoubleSpinBox()
        self.fade_out.setRange(0, 10)
        self.fade_out.setValue(0.5)
        self.fade_out.setSuffix(" с")
        self.fade_out.setFixedWidth(68)
        row.addWidget(self.fade_out)
        row.addStretch()
        return row

    # ── Треки ─────────────────────────────────────────────

    def _on_add_tracks(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Выбрать треки", "",
            "Аудио (*.mp3 *.wav *.ogg *.m4a *.flac);;Все файлы (*)"
        )
        for p in paths:
            item = QListWidgetItem(f"{os.path.basename(p)}  —  ...")
            item.setData(Qt.UserRole, p)
            item.setToolTip(p)
            self.track_list.addItem(item)
            threading.Thread(target=self._probe_bg, args=(p,), daemon=True).start()
        self._recalc()
        self._save_state()

    def _move_track(self, delta: int):
        row = self.track_list.currentRow()
        if row < 0:
            return
        new = row + delta
        if new < 0 or new >= self.track_list.count():
            return
        item = self.track_list.takeItem(row)
        self.track_list.insertItem(new, item)
        self.track_list.setCurrentRow(new)
        self._recalc()
        self._save_state()

    def _del_track(self):
        row = self.track_list.currentRow()
        if row >= 0:
            self.track_list.takeItem(row)
            self._recalc()
            self._save_state()

    def _track_paths(self) -> list[str]:
        return [self.track_list.item(i).data(Qt.UserRole)
                for i in range(self.track_list.count())]

    # ── Медиа (карточки) ──────────────────────────────────

    def _on_add_media(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Выбрать видеофрагменты", "",
            "Видео (*.mp4 *.mov *.mkv *.avi *.webm);;Все файлы (*)"
        )
        for p in paths:
            self._add_media_card(p)
        self._recalc()
        self._save_state()

    def _add_media_card(self, path: str):
        card = _MediaCard(path)
        card.request_up.connect(self._on_card_up)
        card.request_dn.connect(self._on_card_dn)
        card.request_add_version.connect(self._on_card_add_version)
        card.request_remove.connect(self._on_card_remove)
        card.request_probe.connect(self._on_card_probe)
        insert_pos = self._cards_layout.count() - 1
        self._cards_layout.insertWidget(insert_pos, card)
        self._media_cards.append(card)
        threading.Thread(target=self._load_card_bg, args=(path,), daemon=True).start()

    def _load_card_bg(self, path: str):
        dur = _probe_duration(path)
        pm  = _make_thumb(path)
        self._sig.dur_ready.emit(path, dur)
        self._sig.thumb_ready.emit(path, pm)

    def _on_card_probe(self, card: _MediaCard):
        threading.Thread(
            target=self._load_card_bg, args=(card.path,), daemon=True
        ).start()

    def _on_card_up(self, card: _MediaCard):
        idx = self._media_cards.index(card)
        if idx <= 0:
            return
        self._media_cards.pop(idx)
        self._media_cards.insert(idx - 1, card)
        self._rebuild_cards_layout()
        self._recalc()
        self._save_state()

    def _on_card_dn(self, card: _MediaCard):
        idx = self._media_cards.index(card)
        if idx >= len(self._media_cards) - 1:
            return
        self._media_cards.pop(idx)
        self._media_cards.insert(idx + 1, card)
        self._rebuild_cards_layout()
        self._recalc()
        self._save_state()

    def _on_card_add_version(self, card: _MediaCard):
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузить версию", "",
            "Видео (*.mp4 *.mov *.mkv *.avi *.webm);;Все файлы (*)"
        )
        if not path:
            return
        card.add_version(path)
        threading.Thread(target=self._load_card_bg, args=(path,), daemon=True).start()
        self._recalc()

    def _on_card_remove(self, card: _MediaCard):
        if card in self._media_cards:
            self._media_cards.remove(card)
        card.setParent(None)
        card.deleteLater()
        self._recalc()
        self._save_state()

    def _clear_media(self):
        from PySide6.QtWidgets import QMessageBox
        mb = QMessageBox(self)
        mb.setWindowTitle("Очистить видеоряд?")
        mb.setText("Удалить все видеофрагменты из списка?")
        mb.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        mb.setDefaultButton(QMessageBox.No)
        mb.button(QMessageBox.Yes).setText("Очистить")
        mb.button(QMessageBox.No).setText("Отмена")
        if mb.exec() != QMessageBox.Yes:
            return
        for card in list(self._media_cards):
            card.setParent(None)
            card.deleteLater()
        self._media_cards.clear()
        self._recalc()
        self._save_state()

    def _rebuild_cards_layout(self):
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        for card in self._media_cards:
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

    def _media_paths(self) -> list[str]:
        return [c.path for c in self._media_cards]

    # ── Длительности и превью ─────────────────────────────

    def _probe_bg(self, path: str):
        dur = _probe_duration(path)
        self._sig.dur_ready.emit(path, dur)

    def _on_dur_ready(self, path: str, dur: float):
        self._durations[path] = dur
        for i in range(self.track_list.count()):
            item = self.track_list.item(i)
            if item.data(Qt.UserRole) == path:
                item.setText(f"{os.path.basename(path)}  —  {_fmt(dur)}")
        for card in self._media_cards:
            card.receive_duration(path, dur)
        self._recalc()

    def _on_thumb_ready(self, path: str, pm):
        for card in self._media_cards:
            card.receive_thumb(path, pm)

    # ── Пересчёт статуса ──────────────────────────────────

    def _recalc(self):
        track_paths = self._track_paths()
        track_dur = sum(self._durations.get(p, 0.0) for p in track_paths)

        if not track_paths:
            self.track_total_lbl.setText("Длина: —")
        else:
            self.track_total_lbl.setText(f"Общая длина: {_fmt(track_dur)}")

        media_paths = self._media_paths()
        n = len(media_paths)

        if n == 0:
            self._set_cover("dim", "Добавь видеофрагменты")
            return

        media_dur = sum(self._durations.get(p, 0.0) for p in media_paths)
        if track_dur <= 0:
            self._set_cover("dim", f"{n} фрагментов, ~{_fmt(media_dur)}")
        elif media_dur >= track_dur:
            self._set_cover("ok", f"{n} фрагментов, {_fmt(media_dur)}  — покрывает трек ({_fmt(track_dur)})")
        else:
            cycles = int(track_dur / media_dur) + 1 if media_dur > 0 else "?"
            self._set_cover("dim",
                f"{n} фрагментов, {_fmt(media_dur)}  — не хватает, зациклится (~{cycles}x)")

    def _set_cover(self, kind: str, text: str):
        obj = {"ok": "label_ok", "dim": "label_dim", "err": "label_err"}.get(kind, "label_dim")
        self.media_cover_lbl.setObjectName(obj)
        self.media_cover_lbl.setText(text)
        self.media_cover_lbl.style().polish(self.media_cover_lbl)

    # ── Рендер ────────────────────────────────────────────

    def _on_render(self):
        if self._running:
            return

        tracks = self._track_paths()
        media  = self._media_paths()

        if not tracks:
            self._set_status("err", "Добавь хотя бы один трек")
            return
        if not media:
            self._set_status("err", "Добавь видеофрагменты")
            return
        for p in tracks + media:
            if not os.path.exists(p):
                self._set_status("err", f"Файл не найден: {os.path.basename(p)}")
                return

        w, h = map(int, self.res_combo.currentData().split("x"))
        settings = {
            "width":          w,
            "height":         h,
            "fps":            25,
            "transition":     self.trans_combo.currentData(),
            "trans_duration": self.trans_dur.value(),
            "fade_in":        self.fade_in.value(),
            "fade_out":       self.fade_out.value(),
            "track_swoosh":   "",
        }

        output_dir = str(_OUTPUT_DIR)
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        self._running = True
        self.render_btn.setEnabled(False)
        self.log_box.clear()
        self.progress_bar.setValue(0)
        self._set_status("", "Монтирую клип...")
        threading.Thread(
            target=self._run_render, args=(tracks, media, settings, output_dir), daemon=True
        ).start()

    def _run_render(self, tracks, media, settings, output_dir):
        from src.clip_render import render_clip
        ok, result = render_clip(
            tracks=tracks,
            media_items=media,
            settings=settings,
            output_dir=output_dir,
            on_log=lambda msg: self._sig.log_line.emit(msg),
            on_progress=lambda v: self._sig.progress.emit(v),
        )
        self._sig.finished.emit(ok, result)

    def _on_finished(self, ok: bool, result: str):
        self._running = False
        self.render_btn.setEnabled(True)
        if ok:
            self._set_status("ok", f"Готово: {os.path.basename(result)}")
        else:
            self._set_status("err", result)

    def _on_progress(self, val: int):
        self.progress_bar.setValue(val)

    def _append_log(self, msg: str):
        self.log_box.append(msg)
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def _on_open_output(self):
        if _OUTPUT_DIR.exists():
            os.startfile(str(_OUTPUT_DIR))

    def _set_status(self, kind: str, text: str):
        obj = {"ok": "label_ok", "err": "label_err"}.get(kind, "label_dim")
        self.status_lbl.setObjectName(obj)
        self.status_lbl.setText(text)
        self.status_lbl.style().polish(self.status_lbl)

    # ── Сохранение/загрузка состояния ────────────────────

    def _save_state(self):
        s = state.load()
        s["clip"] = {
            "tracks": self._track_paths(),
            "media":  self._media_paths(),
            "trans":  self.trans_combo.currentData(),
            "trans_dur": self.trans_dur.value(),
            "fade_in":   self.fade_in.value(),
            "fade_out":  self.fade_out.value(),
            "resolution": self.res_combo.currentData(),
        }
        state.save(s)

    def _load_state(self):
        s = state.load()
        clip = s.get("clip", {})

        for p in clip.get("tracks", []):
            if os.path.exists(p):
                item = QListWidgetItem(f"{os.path.basename(p)}  —  ...")
                item.setData(Qt.UserRole, p)
                item.setToolTip(p)
                self.track_list.addItem(item)
                threading.Thread(target=self._probe_bg, args=(p,), daemon=True).start()

        for p in clip.get("media", []):
            if os.path.exists(p):
                self._add_media_card(p)

        trans = clip.get("trans", "fade")
        idx = self.trans_combo.findData(trans)
        if idx >= 0:
            self.trans_combo.setCurrentIndex(idx)

        self.trans_dur.setValue(clip.get("trans_dur", 0.5))
        self.fade_in.setValue(clip.get("fade_in", 0.5))
        self.fade_out.setValue(clip.get("fade_out", 0.5))

        res = clip.get("resolution", "1920x1080")
        idx = self.res_combo.findData(res)
        if idx >= 0:
            self.res_combo.setCurrentIndex(idx)

        self._recalc()
