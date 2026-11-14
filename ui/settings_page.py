import os
import shutil
import subprocess
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
                             QPushButton, QCheckBox, QListWidget, QListWidgetItem, 
                             QFileDialog, QInputDialog, QMessageBox, QStackedWidget, 
                             QScrollArea, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPalette
from db.database import get_connection
from ui.theme import apply_mint_theme
from ui.widgets import make_refresh_icon

CACHE_ARTWORK_DIR = Path(os.getenv('XDG_CACHE_HOME', Path.home() / '.cache')) / 'minttune' / 'artwork'

ACCENT_SWATCHES = [
    ("Sistem", ""),
    ("Mint", "#87ab63"),
    ("Teal", "#2ea586"),
    ("Aqua", "#3fa3b4"),
    ("Biru", "#417db7"),
    ("Ungu", "#905bb6"),
    ("Pink", "#e91e63"),
    ("Oranye", "#e48a3c"),
    ("Merah", "#d34141"),
]

class SettingsPage(QWidget):
    folders_changed = pyqtSignal()
    library_updated = pyqtSignal()
    full_rescan_requested = pyqtSignal()
    theme_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.conn = get_connection()
        self.theme_buttons = {}
        self.swatch_buttons = {}
        self.init_ui()
        self.load_all_data()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(12)

        # --- BARIS PILL TAB ALA DRIBBBLE ---
        tab_bar = QHBoxLayout()
        tab_bar.setSpacing(8)
        self.btn_tab_general = QPushButton("🎨 Tampilan & Umum")
        self.btn_tab_folders = QPushButton("📁 Folder Musik")
        self.btn_tab_keys = QPushButton("⌨️ Pintasan")

        self.tab_buttons = [self.btn_tab_general, self.btn_tab_folders, self.btn_tab_keys]
        for idx, b in enumerate(self.tab_buttons):
            b.setObjectName("tabPill")
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _, i=idx: self.switch_tab(i))
            tab_bar.addWidget(b)
        tab_bar.addStretch()

        self.stack = QStackedWidget()

        # =========================================================
        # TAB 0: TAMPILAN & UMUM
        # =========================================================
        scroll_gen = QScrollArea()
        scroll_gen.setWidgetResizable(True)
        gen_wrap = QWidget()
        gen_l = QVBoxLayout(gen_wrap)
        gen_l.setContentsMargins(0, 0, 4, 4)
        gen_l.setSpacing(12)

        # Card 1: Tema & Warna Aksen
        card_theme = QFrame()
        card_theme.setObjectName("innerCard")
        ct_l = QVBoxLayout(card_theme)
        ct_l.setContentsMargins(18, 16, 18, 16)
        ct_l.setSpacing(12)

        lbl_t_title = QLabel("Tema & Warna Aksen")
        lbl_t_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        lbl_t_sub = QLabel("Sesuaikan tampilan MintTune agar selaras dengan desktop Linux Mint Anda.")
        lbl_t_sub.setStyleSheet("font-size: 12px;")

        lbl_mode = QLabel("Mode Tema:")
        lbl_mode.setStyleSheet("font-weight: bold; font-size: 12px;")
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        for label, val in [("🖥️ Ikuti Sistem", "system"), ("🌙 Mode Gelap", "dark"), ("☀️ Mode Terang", "light")]:
            btn = QPushButton(label)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _, v=val: self.set_theme_mode(v))
            self.theme_buttons[val] = btn
            mode_row.addWidget(btn)
        mode_row.addStretch()

        lbl_accent = QLabel("Warna Aksen (Accent Color):")
        lbl_accent.setStyleSheet("font-weight: bold; font-size: 12px; margin-top: 4px;")
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(10)
        for name, hex_val in ACCENT_SWATCHES:
            btn = QPushButton("🖥️" if not hex_val else "")
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setFixedSize(32, 32)
            btn.setToolTip(f"Warna Aksen: {name}")
            btn.clicked.connect(lambda _, h=hex_val: self.set_accent_color(h))
            self.swatch_buttons[hex_val] = btn
            swatch_row.addWidget(btn)
        swatch_row.addStretch()

        ct_l.addWidget(lbl_t_title)
        ct_l.addWidget(lbl_t_sub)
        ct_l.addWidget(lbl_mode)
        ct_l.addLayout(mode_row)
        ct_l.addWidget(lbl_accent)
        ct_l.addLayout(swatch_row)

        # Card 2: Perilaku Pemutar & Pemindaian
        card_behav = QFrame()
        card_behav.setObjectName("innerCard")
        cb_l = QVBoxLayout(card_behav)
        cb_l.setContentsMargins(18, 16, 18, 16)
        cb_l.setSpacing(10)

        lbl_b_title = QLabel("Perilaku Aplikasi")
        lbl_b_title.setStyleSheet("font-size: 15px; font-weight: bold;")

        self.chk_auto_scan = QCheckBox("Pindai folder musik otomatis (incremental) saat aplikasi dibuka")
        self.chk_auto_scan.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.chk_auto_scan.toggled.connect(lambda checked: self.save_setting("auto_scan", str(checked)))

        self.chk_resume = QCheckBox("Ingat & lanjutkan lagu serta posisi detik terakhir saat dibuka kembali")
        self.chk_resume.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.chk_resume.toggled.connect(lambda checked: self.save_setting("resume_session", str(checked)))

        cb_l.addWidget(lbl_b_title)
        cb_l.addWidget(self.chk_auto_scan)
        cb_l.addWidget(self.chk_resume)

        gen_l.addWidget(card_theme)
        gen_l.addWidget(card_behav)
        gen_l.addStretch()
        scroll_gen.setWidget(gen_wrap)

        # =========================================================
        # TAB 1: FOLDER MUSIK (WHITELIST & BLACKLIST)
        # =========================================================
        folders_tab = QWidget()
        ft_l = QVBoxLayout(folders_tab)
        ft_l.setContentsMargins(0, 0, 0, 0)
        ft_l.setSpacing(10)

        cols = QHBoxLayout()
        cols.setSpacing(12)

        # Card Whitelist
        wl_card = QFrame()
        wl_card.setObjectName("innerCard")
        wl_l = QVBoxLayout(wl_card)
        wl_l.setContentsMargins(14, 14, 14, 14)
        lbl_wl = QLabel("✅ Folder Dipindai (Whitelist)")
        lbl_wl.setStyleSheet("font-size: 14px; font-weight: bold;")
        lbl_wl_sub = QLabel("Hanya lagu di dalam folder ini yang masuk library.")
        lbl_wl_sub.setStyleSheet("font-size: 11px;")
        self.list_whitelist = QListWidget()
        self.list_whitelist.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_whitelist.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        wl_btns = QHBoxLayout()
        btn_add_wl = QPushButton("➕ Tambah")
        btn_add_wl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_add_wl.clicked.connect(self.add_whitelist_folder)
        btn_open_wl = QPushButton("📂 Buka")
        btn_open_wl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_open_wl.clicked.connect(self.open_selected_whitelist)
        btn_del_wl = QPushButton("🗑️ Hapus")
        btn_del_wl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_del_wl.clicked.connect(self.delete_selected_whitelist)
        wl_btns.addWidget(btn_add_wl)
        wl_btns.addWidget(btn_open_wl)
        wl_btns.addWidget(btn_del_wl)

        wl_l.addWidget(lbl_wl)
        wl_l.addWidget(lbl_wl_sub)
        wl_l.addWidget(self.list_whitelist, stretch=1)
        wl_l.addLayout(wl_btns)

        # Card Blacklist
        bl_card = QFrame()
        bl_card.setObjectName("innerCard")
        bl_l = QVBoxLayout(bl_card)
        bl_l.setContentsMargins(14, 14, 14, 14)
        lbl_bl = QLabel("🚫 Dikecualikan (Blacklist)")
        lbl_bl.setStyleSheet("font-size: 14px; font-weight: bold;")
        lbl_bl_sub = QLabel("Folder/pola ini dilewati dan tidak akan dipindai.")
        lbl_bl_sub.setStyleSheet("font-size: 11px;")
        self.list_blacklist = QListWidget()
        self.list_blacklist.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_blacklist.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        bl_btns = QHBoxLayout()
        btn_add_bl = QPushButton("🚫 Folder")
        btn_add_bl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_add_bl.clicked.connect(self.add_blacklist_folder)
        btn_add_pat = QPushButton("⚙️ Pola")
        btn_add_pat.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_add_pat.clicked.connect(self.add_blacklist_pattern)
        btn_del_bl = QPushButton("🗑️ Hapus")
        btn_del_bl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_del_bl.clicked.connect(self.delete_selected_blacklist)
        bl_btns.addWidget(btn_add_bl)
        bl_btns.addWidget(btn_add_pat)
        bl_btns.addWidget(btn_del_bl)

        bl_l.addWidget(lbl_bl)
        bl_l.addWidget(lbl_bl_sub)
        bl_l.addWidget(self.list_blacklist, stretch=1)
        bl_l.addLayout(bl_btns)

        cols.addWidget(wl_card, stretch=1)
        cols.addWidget(bl_card, stretch=1)

        footer_f = QHBoxLayout()
        lbl_warn = QLabel("Catatan: Menghapus folder dari daftar tidak menghapus file audio di harddisk Anda.")
        lbl_warn.setStyleSheet("font-size: 11px;")
        btn_scan_now = QPushButton(" Pindai Ulang Sekarang")
        btn_scan_now.setIcon(make_refresh_icon(QApplication.palette().color(QPalette.ColorRole.WindowText), 18))
        btn_scan_now.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_scan_now.clicked.connect(self.folders_changed.emit)
        footer_f.addWidget(lbl_warn)
        footer_f.addStretch()
        footer_f.addWidget(btn_scan_now)

        ft_l.addLayout(cols, stretch=1)
        ft_l.addLayout(footer_f)

        # =========================================================
        # TAB 2: PINTASAN KEYBOARD
        # =========================================================
        keys_tab = QWidget()
        kt_l = QVBoxLayout(keys_tab)
        kt_l.setContentsMargins(0, 0, 0, 0)
        keys_card = QFrame()
        keys_card.setObjectName("innerCard")
        kc_l = QVBoxLayout(keys_card)
        kc_l.setContentsMargins(20, 18, 20, 18)

        lbl_k_title = QLabel("Pintasan Keyboard MintTune")
        lbl_k_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        txt_keys = QLabel(
            "<table cellspacing='10'>"
            "<tr><td><b>Spasi</b></td><td>Putar / Jeda lagu (Play / Pause)</td></tr>"
            "<tr><td><b>Ctrl + F</b></td><td>Fokus ke kotak pencarian lagu</td></tr>"
            "<tr><td><b>Ctrl + Panah Kanan</b></td><td>Lagu berikutnya (Next)</td></tr>"
            "<tr><td><b>Ctrl + Panah Kiri</b></td><td>Lagu sebelumnya (Previous)</td></tr>"
            "<tr><td><b>Panah Atas / Bawah</b></td><td>Navigasi baris lagu di tabel</td></tr>"
            "<tr><td><b>Enter</b></td><td>Putar lagu yang sedang disorot</td></tr>"
            "<tr><td><b>Shift / Ctrl + Klik</b></td><td>Pilih banyak lagu sekaligus</td></tr>"
            "<tr><td><b>Esc</b></td><td>Keluar dari mode layar penuh Now Playing</td></tr>"
            "</table>"
        )
        txt_keys.setStyleSheet("font-size: 13px;")
        kc_l.addWidget(lbl_k_title)
        kc_l.addSpacing(8)
        kc_l.addWidget(txt_keys)
        kc_l.addStretch()
        kt_l.addWidget(keys_card)

        self.stack.addWidget(scroll_gen)
        self.stack.addWidget(folders_tab)
        self.stack.addWidget(keys_tab)

        layout.addLayout(tab_bar)
        layout.addWidget(self.stack, stretch=1)
        self.switch_tab(0)

    def switch_tab(self, index: int):
        if index >= len(self.tab_buttons):
            index = 0
        self.stack.setCurrentIndex(index)
        for i, b in enumerate(self.tab_buttons):
            b.setObjectName("tabPillActive" if i == index else "tabPill")
            b.style().unpolish(b)
            b.style().polish(b)
        if index == 1:
            self.load_folders()

    def get_setting(self, key, default):
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row['value'] if row else default

    def save_setting(self, key, value):
        self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        self.conn.commit()

    def load_all_data(self):
        self.chk_auto_scan.blockSignals(True)
        self.chk_resume.blockSignals(True)
        self.chk_auto_scan.setChecked(self.get_setting("auto_scan", "True") == "True")
        self.chk_resume.setChecked(self.get_setting("resume_session", "True") == "True")
        self.chk_auto_scan.blockSignals(False)
        self.chk_resume.blockSignals(False)
        self.refresh_theme_buttons(); self.theme_changed.emit()
        self.load_folders()
        self.refresh_diagnostics()

    def refresh_theme_buttons(self):
        cur_mode = self.get_setting("theme_mode", "system")
        cur_accent = self.get_setting("accent_color", "")

        for mode, btn in self.theme_buttons.items():
            if mode == cur_mode:
                btn.setStyleSheet("background-color: palette(highlight); color: palette(highlighted-text); font-weight: bold;")
            else:
                btn.setStyleSheet("")

        for hex_val, btn in self.swatch_buttons.items():
            border = "3px solid palette(window-text)" if hex_val == cur_accent else "1px solid palette(mid)"
            bg = hex_val if hex_val else "palette(button)"
            btn.setStyleSheet(f"background-color: {bg}; border: {border}; border-radius: 16px; padding: 0px;")

    def set_theme_mode(self, mode):
        self.save_setting("theme_mode", mode)
        accent = self.get_setting("accent_color", "")
        apply_mint_theme(QApplication.instance(), mode, accent)
        self.refresh_theme_buttons(); self.theme_changed.emit()

    def set_accent_color(self, hex_val):
        self.save_setting("accent_color", hex_val)
        mode = self.get_setting("theme_mode", "system")
        apply_mint_theme(QApplication.instance(), mode, hex_val)
        self.refresh_theme_buttons(); self.theme_changed.emit()

    def load_folders(self):
        self.list_whitelist.clear()
        self.list_blacklist.clear()
        for row in self.conn.execute("SELECT id, path FROM library_folders WHERE type='whitelist' AND enabled=1").fetchall():
            item = QListWidgetItem(f"📁  {row['path']}")
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            item.setData(Qt.ItemDataRole.UserRole + 1, row['path'])
            self.list_whitelist.addItem(item)
        for row in self.conn.execute("SELECT id, path, pattern FROM library_folders WHERE type='blacklist' AND enabled=1").fetchall():
            disp = f"🚫  {row['path']}" if row['path'] else f"⚙️  Pola: {row['pattern']}"
            item = QListWidgetItem(disp)
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            self.list_blacklist.addItem(item)

    def add_whitelist_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder Musik untuk Whitelist")
        if folder:
            canonical = os.path.realpath(folder)
            try:
                self.conn.execute("INSERT INTO library_folders (path, type, enabled) VALUES (?, 'whitelist', 1)", (canonical,))
                self.conn.commit()
                self.load_folders()
                self.folders_changed.emit()
            except Exception:
                QMessageBox.warning(self, "Peringatan", "Folder ini sudah ada di Whitelist!")

    def open_selected_whitelist(self):
        item = self.list_whitelist.currentItem()
        if item:
            path = item.data(Qt.ItemDataRole.UserRole + 1)
            if os.path.exists(path):
                subprocess.Popen(['xdg-open', path])

    def delete_selected_whitelist(self):
        item = self.list_whitelist.currentItem()
        if not item: return
        fid = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "Konfirmasi", "Hapus folder ini dari Whitelist?\n(File musik asli di harddisk Anda tetap aman)") == QMessageBox.StandardButton.Yes:
            self.conn.execute("DELETE FROM library_folders WHERE id=?", (fid,))
            self.conn.commit()
            self.load_folders()
            self.folders_changed.emit()

    def add_blacklist_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder untuk Dikecualikan (Blacklist)")
        if folder:
            canonical = os.path.realpath(folder)
            try:
                self.conn.execute("INSERT INTO library_folders (path, type, enabled) VALUES (?, 'blacklist', 1)", (canonical,))
                self.conn.commit()
                self.load_folders()
                self.folders_changed.emit()
            except Exception:
                QMessageBox.warning(self, "Peringatan", "Folder ini sudah ada di Blacklist!")

    def add_blacklist_pattern(self):
        pattern, ok = QInputDialog.getText(self, "Tambah Pola Blacklist", "Masukkan pola nama file/folder:\n(Contoh: *.tmp, *sample*, .hidden)")
        if ok and pattern.strip():
            self.conn.execute("INSERT INTO library_folders (pattern, type, enabled) VALUES (?, 'blacklist', 1)", (pattern.strip(),))
            self.conn.commit()
            self.load_folders()
            self.folders_changed.emit()

    def delete_selected_blacklist(self):
        item = self.list_blacklist.currentItem()
        if not item: return
        self.conn.execute("DELETE FROM library_folders WHERE id=?", (item.data(Qt.ItemDataRole.UserRole),))
        self.conn.commit()
        self.load_folders()
        self.folders_changed.emit()

    def refresh_diagnostics(self):
        pass

    def remove_missing_tracks(self):
        count = self.conn.execute("SELECT COUNT(*) FROM tracks WHERE missing=1").fetchone()[0]
        if count == 0:
            QMessageBox.information(self, "Bersih", "Tidak ada track berstatus 'missing' di database.")
            return
        self.conn.execute("DELETE FROM playlist_tracks WHERE track_id IN (SELECT id FROM tracks WHERE missing=1)")
        self.conn.execute("DELETE FROM tracks WHERE missing=1")
        self.conn.commit()
        self.library_updated.emit()
        self.refresh_diagnostics()
        QMessageBox.information(self, "Berhasil", f"{count} track hilang dibersihkan dari database.")

    def clear_artwork_cache(self):
        try:
            if CACHE_ARTWORK_DIR.exists():
                shutil.rmtree(CACHE_ARTWORK_DIR)
            CACHE_ARTWORK_DIR.mkdir(parents=True, exist_ok=True)
            QMessageBox.information(self, "Berhasil", "Cache thumbnail cover art dikosongkan!")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Gagal menghapus cache: {e}")
