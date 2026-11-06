"""Oyun & sistem performans modülü.

CachyOS başta olmak üzere Linux için sistemsel optimizasyonları okur ve uygular.
Kasım 2025 - Mayıs 2026 arası en güncel pratikler temel alındı:

  * sched-ext (scx_bpfland Gaming profili önerilen; scx_lavd'da hybrid CPU bug'ı var)
  * power-profiles-daemon + cpupower
  * AMD P-State EPP, AMD 3D V-Cache mode
  * BBR / BBR3 TCP, fq qdisc
  * zram / zswap, swappiness
  * KWin compositor (Wayland), Explicit Sync
  * cachyos-gaming-meta + cachyos-gaming-applications
  * game-performance (cachyos-settings) ve mangohud
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


# ----------------------------- yardımcılar -----------------------------

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
    out = _run(["powerprofilesctl", "list"])
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


# ----------------------------- veri sınıfları -----------------------------

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


# ----------------------------- okuyucular -----------------------------

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
        try:
            total += int(p.read_text().strip() or 0)
        except (OSError, ValueError):
            pass
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
    try:
        st.swappiness = int(_read("/proc/sys/vm/swappiness") or 60)
    except ValueError:
        pass
    try:
        st.vm_max_map_count = int(_read("/proc/sys/vm/max_map_count") or 0)
    except ValueError:
        pass
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


# ----------------------------- aksiyonlar (komut üreticiler) -----------------------------
#
# Her aksiyon shell-uygun bir komut listesi döner.
# UI bunu run_in_terminal ile çalıştırır; sudo gerekenler terminalde şifre ister.

def cmd_set_governor(g: str) -> list[str]:
    return ["sudo", "cpupower", "frequency-set", "-g", _safe_word(g, allow=r"[A-Za-z0-9_-]+")]


def cmd_set_epp(epp: str) -> list[str]:
    # tüm cpu'lara yaz — değeri whitelist ile doğrula
    epp = _safe_word(epp, allow=r"[A-Za-z0-9_-]+")
    return ["bash", "-lc",
            f"for f in /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference; do "
            f"echo {epp} | sudo tee \"$f\" >/dev/null; done && echo 'EPP -> {epp}'"]


def cmd_power_profile(profile: str) -> list[str]:
    profile = _safe_word(profile, allow=r"[A-Za-z0-9_-]+")
    return ["powerprofilesctl", "set", profile]


def cmd_sysctl(kv: dict[str, str], persist: bool = False) -> list[str]:
    """sysctl ayarlarını uygula. Persist=True ise /etc/sysctl.d/99-abrekoptimizer.conf'a yazar.

    - Aynı key tekrar eklenmez (eski kayıt güncellenir, dosya şişmez).
    - Runtime değerler ilk değişimde /etc/sysctl.d/99-abrekoptimizer.bak'a yedeklenir;
      cmd_revert_sysctl() bu yedeği geri yükleyerek anında eski değere döner.
    """
    for k, v in kv.items():
        _safe_word(k, allow=r"[A-Za-z0-9_.-]+")
        _safe_word(v, allow=r"[A-Za-z0-9_.:+/-]+")
    if not persist:
        runtime = " && ".join(f"sudo sysctl -w {k}={v}" for k, v in kv.items())
        return ["bash", "-lc", runtime]
    # Her key için: (1) yedekte yoksa mevcut runtime değerini sakla,
    # (2) conf'dan eski satırı çıkar, (3) yeni değeri yaz ve runtime uygula.
    body = []
    for k, v in kv.items():
        body.append(
            f'key="{k}"; val="{v}"; '
            'if ! grep -q "^${key}[[:space:]]*=" "$bk" 2>/dev/null; then '
            'prev="$(sysctl -n "$key" 2>/dev/null || true)"; '
            '[ -n "$prev" ] && printf \'%s = %s\\n\' "$key" "$prev" | sudo tee -a "$bk" >/dev/null; fi; '
            'grep -v "^${key}[[:space:]]*=" "$f" 2>/dev/null | sudo tee "$f.tmp" >/dev/null 2>&1 || true; '
            'sudo mv "$f.tmp" "$f" 2>/dev/null || true; '
            'printf \'%s = %s\\n\' "$key" "$val" | sudo tee -a "$f" >/dev/null; '
            'sudo sysctl -w "${key}=${val}" >/dev/null'
        )
    script = (
        "set -e\n"
        "f=/etc/sysctl.d/99-abrekoptimizer.conf\n"
        "bk=/etc/sysctl.d/99-abrekoptimizer.bak\n"
        "sudo touch \"$f\" \"$bk\"\n"
        + "\n".join(body) + "\n"
        "echo 'Ayarlar $f dosyasına kaydedildi (eski değerler $bk içinde yedeklendi).'"
    )
    return ["bash", "-lc", script]


def cmd_set_swappiness(value: int, persist: bool = False) -> list[str]:
    return cmd_sysctl({"vm.swappiness": str(value)}, persist=persist)


def cmd_enable_bbr(persist: bool = True) -> list[str]:
    return cmd_sysctl(
        {"net.core.default_qdisc": "fq",
         "net.ipv4.tcp_congestion_control": "bbr"},
        persist=persist,
    )


def cmd_set_thp(mode: str) -> list[str]:
    # mode: always / madvise / never
    mode = _safe_word(mode, allow=r"[A-Za-z0-9_-]+")
    return ["bash", "-lc",
            f"echo {mode} | sudo tee /sys/kernel/mm/transparent_hugepage/enabled >/dev/null"]


def _qdbus_bin() -> str:
    """KDE 6 ise qdbus6, değilse qdbus."""
    return "qdbus6" if shutil.which("qdbus6") else "qdbus"


def cmd_kwin_compositor_suspend() -> list[str]:
    """X11'de compositing'i kapatır. Wayland'de no-op (compositor zorunlu)."""
    qd = _qdbus_bin()
    return ["bash", "-lc",
            f"if [ \"$XDG_SESSION_TYPE\" = wayland ]; then "
            f"  echo 'UYARI: Wayland oturumunda compositor kapatılamaz (zorunlu). "
            f"AllowTearing veya VRR ile düşük gecikme elde edebilirsiniz.'; "
            f"else "
            f"  {qd} org.kde.KWin /Compositor org.kde.kwin.Compositing.suspend && "
            f"  echo 'Compositor askıya alındı.'; "
            f"fi"]


