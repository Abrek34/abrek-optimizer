"""Sistem durumu tespiti (read-only)."""
from __future__ import annotations

import contextlib
import os
import re
import subprocess
from pathlib import Path

from ._helpers import _C_ENV, _read, _run, has, pkg_installed
from .models import Status


def _detect_cpu() -> tuple[str, str, str]:
    vendor = model = driver = ""
    try:
        txt = Path("/proc/cpuinfo").read_text()
        for line in txt.splitlines():
            if line.startswith("vendor_id") and not vendor:
                vendor = line.split(":", 1)[1].strip()
            elif line.startswith("model name") and not model:
                model = line.split(":", 1)[1].strip()
            if vendor and model:
                break
    except OSError:
        pass
    driver = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver")
    return vendor, model, driver


def _detect_gpu() -> tuple[str, str]:
    out = _run(["lspci", "-mm"]).lower()
    vendor = ""
    name = ""
    for line in out.splitlines():
        if " vga " in line or "3d controller" in line or "display controller" in line:
            if "nvidia" in line:
                vendor = "NVIDIA"
            elif "amd" in line or "advanced micro devices" in line or "ati" in line:
                vendor = "AMD"
            elif "intel" in line:
                vendor = "Intel"
            # tırnak içindeki ürün adını kabaca al
            m = re.findall(r'"([^"]+)"', line)
            if len(m) >= 4:
                name = m[3]
            break
    return vendor, name


def _systemctl_state(unit: str) -> str:
    r = subprocess.run(
        ["systemctl", "is-active", unit], capture_output=True, text=True, env=_C_ENV,
    )
    s = (r.stdout or "").strip()
    if not s:
        return "missing"
    return s  # active / inactive / failed / unknown


def _scx_running() -> str:
    """Çalışan scx scheduler adını döner ('' = yok)."""
    cur = _read("/sys/kernel/sched_ext/root/ops")
    if cur:
        return cur
    # alternatif: process arama
    for name in ("scx_bpfland", "scx_lavd", "scx_rusty", "scx_rustland", "scx_simple", "scx_flash"):
        if subprocess.run(["pgrep", "-x", name], capture_output=True, env=_C_ENV).returncode == 0:
            return name
    return ""


def _detect_amd_x3d() -> tuple[str, str]:
    """(mode, path) — AMD 3D V-Cache modu. 6.13+ kernelinde driver yolu değişti."""
    candidates = [
        Path("/sys/bus/platform/drivers/amd_x3d_vcache"),
        Path("/sys/bus/wmi/drivers/amd_x3d_vcache"),
    ]
    for base in candidates:
        if not base.exists():
            continue
        for p in base.glob("*/amd_x3d_mode"):
            try:
                txt = p.read_text().strip()
                m = re.search(r"\[(\w+)\]", txt)
                return (m.group(1) if m else txt), str(p)
            except OSError:
                continue
    return "", ""


def _zram_size() -> int:
    """Toplam zram disksize (bytes)."""
    total = 0
    for p in Path("/sys/block").glob("zram*/disksize"):
        with contextlib.suppress(OSError, ValueError):
            total += int(p.read_text().strip() or 0)
    return total


def _detect_desktop_env() -> str:
    de = os.environ.get("XDG_CURRENT_DESKTOP", "")
    if de:
        return de
    return os.environ.get("DESKTOP_SESSION", "")


def _pipewire_rt_active() -> bool:
    """PipeWire daemon RT priority alıyor mu?"""
    try:
        r = subprocess.run(
            ["pgrep", "-x", "pipewire"],
            capture_output=True, text=True, env=_C_ENV,
        )
        if not r.stdout.strip():
            return False
        pid = r.stdout.strip().splitlines()[0]
        sched = Path(f"/proc/{pid}/sched").read_text(errors="ignore")
        # SCHED_FIFO veya SCHED_RR varsa RT
        return "SCHED_FIFO" in sched or "SCHED_RR" in sched or "policy=1" in sched or "policy=2" in sched
    except (OSError, subprocess.SubprocessError):
        return False


