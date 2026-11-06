"""Paket adından uygulama ikonu çözümleyici.

Strateji:
  1. Bir kez sistem genelinde tüm .desktop dosyalarını paket sahipliği ile eşleştir.
     - pacman:  'pacman -Qo <files>'  →  "<path> is owned by <pkg> <ver>"
     - dpkg:    'dpkg-query -S <files>'
     - rpm:     'rpm -qf --queryformat ... <files>'
  2. Her .desktop'tan Icon= değerini çıkar.
  3. icon_for_package() → QIcon.fromTheme(...) → /usr/share/pixmaps fallback.

Eski sürümdeki HATA: 'pacman -Qoq' kullanılıyordu; orphan dosyalar atlandığı için
zip(desktops, owners) sırası kayıyor ve yanlış ikonlar eşleşiyordu
(örn: firefox → org.cachyos.KernelManager). Şimdi 'pacman -Qo' ile her satırda
hem dosya hem paket geliyor, parse ediliyor.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QIcon


# Tüm alt-süreçler için İngilizce çıktı zorla — Türkçe locale'da
# 'is owned by' yerine 'paketine ait' yazıyor; regex bozulur.
_C_ENV = {**os.environ, "LC_ALL": "C", "LANG": "C", "LANGUAGE": "C"}


_DESKTOP_DIRS = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path.home() / ".local/share/flatpak/exports/share/applications",
]

_PIXMAPS = [
    Path("/usr/share/pixmaps"),
    Path("/usr/share/icons/hicolor/256x256/apps"),
    Path("/usr/share/icons/hicolor/128x128/apps"),
    Path("/usr/share/icons/hicolor/scalable/apps"),
]

# {pkg_name: icon_name_or_path}
_pkg_to_icon: dict[str, str] = {}
# .desktop'lardan toplanan icon isimleri seti (paket adıyla benzeyene düşmek için)
_all_icon_names: set[str] = set()
_index_built = False


# ----------------------------- desktop parse -----------------------------

def _read_icon_from_desktop(path: Path) -> str:
    """Sadece [Desktop Entry] section'ından Icon= değerini al."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return ""
    in_main = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            in_main = s == "[Desktop Entry]"
            continue
        if in_main and s.startswith("Icon="):
            return s.split("=", 1)[1].strip()
    return ""


# ----------------------------- paket-dosya eşleştirme -----------------------------

# Örn: '/usr/share/applications/firefox.desktop is owned by firefox 142.0-1'
_PACMAN_QO_RE = re.compile(r"^(.+?) is owned by (\S+)\s")


def _scan_pacman(desktops: list[Path]) -> None:
    if not shutil.which("pacman"):
        return
    files = [str(p) for p in desktops if str(p).startswith("/usr")]
    if not files:
        return
    # Çok uzun argümanları parçalara böl (ARG_MAX güvenliği)
    CHUNK = 200
    for i in range(0, len(files), CHUNK):
        chunk = files[i:i + CHUNK]
        r = subprocess.run(
            ["pacman", "-Qo", *chunk],
            capture_output=True, text=True, timeout=30, env=_C_ENV,
        )
        # stdout ve stderr birlikte; orphan dosyalar stderr'e gider, biz stdout'u alıyoruz
        for line in r.stdout.splitlines():
            m = _PACMAN_QO_RE.match(line)
            if not m:
                continue
            path, pkg = m.group(1), m.group(2)
            # path sonunda virgül olabilir: '/path, pkg ver'
            path = path.rstrip(",")
            icon = _read_icon_from_desktop(Path(path))
            if icon and pkg not in _pkg_to_icon:
                _pkg_to_icon[pkg] = icon


def _scan_dpkg(desktops: list[Path]) -> None:
    if not shutil.which("dpkg-query"):
        return
    files = [str(p) for p in desktops if str(p).startswith("/usr")]
    if not files:
        return
    CHUNK = 200
    for i in range(0, len(files), CHUNK):
        chunk = files[i:i + CHUNK]
        r = subprocess.run(
            ["dpkg-query", "-S", *chunk],
            capture_output=True, text=True, timeout=30, env=_C_ENV,
        )
        for line in r.stdout.splitlines():
            # "pkg[:arch]: /path"
            if ": " not in line:
                continue
            head, path = line.rsplit(": ", 1)
            pkg = head.split(",")[0].split(":")[0].strip()
            icon = _read_icon_from_desktop(Path(path.strip()))
            if pkg and icon and pkg not in _pkg_to_icon:
                _pkg_to_icon[pkg] = icon