def cmd_kwin_compositor_resume() -> list[str]:
    qd = _qdbus_bin()
    return ["bash", "-lc",
            f"{qd} org.kde.KWin /Compositor org.kde.kwin.Compositing.resume && "
            f"echo 'Compositor geri açıldı.'"]


def cmd_kwin_allow_tearing(enable: bool) -> list[str]:
    """KWin tearing izni — Wayland'de VRR + low-latency için kritik."""
    val = "true" if enable else "false"
    qd = _qdbus_bin()
    kwc = "kwriteconfig6" if shutil.which("kwriteconfig6") else "kwriteconfig5"
    return ["bash", "-lc",
            f"{kwc} --file kwinrc --group Compositing --key AllowTearing {val} && "
            f"{qd} org.kde.KWin /KWin reconfigure && "
            f"echo 'AllowTearing -> {val}'"]


def cmd_kwin_latency_policy(policy: str = "ExtremelyLow") -> list[str]:
    """KWin LatencyPolicy: ExtremelyLow (en düşük gecikme) / Low / Medium / High / ExtremelyHigh."""
    policy = _safe_word(policy, allow=r"[A-Za-z0-9_-]+")
    qd = _qdbus_bin()
    kwc = "kwriteconfig6" if shutil.which("kwriteconfig6") else "kwriteconfig5"
    return ["bash", "-lc",
            f"{kwc} --file kwinrc --group Compositing --key LatencyPolicy {policy} && "
            f"{qd} org.kde.KWin /KWin reconfigure && "
            f"echo 'LatencyPolicy -> {policy}'"]


def cmd_amd_x3d_mode(mode: str, sysfs_path: str = "") -> list[str]:
    """AMD 3D V-Cache modunu ayarla. mode: cache | frequency"""
    mode = _safe_word(mode, allow=r"[A-Za-z0-9_-]+")
    if sysfs_path:
        import shlex
        return ["bash", "-lc", f"echo {mode} | sudo tee {shlex.quote(sysfs_path)} >/dev/null && echo 'AMD x3d -> {mode}'"]
    # path bilinmiyorsa olası lokasyonları dene
    return ["bash", "-lc",
            f"found=0; for f in /sys/bus/platform/drivers/amd_x3d_vcache/*/amd_x3d_mode "
            f"/sys/bus/wmi/drivers/amd_x3d_vcache/*/amd_x3d_mode; do "
            f"  [ -e \"$f\" ] || continue; "
            f"  echo {mode} | sudo tee \"$f\" >/dev/null; found=1; "
            f"done; "
            f"[ $found = 1 ] && echo 'AMD x3d -> {mode}' || echo 'AMD 3D V-Cache sysfs bulunamadı.'"]


