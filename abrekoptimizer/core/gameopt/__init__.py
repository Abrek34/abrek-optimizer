"""Oyun & sistem performans modülü.

Alt modüllere ayrılmış yapı; mevcut API geriye dönük uyumlu olarak re-export edilir.
"""
from ._helpers import _C_ENV, _read, _run, _safe_word, has, pkg_installed, ppd_available_profiles
from .commands import (
    cmd_amd_gpu_perf_level,
    cmd_amd_x3d_mode,
    cmd_disable_service,
    cmd_enable_bbr,
    cmd_enable_service,
    cmd_kwin_allow_tearing,
    cmd_kwin_compositor_resume,
    cmd_kwin_compositor_suspend,
    cmd_kwin_latency_policy,
    cmd_nvidia_max_perf,
    cmd_pipewire_rt,
    cmd_power_profile,
    cmd_revert_sysctl,
    cmd_scx_set_scheduler,
    cmd_scx_stop,
    cmd_set_epp,
    cmd_set_governor,
    cmd_set_swappiness,
    cmd_set_thp,
    cmd_setup_zram,
    cmd_show_sysctl_diff,
    cmd_sysctl,
    install_packages_command,
)
from .detect import read_status
from .models import Recommendation, Status
from .recommendations import recommended_for_competitive_fps

__all__ = [
    "Status", "Recommendation",
    "read_status", "recommended_for_competitive_fps",
    "has", "pkg_installed", "ppd_available_profiles",
    "_run", "_read", "_safe_word", "_C_ENV",
    "cmd_set_governor", "cmd_set_epp", "cmd_power_profile", "cmd_sysctl",
    "cmd_set_swappiness", "cmd_enable_bbr", "cmd_set_thp",
    "cmd_kwin_compositor_suspend", "cmd_kwin_compositor_resume",
    "cmd_kwin_allow_tearing", "cmd_kwin_latency_policy",
    "cmd_amd_x3d_mode", "cmd_nvidia_max_perf", "cmd_amd_gpu_perf_level",
    "cmd_scx_set_scheduler", "cmd_scx_stop",
    "cmd_enable_service", "cmd_disable_service",
    "cmd_pipewire_rt", "cmd_setup_zram", "cmd_revert_sysctl", "cmd_show_sysctl_diff",
    "install_packages_command",
]
