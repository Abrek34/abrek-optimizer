#!/usr/bin/env bash
# Abrek Optimizer — kullanıcı seviyesi kurulum (root/gerek sudo YOK).
#   * .venv oluşturur/update eder
#   * pip install -e .  (paket + `abrek-optimizer` konsol scripti)
#   * ~/.local/bin/abrek-optimizer wrapper'ı
#   * desktop dosyasını ~/.local/share/applications/ kopyalar
set -euo pipefail

APP_NAME="Abrek Optimizer"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
WRAPPER="$BIN_DIR/abrek-optimizer"

# Sadece sudoers kuralını ekle/yenile
if [ "${1:-}" = "--add-sudoers" ]; then
    BINS=""
    for b in pacman apt-get dnf zypper journalctl systemctl sysctl tee find pkill gpasswd; do
        p="$(command -v "$b" 2>/dev/null || true)"
        [ -n "$p" ] && BINS="${BINS:+$BINS, }$p"
    done
    echo "$USER ALL=(root) NOPASSWD: $BINS" | sudo tee /etc/sudoers.d/90-abrek-optimizer
    sudo chmod 0440 /etc/sudoers.d/90-abrek-optimizer
    echo "[${APP_NAME}] sudoers kuralı eklendi."
    exit 0
fi

cd "$PROJECT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[${APP_NAME}] HATA: 'python3' bulunamadı." >&2
    exit 1
fi

# --- 1) Sanal ortam --------------------------------------------------------
if [ ! -f .venv/pyvenv.cfg ] || ! .venv/bin/python -c "import sys" >/dev/null 2>&1; then
    echo "[${APP_NAME}] .venv oluşturuluyor..."
    rm -rf .venv
    python3 -m venv .venv
fi

# --- 2) Eski sürümü kaldır, paketi taze kur -------------------------------
# Önce kurulu olan abrek-optimizer sürümünü sil; sonra editable olarak yeniden kur.
if .venv/bin/pip show abrek-optimizer >/dev/null 2>&1; then
    echo "[${APP_NAME}] Eski sürüm kaldırılıyor..."
    .venv/bin/pip uninstall -y abrek-optimizer
fi
echo "[${APP_NAME}] pip install -e ."
.venv/bin/python -m pip install --upgrade pip wheel
.venv/bin/python -m pip install -e .

# --- 3) Wrapper: ~/.local/bin/abrek-optimizer -----------------------------
mkdir -p "$BIN_DIR"
cat > "$WRAPPER" <<EOF
#!/usr/bin/env bash
# Oluşturuldu: ${PROJECT_DIR}/install.sh — silinmesi güvenli.
exec "${PROJECT_DIR}/.venv/bin/python" -m abrekoptimizer "\$@"
EOF
chmod 0755 "$WRAPPER"
echo "[${APP_NAME}] Wrapper: $WRAPPER"

# --- 4) Desktop dosyası ----------------------------------------------------
mkdir -p "$APP_DIR"
# Desktop dosyası kullanıcının gerçek yollarına göre üretilir
sed -e "s|^Exec=.*|Exec=$WRAPPER|" -e "s|^TryExec=.*|TryExec=$WRAPPER|" \
    "$PROJECT_DIR/AbrekOptimizer.desktop" > "$APP_DIR/AbrekOptimizer.desktop"
chmod 0644 "$APP_DIR/AbrekOptimizer.desktop"
# İkon
install -Dm644 "$PROJECT_DIR/assets/abrek-optimizer.svg" \
    "$HOME/.local/share/icons/hicolor/scalable/apps/abrek-optimizer.svg"
command -v update-desktop-database >/dev/null 2>&1 \
    && update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
echo "[${APP_NAME}] Menü girdisi: $APP_DIR/AbrekOptimizer.desktop"

# --- 5) PATH notu ----------------------------------------------------------
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *)
        echo "[${APP_NAME}] NOT: '$BIN_DIR' PATH'te değil. Şunu ekleyin:"
        echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
        ;;
esac

echo "[${APP_NAME}] Kurulum tamam. Çalıştır: abrek-optimizer  (veya ./run.sh)"

# --- 6) İsteğe bağlı: sudo şifresiz kural (NOPASSWD) ------------------------
# Abrek Optimizer'un çalıştırdığı sistem komutları için kullanıcıya tek seferlik
# bir sudoers kuralı ekler; böylece her işlemde şifre sorulmaz.
# Devre dışı bırakmak için:   ABREK_NOPASSWD=0 ./install.sh
if [ "${ABREK_NOPASSWD:-1}" = "1" ]; then
    echo ""
    echo "[${APP_NAME}] ============================================================"
    echo "[${APP_NAME}] Abrek Optimizer sistem komutlarını sudo ile çalıştırır."
    echo "[${APP_NAME}] Şifre sormadan çalışması için bir kez sudo şifresi"
    echo "[${APP_NAME}] gerekir ve /etc/sudoers.d/90-abrek-optimizer dosyası"
    echo "[${APP_NAME}] oluşturulur. Onaylıyor musunuz?"
    echo "============================================================"
    if [ -t 0 ]; then
        read -r -p "[${APP_NAME}] sudoers kuralı eklensin mi? [E/h] " yn
    else
        yn="h"
        echo "[${APP_NAME}] Etkileşimli terminal yok — sudoers kuralı atlanıyor."
        echo "[${APP_NAME}] Elle eklemek için: sudo ./install.sh --add-sudoers"
    fi
    case "${yn:-e}" in
        e|E|y|Y|"")
            echo "[${APP_NAME}] sudo şifresiz kuralı ekleniyor (bir kez şifre istenecek)..."
            BINS=""
            for b in pacman apt-get dnf zypper journalctl systemctl sysctl tee find pkill gpasswd; do
                p="$(command -v "$b" 2>/dev/null || true)"
                [ -n "$p" ] && BINS="${BINS:+$BINS, }$p"
            done
            if [ -n "$BINS" ]; then
                echo "$USER ALL=(root) NOPASSWD: $BINS" \
                    | sudo tee /etc/sudoers.d/90-abrek-optimizer >/dev/null \
                    && sudo chmod 0440 /etc/sudoers.d/90-abrek-optimizer \
                    && echo "[${APP_NAME}] /etc/sudoers.d/90-abrek-optimizer kuruldu." \
                    || echo "[${APP_NAME}] UYARI: sudoers kuralı eklenemedi (şifre sorulmaya devam eder)."
            fi
            ;;
        *)
            echo "[${APP_NAME}] sudoers kuralı eklenmedi; her işlemde şifre sorulacak."
            ;;
    esac
fi

