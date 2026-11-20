"""Sistem durumu anlık görüntüsü (snapshot) ve geri yükleme.

Optimizasyon uygulamadan önce mevcut ayarları kaydeder; geri yükleme
komutları üreterek kullanıcıyı uygulama öncesi duruma döndürür.

Kaydedilen alanlar:
  - CPU governor, EPP, güç profili (PPD)
  - Swappiness, THP, vm.max_map_count
  - TCP congestion control, default qdisc
  - scx scheduler (çalışan)
  - KWin AllowTearing, LatencyPolicy (KDE ise)
  - Abrek sysctl konfigürasyonu (içerik)
  - zram durumu (aktif/pasif)
"""
from __future__ import annotations

import contextlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from abrekoptimizer.core import gameopt as go

_STATE_DIR = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "abrek"
SNAPSHOT_DIR = _STATE_DIR / "snapshots"


@dataclass
class SystemSnapshot:
    """Uygulama öncesi sistem durumunu temsil eder."""
    name: str
    created_at: float = field(default_factory=time.time)
    # CPU & güç
    cpu_governor: str = ""
    epp: str = ""
    power_profile: str = ""
    # Bellek
    swappiness: int = 60
    thp: str = "madvise"
    vm_max_map_count: int = 65530
    # Ağ
    tcp_cc: str = "cubic"
    tcp_qdisc: str = "fq_codel"
    # Scheduler
    scx_running: str = ""
    # GPU / KWin
    kwin_allow_tearing: str = ""
    kwin_latency_policy: str = ""
    # sysctl abrek config
    abrek_sysctl_conf: str = ""
    abrek_sysctl_bak: str = ""
    # zram
    zram_active: bool = False
    # meta
    kernel: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SystemSnapshot:
        fields = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in fields})