def _scan_rpm(desktops: list[Path]) -> None:
    if not shutil.which("rpm"):
        return
    for d in desktops:
        if not str(d).startswith("/usr"):
            continue
        r = subprocess.run(
            ["rpm", "-qf", "--queryformat", "%{NAME}\n", str(d)],
            capture_output=True, text=True, env=_C_ENV,
        )
        if r.returncode != 0:
            continue
        pkg = r.stdout.strip().split("\n", 1)[0]
        if not pkg or pkg.startswith("file "):  # "file ... is not owned"
            continue
        icon = _read_icon_from_desktop(d)
        if icon and pkg not in _pkg_to_icon:
            _pkg_to_icon[pkg] = icon


def _scan_user_desktops(desktops: list[Path]) -> None:
    """~/.local/share/applications altındaki ikonları paket adıyla eşitle.
    Bu dosyaların paket sahibi yoktur; desktop dosyasının ID'sini paket ismi olarak
    kullanmaya çalışırız (heuristic)."""
    for d in desktops:
        if str(d).startswith("/usr") or str(d).startswith("/var"):
            continue
        icon = _read_icon_from_desktop(d)
        if not icon:
            continue
        _all_icon_names.add(icon)
        # Bazı tipik isim eşleşmeleri (paket adı = desktop stem)
        candidate = d.stem.lower().split(".")[-1]
        _pkg_to_icon.setdefault(candidate, icon)


def _build_index() -> None:
    global _index_built
    if _index_built:
        return
    _index_built = True

    desktops: list[Path] = []
    for d in _DESKTOP_DIRS:
        if d.exists():
            desktops.extend(d.glob("*.desktop"))
    if not desktops:
        return

    if shutil.which("pacman"):
        _scan_pacman(desktops)
    elif shutil.which("dpkg-query"):
        _scan_dpkg(desktops)
    elif shutil.which("rpm"):
        _scan_rpm(desktops)

    _scan_user_desktops(desktops)

    # Tüm toplanan ikon isimlerini sete koy (paket adıyla benzerlik araması için)
    _all_icon_names.update(_pkg_to_icon.values())


def build_index_now() -> int:
    """İndexi açıkça oluştur; eşleşen paket sayısını döner. Arka plan thread'inde
    çağrılması önerilir."""
    _build_index()
    return len(_pkg_to_icon)


# ----------------------------- public API -----------------------------

@lru_cache(maxsize=8192)
def icon_name_for_package(pkg: str) -> str:
    """Paket için en uygun ikon ismini döner (boş string olabilir)."""
    if not _index_built:
        _build_index()

    # 1) Doğrudan eşleşme
    if pkg in _pkg_to_icon:
        return _pkg_to_icon[pkg]

    # 2) Heuristic eşlemeler (yaygın isim varyasyonları)
    lower = pkg.lower()
    for variant in (
        lower,
        lower.replace("-bin", ""),
        lower.replace("-git", ""),
        lower.replace("-stable", ""),
        lower.replace("-beta", ""),
        lower.split("-")[0],  # firefox-developer-edition → firefox
    ):
        if variant and variant in _pkg_to_icon:
            return _pkg_to_icon[variant]

    # 3) Paket adı tema simgesiyle aynı isimde olabilir
    return pkg


@lru_cache(maxsize=8192)
def icon_for_package(pkg: str) -> QIcon:
    """Paket için QIcon döner. Bulamazsa boş QIcon."""
    name = icon_name_for_package(pkg)
    if not name:
        return QIcon()

    # Mutlak yol mu?
    if name.startswith("/") and Path(name).exists():
        return QIcon(name)

    # Tema (HiColor / kullanıcının teması)
    ic = QIcon.fromTheme(name)
    if not ic.isNull():
        return ic

    # /usr/share/pixmaps fallback (raw dosya)
    for d in _PIXMAPS:
        for ext in (".png", ".svg", ".svgz", ".xpm"):
            p = d / f"{name}{ext}"
            if p.exists():
                return QIcon(str(p))
    return QIcon()


@lru_cache(maxsize=8192)
def icon_from_name(name: str) -> QIcon:
    """Desktop Icon= değerinden QIcon döner."""
    if not name:
        return QIcon()
    if name.startswith("/") and Path(name).exists():
        return QIcon(name)
    ic = QIcon.fromTheme(name)
    if not ic.isNull():
        return ic
    stem = Path(name).stem if Path(name).suffix else name
    for d in _PIXMAPS:
        for ext in (".png", ".svg", ".svgz", ".xpm"):
            p = d / f"{stem}{ext}"
            if p.exists():
                return QIcon(str(p))
    return QIcon()


def clear_cache() -> None:
    """Cache'i sıfırla (örn. paket kurulduktan sonra)."""
    global _index_built
    _pkg_to_icon.clear()
    _all_icon_names.clear()
    _index_built = False
    icon_name_for_package.cache_clear()
    icon_for_package.cache_clear()
    icon_from_name.cache_clear()
