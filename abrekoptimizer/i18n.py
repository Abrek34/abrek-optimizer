"""Basit dil çevirisi (TR/EN)."""
from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "abrek"
CONFIG_FILE = CONFIG_DIR / "config.json"

_current = "tr"

LANGUAGES = {"tr": "Türkçe", "en": "English"}

# Çeviri sözlüğü: anahtar = Türkçe metin
TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Genel
        "Abrek Program Silme Aracı": "Abrek Program Removal Tool",
        "Paket yöneticisi": "Package manager",
        "Bilgi": "Info",
        "Onayla": "Confirm",
        "Hata": "Error",
        "Uyarı": "Warning",
        "İptal": "Cancel",
        "Yenile": "Refresh",
        "Yükleniyor...": "Loading...",
        "Tümünü seç": "Select all",
        "Yardım": "Help",
        "Oyun Modu": "Game Mode",
        "Sistem Durumu": "System Status",
        "CS2 / Rekabetçi FPS için Önerilenler": "Recommended for CS2 / Competitive FPS",
        "Önerilenleri sırayla uygula": "Apply recommendations in order",
        "Durumu yenile": "Refresh status",
        "Uygulanacak öneri yok.": "No recommendations to apply.",
        "Toplam": "Total",
        "Devam edilsin mi?": "Continue?",
        "Hayır": "No",
        "Evet": "Yes",
        # Sekmeler
        "Paketler / Kaldırma": "Packages / Removal",
        "Temizleme": "Cleanup",
        "Başlangıç": "Startup",
        "Performans": "Performance",
        # Paket sekmesi
        "Paket ara...": "Search packages...",
        "Ad": "Name",
        "Sürüm": "Version",
        "Boyut": "Size",
        "Açıklama": "Description",
        "Yapılandırma + bağımlılıkları sil (-Rns / purge)": "Remove configs + dependencies (-Rns / purge)",
        "Pacman'da -Rns: konfig dosyalarını ve kullanılmayan bağımlılıkları siler.": "Pacman -Rns: removes config files and unused dependencies.",
        "Bağımlı paketleri de kaldır (cascade)": "Also remove dependent packages (cascade)",
        "Bu paketi gerektiren DİĞER paketleri de kaldırır.\nÖrn: 'gamescope' kaldırılırken 'cachyos-gaming-applications' meta-paketi de gider.\nDİKKAT: Beklenmedik kadar çok paket kaldırılabilir.": "Also removes OTHER packages that require this one.\nE.g.: removing 'gamescope' will also remove the 'cachyos-gaming-applications' meta-package.\nWARNING: Unexpectedly many packages may be removed.",
        "Neye bağımlı?": "What depends on this?",
        "Seçili paketin hangi başka paketler tarafından gerektirildiğini gösterir.": "Shows which other packages require the selected one.",
        "Yetim paketleri kaldır": "Remove orphan packages",
        "Paket önbelleğini temizle": "Clean package cache",
        "Seçilenleri kaldır": "Remove selected",
        "Lütfen kaldırılacak paket(ler)i seçin.": "Please select package(s) to remove.",
        "Lütfen bir paket seçin.": "Please select a package.",
        "Yetim paketler kaldırılsın mı?": "Remove orphan packages?",
        "Paket önbelleği temizlensin mi?": "Clean package cache?",
        "Pacman bu işlemi reddediyor:": "Pacman rejected this operation:",
        "Çünkü seçtiğiniz paketlere başka paketler bağımlı. Cascade modunu açıp tekrar deneyin (alttaki kutu).": "Because other packages depend on what you selected. Enable cascade mode and try again (checkbox below).",
        "Bağımlılık çatışması": "Dependency conflict",
        "İşlem başlatılamadı.": "Operation could not be started.",
        "Cascade'i aç ve tekrar dene": "Enable cascade and retry",
        "Toplam <b>{n}</b> paket kaldırılacak.": "<b>{n}</b> packages will be removed in total.",
        "Seçtiğiniz: {n}": "Your selection: {n}",
        "Ek (bağımlılar/cascade): {n}": "Additional (dependents/cascade): {n}",
        "Seçilen ({n}):": "Selected ({n}):",
        "— Ek olarak kaldırılacak —": "— Additionally removed —",
        "… ve {n} tane daha": "… and {n} more",
        "⚠ CASCADE: meta paketler ve bağımlılar da kaldırılacak.": "⚠ CASCADE: meta packages and dependents will also be removed.",
        "Desteklenmiyor": "Not supported",
        "Bu paket yöneticisi için desteklenmiyor.": "Not supported for this package manager.",
        "Komut çalıştırılamadı: {e}\n\nKomut: {cmd}": "Could not run command: {e}\n\nCommand: {cmd}",
        "'{name}' neye bağımlı?": "What depends on '{name}'?",
        "<b>{name}</b> paketini gerektirenler:": "Packages requiring <b>{name}</b>:",
        "(çıktı yok)": "(no output)",
        # Temizleme
        "Temizlenecek hedefleri seçin. <b>Root</b> gerektiren öğeler için terminal açılıp şifre istenecektir.": "Select cleanup targets. Items requiring <b>root</b> will open a terminal and ask for your password.",
        "Hedef": "Target",
        "Tara (boyutları hesapla)": "Scan (calculate sizes)",
        "Seçilenleri Temizle": "Clean selected",
        "Journal log'larını 7 günde tut": "Keep journal logs for 7 days",
        "Toplam: —": "Total: —",
        "Toplam: <b>{size}</b>": "Total: <b>{size}</b>",
        "Tarama başladı...": "Scanning...",
        "Tarama tamam. Toplam: {size}": "Scan done. Total: {size}",
        "Lütfen temizlenecek hedef seçin.": "Please select cleanup targets.",
        "{n} hedef temizlenecek. Bu işlem geri alınamaz. Devam?": "{n} targets will be cleaned. This cannot be undone. Continue?",
        "✓ {label}: {size} boşaltıldı": "✓ {label}: {size} freed",
        " ({n} hata)": " ({n} errors)",
        "<b>Toplam boşaltılan (kullanıcı): {size}</b>": "<b>Total freed (user): {size}</b>",
        "↗ {label}: terminalde çalıştırılıyor (root)": "↗ {label}: running in terminal (root)",
        "Kullanıcı önbelleği (~/.cache)": "User cache (~/.cache)",
        "Uygulama önbellek dosyaları. Güvenle silinebilir.": "Application cache files. Safe to delete.",
        "Çöp kutusu": "Trash",
        "Çöp kutusundaki dosyalar.": "Files in the trash.",
        "Thumbnail önbelleği": "Thumbnail cache",
        "Resim küçük görsel önbellekleri.": "Image thumbnail cache.",
        "Tarayıcı önbelleği (Firefox/Chromium)": "Browser cache (Firefox/Chromium)",
        "Tarayıcılara ait disk önbellekleri.": "Browser disk caches.",
        "Geçici dosyalar (/tmp)": "Temporary files (/tmp)",
        "Sistem geçici klasörü. Açık uygulamalar etkilenebilir.": "System temp folder. Open apps may be affected.",
        "Sistem logları (journalctl)": "System logs (journalctl)",
        "Sistem günlükleri. journalctl --vacuum kullanır.": "System logs. Uses journalctl --vacuum.",
        "Paket yöneticisi önbelleği": "Package manager cache",
        "Paket yöneticisinin indirme önbelleği.": "Package manager download cache.",
        # Autostart
        "Açılışta çalışan masaüstü uygulamaları (XDG autostart). Onay kutusunu kapatınca devre dışı kalır.": "Desktop apps that run at startup (XDG autostart). Unchecking disables them.",
        "Aktif": "Enabled",
        "Komut": "Command",
        # Performans
        "RAM: <b>{used}</b> / {total} &nbsp;|&nbsp; Disk: <b>{dused}</b> / {dtotal} &nbsp;|&nbsp; Süreç: <b>{procs}</b> &nbsp;|&nbsp; Yük: {l1:.2f} {l2:.2f} {l3:.2f}":
            "RAM: <b>{used}</b> / {total} &nbsp;|&nbsp; Disk: <b>{dused}</b> / {dtotal} &nbsp;|&nbsp; Processes: <b>{procs}</b> &nbsp;|&nbsp; Load: {l1:.2f} {l2:.2f} {l3:.2f}",
        "<b>En çok bellek kullanan süreçler</b>": "<b>Top memory-using processes</b>",
        "PID": "PID",
        "Kullanıcı": "User",
        "Seçili süreci sonlandır (SIGTERM)": "Terminate selected process (SIGTERM)",
        # Menü
        "Dil": "Language",
        "Hakkında": "About",
        "Toplam {n} öneri terminalde sırayla çalıştırılacak.": "{n} recommendations will be run in order in a terminal.",
        "Dil değiştirildi.": "Language changed.",
        # Yardım / hakkında
        "Abrek Optimizer / CachyOS bakım ve oyun performansı aracı.": "Abrek Optimizer / CachyOS maintenance and gaming performance tool.",
        # Performans: ölçer etiketleri ve SIGTERM onayı
        "CPU": "CPU",
        "RAM": "RAM",
        "Swap": "Swap",
        "Disk /": "Disk /",
        "Onay": "Confirm",
        "Seçili süreçlere SIGTERM gönderilsin mi?": "Send SIGTERM to the selected processes?",
        # Oyun Modu: grup başlıkları ve ayar satırları
        "CPU & Güç": "CPU & Power",
        "Uygula": "Apply",
        "Uygula (AMD EPP)": "Apply (AMD EPP)",
        "Uygula (kalıcı)": "Apply (persistent)",
        "Uygula (oturum)": "Apply (session)",
        "Governor:": "Governor:",
        "AMD EPP:": "AMD EPP:",
        "Güç profili (PPD):": "Power profile (PPD):",
        "AMD 3D V-Cache:": "AMD 3D V-Cache:",
        "Sched-ext (CachyOS scheduler)": "Sched-ext (CachyOS scheduler)",
        "Scheduler:": "Scheduler:",
        "Etkinleştir (Gaming)": "Enable (Gaming)",
        "Kapat": "Off",
        "Aç": "On",
        "<i>Not: 2026/05 itibariyle hybrid CPU'larda <b>scx_bpfland Gaming</b> en stabil seçenek. scx_lavd'da bilinen bellek sızıntısı (#3340) var.</i>":
            "<i>Note: as of 2026/05, on hybrid CPUs <b>scx_bpfland Gaming</b> is the most stable option. scx_lavd has a known memory leak (#3340).</i>",
        "Bellek": "Memory",
        "Swappiness:": "Swappiness:",
        "vm.max_map_count = 1048576 (kalıcı)": "vm.max_map_count = 1048576 (persistent)",
        "Transparent Hugepage:": "Transparent Hugepage:",
        "Ağ (online oyun gecikmesi)": "Network (online gaming latency)",
        "TCP BBR + fq qdisc aktif et (kalıcı)": "Enable TCP BBR + fq qdisc (persistent)",
        "GPU": "GPU",
        "NVIDIA: Prefer Maximum Performance (oturum)": "NVIDIA: Prefer Maximum Performance (session)",
        "AMD GPU: performance level = high": "AMD GPU: performance level = high",
        "AMD GPU: auto'ya döndür": "Return AMD GPU to auto",
        "KDE / KWin Compositor": "KDE / KWin Compositor",
        "Compositing'i askıya al (Shift+Alt+F12 eşdeğeri)": "Suspend compositing (equivalent to Shift+Alt+F12)",
        "Compositing'i geri aç": "Resume compositing",
        "AllowTearing açık (VRR / düşük gecikme)": "AllowTearing on (VRR / low latency)",
        "AllowTearing kapalı": "AllowTearing off",
        "Eksik paketleri kur (CachyOS / Arch)": "Install missing packages (CachyOS / Arch)",
        "cachyos-gaming-meta + cachyos-gaming-applications": "cachyos-gaming-meta + cachyos-gaming-applications",
        "scx-scheds + scx_loader": "scx-scheds + scx_loader",
        "gamemode + gamescope + mangohud": "gamemode + gamescope + mangohud",
        "ananicy-cpp (oyun süreçlerine otomatik öncelik)": "ananicy-cpp (automatic priority for game processes)",
        "proton-cachyos (Steam'de seçilebilir hale gelir)": "proton-cachyos (becomes selectable in Steam)",
        "Servisler": "Services",
        # Sistem durumu satırları (_render_status)
        "Kernel": "Kernel",
        "Kernel paketi": "Kernel package",
        "CPU sürücüsü": "CPU driver",
        "Governor": "Governor",
        "AMD EPP": "AMD EPP",
        "Güç profili (PPD)": "Power profile (PPD)",
        "Çalışan SCX": "Running SCX",
        "scx_loader servisi": "scx_loader service",
        "TCP congestion": "TCP congestion",
        "Swappiness": "Swappiness",
        "vm.max_map_count": "vm.max_map_count",
        "Transparent Hugepage": "Transparent Hugepage",
        "zram / zswap": "zram / zswap",
        "AMD 3D V-Cache modu": "AMD 3D V-Cache mode",
        "Mitigations off": "Mitigations off",
        "Oturum tipi": "Session type",
        "Paketler": "Packages",
        "(kapalı)": "(off)",
        "aktif": "on",
        "kapalı": "off",
        "EVET": "YES",
        "hayır": "no",
        # Öneri günlüğü (oyun modu)
        "<b>✓ Sistem zaten optimize görünüyor.</b><br/>Oyunu başlatırken Steam launch options'a <code>game-performance %command%</code> eklemeyi unutmayın.":
            "<b>The system already looks optimized.</b><br/>When launching the game, don't forget to add <code>game-performance %command%</code> to the Steam launch options.",
        "<b>Şu öneriler uygulanabilir:</b><br/>": "<b>The following recommendations can be applied:</b><br/>",
        # Oyun cache temizleme hedefleri
        "Mesa shader cache": "Mesa shader cache",
        "Mesa (AMD/Intel) Vulkan/GL shader önbelleği. Silinince ilk açılışta yeniden derlenir.":
            "Mesa (AMD/Intel) Vulkan/GL shader cache. Recompiled on first launch after deletion.",
        "NVIDIA shader cache": "NVIDIA shader cache",
        "NVIDIA GL/CUDA shader önbelleği. Eski sürücüden kalanlar problem yapabilir.":
            "NVIDIA GL/CUDA shader cache. Leftovers from old drivers can cause problems.",
        "Steam shader cache": "Steam shader cache",
        "Steam'in oyun başına Vulkan pipeline cache'i. Büyür; problem yaratırsa silin.":
            "Per-game Vulkan pipeline cache from Steam. Grows large; delete if it causes issues.",
        "DXVK / VKD3D shader cache": "DXVK / VKD3D shader cache",
        "Wine/Proton DirectX→Vulkan çevirici shader cache'i.":
            "Wine/Proton DirectX→Vulkan translation shader cache.",
        "Discord cache": "Discord cache",
        "Discord uygulamasının disk önbelleği.": "Discord's on-disk cache.",
        "Lutris / Heroic / Bottles cache": "Lutris / Heroic / Bottles cache",
        "Oyun launcher'larının önbellekleri.": "Game launchers' caches.",
        "CPU %": "CPU %",
        "RAM %": "RAM %",
        "✓": "✓",
        # Yeni sekmeler ve özellikler
        "Özet": "Summary",
        "Geçmiş": "History",
        "Zaman": "Time",
        "İşlem": "Action",
        "Durum": "Status",
        "Kaynak": "Source",
        "Ara...": "Search...",
        "systemd user servislerini de göster": "Also show systemd user services",
        "Açılışta çalışan öğeler: XDG autostart girdileri ve kullanıcı systemd servisleri. Onay kutusunu kapatınca devre dışı kalır.":
            "Startup items: XDG autostart entries and systemd user services. Unchecking disables them.",
        "Profiller": "Profiles",
        "Profil:": "Profile:",
        "Mevcut durumu kaydet": "Save current state",
        "Sil": "Delete",
        "Profil adı": "Profile name",
        "Profil adı:": "Profile name:",
        "'{name}' profili uygulanacak. Emin misiniz?": "Apply profile '{name}'. Continue?",
        "Kayıtlı profil yok.": "No saved profiles.",
        "Bu profilde uygulanacak ayar yok.": "This profile has no settings to apply.",
        "Önce 'Durumu yenile' ile durum okunmalı.": "First refresh the status to read the current state.",
        "Profil": "Profile",
        "Öneriler uygulanıyor": "Applying recommendations",
        "Temizlik tamamlandı": "Cleanup finished",
        "{size} boşaltıldı ({n} hedef)": "{size} freed ({n} targets)",
        "İşlem tamamlandı": "Operation finished",
        "Paket kaldırma": "Package removal",
        "Yetim paketler": "Orphan packages",
        "Paket önbelleği": "Package cache",
        "'{label}' root ile temizlenecek. Emin misiniz?": "Clean '{label}' as root. Continue?",
        "↗ {label}: uygulamada çalıştırıldı (root)": "↗ {label}: ran in-app (root)",
        "Journal log'ları 7 güne indirilecek. Emin misiniz?": "Trim journal logs to 7 days. Continue?",
        "Journal vacuum": "Journal vacuum",
        "<b>Sağlık skoru: {score}/100</b> — {crit} kritik, {warn} uyarı önerisi var.":
            "<b>Health score: {score}/100</b> — {crit} critical, {warn} warning recommendations.",
        "Sağlık skoru: hesaplanıyor...": "Health score: calculating...",
        "<b>Sağlık skoru:</b> hesaplanıyor...": "<b>Health score:</b> calculating...",
        "zram kur (RAM/2, lz4)": "Install zram (RAM/2, lz4)",
        "PipeWire RT önceliği ver": "Give PipeWire RT priority",
        "Geri Al (varsayılanlara dön)": "Revert (back to defaults)",
        "Abrek sysctl ayarlarını kaldır + eski değerleri geri yükle": "Remove Abrek sysctl settings + restore old values",
        "Governor: schedutil": "Governor: schedutil",
        "EPP: balance_performance": "EPP: balance_performance",
        "Güç profili: balanced": "Power profile: balanced",
        "THP: madvise": "THP: madvise",
        "Swappiness: 60": "Swappiness: 60",
        "scx scheduler'i kapat": "Disable scx scheduler",
        "Uygulama sonrası sağlık skoru: <b>{s}/100</b> ({sign}{d})": "Health score after applying: <b>{s}/100</b> ({sign}{d})",
        "Optimizasyon skoru": "Optimization score",
        "Disk Analizi": "Disk Analyzer",
        "Rapor": "Report",
        "Raporu yenile": "Refresh report",
        "Tara": "Scan",
        "Yol": "Path",
        "En büyük klasörler (du ile hızlı tarama; root gerekmez, ev dizini + sistem önbellekleri).":
            "Largest folders (fast du scan; no root needed; home + system caches).",
        "Önce tarama yapın.": "Run a scan first.",
        "Akıllı seçim (≥50MB, root'suz)": "Smart select (≥50MB, no root)",
        "Akıllı seçim: {n} hedef işaretlendi (≥50MB, root'suz).": "Smart select: {n} targets checked (≥50MB, no root).",
        "Sistem Raporu": "System Report",
        "Son işlemler": "Recent actions",
        "Öneriler": "Recommendations",
        "(kayıt yok)": "(no records)",
        "✓ Öneri yok — sistem optimize görünüyor.": "✓ No recommendations — system looks optimized.",
        "Sağlık skoru": "Health score",
        "Güç profili": "Power profile",
        "Trend (son örnekler)": "Trend (latest samples)",
        "(henüz örnek yok)": "(no samples yet)",
        "Benchmark çalıştır (~8sn)": "Run benchmark (~8s)",
        "Benchmark sonuçları burada görünür...": "Benchmark results will appear here...",
        "Benchmark başladı...": "Benchmark started...",
        "CPU ~{cpu:,.0f} op/s | Bellek kopyalama ~{mem:.1f} GB/s | Disk yazma ~{disk:.0f} MB/s":
            "CPU ~{cpu:,.0f} op/s | Memory copy ~{mem:.1f} GB/s | Disk write ~{disk:.0f} MB/s",
        "Açık kalma: <b>{up}</b> &nbsp;|&nbsp; CPU: {cpu:.0f}°C &nbsp;|&nbsp; RAM: <b>{used}</b> / {total} &nbsp;|&nbsp; Disk: <b>{dused}</b> / {dtotal} &nbsp;|&nbsp; Süreç: <b>{procs}</b> &nbsp;|&nbsp; Yük: {l1:.2f}":
            "Uptime: <b>{up}</b> &nbsp;|&nbsp; CPU: {cpu:.0f}°C &nbsp;|&nbsp; RAM: <b>{used}</b> / {total} &nbsp;|&nbsp; Disk: <b>{dused}</b> / {dtotal} &nbsp;|&nbsp; Processes: <b>{procs}</b> &nbsp;|&nbsp; Load: {l1:.2f}",
    }
}


def load() -> None:
    global _current
    try:
        data = json.loads(CONFIG_FILE.read_text())
        lang = data.get("language", "tr")
        if lang in LANGUAGES:
            _current = lang
    except (OSError, ValueError):
        pass


def save(lang: str) -> None:
    """Dili kalıcı kaydeder ve aynı anda geçerli dil olarak uygular (yeniden başlatma gerekmez)."""
    global _current
    if lang not in LANGUAGES:
        return
    _current = lang
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {}
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        pass
    data["language"] = lang
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def current() -> str:
    return _current


def tr(text: str) -> str:
    if _current == "tr":
        return text
    return TRANSLATIONS.get(_current, {}).get(text, text)