def _snapshot_path(name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return SNAPSHOT_DIR / f"{safe}.json"


def capture(name: str = "", notes: str = "") -> SystemSnapshot:
    """Mevcut sistem durumunu yakala ve diske kaydet. name boşsa zaman damgası kullan."""
    if not name:
        name = time.strftime("snapshot_%Y%m%d_%H%M%S")
    st = go.read_status()
    snap = SystemSnapshot(
        name=name,
        notes=notes,
        cpu_governor=st.cpu_governor,
        epp=st.epp,
        power_profile=st.power_profile,
        swappiness=st.swappiness,
        thp=st.thp,
        vm_max_map_count=st.vm_max_map_count,
        tcp_cc=st.tcp_cc,
        tcp_qdisc=st.tcp_qdisc,
        scx_running=st.scx_running,
        kernel=st.kernel,
        zram_active=st.zram_active,
    )
    # KWin ayarlarını oku (varsa)
    try:
        import subprocess
        kwc = "kreadconfig6" if __import__("shutil").which("kreadconfig6") else "kreadconfig5"
        r = subprocess.run(
            [kwc, "--file", "kwinrc", "--group", "Compositing", "--key", "AllowTearing"],
            capture_output=True, text=True, timeout=3,
        )
        snap.kwin_allow_tearing = r.stdout.strip()
        r2 = subprocess.run(
            [kwc, "--file", "kwinrc", "--group", "Compositing", "--key", "LatencyPolicy"],
            capture_output=True, text=True, timeout=3,
        )
        snap.kwin_latency_policy = r2.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass

    # Abrek sysctl config içeriğini kaydet
    conf = Path("/etc/sysctl.d/99-abrekoptimizer.conf")
    bak = Path("/etc/sysctl.d/99-abrekoptimizer.bak")
    with contextlib.suppress(OSError):
        snap.abrek_sysctl_conf = conf.read_text() if conf.exists() else ""
    with contextlib.suppress(OSError):
        snap.abrek_sysctl_bak = bak.read_text() if bak.exists() else ""

    save(snap)
    return snap


def save(snap: SystemSnapshot) -> Path:
    """Snapshot'ı diske kaydet."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = _snapshot_path(snap.name)
    path.write_text(json.dumps(snap.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load(name: str) -> SystemSnapshot | None:
    """İsme göre snapshot yükle."""
    path = _snapshot_path(name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SystemSnapshot.from_dict(data)
    except (OSError, ValueError, TypeError):
        return None


def list_snapshots() -> list[SystemSnapshot]:
    """Mevcut snapshot'ları (en yeni önce) döner."""
    if not SNAPSHOT_DIR.exists():
        return []
    out: list[SystemSnapshot] = []
    for p in sorted(SNAPSHOT_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append(SystemSnapshot.from_dict(data))
        except (OSError, ValueError, TypeError):
            continue
    return out


def delete(name: str) -> bool:
    """Snapshot dosyasını sil."""
    path = _snapshot_path(name)
    try:
        if path.exists():
            path.unlink()
            return True
    except OSError:
        pass
    return False


def restore_commands(snap: SystemSnapshot) -> list[list[str]]:
    """Snapshot'tan geri yükleme komutları üret.

    Her komut ayrı bir liste olarak döner; UI bunları sırayla çalıştırabilir.
    """
    cmds: list[list[str]] = []

    # CPU governor
    if snap.cpu_governor:
        cmds.append(go.cmd_set_governor(snap.cpu_governor))

    # EPP
    if snap.epp:
        cmds.append(go.cmd_set_epp(snap.epp))

    # Power profile
    if snap.power_profile:
        cmds.append(go.cmd_power_profile(snap.power_profile))

    # Swappiness
    cmds.append(go.cmd_set_swappiness(snap.swappiness, persist=True))

    # THP
    if snap.thp:
        cmds.append(go.cmd_set_thp(snap.thp))

    # vm.max_map_count (varsayılan 65530, ama kaydedilen değeri geri yükle)
    if snap.vm_max_map_count and snap.vm_max_map_count != 65530:
        cmds.append(go.cmd_sysctl({"vm.max_map_count": str(snap.vm_max_map_count)}, persist=True))

    # TCP congestion + qdisc
    if snap.tcp_cc and snap.tcp_cc != "bbr":
        cmds.append(go.cmd_sysctl(
            {"net.ipv4.tcp_congestion_control": snap.tcp_cc,
             "net.core.default_qdisc": snap.tcp_qdisc},
            persist=True,
        ))

    # scx scheduler geri yükleme
    if snap.scx_running:
        cmds.append(go.cmd_scx_set_scheduler(snap.scx_running, "gaming"))
    else:
        cmds.append(go.cmd_scx_stop())

    # KWin AllowTearing
    if snap.kwin_allow_tearing:
        val = snap.kwin_allow_tearing.lower() == "true"
        cmds.append(go.cmd_kwin_allow_tearing(val))

    # KWin LatencyPolicy
    if snap.kwin_latency_policy:
        cmds.append(go.cmd_kwin_latency_policy(snap.kwin_latency_policy))

    # Abrek sysctl config geri yükle
    if snap.abrek_sysctl_conf or snap.abrek_sysctl_bak:
        # Önce mevcut abrek config'i sil, sonra yedeği geri yükle
        restore_script = "sudo rm -f /etc/sysctl.d/99-abrekoptimizer.conf /etc/sysctl.d/99-abrekoptimizer.bak\n"
        if snap.abrek_sysctl_conf:
            import shlex
            restore_script += f"printf '%s' {shlex.quote(snap.abrek_sysctl_conf)} | sudo tee /etc/sysctl.d/99-abrekoptimizer.conf >/dev/null\n"
        if snap.abrek_sysctl_bak:
            import shlex
            restore_script += f"printf '%s' {shlex.quote(snap.abrek_sysctl_bak)} | sudo tee /etc/sysctl.d/99-abrekoptimizer.bak >/dev/null\n"
        # sysctl değerlerini uygula
        if snap.abrek_sysctl_bak:
            restore_script += "sudo sysctl --system >/dev/null 2>&1 || true\n"
        cmds.append(["bash", "-lc", restore_script])

    return cmds


def restore_command_chain(snap: SystemSnapshot) -> list[str]:
    """Geri yükleme komutlarını tek bir bash zincirine çevir (terminal için)."""
    import shlex
    parts = []
    for cmd in restore_commands(snap):
        parts.append(" ".join(shlex.quote(c) for c in cmd))
    return ["bash", "-lc", " ; ".join(parts)] if parts else ["true"]


def format_snapshot(snap: SystemSnapshot) -> str:
    """Snapshot'ı okunabilir metin olarak formatla."""
    import datetime
    ts = datetime.datetime.fromtimestamp(snap.created_at).strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"Snapshot: {snap.name}",
        f"Tarih: {ts}",
        f"Kernel: {snap.kernel}",
        f"Governor: {snap.cpu_governor}",
        f"EPP: {snap.epp or '(yok)'}",
        f"Power profile: {snap.power_profile or '(yok)'}",
        f"Swappiness: {snap.swappiness}",
        f"THP: {snap.thp}",
        f"vm.max_map_count: {snap.vm_max_map_count}",
        f"TCP: {snap.tcp_cc} / {snap.tcp_qdisc}",
        f"SCX: {snap.scx_running or '(kapalı)'}",
        f"zram: {'aktif' if snap.zram_active else 'kapalı'}",
    ]
    if snap.kwin_allow_tearing:
        lines.append(f"KWin AllowTearing: {snap.kwin_allow_tearing}")
    if snap.kwin_latency_policy:
        lines.append(f"KWin LatencyPolicy: {snap.kwin_latency_policy}")
    if snap.notes:
        lines.append(f"Not: {snap.notes}")
    return "\n".join(lines)
