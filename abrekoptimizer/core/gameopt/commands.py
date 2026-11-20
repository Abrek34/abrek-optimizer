"""Komut üreticileri (uygulama/geri alma)."""
from __future__ import annotations

import os
import shutil

from ._helpers import _safe_word, has


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
