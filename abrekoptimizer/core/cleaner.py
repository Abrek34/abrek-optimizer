"""Cache, log, çöp ve geçici dosya temizleyici."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


# Temizleme sırasında ASLA dokunulmayacak dizinler (veri güvenliği).
PROTECTED_PREFIXES: list[Path] = [
    Path.home() / ".config",
    Path.home() / ".ssh",
    Path.home() / ".gnupg",
    Path.home() / ".pki",
    Path.home() / ".local" / "share" / "keyrings",
    Path.home() / ".mozilla",
    Path.home() / ".steam" / "userdata",
    Path.home() / ".local" / "share" / "Steam" / "userdata",
]


def _is_protected(path: Path) -> bool:
    try:
        real = path.resolve()
    except OSError:
        return True  # çözülemiyorsa riskli kabul et, atla
    for pref in PROTECTED_PREFIXES:
        try:
            real.relative_to(pref.resolve())
            return True
        except ValueError:
            continue
    return False


@dataclass
class CleanTarget:
    label: str
    paths: list[Path] = field(default_factory=list)
    needs_root: bool = False
    description: str = ""

    def size(self) -> int:
        total = 0
        for p in self.paths:
            if not p.exists() and not p.is_symlink():
                continue
            if _is_protected(p):
                continue
            try:
                if p.is_symlink() or p.is_file():
                    # lstat: symlink'in kendisinin boyutunu al, hedefini takip etme
                    total += p.lstat().st_size
                else:
                    for root, _dirs, files in os.walk(p, onerror=lambda e: None, followlinks=False):
                        for f in files:
                            try:
                                total += os.lstat(os.path.join(root, f)).st_size
                            except OSError:
                                pass
            except (OSError, PermissionError):
                pass
        return total

    def clean(self) -> tuple[int, list[str]]:
        """Hedefin içeriğini siler (klasörün kendisini değil). (silinen_byte, hatalar) döner."""
        freed = 0
        errors: list[str] = []
        for p in self.paths:
            if not p.exists() and not p.is_symlink():
                continue
            try:
                if p.is_symlink() or p.is_file():
                    size = p.lstat().st_size
                    p.unlink(missing_ok=True)
                    if not p.exists() and not p.is_symlink():
                        freed += size
                else:
                    for entry in p.iterdir():
                        try:
                            if _is_protected(entry):
                                errors.append(f"{entry}: korumalı dizin, atlandı")
                                continue
                            if entry.is_symlink() or entry.is_file():
                                # lstat: hedef dosya boyutu değil, link'in kendisi
                                size = entry.lstat().st_size
                                entry.unlink()
                                if not entry.exists() and not entry.is_symlink():
                                    freed += size
                            else:
                                size = _dir_size(entry)
                                shutil.rmtree(entry, ignore_errors=True)
                                if not entry.exists():
                                    freed += size
                        except (OSError, PermissionError) as e:
                            errors.append(f"{entry}: {e}")
            except (OSError, PermissionError) as e:
                errors.append(f"{p}: {e}")
        return freed, errors


def _dir_size(path: Path) -> int:
    total = 0
    for root, _d, files in os.walk(path, onerror=lambda e: None, followlinks=False):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def default_targets() -> list[CleanTarget]:
    home = Path.home()
    cache = Path(os.environ.get("XDG_CACHE_HOME") or home / ".cache")
    return [
        CleanTarget(
            "Kullanıcı önbelleği (~/.cache)",
            [cache],
            description="Uygulama önbellek dosyaları. Güvenle silinebilir.",
        ),
        CleanTarget(
            "Çöp kutusu",
            [home / ".local/share/Trash/files", home / ".local/share/Trash/info"],
            description="Çöp kutusundaki dosyalar.",
        ),
        CleanTarget(
            "Thumbnail önbelleği",
            [cache / "thumbnails"],
            description="Resim küçük görsel önbellekleri.",
        ),
        CleanTarget(
            "Tarayıcı önbelleği (Firefox/Chromium)",
            [
                home / ".cache/mozilla",
                home / ".cache/google-chrome",
                home / ".cache/chromium",
                home / ".cache/BraveSoftware",
            ],
            description="Tarayıcılara ait disk önbellekleri.",
        ),
        CleanTarget(
            "Geçici dosyalar (/tmp)",
            [Path("/tmp")],
            needs_root=True,
            description="Sistem geçici klasörü. Açık uygulamalar etkilenebilir.",
        ),
        CleanTarget(
            "Sistem logları (journalctl)",
            [Path("/var/log/journal")],
            needs_root=True,
            description="Sistem günlükleri. journalctl --vacuum kullanır.",
        ),
        CleanTarget(
            "Paket yöneticisi önbelleği",
            [
                Path("/var/cache/pacman/pkg"),
                Path("/var/cache/apt/archives"),
                Path("/var/cache/dnf"),
                Path("/var/cache/zypp"),
            ],
            needs_root=True,
            description="Paket yöneticisinin indirme önbelleği.",
        ),
        # --- Oyun cache hedefleri ---
        CleanTarget(
            "Mesa shader cache",
            [cache / "mesa_shader_cache", cache / "mesa_shader_cache_db"],
            description="Mesa (AMD/Intel) Vulkan/GL shader önbelleği. Silinince ilk açılışta yeniden derlenir.",
        ),
        CleanTarget(
            "NVIDIA shader cache",
            [
                home / ".nv/GLCache",
                home / ".nv/ComputeCache",
                cache / "nvidia",
            ],
            description="NVIDIA GL/CUDA shader önbelleği. Eski sürücüden kalanlar problem yapabilir.",
        ),
        CleanTarget(
            "Steam shader cache",
            [home / ".steam/steam/steamapps/shadercache",
             home / ".local/share/Steam/steamapps/shadercache"],
            description="Steam'in oyun başına Vulkan pipeline cache'i. Büyür; problem yaratırsa silin.",
        ),
        CleanTarget(
            "DXVK / VKD3D shader cache",
            [cache / "dxvk-cache", cache / "vkd3d-proton"],
            description="Wine/Proton DirectX→Vulkan çevirici shader cache'i.",
        ),
        CleanTarget(
            "Discord cache",
            [home / ".config/discord/Cache",
             home / ".config/discord/Code Cache",
             home / ".config/discord/GPUCache"],
            description="Discord uygulamasının disk önbelleği.",
        ),
        CleanTarget(
            "Lutris / Heroic / Bottles cache",
            [cache / "lutris", cache / "heroic", cache / "bottles"],
            description="Oyun launcher'larının önbellekleri.",
        ),
    ]


def vacuum_journal(days: int = 7) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["sudo", "journalctl", f"--vacuum-time={days}d"],
        capture_output=True, text=True, check=False,
    )


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"