def cmd_nvidia_max_perf() -> list[str]:
    # NVIDIA PowerMizer Prefer Maximum Performance + Force Composition Pipeline kapalı
    return ["bash", "-lc",
            "nvidia-settings -a '[gpu:0]/GPUPowerMizerMode=1' "
            "-a '[gpu:0]/GpuPowerMizerDefaultMode=1' 2>&1 | tail -3"]


def cmd_amd_gpu_perf_level(level: str) -> list[str]:
    # level: auto / low / high / manual
    level = _safe_word(level, allow=r"[A-Za-z0-9_-]+")
    return ["bash", "-lc",
            f"for f in /sys/class/drm/card*/device/power_dpm_force_performance_level; do "
            f"echo {level} | sudo tee \"$f\" >/dev/null 2>&1 || true; done && echo 'AMD GPU -> {level}'"]


def cmd_scx_set_scheduler(name: str, mode: str = "gaming") -> list[str]:
    """scx_loader.toml'a yaz ve servisi yeniden başlat.

    Heredoc kullanılır; aksi halde Python repr içindeki \\n literal yazılır
    ve scx_loader TOML parse hatası verir.
    """
    name = _safe_word(name, allow=r"[A-Za-z0-9_-]+")
    _safe_word(mode, allow=r"[A-Za-z0-9_-]+")
    script = f'''sudo tee /etc/scx_loader.toml >/dev/null <<'EOF'
default_sched = "{name}"
default_mode = "Gaming"

[scheds.{name}]
auto_mode = []
gaming_mode = ["-m", "performance"]
lowlatency_mode = []
powersave_mode = []
EOF
sudo systemctl enable --now scx_loader.service
sudo systemctl restart scx_loader.service
sleep 1
echo
echo "Aktif scheduler:"
cat /sys/kernel/sched_ext/root/ops 2>/dev/null || echo "(scheduler henüz yüklenmedi)"
systemctl status scx_loader.service --no-pager | head -5
'''
    return ["bash", "-lc", script]


def cmd_scx_stop() -> list[str]:
    return ["bash", "-lc",
            "sudo systemctl disable --now scx_loader.service 2>/dev/null; "
            "for s in scx_bpfland scx_lavd scx_rusty scx_rustland scx_flash; do "
            "  sudo pkill -x $s 2>/dev/null; done; echo 'scx kapatıldı.'"]


def cmd_enable_service(unit: str, now: bool = True) -> list[str]:
    unit = _safe_word(unit, allow=r"[A-Za-z0-9_.:@-]+")
    return ["sudo", "systemctl", "enable", "--now" if now else "enable", unit]


def cmd_disable_service(unit: str) -> list[str]:
    unit = _safe_word(unit, allow=r"[A-Za-z0-9_.:@-]+")
    return ["sudo", "systemctl", "disable", "--now", unit]


def cmd_pipewire_rt() -> list[str]:
    """PipeWire kullanıcı servisini RT priority ile yeniden başlat.
    rtkit-daemon zaten kuruluysa otomatik RT verir; bu komut limits.d ekler ve
    gruba ekler."""
    user = os.environ.get("USER", "")
    return ["bash", "-lc",
            f"sudo tee /etc/security/limits.d/95-pipewire-rt.conf >/dev/null <<'EOF'\n"
            f"@audio   - rtprio     95\n"
            f"@audio   - memlock    unlimited\n"
            f"@audio   - nice       -19\n"
            f"EOF\n"
            f"sudo gpasswd -a {user} audio 2>/dev/null || true\n"
            f"systemctl --user restart pipewire pipewire-pulse wireplumber 2>/dev/null || true\n"
            f"echo 'PipeWire RT yapılandırıldı. Yeniden oturum açmanız önerilir.'"]


