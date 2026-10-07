"""XDG autostart (.desktop) ve systemd kullanıcı servisleri yönetimi."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AutostartEntry:
    name: str
    path: Path
    exec_cmd: str
    enabled: bool
    comment: str = ""
    source: str = "xdg"      # xdg | systemd
    icon: str = ""           # .desktop'taki Icon= değeri


def _parse_desktop(p: Path) -> AutostartEntry | None:
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    name = exec_cmd = comment = icon = ""
    hidden = False
    enabled_key = True
    in_main = False
    only_show_in: list[str] = []
    not_show_in: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            in_main = s == "[Desktop Entry]"
            continue
        if not in_main or "=" not in s or s.startswith("#"):
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        v = v.strip()
        # 'Name[tr]=...' gibi locale anahtarlarını da yakala
        base_k = k.split("[")[0]
        if base_k == "Name" and (not name or "[" in k):
            # Locale-spesifik isim varsa onu tercih et
            if "[" in k or not name:
                name = v
        elif base_k == "Exec":
            exec_cmd = v
        elif base_k == "Comment" and (not comment or "[" in k):
            if "[" in k or not comment:
                comment = v
        elif base_k == "Icon":
            icon = v
        elif k == "Hidden":
            hidden = v.lower() == "true"
        elif k == "X-GNOME-Autostart-enabled":
            enabled_key = v.lower() != "false"
        elif k == "OnlyShowIn":
            only_show_in = [x.strip() for x in v.rstrip(";").split(";") if x.strip()]
        elif k == "NotShowIn":
            not_show_in = [x.strip() for x in v.rstrip(";").split(";") if x.strip()]

    # OnlyShowIn / NotShowIn — entry mevcut DE'de gerçekten çalışacak mı?
    # (sadece raporlama amaçlı; kullanıcı görsün diye comment'a ekle)
    if only_show_in or not_show_in:
        de_info = []
        if only_show_in:
            de_info.append(f"Yalnızca: {','.join(only_show_in)}")
        if not_show_in:
            de_info.append(f"Hariç: {','.join(not_show_in)}")
        comment = (comment + "  [" + " | ".join(de_info) + "]") if comment else " | ".join(de_info)

    return AutostartEntry(
        name=name or p.stem,
        path=p,
        exec_cmd=exec_cmd,
        enabled=(not hidden) and enabled_key,
        comment=comment,
        icon=icon,
        source="xdg",
    )


def list_xdg_autostart(dirs: list[Path] | None = None) -> list[AutostartEntry]:
    # XDG precedence: user entries shadow system defaults.
    if dirs is None:
        dirs = [
            Path("/etc/xdg/autostart"),
            Path.home() / ".config/autostart",
        ]
    entries: dict[str, AutostartEntry] = {}
    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.glob("*.desktop"):
            e = _parse_desktop(f)
            if e:
                # Kullanıcı dizini sistem tanımını gölgeler
                entries[f.name] = e
    return sorted(entries.values(), key=lambda x: x.name.lower())


def set_xdg_enabled(entry: AutostartEntry, enabled: bool) -> Path:
    """Kullanıcı autostart'ında Hidden flag'i ayarlar (sistem dosyasını da gölgeleyebilir).

    UTF-8 ile okur/yazar (Türkçe karakter koruma).
    """
    user_dir = Path.home() / ".config/autostart"
    user_dir.mkdir(parents=True, exist_ok=True)
    target = user_dir / entry.path.name
    if not target.exists():
        target.write_text(
            entry.path.read_text(encoding="utf-8", errors="replace"),
            encoding="utf-8",
        )
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[str] = []
    seen_hidden = False
    in_main = False
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            if in_main and not seen_hidden:
                out.append(f"Hidden={'false' if enabled else 'true'}")
                seen_hidden = True
            in_main = s == "[Desktop Entry]"
            out.append(line)
            continue
        if in_main and s.startswith("Hidden="):
            out.append(f"Hidden={'false' if enabled else 'true'}")
            seen_hidden = True
        else:
            out.append(line)
    if in_main and not seen_hidden:
        out.append(f"Hidden={'false' if enabled else 'true'}")
    target.write_text("\n".join(out) + "\n", encoding="utf-8")
    return target


def remove_user_override(entry: AutostartEntry) -> bool:
    """Kullanıcı autostart override dosyasını sil (sistem default'una geri dön).
    Sadece ~/.config/autostart altındaki dosyayı siler."""
    user_target = Path.home() / ".config/autostart" / entry.path.name
    if user_target.exists() and user_target.is_file():
        user_target.unlink()
        return True
    return False


def list_systemd_user_units() -> list[AutostartEntry]:
    if not _has("systemctl"):
        return []
    res = subprocess.run(
        ["systemctl", "--user", "list-unit-files", "--type=service", "--no-legend", "--no-pager"],
        capture_output=True, text=True, check=False,
    )
    entries = []
    for line in res.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        unit, state = parts[0], parts[1]
        entries.append(
            AutostartEntry(
                name=unit,
                path=Path(unit),
                exec_cmd="",
                enabled=state in ("enabled", "enabled-runtime", "static", "alias"),
                comment=state,
                source="systemd",
            )
        )
    return entries


def set_systemd_enabled(unit: str, enabled: bool) -> subprocess.CompletedProcess:
    cmd = ["systemctl", "--user", "enable" if enabled else "disable", unit]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _has(name: str) -> bool:
    from shutil import which
    return which(name) is not None