def read_status() -> Status:
    st = Status()
    st.kernel = _run(["uname", "-r"]).strip()
    st.is_cachyos_kernel = "cachyos" in st.kernel
    if st.is_cachyos_kernel and has("pacman"):
        out = _run(["pacman", "-Qq"])
        for line in out.splitlines():
            if line.startswith("linux-cachyos"):
                st.cachyos_kernel_pkg = line
                break

    st.cpu_vendor, st.cpu_model, st.cpu_driver = _detect_cpu()
    st.cpu_governor = _read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    st.epp = _read("/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference")

    # power-profiles-daemon
    if has("powerprofilesctl"):
        st.power_profile = _run(["powerprofilesctl", "get"]).strip()

    # sched-ext
    st.scx_running = _scx_running()
    if has("systemctl"):
        st.scx_loader_service = _systemctl_state("scx_loader.service")
        st.scx_loader_active = st.scx_loader_service == "active"
        st.ananicy_service = _systemctl_state("ananicy-cpp.service")
        if st.ananicy_service == "missing":
            st.ananicy_service = _systemctl_state("ananicy.service")
        st.irqbalance_service = _systemctl_state("irqbalance.service")
        st.ppd_service = _systemctl_state("power-profiles-daemon.service")

    # Ağ
    st.tcp_cc = _read("/proc/sys/net/ipv4/tcp_congestion_control")
    st.tcp_qdisc = _run(["sysctl", "-n", "net.core.default_qdisc"]).strip()

    # Bellek
    with contextlib.suppress(ValueError):
        st.swappiness = int(_read("/proc/sys/vm/swappiness") or 60)
    with contextlib.suppress(ValueError):
        st.vm_max_map_count = int(_read("/proc/sys/vm/max_map_count") or 0)
    thp = _read("/sys/kernel/mm/transparent_hugepage/enabled")
    m = re.search(r"\[(\w+)\]", thp)
    st.thp = m.group(1) if m else thp

    # zram / zswap
    st.zram_size = _zram_size()
    st.zram_active = st.zram_size > 0
    st.zswap_enabled = _read("/sys/module/zswap/parameters/enabled").upper() == "Y"

    # GPU
    st.gpu_vendor, st.gpu_name = _detect_gpu()
    st.amd_x3d_mode, st.amd_x3d_path = _detect_amd_x3d()

    # mitigations / split-lock
    cmdline = _read("/proc/cmdline")
    st.mitigations_off = "mitigations=off" in cmdline
    m = re.search(r"split_lock_detect=(\w+)", cmdline)
    st.split_lock_detect = m.group(1) if m else ""

    # Masaüstü ortamı
    st.compositor = os.environ.get("XDG_SESSION_TYPE", "") or "unknown"
    st.desktop_env = _detect_desktop_env()

    # PipeWire RT
    st.pipewire_rt = _pipewire_rt_active()

    # Paketler
    st.has_gamemode = has("gamemoded") or pkg_installed("gamemode")
    st.has_gamescope = has("gamescope") or pkg_installed("gamescope")
    st.has_mangohud = has("mangohud") or pkg_installed("mangohud")
    st.has_game_performance = has("game-performance")
    st.has_scx_loader = has("scx_loader") or pkg_installed("scx-scheds")
    st.has_cachyos_gaming_meta = pkg_installed("cachyos-gaming-meta")
    st.has_cachyos_gaming_apps = pkg_installed("cachyos-gaming-applications")
    st.has_proton_cachyos = pkg_installed("proton-cachyos") or pkg_installed("proton-cachyos-slr")
    st.has_ananicy_cpp = pkg_installed("ananicy-cpp") or has("ananicy-cpp")
    st.has_irqbalance = pkg_installed("irqbalance") or has("irqbalance")
    st.has_cpupower = has("cpupower")
    st.has_qdbus = has("qdbus6") or has("qdbus")

    return st