def cmd_setup_zram() -> list[str]:
    """zram-generator ile RAM'in yarısı kadar lz4 sıkıştırmalı zram kur.

    Takas performansını ciddi artırır; özellikle oyun + düşük RAM'de güvenli.
    """
    if has("pacman"):
        install = "sudo pacman -S --needed --noconfirm zram-generator"
    elif has("apt-get"):
        install = "sudo apt-get install -y zram-generator"
    elif has("dnf"):
        install = "sudo dnf install -y zram-generator"
    elif has("zypper"):
        install = "sudo zypper --non-interactive install zram-generator"
    else:
        return ["bash", "-lc", "echo 'zram-generator için desteklenen paket yöneticisi bulunamadı.'"]
    return ["bash", "-lc",
            f"{install} && \\\n"
            "sudo mkdir -p /etc/systemd && \\\n"
            "sudo tee /etc/systemd/zram-generator.conf >/dev/null <<'EOF'\n"
            "[zram0]\n"
            "zram-size = ram / 2\n"
            "compression-algorithm = lz4\n"
            "EOF\n"
            "sudo systemctl daemon-reload && \\\n"
            "sudo systemctl start systemd-zram-setup@zram0.service && \\\n"
            "echo 'zram kuruldu:' && zramctl"]


def cmd_revert_sysctl() -> list[str]:
    """Abrek Optimizer'un yazdığı sysctl ayarlarını geri al.

    Önce yedekteki orijinal runtime değerleri geri yükler, sonra conf+yedek dosyalarını siler.
    """
    return ["bash", "-lc",
            "f=/etc/sysctl.d/99-abrekoptimizer.conf; bk=/etc/sysctl.d/99-abrekoptimizer.bak\n"
            "if [ -s \"$bk\" ]; then\n"
            "  while IFS='=' read -r key val; do\n"
            "    key=$(echo \"$key\" | xargs); val=$(echo \"$val\" | xargs)\n"
            "    [ -n \"$key\" ] && sudo sysctl -w \"${key}=${val}\" >/dev/null 2>&1 || true\n"
            "  done < \"$bk\"\n"
            "  sudo rm -f \"$bk\"; removed=1\n"
            "fi\n"
            "if [ -f \"$f\" ]; then sudo rm -f \"$f\"; removed=1; fi\n"
            "if [ -n \"${removed:-}\" ]; then\n"
            "  echo 'Abrek Optimizer sysctl ayarları geri alındı; orijinal runtime değerleri yeniden uygulandı.'\n"
            "else\n"
            "  echo 'Geri alınacak ayar yok.'\n"
            "fi"]


def cmd_show_sysctl_diff() -> list[str]:
    """Mevcut sysctl konfigürasyonu göster."""
    return ["bash", "-lc",
            "echo '=== /etc/sysctl.d/99-abrekoptimizer.conf ==='; "
            "[ -f /etc/sysctl.d/99-abrekoptimizer.conf ] && cat /etc/sysctl.d/99-abrekoptimizer.conf || echo '(yok)'; "
            "echo; echo '=== Aktif kritik değerler ==='; "
            "for k in vm.swappiness vm.max_map_count net.ipv4.tcp_congestion_control "
            "net.core.default_qdisc kernel.sched_autogroup_enabled; do "
            "  echo \"$k = $(sysctl -n $k 2>/dev/null)\"; done"]


# -------- Paket kurulum komutları (CachyOS / Arch öncelikli) --------

def install_packages_command(pkgs: list[str]) -> list[str]:
    if has("pacman"):
        return ["sudo", "pacman", "-S", "--needed", "--noconfirm", *pkgs]
    if has("apt"):
        return ["sudo", "apt-get", "install", "-y", *pkgs]
    if has("dnf"):
        return ["sudo", "dnf", "install", "-y", *pkgs]
    if has("zypper"):
        return ["sudo", "zypper", "--non-interactive", "install", *pkgs]
    return ["echo", "Paket yöneticisi bulunamadı"]


# ----------------------------- önerilen profiller -----------------------------

@dataclass
class Recommendation:
    title: str
    rationale: str
    commands: list[list[str]]
    severity: str = "info"  # info | warn | critical


