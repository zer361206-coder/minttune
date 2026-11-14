import os
import sys
import shutil
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
                             QTextEdit, QPushButton, QLabel, QMessageBox)
from PyQt6.QtCore import pyqtSignal, QT_VERSION_STR, PYQT_VERSION_STR
import mutagen
from db.database import get_connection, DB_PATH

CACHE_ARTWORK_DIR = Path(os.getenv('XDG_CACHE_HOME', Path.home() / '.cache')) / 'minttune' / 'artwork'

def collect_diagnostics_report() -> str:
    lines = ["=== LAPORAN DIAGNOSTIK MINTTUNE ==="]
    lines.append(f"Python       : {sys.version.split()[0]}")
    lines.append(f"PyQt6 / Qt   : {PYQT_VERSION_STR} / Qt {QT_VERSION_STR}")
    lines.append(f"Mutagen      : {mutagen.version_string}")
    lines.append(f"Database     : {DB_PATH}")

    try:
        conn = get_connection()
        total = conn.execute("SELECT COUNT(*) FROM tracks WHERE missing=0").fetchone()[0]
        missing = conn.execute("SELECT COUNT(*) FROM tracks WHERE missing=1").fetchone()[0]
        conn.close()
        lines.append(f"Total Lagu   : {total} aktif, {missing} hilang (missing)")
    except Exception as e:
        lines.append(f"Database Err : {e}")

    lines.append("\n--- Codec Audio QtMultimedia ---")
    try:
        from PyQt6.QtMultimedia import QMediaFormat
        fmt = QMediaFormat()
        codecs = [c.name for c in fmt.supportedAudioCodecs(QMediaFormat.ConversionMode.Decode)]
        lines.append("Didukung     : " + (", ".join(codecs) if codecs else "Tidak terdeteksi"))
    except Exception:
        lines.append("Info Codec   : QtMultimedia tersedia (Detail QMediaFormat butuh Qt 6.2+)")

    lines.append("\n--- Status Paket GStreamer Linux Mint ---")
    gst_pkgs = [
        "gstreamer1.0-plugins-base",
        "gstreamer1.0-plugins-good",
        "gstreamer1.0-plugins-bad",
        "gstreamer1.0-plugins-ugly",
        "gstreamer1.0-libav"
    ]
    for pkg in gst_pkgs:
        try:
            res = subprocess.run(
                ["dpkg-query", "-W", "-f=${Status}", pkg],
                capture_output=True, text=True
            )
            status = "TERINSTAL [OK]" if "install ok installed" in res.stdout else "BELUM ADA [MISSING]"
        except Exception:
            status = "Tidak dapat memeriksa"
        lines.append(f"{pkg:<28}: {status}")

    return "\n".join(lines)

class DiagnosticsDialog(QDialog):
    library_updated = pyqtSignal()
    full_rescan_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🛠️ Diagnostik, Pemeliharaan & Pintasan")
        self.resize(620, 440)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # --- TAB 1: DIAGNOSTIK SISTEM ---
        tab_diag = QWidget()
        diag_layout = QVBoxLayout(tab_diag)
        txt_diag = QTextEdit()
        txt_diag.setReadOnly(True)
        txt_diag.setPlainText(collect_diagnostics_report())
        txt_diag.setStyleSheet("font-family: monospace; font-size: 12px;")
        diag_layout.addWidget(txt_diag)
        tabs.addTab(tab_diag, "🩺 Diagnostik Codec")

        # --- TAB 2: PEMELIHARAAN LIBRARY ---
        tab_maint = QWidget()
        maint_layout = QVBoxLayout(tab_maint)

        lbl_info = QLabel("Gunakan alat ini untuk merawat database dan cache MintTune:")
        lbl_info.setWordWrap(True)

        btn_clean_missing = QPushButton("🧹 Hapus Track Hilang (Missing) dari Database")
        btn_clean_missing.clicked.connect(self.remove_missing_tracks)

        btn_clear_cache = QPushButton("🖼️ Bersihkan Cache Cover Art (~/.cache/minttune)")
        btn_clear_cache.clicked.connect(self.clear_artwork_cache)

        btn_full_rescan = QPushButton("🔄 Full Rescan (Baca Ulang Semua Metadata)")
        btn_full_rescan.clicked.connect(self.trigger_full_rescan)

        maint_layout.addWidget(lbl_info)
        maint_layout.addSpacing(8)
        maint_layout.addWidget(btn_clean_missing)
        maint_layout.addWidget(btn_clear_cache)
        maint_layout.addWidget(btn_full_rescan)
        maint_layout.addStretch()
        tabs.addTab(tab_maint, "🧹 Pemeliharaan")

        # --- TAB 3: PINTASAN KEYBOARD ---
        tab_keys = QWidget()
        keys_layout = QVBoxLayout(tab_keys)
        txt_keys = QTextEdit()
        txt_keys.setReadOnly(True)
        txt_keys.setPlainText(
            "PINTASAN KEYBOARD MINTTUNE:\n"
            "----------------------------------------\n"
            "Spasi            : Play / Pause\n"
            "Ctrl + F         : Fokus ke Kotak Pencarian\n"
            "Ctrl + Kanan     : Lagu Berikutnya (Next)\n"
            "Ctrl + Kiri      : Lagu Sebelumnya (Previous)\n"
            "Panah Atas/Bawah : Navigasi Daftar Lagu\n"
            "Enter            : Putar Lagu yang Disorot\n"
            "Shift / Ctrl+Klik: Pilih Banyak Lagu Sekaligus"
        )
        keys_layout.addWidget(txt_keys)
        tabs.addTab(tab_keys, "⌨️ Pintasan Keyboard")

        btn_close = QPushButton("Tutup")
        btn_close.clicked.connect(self.accept)

        layout.addWidget(tabs)
        layout.addWidget(btn_close)

    def remove_missing_tracks(self):
        conn = get_connection()
        count = conn.execute("SELECT COUNT(*) FROM tracks WHERE missing=1").fetchone()[0]
        if count == 0:
            QMessageBox.information(self, "Bersih", "Tidak ada track berstatus 'missing' di database.")
            conn.close()
            return
        conn.execute("DELETE FROM playlist_tracks WHERE track_id IN (SELECT id FROM tracks WHERE missing=1)")
        conn.execute("DELETE FROM tracks WHERE missing=1")
        conn.commit()
        conn.close()
        self.library_updated.emit()
        QMessageBox.information(self, "Berhasil", f"{count} track hilang berhasil dibersihkan dari database.")

    def clear_artwork_cache(self):
        try:
            if CACHE_ARTWORK_DIR.exists():
                shutil.rmtree(CACHE_ARTWORK_DIR)
            CACHE_ARTWORK_DIR.mkdir(parents=True, exist_ok=True)
            QMessageBox.information(self, "Berhasil", "Cache thumbnail cover art berhasil dikosongkan!")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Gagal menghapus cache: {e}")

    def trigger_full_rescan(self):
        self.full_rescan_requested.emit()
        self.accept()
