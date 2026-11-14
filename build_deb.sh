#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="1.0.0"
PKG_NAME="minttune_${VERSION}_amd64"

cd "$APP_DIR"
echo "=========================================="
echo "    Membangun Paket Installer .deb        "
echo "=========================================="

# 1. Pastikan PyInstaller terpasang di .venv
echo "--> [1/4] Memeriksa compiler PyInstaller..."
./.venv/bin/pip install --quiet pyinstaller

# 2. Compile kode Python menjadi aplikasi binary mandiri
echo "--> [2/4] Memaketkan kode menjadi binary (ini butuh waktu ~1 menit)..."
rm -rf build dist deb_pkg "${PKG_NAME}.deb"
./.venv/bin/pyinstaller --noconfirm --onedir --windowed \
    --name minttune \
    --hidden-import PyQt6.QtSvg \
    --hidden-import PyQt6.QtMultimedia \
    main.py

# 3. Susun folder standar sistem Linux Mint (.deb structure)
echo "--> [3/4] Menyusun struktur paket sistem Linux..."
mkdir -p deb_pkg/DEBIAN
mkdir -p deb_pkg/opt/minttune
mkdir -p deb_pkg/usr/bin
mkdir -p deb_pkg/usr/share/applications
mkdir -p deb_pkg/usr/share/icons/hicolor/scalable/apps

# Copy binary aplikasi dan ikon
cp -r dist/minttune/* deb_pkg/opt/minttune/
if [ -f "resources/icons/minttune.svg" ]; then
    cp resources/icons/minttune.svg deb_pkg/usr/share/icons/hicolor/scalable/apps/minttune.svg
fi

# Buat jalan pintas terminal di /usr/bin
cat << 'BIN' > deb_pkg/usr/bin/minttune
#!/bin/bash
exec /opt/minttune/minttune "$@"
BIN
chmod 755 deb_pkg/usr/bin/minttune

# Buat jalan pintas desktop di Start Menu
cat << 'DESKTOP' > deb_pkg/usr/share/applications/minttune.desktop
[Desktop Entry]
Name=MintTune
Comment=Modern Native Music Player & Library Manager
Exec=/usr/bin/minttune
Icon=minttune
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Music;Player;
DESKTOP
chmod 644 deb_pkg/usr/share/applications/minttune.desktop

# Buat metadata Debian Control
cat << CONTROL > deb_pkg/DEBIAN/control
Package: minttune
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: amd64
Maintainer: MintTune Developer
Depends: libxcb-cursor0, gstreamer1.0-plugins-base, gstreamer1.0-plugins-good, gstreamer1.0-plugins-bad, gstreamer1.0-plugins-ugly, gstreamer1.0-libav
Description: Modern native desktop music player for Linux Mint
 MintTune is an offline desktop music player and library manager built
 with Python and PyQt6, featuring Mint theme integration and Bento UI.
CONTROL
chmod 755 deb_pkg/DEBIAN

# 4. Bangun paket .deb final
echo "--> [4/4] Mengompresi menjadi file .deb..."
dpkg-deb --build deb_pkg "${PKG_NAME}.deb"

# Bersihkan folder sementara
rm -rf build dist deb_pkg minttune.spec

echo ""
echo "=========================================="
echo "    🎉 File Installer .deb Berhasil!     "
echo "=========================================="
echo "File tersimpan di: $APP_DIR/${PKG_NAME}.deb"
echo ""