def recommended_for_competitive_fps(st: Status) -> list[Recommendation]:
    """CS2 / Valorant gibi rekabetçi FPS oyunları için sistemsel öneriler.

    Her öneri 'severity' alanı içerir:
      * critical: önemli FPS / gecikme etkisi
      * warn: makul kazanç
      * info: küçük iyileştirme / kalite-yaşam
    """
    recs: list[Recommendation] = []

    # 1) Performance profili (PPD) — CRITICAL (bu makinede varsa)
    _ppd = ppd_available_profiles()
    if ("performance" in _ppd and st.power_profile and st.power_profile != "performance"
            and has("powerprofilesctl")):
        recs.append(Recommendation(
            "Güç profilini 'performance' yap",
            "Düşük gecikme + maksimum frekans. "
            "Oyunda 'game-performance %command%' kullanırsan otomatik aktif olur.",
            [cmd_power_profile("performance")],
            "critical",
        ))
    elif has("powerprofilesctl") and "performance" not in _ppd:
        recs.append(Recommendation(
            "Bu makinede 'performance' güç profili yok",
            "power-profiles-daemon yalnızca 'balanced' ve 'power-saver' sunuyor; "
            "firmware/sürücü desteği olmadığı için 'performance' yok. "
            "Bu durumda CPU governor'ı 'performance' yapmak işe yarar.",
            [],
            "info",
        ))

    # 2) CPU governor — CRITICAL
    if st.cpu_governor and st.cpu_governor not in ("performance",):
        # amd-pstate-epp veya intel_pstate driver'ında 'powersave' EPP ile birleşince OK olur
        # ama yine de FPS dip'lerini azaltmak için performance daha güvenli
        recs.append(Recommendation(
            "CPU governor: performance",
            f"Şu an '{st.cpu_governor}'. 'performance' frekansı sabit yüksekte tutar; "
            "1% low FPS değerlerini iyileştirir.",
            [cmd_set_governor("performance")],
            "critical",
        ))

    # 3) AMD EPP — CRITICAL (amd-pstate-epp ailesi)
    if "amd-pstate" in (st.cpu_driver or "") and st.epp and st.epp != "performance":
        recs.append(Recommendation(
            "AMD EPP: performance",
            f"amd-pstate-epp tercihi şu an '{st.epp}'. 'performance' yapınca CPU clock'ları "
            "oyun süresince yukarıda kalır.",
            [cmd_set_epp("performance")],
            "critical",
        ))

    # 4) Scheduler önerisi — WARN
    if st.has_scx_loader and st.scx_running not in ("scx_bpfland", "scx_lavd"):
        recs.append(Recommendation(
            "scx_bpfland Gaming scheduler",
            "2026/05 itibariyle hybrid CPU'larda en stabil sched-ext seçeneği. "
            "scx_lavd'da bilinen bellek sızıntısı (#3340) var, bpfland tercih et.",
            [cmd_scx_set_scheduler("scx_bpfland", "gaming")],
            "warn",
        ))

    # 5) BBR + fq — WARN (online oyunlar için)
    if st.tcp_cc not in ("bbr", "bbr3"):
        recs.append(Recommendation(
            "TCP BBR + fq qdisc (online oyun gecikmesi)",
            f"Şu an '{st.tcp_cc or 'bilinmiyor'}'. BBR + fq paket jitter'ı azaltır; "
            "CS2 / Valorant gibi rekabetçi oyunlarda gözle görülür fark yaratır.",
            [cmd_enable_bbr(persist=True)],
            "warn",
        ))

    # 6) Swappiness — zram durumuna göre AKILLI
    if st.zram_active:
        # zram varsa yüksek swappiness MANTIKLI (CachyOS default 180)
        if st.swappiness < 100:
            recs.append(Recommendation(
                "zram için swappiness'i artır (180)",
                f"Şu an {st.swappiness}. zram aktif olduğunda yüksek swappiness "
                "RAM baskısında daha hızlı sıkıştırma yapar, oyunlarda daha az takılma olur. "
                "CachyOS varsayılanı 180.",
                [cmd_set_swappiness(180, persist=True)],
                "info",
            ))
    else:
        if st.swappiness > 30:
            recs.append(Recommendation(
                "Swappiness'i düşür (10)",
                f"Şu an {st.swappiness}. zram yok; düşük değer RAM'i swap'a karşı "
                "tercih ettirir ve disk-tabanlı swap kullanımını azaltır.",
                [cmd_set_swappiness(10, persist=True)],
                "warn",
            ))

    # 7) max_map_count — CRITICAL (modern Proton/DX12)
    if st.vm_max_map_count and st.vm_max_map_count < 1048576:
        recs.append(Recommendation(
            "vm.max_map_count = 1048576",
            f"Şu an {st.vm_max_map_count}. Modern DX12 oyunları (Star Citizen, Hogwarts Legacy, "
            "CS2 dahil bazı Proton oyunları) bu değer küçük olunca crash veriyor.",
            [cmd_sysctl({"vm.max_map_count": "1048576"}, persist=True)],
            "critical",
        ))

    # 8) AMD 3D V-Cache → cache — CRITICAL (sahibi olanlar için)
    if st.amd_x3d_mode and st.amd_x3d_mode != "cache":
        recs.append(Recommendation(
            "AMD 3D V-Cache: cache modu",
            f"Şu an '{st.amd_x3d_mode}'. Oyunlar V-Cache CCD'sinden büyük fayda görür "
            "(7950X3D / 7900X3D / 9950X3D vs.) — %15-25 FPS artışı raporlanmıştır.",
            [cmd_amd_x3d_mode("cache", st.amd_x3d_path)],
            "critical",
        ))

    # 9) NVIDIA prefer max perf — INFO
    if st.gpu_vendor == "NVIDIA" and has("nvidia-settings"):
        recs.append(Recommendation(
            "NVIDIA: Prefer Maximum Performance",
            "PowerMizer'ı maksimum performansta sabitler. Sadece oturum boyunca; "
            "kalıcı için autostart girdisi gerekir.",
            [cmd_nvidia_max_perf()],
            "warn",
        ))

    # 10) AMD GPU performans seviyesi — INFO
    if st.gpu_vendor == "AMD":
        recs.append(Recommendation(
            "AMD GPU: power_dpm_force_performance_level=high",
            "GPU clock'larını oyun süresince yukarıda tutar. Düşük güçten dolayı oluşan "
            "stutter'ları engeller.",
            [cmd_amd_gpu_perf_level("high")],
            "warn",
        ))

    # 11) ananicy-cpp — INFO
    if st.has_ananicy_cpp and st.ananicy_service != "active":
        recs.append(Recommendation(
            "ananicy-cpp servisini aç",
            "Oyun süreçlerine otomatik yüksek öncelik (nice / scheduler) verir.",
            [cmd_enable_service("ananicy-cpp.service")],
            "info",
        ))

    # 12) KWin AllowTearing (Wayland) — WARN
    if st.is_wayland and st.is_kde:
        recs.append(Recommendation(
            "KWin AllowTearing aç (Wayland + VRR)",
            "Wayland'de compositor kapatılamaz; bunun yerine AllowTearing açarak "
            "oyunlarda V-Sync benzeri gecikmeyi atlatırsın. VRR monitör varsa şart.",
            [cmd_kwin_allow_tearing(True),
             cmd_kwin_latency_policy("ExtremelyLow")],
            "info",
        ))

    # 13) PPD servisi yoksa uyar
    if st.ppd_service in ("inactive", "failed", "missing") and has("powerprofilesctl"):
        recs.append(Recommendation(
            "power-profiles-daemon servisini aç",
            "PPD kapalıyken 'powerprofilesctl set' çalışmaz; 'game-performance' wrapper'ı da "
            "etkisiz kalır.",
            [cmd_enable_service("power-profiles-daemon.service")],
            "warn",
        ))

    # 14) zram aktif değilse — INFO (güvenli hızlandırma)
    if not st.zram_active:
        recs.append(Recommendation(
            "zram'i etkinleştir",
            "RAM baskısında takas yerine RAM içi sıkıştırma (lz4) kullanır; "
            "özellikle 8-16 GB RAM'de oyunlarda takılmayı azaltır.",
            [cmd_setup_zram()],
            "info",
        ))

    # 15) THP 'always' ise 'madvise' öner — WARN (güvenlik/stabilite)
    if st.thp == "always":
        recs.append(Recommendation(
            "THP: madvise'e dön (always yerine)",
            "'always' modunda kernel her alokasyonda hugepage arayarak "
            "gecikme sıçramaları (latency spike) yaratabilir. 'madvise' aynı "
            "faydayı daha kontrollü verir.",
            [cmd_set_thp("madvise")],
            "warn",
        ))

    # 16) PipeWire RT kapalıysa — INFO
    if not st.pipewire_rt:
        recs.append(Recommendation(
            "PipeWire RT önceliği",
            "Ses sunucusuna gerçek zamanlı öncelik verir; oyunda ses "
            "takılmalarını ve çatlama seslerini azaltır.",
            [cmd_pipewire_rt()],
            "info",
        ))

    # 17) Oyun araçları eksikse — INFO
    eksik = []
    if not st.has_gamemode:
        eksik.append("gamemode")
    if not st.has_mangohud:
        eksik.append("mangohud")
    if not st.has_gamescope:
        eksik.append("gamescope")
    if eksik and has("pacman"):
        recs.append(Recommendation(
            f"Oyun araçları kur: {', '.join(eksik)}",
            "gamemode CPU/GPU'yu oyun için önceliklendirir, mangohud FPS/donanım "
            "overlay'i sağlar, gamescope düşük gecikmeli compositor sunar.",
            [install_packages_command(eksik + [f"lib32-{x}" for x in eksik if x != "gamescope"])],
            "info",
        ))

    return recs
