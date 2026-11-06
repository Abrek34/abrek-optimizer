"""Performans ölçümleri (psutil + sysfs)."""
from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import psutil


@dataclass
class Snapshot:
    cpu_percent: float = 0.0
    cpu_per_core: list[float] = field(default_factory=list)
    cpu_freq_mhz: float = 0.0
    cpu_temp_c: float = 0.0
    mem_percent: float = 0.0
    mem_used: int = 0
    mem_total: int = 0
    mem_available: int = 0
    swap_percent: float = 0.0
    swap_used: int = 0
    swap_total: int = 0
    disk_percent: float = 0.0
    disk_used: int = 0
    disk_total: int = 0
    disk_read: int = 0
    disk_write: int = 0
    net_sent: int = 0
    net_recv: int = 0
    load_avg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    boot_time: float = 0.0
    process_count: int = 0
    gpu_busy: float = 0.0      # 0-100
    gpu_temp_c: float = 0.0
    gpu_mem_used: int = 0       # bytes
    gpu_mem_total: int = 0
    gpu_name: str = ""


# psutil cpu_percent ilk çağrıda 0 döner; modül yüklendiğinde prime et
psutil.cpu_percent(interval=None)
psutil.cpu_percent(interval=None, percpu=True)
# process iter cpu_percent için de prime
for _p in psutil.process_iter():
    try:
        _p.cpu_percent(interval=None)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


def _read_int(path: str) -> int:
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return 0


def _cpu_temp() -> float:
    """coretemp / k10temp / zenpower'dan ana CPU sıcaklığını al."""
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return 0.0
    for key in ("coretemp", "k10temp", "zenpower", "amdgpu", "cpu_thermal", "acpitz"):
        if key in temps and temps[key]:
            for t in temps[key]:
                if t.label in ("Package id 0", "Tctl", "Tdie", "") or "Package" in (t.label or ""):
                    if t.current:
                        return float(t.current)
            return float(temps[key][0].current or 0.0)
    return 0.0


def _gpu_info() -> tuple[float, float, int, int, str]:
    """(busy%, temp_c, mem_used, mem_total, name) — AMD/Intel sysfs, NVIDIA nvidia-smi."""
    busy = temp = 0.0
    mem_u = mem_t = 0
    name = ""

    # AMD / Intel: /sys/class/drm/card*/device/
    for card in sorted(Path("/sys/class/drm").glob("card[0-9]")):
        dev = card / "device"
        if not dev.exists():
            continue
        # busy%
        b = dev / "gpu_busy_percent"
        if b.exists():
            try:
                busy = float(b.read_text().strip())
            except (OSError, ValueError):
                pass
        # vram
        u = dev / "mem_info_vram_used"
        t = dev / "mem_info_vram_total"
        if u.exists() and t.exists():
            mem_u = _read_int(str(u))
            mem_t = _read_int(str(t))
        # sıcaklık (hwmon)
        for hw in (dev / "hwmon").glob("hwmon*") if (dev / "hwmon").exists() else []:
            for tf in hw.glob("temp*_input"):
                try:
                    val = int(tf.read_text().strip()) / 1000.0
                    if val > temp:
                        temp = val
                except (OSError, ValueError):
                    pass
        if busy or mem_t:
            break

    # NVIDIA
    if shutil.which("nvidia-smi") and not busy:
        try:
            out = subprocess.run(
                ["nvidia-smi",
                 "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total,name",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=2,
            ).stdout.strip().splitlines()
            if out:
                parts = [x.strip() for x in out[0].split(",")]
                if len(parts) >= 5:
                    busy = float(parts[0] or 0)
                    temp = float(parts[1] or 0)
                    mem_u = int(float(parts[2] or 0)) * 1024 * 1024  # MiB → B
                    mem_t = int(float(parts[3] or 0)) * 1024 * 1024
                    name = parts[4]
        except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
            pass

    return busy, temp, mem_u, mem_t, name


# Disk I/O delta (önceki snapshot'la karşılaştır)
_prev_disk = psutil.disk_io_counters()


def snapshot() -> Snapshot:
    global _prev_disk
    s = Snapshot()
    s.cpu_percent = psutil.cpu_percent(interval=None)
    s.cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
    try:
        f = psutil.cpu_freq()
        s.cpu_freq_mhz = f.current if f else 0.0
    except (FileNotFoundError, OSError):
        pass
    s.cpu_temp_c = _cpu_temp()

    vm = psutil.virtual_memory()
    s.mem_percent = vm.percent
    s.mem_used = vm.used
    s.mem_total = vm.total
    s.mem_available = vm.available

    sw = psutil.swap_memory()
    s.swap_percent = sw.percent
    s.swap_used = sw.used
    s.swap_total = sw.total

    du = psutil.disk_usage("/")
    s.disk_percent = du.percent
    s.disk_used = du.used
    s.disk_total = du.total

    cur = psutil.disk_io_counters()
    if cur and _prev_disk:
        s.disk_read = max(0, cur.read_bytes - _prev_disk.read_bytes)
        s.disk_write = max(0, cur.write_bytes - _prev_disk.write_bytes)
    _prev_disk = cur

    nio = psutil.net_io_counters()
    s.net_sent = nio.bytes_sent
    s.net_recv = nio.bytes_recv

    try:
        s.load_avg = psutil.getloadavg()
    except (AttributeError, OSError):
        pass

    s.boot_time = psutil.boot_time()
    s.process_count = len(psutil.pids())

    s.gpu_busy, s.gpu_temp_c, s.gpu_mem_used, s.gpu_mem_total, s.gpu_name = _gpu_info()
    return s


def top_processes(by: str = "memory", n: int = 15) -> list[dict]:
    """En çok kaynak kullanan süreçleri döner."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "memory_percent", "cpu_percent", "memory_info"]):
        try:
            info = p.info
            info["memory_percent"] = info.get("memory_percent") or 0.0
            info["cpu_percent"] = info.get("cpu_percent") or 0.0
            mi = info.get("memory_info")
            info["rss"] = mi.rss if mi else 0
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    key = "memory_percent" if by == "memory" else "cpu_percent"
    procs.sort(key=lambda x: x.get(key, 0.0), reverse=True)
    return procs[:n]


def uptime_seconds() -> int:
    return int(time.time() - psutil.boot_time())


def format_uptime(seconds: int) -> str:
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, _ = divmod(r, 60)
    if d:
        return f"{d}g {h}s {m}d"
    if h:
        return f"{h}s {m}d"
    return f"{m}d"
