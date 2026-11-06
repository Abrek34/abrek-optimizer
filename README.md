# Abrek Optimizer
Release: [v0.3.0](https://github.com/Abrek34/abrek-optimizer/releases/tag/v0.3.0)

![tests](https://github.com/Abrek34/abrek-optimizer/actions/workflows/tests.yml/badge.svg)
![python](https://img.shields.io/badge/python-%E2%89%A53.10-blue)
![license](https://img.shields.io/badge/license-personal-orange)

Linux için **Abrek Optimizer**: kaldırma + sistem temizleme + performans izleme aracı. PySide6 (Qt6) ile yazıldı, **KDE Plasma + Wayland**'da test edildi ve **Arch / Debian-Ubuntu / Fedora / openSUSE** üzerinde çalışacak şekilde paket yöneticisini otomatik tespit eder.

## Özellikler

- **Paketler / Kaldırma**: Yüklü tüm paketleri listeler, arama yapar, çoklu seçimle kaldırır, yetim paketleri (`autoremove`) ve paket önbelleğini temizler. Arch'ta `pacman -Rns`, Debian'da `apt purge`, Fedora'da `dnf remove`, openSUSE'de `zypper rm --clean-deps`.
- **Temizleme**: `~/.cache`, çöp kutusu, thumbnail önbelleği, tarayıcı cache'leri (Firefox/Chromium/Brave), `/tmp`, `journalctl` log'ları, paket yöneticisi cache'i (`/var/cache/...`). Önce **tara → boyutları gör → seç → temizle**.
- **Başlangıç (Autostart)**: `~/.config/autostart` ve `/etc/xdg/autostart` altındaki `.desktop` girdilerini listeler, tek tıkla devre dışı bırakır (sistem girdileri için kullanıcı dizinine override yazar).
- **Performans**: CPU/RAM/Swap/Disk canlı çubukları, yük ortalaması, en çok bellek kullanan süreçler, tek tıkla `SIGTERM` gönderme.
- **Oyun Modu**: sistemsel optimizasyon önerileri (scx scheduler, EPP, BBR, zram, THP, KWin tearing...), durum-farkında, geri alınabilir; profilleri kaydet/yükle.
- **Disk Analizi**: du tabanlı en büyük 20 klasör.
- **Rapor**: sağlık skoru + öneri listesi + trend + benchmark + son işlemler.
- **Geçmiş**: tüm işlem kayıtları (JSONL).
- **Trend**: saatlik sağlık skoru/disk/bellek örnekleri.

## Kurulum & Çalıştırma

Üç seçenek vardır; **hiçbiri root/gerek sudo gerektirmez**.

### Seçenek 1 — `./run.sh` (en basit)

```bash
cd ~/Masaüstü/"Abrek Optimizer Linux"
./run.sh
```

`run.sh` bozuk/eksik bir `.venv` varsa yeniden kurar, `requirements.txt` değiştiyse
bağımlılıkları tekrar yükler (`pip install -r` çıktısını gösterir), sonra programı başlatır.

### Seçenek 2 — `pip install .` (pyproject ile)

```bash
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/abrek-optimizer
```

`pyproject.toml` sürümü **dinamiktir**: tek doğruluk kaynağı
`abrekoptimizer/__init__.py` içindeki `__version__` değişkenidir (`0.3.0`),
pyproject'e elle sürüm yazılmaz. Konsol scripti: `abrek-optimizer`.

### Seçenek 3 — `./install.sh` (sistem entegrasyonu, kullanıcı seviyesi)

```bash
./install.sh
```

- `.venv` kurar ve `pip install -e .` çalıştırır
- `~/.local/bin/abrek-optimizer` wrapper'ı oluşturur
- `AbrekOptimizer.desktop` dosyasını `~/.local/share/applications/`e kopyalar (KDE/GNOME menüsüne eklenir)

### Seçenek 4 — Grafiksel kurulum (sihirbaz)

```bash
./install-gui.sh
```

`installer.py` aynı `install.sh` adımlarını bir Qt penceresinde canlı günlükle çalıştırır.

`~/.local/bin` PATH'te değilse terminalde gösterilen notu uygulayın:
`export PATH="$HOME/.local/bin:$PATH"`.

> Arch / CachyOS'ta sistem `python` ile sorun yaşarsanız: `sudo pacman -S python python-pip` yeterlidir. (Sanal ortam zaten ayrı.)

### Desktop dosyası (elle kurulum)

`Exec=abrek-optimizer` kullanır; yani önce `./install.sh` çalıştırın (wrapper'ı
`~/.local/bin`e kurar). `desktop-file-validate` ile doğrulanmıştır.

## Güvenlik

- `sudo` gerektiren tüm işlemler kullanıcı onayı ister; NOPASSWD sudoers kuralı (isteğe bağlı) kurulursa şifre sorulmaz, aksi hâlde komut terminalde şifre ister. GUI şifre saklamaz.
- Temizleme öğeleri **işaretlemeli**dir; yanlışlıkla bir şey silinmez. Onay penceresi her destrüktif işlemden önce çıkar.
- Hiçbir paket önyüklemesinde otomatik silme yoktur.
- **Paket adı doğrulaması**: kaldırma işlemleri yalnızca paket listesinden seçilen geçerli
  paket adlarıyla çalışır; ad boş veya tanınmıyorsa işlem iptal edilir.
- Kurulum tamamen **kullanıcı seviyesindedir** (`.venv`, `~/.local/bin`,
  `~/.local/share/applications`); sistem dizinlerine root ile hiçbir şey yazılmaz.

## Proje yapısı

```
Abrek Optimizer Linux/
├── run.sh                 # venv kur/sağlık kontrolü + başlat
├── install.sh             # kullanıcı seviyesi entegrasyon (root yok)
├── pyproject.toml         # paket tanımı (sürüm: abrekoptimizer.__version__)
├── requirements.txt
├── AbrekOptimizer.desktop  # menü girdisi (Exec=abrek-optimizer)
├── abrekoptimizer/
│   ├── __main__.py        # giriş noktası: main()
│   ├── core/
│   │   ├── pkgmanager.py  # apt/dnf/pacman/zypper soyutlaması
│   │   ├── cleaner.py     # cache/log/tmp temizleyici (+korumalı dizinler)
│   │   ├── autostart.py   # XDG autostart + systemd user servisleri
│   │   ├── perfmon.py     # psutil tabanlı izleme
│   │   ├── gameopt.py     # oyun/sistem optimizasyonu
│   │   ├── profiles.py    # profil kaydet/yükle
│   │   ├── history.py     # işlem geçmişi (JSONL)
│   │   ├── trend.py       # saatlik sağlık skoru trendi
│   │   └── applog.py      # log altyapısı
│   └── ui/
│       └── main_window.py # PySide6 sekmeli arayüz
├── installer.py           # GUI kurulum sihirbazı
├── install-gui.sh         # GUI başlatıcı
└── README.md
```

## KDE menüsüne eklemek

En kolayı `./install.sh` (wrapper + desktop dosyasını kurar). Elle kurmak için:

```bash
cp ~/Masaüstü/"Abrek Optimizer Linux"/AbrekOptimizer.desktop ~/.local/share/applications/
```

Not: Desktop dosyası `Exec=abrek-optimizer` çağırır; `~/.local/bin` içindeki wrapper'ın
var olması gerekir (`./install.sh` kurar).

## Lisans

Kişisel kullanım. İstediğiniz gibi değiştirin.
