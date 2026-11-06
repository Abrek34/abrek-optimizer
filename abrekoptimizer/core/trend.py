"""Sağlık skoru / disk kullanımı trend kaydı (JSONL, saatte bir örnek)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

_STATE_DIR = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "abrek"
TREND_FILE = _STATE_DIR / "trend.jsonl"
_MIN_INTERVAL = 3600  # saniye


def record_sample(score: int, disk_used: int = 0, mem_used: int = 0) -> bool:
    """En fazla saatte bir kayıt ekler; eklendiyse True döner."""
    try:
        now = time.time()
        if TREND_FILE.exists():
            lines = TREND_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
            if lines:
                try:
                    last = json.loads(lines[-1])
                    if now - last.get("ts", 0) < _MIN_INTERVAL:
                        return False
                except ValueError:
                    pass
        TREND_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = {"ts": now, "score": score, "disk_used": disk_used, "mem_used": mem_used}
        with TREND_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return True
    except OSError:
        return False


def samples(limit: int = 24) -> list[dict]:
    try:
        lines = TREND_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-limit:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out
