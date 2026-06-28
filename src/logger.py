import logging
from pathlib import Path

_LOG_FILE = Path(__file__).parent.parent / "songbird.log"
_logger: logging.Logger | None = None
_status_callback = None


def register_status_callback(fn) -> None:
    global _status_callback
    _status_callback = fn


class _StatusBarHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if _status_callback:
            try:
                _status_callback(record.levelno, record.getMessage())
            except Exception:
                pass


def _clip_log(file_path: Path, max_lines: int = 100):
    if not file_path.exists():
        return
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        if len(lines) > max_lines:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"--- LOG CLIPPED (kept last {max_lines} lines) ---\n")
                f.writelines(lines[-max_lines:])
    except Exception:
        pass


def get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    _clip_log(_LOG_FILE, 100)

    _logger = logging.getLogger("SongBird")
    _logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    _logger.addHandler(fh)
    _logger.addHandler(_StatusBarHandler())

    return _logger


def status_text(msg: str, limit: int = 80) -> str:
    return msg if len(msg) <= limit else msg[:limit - 1] + "…"
