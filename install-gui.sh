#!/usr/bin/env bash
# Abrek Optimizer grafiksel kurulumunu başlatır.
set -euo pipefail
cd "$(dirname "$0")"

# Önce proje venv'i dene; yoksa sistem python3 + PySide6.
if [ -x .venv/bin/python ] && .venv/bin/python -c "import PySide6" 2>/dev/null; then
    exec .venv/bin/python installer.py "$@"
elif command -v python3 >/dev/null && python3 -c "import PySide6" 2>/dev/null; then
    exec python3 installer.py "$@"
else
    echo "PySide6 bulunamadı. Önce komut satırı kurulumunu çalıştırın:"
    echo "    ./install.sh"
    echo "veya sistem PySide6'sını kurun:"
    echo "    sudo pacman -S python-pyside6      # Arch/CachyOS"
    echo "    sudo apt install python3-pyside6   # Debian/Ubuntu"
    exit 1
fi
