import json
from pathlib import Path

_STATE_FILE = Path(__file__).parent.parent / "state.json"
_THEMES_DIR = Path(__file__).parent.parent / "themes"

# Дефолтная янтарная тема
_DEFAULTS = {
    "bg":      "#0D0A06",
    "panel":   "#171209",
    "input":   "#211A0E",
    "text":    "#EDE8DC",
    "border":  "#4A3C18",
    "btn":     "#241A0A",
    "btn_hov": "#38260E",
    "btn_prs": "#4A3318",
    "accent":  "#D4920A",
    "dim":     "#7A6A50",
    "err":     "#E05050",
    "ok":      "#5CB85C",
    "radius":  4,
}


def _map(raw: dict) -> dict:
    t = dict(_DEFAULTS)
    if "bg_color"            in raw: t["bg"]      = raw["bg_color"]
    if "chat_bg"             in raw: t["panel"]   = raw["chat_bg"]
    if "input_bg"            in raw: t["input"]   = raw["input_bg"]
    if "text_color"          in raw: t["text"]    = raw["text_color"]
    if "border_color"        in raw: t["border"]  = raw["border_color"]
    if "button_bg"           in raw: t["btn"]     = raw["button_bg"]
    if "button_hover_bg"     in raw: t["btn_hov"] = raw["button_hover_bg"]
    if "button_pressed_bg"   in raw: t["btn_prs"] = raw["button_pressed_bg"]
    if "accent_color"        in raw: t["accent"]  = raw["accent_color"]
    elif "bubble_prefix_color" in raw: t["accent"] = raw["bubble_prefix_color"]
    if "bubble_prefix_color" in raw: t["dim"]     = raw["bubble_prefix_color"]
    # border_radius из темы игнорируем — везде фиксированные 4px
    return t


_CURRENT: dict = {}


def set_current(t: dict):
    global _CURRENT
    _CURRENT = t


def current() -> dict:
    return _CURRENT if _CURRENT else load_theme()


def load_theme() -> dict:
    try:
        state = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        path = state.get("theme_path", "")
        if path and Path(path).exists():
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            return _map(raw)
    except Exception:
        pass
    return dict(_DEFAULTS)


