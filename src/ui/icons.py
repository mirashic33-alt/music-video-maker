from PySide6.QtGui import QIcon, QPixmap, QPainter, QFont, QColor
from PySide6.QtCore import Qt, QSize

# Segoe MDL2 Assets — коды через chr() чтобы не зависеть от кодировки файла
IC_DELETE   = chr(0xE74D)  # trash
IC_REFRESH  = chr(0xECC5)  # sync
IC_FOLDER   = chr(0xED25)  # open folder
IC_SAVE     = chr(0xE74E)  # save
IC_SETTINGS = chr(0xE713)  # gear
IC_PLAY     = chr(0xE768)  # play
IC_STOP     = chr(0xE71A)  # stop
IC_PREV     = chr(0xE76B)  # chevron left (вверх по списку)
IC_NEXT     = chr(0xE76C)  # chevron right (вниз по списку)
IC_COPY     = chr(0xE8C8)  # copy
IC_CHECK    = chr(0xE73E)  # checkmark
IC_UP       = chr(0xE70E)  # chevron up
IC_DOWN     = chr(0xE70D)  # chevron down

ICON_SIZE = 18


def mdl2(char: str, color: str = None, px_size: int = ICON_SIZE) -> QIcon:
    """Render a Segoe MDL2 Assets character into a QIcon."""
    if color is None:
        from src.theme import current as _t
        color = _t().get("text", "#D0CEC8")
    scale = 2
    buf = px_size * scale
    pm = QPixmap(buf, buf)
    pm.fill(Qt.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setFont(QFont("Segoe MDL2 Assets", int(buf * 0.7)))
    p.setPen(QColor(color))
    p.drawText(pm.rect(), Qt.AlignCenter, char)
    p.end()

    pm.setDevicePixelRatio(scale)
    return QIcon(pm)


def apply(btn, char: str, color: str = None, size: int = ICON_SIZE):
    """Set Segoe MDL2 icon on a button."""
    btn.setIcon(mdl2(char, color, size))
    btn.setIconSize(QSize(size, size))
