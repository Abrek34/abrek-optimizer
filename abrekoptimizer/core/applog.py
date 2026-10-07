"""Uygulama log altyapısı — hem stderr'e hem dosyaya yazar."""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


_LOG_DIR = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "abrek"
_LOG_FILE = _LOG_DIR / "abrek.log"


_configured = False


def configure(level: int = logging.INFO) -> Path:
    """Logging'i kur, log dosyasının yolunu döner. Çoklu çağrı no-op."""
    global _configured
    if _configured:
        return _LOG_FILE
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    root = logging.getLogger("abrekoptimizer")
    root.setLevel(level)
    root.handlers.clear()

    # Dosya (rotasyonlu)
    fh = RotatingFileHandler(_LOG_FILE, maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # stderr
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    _configured = True
    root.info("=== Abrek Optimizer başlatıldı ===")
    return _LOG_FILE


def get(name: str) -> logging.Logger:
    if not _configured:
        configure()
    return logging.getLogger(f"abrekoptimizer.{name}")


def log_path() -> Path:
    return _LOG_FILE