def build_qss(t: dict | None = None) -> str:
    if t is None:
        t = load_theme()

    from pathlib import Path as _P
    _CHECK_SVG = str(_P(__file__).parent.parent / "img" / "check.svg").replace("\\", "/")

    BG       = t["bg"]
    PANEL    = t["panel"]
    INPUT_BG = t["input"]
    TEXT     = t["text"]
    BORDER   = t["border"]
    BTN      = t["btn"]
    BTN_HOV  = t["btn_hov"]
    BTN_PRS  = t["btn_prs"]
    ACCENT   = t["accent"]
    DIM      = t["dim"]
    ERR      = t["err"]
    OK       = t["ok"]
    RADIUS   = t["radius"]

    return f"""
* {{
    font-family: 'Segoe UI', sans-serif;
}}

QMainWindow, QDialog {{
    background: {BG};
}}

QWidget#root_widget {{
    background: {BG};
}}

/* ── Вкладки ── */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-top: none;
    border-radius: {RADIUS}px;
    background: {PANEL};
    padding: 2px;
}}

QTabBar::tab {{
    background: {BTN};
    color: {DIM};
    border: 1px solid {BORDER};
    border-radius: 0;
    border-top-left-radius: {RADIUS}px;
    border-top-right-radius: {RADIUS}px;
    padding: 6px 18px;
    font-size: 13px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {PANEL};
    color: {TEXT};
    border-bottom: 1px solid {PANEL};
}}
QTabBar::tab:hover:!selected {{
    background: {BTN_HOV};
    color: {TEXT};
}}

/* ── Текстовые поля ── */
QTextEdit, QLineEdit {{
    background: {INPUT_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 6px 10px;
    font-size: 13px;
    selection-background-color: {BTN_HOV};
}}
QTextEdit:focus, QLineEdit:focus {{
    border-color: {ACCENT};
}}

/* ── Выпадающий список ── */
QComboBox {{
    background: {INPUT_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 4px 10px;
    font-size: 13px;
    min-height: 24px;
}}
QComboBox:hover {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox::down-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {DIM};
    width: 0; height: 0;
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background: {INPUT_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    selection-background-color: {BTN_HOV};
    outline: none;
}}

/* ── Кнопки ── */
QPushButton {{
    background: {BTN};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 3px 14px;
    font-size: 13px;
    min-height: 23px;
}}
QPushButton:hover   {{ background: {BTN_HOV}; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {BTN_PRS}; }}
QPushButton:disabled {{ background: {BG}; color: {DIM}; border-color: {BORDER}; }}

/* ── Акцент-кнопка ── */
QPushButton#accent_btn {{
    background: {BTN};
    color: {ACCENT};
    border: 1px solid {BORDER};
    font-size: 13px;
    font-weight: 600;
    padding: 4px 12px;
}}
QPushButton#accent_btn:hover   {{ background: {BTN_HOV}; border-color: {ACCENT}; }}
QPushButton#accent_btn:pressed {{ background: {BTN_PRS}; }}
QPushButton#accent_btn:disabled {{ color: {DIM}; }}

/* ── Список ── */
QListWidget {{
    background: {INPUT_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 4px;
    font-size: 13px;
    outline: none;
}}
QListWidget::item {{ padding: 6px 8px; border-radius: 3px; }}
QListWidget::item:selected {{ background: {BTN_HOV}; color: {TEXT}; }}
QListWidget::item:hover {{ background: {BTN_HOV}; }}

/* ── Разделители ── */
QFrame[frameShape="4"] {{
    border: none;
    background: {BORDER};
    max-height: 1px;
}}
QFrame[frameShape="5"] {{
    border: none;
    background: {BORDER};
    max-width: 1px;
}}

/* ── Строка статуса ── */
QStatusBar {{
    background: {BG};
    color: {DIM};
    font-size: 12px;
    border-top: 1px solid {BORDER};
    padding: 0 8px;
}}
QStatusBar QLabel {{
    color: {DIM};
    font-size: 12px;
    padding: 0 4px;
}}

/* ── Прогресс-бар ── */
QProgressBar {{
    background: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 3px;
    height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}

/* ── Лейблы ── */
QLabel {{
    color: {TEXT};
    font-size: 13px;
}}
QLabel#label_h1 {{
    font-size: 16px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#label_dim  {{ font-size: 12px; color: {DIM}; }}
QLabel#label_err  {{ font-size: 12px; color: {ERR}; }}
QLabel#label_ok   {{ font-size: 12px; color: {OK};  }}

/* ── ScrollArea ── */
QScrollArea {{
    background: transparent;
    border: none;
}}

/* ── Tooltip ── */
QToolTip {{
    background: {BTN};
    color: {TEXT};
    border: 1px solid {ACCENT};
    border-radius: {RADIUS}px;
    padding: 4px 10px;
    font-size: 12px;
}}

/* ── Чекбокс ── */
QCheckBox {{
    color: {TEXT};
    font-size: 13px;
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1.5px solid {ACCENT};
    border-radius: 3px;
    background: transparent;
}}
QCheckBox::indicator:checked {{
    background: transparent;
    border-color: {ACCENT};
    image: url({_CHECK_SVG});
}}
QCheckBox::indicator:unchecked {{ background: transparent; }}
QCheckBox::indicator:hover   {{ border-color: {ACCENT}; }}

/* ── Радиокнопка ── */
QRadioButton {{
    color: {TEXT};
    font-size: 13px;
    spacing: 6px;
}}
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER};
    border-radius: 7px;
    background: {INPUT_BG};
}}
QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

/* ── Спинбокс ── */
QSpinBox, QDoubleSpinBox {{
    background: {INPUT_BG};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 4px 8px;
    font-size: 13px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 16px;
    border: none;
    background: {BTN};
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {BTN_HOV};
}}

/* ── ScrollBar ── */
QScrollBar:vertical {{
    background: {BG};
    width: 8px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {BG};
    height: 8px;
    border: none;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 4px;
    min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Таб-бар контейнер ── */
QWidget#tab_bar_container {{
    background: {BG};
}}

/* ── Главная ── */
QWidget#home_bar {{
    background: {BG};
    border-top: 1px solid {BORDER};
}}
QLabel#home_img     {{ background: {BG}; }}
QLabel#home_counter {{ color: {DIM}; font-size: 12px; min-width: 40px; }}
QLabel#home_title   {{ color: {ACCENT}; letter-spacing: 2px; }}
QLabel#home_name    {{ color: {DIM}; font-size: 11px; }}
QPushButton#home_nav_btn {{
    background: transparent;
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}
QPushButton#home_nav_btn:hover {{ background: {BTN_HOV}; border-color: {ACCENT}; }}

/* ── YouTube ── */
QLabel#section_title {{
    color: {ACCENT};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#yt_checklist {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 12px 16px;
    color: {DIM};
    font-size: 12px;
}}

/* ── Клип: общие заголовки панелей ── */
QLabel#panel_title {{
    font-weight: bold;
    font-size: 13px;
    color: {TEXT};
}}
QPushButton#ver_btn {{
    background: {BTN};
    border: 1px solid {BORDER};
    color: {DIM};
    font-size: 11px;
    padding: 0px;
}}
QLabel#thumb_lbl {{
    background: {BG};
    border: 1px solid {BORDER};
    color: {DIM};
    font-size: 11px;
}}
QLabel#card_ver {{ color: {ACCENT}; font-size: 10px; }}
QLabel#card_name {{ color: {TEXT}; font-size: 12px; }}

/* ── Строка статуса ── */
QLabel#status_log {{ color: {DIM}; font-size: 11px; }}
QLabel#status_err {{ color: {ERR}; font-size: 11px; padding-right: 8px; }}

/* ── Клип: панели ── */
QWidget#clip_left_panel {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}
QWidget#clip_right_panel {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}
QWidget#media_cards_bg {{
    background: {PANEL};
}}
QWidget#media_card {{
    background: {BTN};
    border-radius: {RADIUS}px;
}}
QTextEdit#clip_log {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    font-family: Consolas, monospace;
    font-size: 11px;
    color: {TEXT};
}}
"""


# Совместимость с прежним импортом `from src.theme import QSS`
QSS = build_qss()
