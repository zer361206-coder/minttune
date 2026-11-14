#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "       Instalasi MintTune Desktop        "
echo "=========================================="

echo "--> [1/5] Memeriksa & menginstal paket sistem Linux Mint..."
sudo apt update
sudo apt install -y python3-pip python3-venv libxcb-cursor0 sqlite3 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav

echo "--> [2/5] Menyiapkan Python Virtual Environment..."
cd "$APP_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "--> [3/5] Menyiapkan direktori penyimpanan XDG..."
mkdir -p ~/.config/minttune
mkdir -p ~/.local/share/minttune
mkdir -p ~/.cache/minttune
mkdir -p ~/.local/share/applications
mkdir -p ~/.local/share/icons/hicolor/scalable/apps
mkdir -p ~/.local/bin

echo "--> [4/5] Memasang ikon resmi MintTune..."
if [ -f "$APP_DIR/resources/icons/minttune.svg" ]; then
    cp "$APP_DIR/resources/icons/minttune.svg" ~/.local/share/icons/hicolor/scalable/apps/minttune.svg
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor || true
fi

echo "--> [5/5] Mendaftarkan ke Menu Start & Terminal..."
cat <<DESKTOP > ~/.local/share/applications/minttune.desktop
[Desktop Entry]
Name=MintTune
Comment=Modern Native Music Player & Library Manager
Exec=$APP_DIR/.venv/bin/python $APP_DIR/main.py
Icon=minttune
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Music;Player;
DESKTOP

cat <<BIN > ~/.local/bin/minttune
#!/bin/bash
exec "$APP_DIR/.venv/bin/python" "$APP_DIR/main.py" "\$@"
BIN
chmod +x ~/.local/bin/minttune

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database ~/.local/share/applications || true

echo ""
echo "=========================================="
echo "     ✅ Instalasi MintTune Berhasil!     "
echo "=========================================="
echo "Aplikasi sekarang bisa dibuka lewat:"
echo " 1. Menu Aplikasi Linux Mint (cari: MintTune)"
echo " 2. Terminal (cukup ketik: minttune)"
echo ""
