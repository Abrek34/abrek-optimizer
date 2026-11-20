"""Öneri üretimi."""
from __future__ import annotations

from ._helpers import has, ppd_available_profiles
from .commands import (
    cmd_amd_gpu_perf_level, cmd_amd_x3d_mode, cmd_enable_bbr,
    cmd_enable_service, cmd_kwin_allow_tearing, cmd_kwin_latency_policy,
    cmd_nvidia_max_perf, cmd_pipewire_rt, cmd_power_profile,
    cmd_scx_set_scheduler, cmd_set_epp, cmd_set_governor, cmd_set_swappiness,
    cmd_set_thp, cmd_setup_zram, cmd_sysctl, install_packages_command,
)
from .models import Recommendation, Status


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
