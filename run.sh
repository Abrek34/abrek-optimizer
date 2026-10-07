#!/usr/bin/env bash
# Abrek Optimizer çalıştırma scripti — venv kurar/yeniler (gerekirse) ve başlatır.
set -euo pipefail

APP_NAME="Abrek Optimizer"
cd "$(dirname "$0")"

# --- Python kontrolü -------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "[${APP_NAME}] HATA: 'python3' bulunamadı." >&2
    echo "  Debian/Ubuntu: sudo apt install python3 python3-venv python3-pip" >&2
    echo "  Arch/CachyOS : sudo pacman -S python python-pip" >&2
    echo "  Fedora       : sudo dnf install python3 python3-pip" >&2
    exit 1
fi

# --- Sanal ortam sağlığı ---------------------------------------------------
venv_ok() {
    [ -f .venv/pyvenv.cfg ] \
        && [ -x .venv/bin/python ] \
        && [ -x .venv/bin/pip ] \
        && .venv/bin/python -c "import sys" >/dev/null 2>&1
}

if ! venv_ok; then
    echo "[${APP_NAME}] Sanal ortam yok/bozuk — yeniden oluşturuluyor..."
    rm -rf .venv
    python3 -m venv .venv
    rm -f .venv/.requirements.stamp
fi

# --- requirements değiştiyse bağımlılıkları yeniden kur --------------------
# .venv/.requirements.stamp, en son kurulan requirements.txt'nin kopyasıdır.
stamp=".venv/.requirements.stamp"
if [ ! -f "$stamp" ] || ! cmp -s requirements.txt "$stamp"; then
    echo "[${APP_NAME}] Bağımlılıklar kuruluyor (pip install -r requirements.txt)..."
    .venv/bin/python -m pip install --upgrade pip wheel
    .venv/bin/python -m pip install -r requirements.txt
    cp requirements.txt "$stamp"
else
    echo "[${APP_NAME}] Bağımlılıklar güncel."
fi

exec .venv/bin/python -m abrekoptimizer "$@"
