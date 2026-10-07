"""Abrek Optimizer işlem geçmişi (JSONL)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

_STATE_DIR = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "abrek"
HISTORY_FILE = _STATE_DIR / "history.jsonl"


def record(action: str, detail: str = "", ok: bool = True) -> None:
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = {"ts": time.time(), "action": action, "detail": detail, "ok": ok}
        with HISTORY_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def entries(limit: int = 200) -> list[dict]:
    try:
        lines = HISTORY_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for ln in reversed(lines[-limit:]):
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out
