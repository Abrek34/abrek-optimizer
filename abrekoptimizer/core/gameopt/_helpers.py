"""Yardımcı fonksiyonlar ve sabitler."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

# İngilizce çıktı zorla — Türkçe locale'da çıktı parsing bozulur
_C_ENV = {**os.environ, "LC_ALL": "C", "LANG": "C", "LANGUAGE": "C"}


def _safe_word(v: str, *, allow: str) -> str:
    import re as _re
    if not _re.fullmatch(allow, v.replace('-', '_')):
        raise ValueError(f"unsafe value: {v!r}")
    return v


def _run(cmd: list[str], timeout: int = 5) -> str:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False, env=_C_ENV,
        )
        return (r.stdout or "") + ("\n" + r.stderr if r.returncode and r.stderr else "")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _read(path: str) -> str:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return ""


def has(bin_name: str) -> bool:
    return shutil.which(bin_name) is not None


def ppd_available_profiles() -> set[str]:
    """power-profiles-daemon'in bu makinedeki geçerli profilleri (örn. {'balanced','power-saver'})."""
    # gameopt paketi üzerinden çağır: testlerde mock.patch.object(gameopt, "_run") ile uyumlu kalsın.
    from abrekoptimizer.core import gameopt as _gameopt
    out = _gameopt._run(["powerprofilesctl", "list"])
    profs = set()
    for line in out.splitlines():
        s = line.strip()
        if s.startswith(":") or s.startswith("*") or (":" in s and s[0].isalpha()):
            name = s.lstrip("* ").split(":", 1)[0]
            if name in ("performance", "balanced", "power-saver"):
                profs.add(name)
    return profs


def pkg_installed(name: str) -> bool:
    """pacman/dpkg/rpm üzerinde paket kurulu mu?"""
    if has("pacman"):
        return subprocess.run(["pacman", "-Q", name], capture_output=True, env=_C_ENV).returncode == 0
    if has("dpkg-query"):
        return subprocess.run(
            ["dpkg-query", "-W", "-f=${Status}", name],
            capture_output=True, text=True, env=_C_ENV,
        ).stdout.startswith("install ok installed")
    if has("rpm"):
        return subprocess.run(["rpm", "-q", name], capture_output=True, env=_C_ENV).returncode == 0
    return False
