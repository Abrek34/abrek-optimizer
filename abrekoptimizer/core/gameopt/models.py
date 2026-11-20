"""Veri sınıfları."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Status:
    """Sistemden okunan anlık durum (read-only)."""
    kernel: str = ""
    is_cachyos_kernel: bool = False
    cachyos_kernel_pkg: str = ""          # linux-cachyos / -bore / -lts ...
    cpu_vendor: str = ""                   # GenuineIntel / AuthenticAMD
    cpu_model: str = ""
    cpu_driver: str = ""                   # amd-pstate-epp / intel_pstate / acpi-cpufreq
    cpu_governor: str = ""                 # performance / powersave / schedutil
    epp: str = ""                          # amd-pstate-epp tercihi
    power_profile: str = ""                # power-profiles-daemon aktif profili
    scx_running: str = ""                  # scx_bpfland / scx_lavd / ""
    scx_loader_active: bool = False
    tcp_cc: str = ""                       # bbr / cubic / bbr3
    tcp_qdisc: str = ""                    # fq / fq_codel / cake
    swappiness: int = 60
    vm_max_map_count: int = 0
    thp: str = ""                          # transparent_hugepage
    zram_active: bool = False
    zram_size: int = 0                     # bytes
    zswap_enabled: bool = False
    gpu_vendor: str = ""                   # NVIDIA / AMD / Intel
    gpu_name: str = ""
    amd_x3d_mode: str = ""                 # cache / frequency / ""
    amd_x3d_path: str = ""                 # gerçek sysfs yolu
    mitigations_off: bool = False
    split_lock_detect: str = ""            # warn / fatal / off
    compositor: str = ""                   # wayland / x11 / unknown
    desktop_env: str = ""                  # KDE / GNOME / ...
    kwin_triple_buffer: str = ""           # bilinmiyorsa boş
    pipewire_rt: bool = False              # PipeWire RT priority?
    # paketler
    has_gamemode: bool = False
    has_gamescope: bool = False
    has_mangohud: bool = False
    has_game_performance: bool = False     # cachyos-settings içinde
    has_scx_loader: bool = False
    has_cachyos_gaming_meta: bool = False
    has_cachyos_gaming_apps: bool = False
    has_proton_cachyos: bool = False
    has_ananicy_cpp: bool = False
    has_irqbalance: bool = False
    has_cpupower: bool = False
    has_qdbus: bool = False
    # servisler
    scx_loader_service: str = ""           # active/inactive/missing
    ananicy_service: str = ""
    irqbalance_service: str = ""
    ppd_service: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def is_wayland(self) -> bool:
        return self.compositor == "wayland"

    @property
    def is_kde(self) -> bool:
        return "kde" in self.desktop_env.lower() or "plasma" in self.desktop_env.lower()


@dataclass
class Recommendation:
    title: str
    rationale: str
    commands: list[list[str]]
    severity: str = "info"  # info | warn | critical
