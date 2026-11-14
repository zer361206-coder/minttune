import os
import sys
import argparse

os.environ["VK_ICD_FILENAMES"] = ""
os.environ["VK_DRIVER_FILES"] = ""
os.environ["QT_LOGGING_RULES"] = "*.debug=false"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication
from db.database import init_db, get_connection
from core.logger import setup_logger
from ui.main_window import MainWindow
from ui.theme import apply_mint_theme
from ui.diagnostics_dialog import collect_diagnostics_report

VERSION = "1.0.0"

def main():
    logger = setup_logger()
    parser = argparse.ArgumentParser(description="MintTune - Pemutar Musik Native Linux Mint")
    parser.add_argument("--version", action="store_true", help="Tampilkan versi aplikasi")
    parser.add_argument("--diagnostics", action="store_true", help="Periksa dependensi GStreamer dan codec")
    parser.add_argument("--scan", action="store_true", help="Jalankan pemindaian library lewat CLI")
    args = parser.parse_args()

    if args.version:
        print(f"MintTune v{VERSION}")
        sys.exit(0)

    init_db()

    if args.diagnostics:
        _ = QCoreApplication(sys.argv)
        print(collect_diagnostics_report())
        sys.exit(0)

    if args.scan:
        _ = QCoreApplication(sys.argv)
        from core.library_scanner import LibraryScanner
        logger.info("Menjalankan full scan dari CLI")
        print("Memulai pemindaian library MintTune...")
        scanner = LibraryScanner(full_rescan=True)
        scanner.run()
        print(f"Pemindaian selesai: {scanner.stats}")
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setApplicationName("MintTune")

    # Baca preferensi tema tersimpan
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM settings WHERE key IN ('theme_mode', 'accent_color')").fetchall()
    prefs = {r['key']: r['value'] for r in rows}
    conn.close()

    apply_mint_theme(app, prefs.get('theme_mode', 'system'), prefs.get('accent_color', ''))

    logger.info("MintTune GUI dimulai")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
