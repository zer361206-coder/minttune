import os
from pathlib import Path
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, 
                             QComboBox, QCheckBox, QPushButton, QLineEdit, QFileDialog, 
                             QApplication)
from PyQt6.QtCore import pyqtSignal
from db.database import get_connection
from ui.theme import apply_mint_theme

ACCENT_OPTIONS = [
    ("Ikuti Sistem Linux Mint", ""),
    ("Hijau Mint (Default)", "#87ab63"),
    ("Teal", "#2ea586"),
    ("Aqua", "#3fa3b4"),
    ("Biru", "#417db7"),
    ("Oranye", "#e48a3c"),
    ("Ungu", "#905bb6"),
    ("Merah", "#d34141"),
]

THEME_OPTIONS = [
    ("Ikuti Sistem (Otomatis)", "system"),
    ("Mode Gelap (Dark)", "dark"),
    ("Mode Terang (Light)", "light"),
]

class SettingsDialog(QDialog):
    open_folders_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎛️ Pengaturan MintTune")
        self.resize(480, 310)
        self.conn = get_connection()
        self.init_ui()
        self.load_values()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.cmb_theme = QComboBox()
        for label, val in THEME_OPTIONS:
            self.cmb_theme.addItem(label, val)

        self.cmb_accent = QComboBox()
        for label, val in ACCENT_OPTIONS:
            self.cmb_accent.addItem(label, val)

        self.chk_auto_scan = QCheckBox("Pindai folder musik otomatis saat aplikasi dibuka")
        self.chk_resume = QCheckBox("Ingat & lanjutkan lagu terakhir saat aplikasi dibuka")

        btn_folders = QPushButton("⚙️ Buka Manajemen Folder (Whitelist & Blacklist)")
        btn_folders.clicked.connect(lambda: (self.accept(), self.open_folders_requested.emit()))

        form.addRow("Mode Tema:", self.cmb_theme)
        form.addRow("Warna Aksen:", self.cmb_accent)
        form.addRow("Pemindaian:", self.chk_auto_scan)
        form.addRow("Playback:", self.chk_resume)
        form.addRow("Folder Musik:", btn_folders)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Batal")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("💾 Simpan & Terapkan")
        btn_save.clicked.connect(self.save_and_apply)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)

        layout.addLayout(form)
        layout.addStretch()
        layout.addLayout(btn_layout)

    def get_setting(self, key, default):
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row['value'] if row else default

    def set_setting(self, key, value):
        self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

    def load_values(self):
        theme_mode = self.get_setting("theme_mode", "system")
        accent = self.get_setting("accent_color", "")
        auto_scan = self.get_setting("auto_scan", "True") == "True"
        resume = self.get_setting("resume_session", "True") == "True"

        idx_t = self.cmb_theme.findData(theme_mode)
        if idx_t >= 0: self.cmb_theme.setCurrentIndex(idx_t)

        idx_a = self.cmb_accent.findData(accent)
        if idx_a >= 0: self.cmb_accent.setCurrentIndex(idx_a)

        self.chk_auto_scan.setChecked(auto_scan)
        self.chk_resume.setChecked(resume)

    def save_and_apply(self):
        theme_mode = self.cmb_theme.currentData()
        accent = self.cmb_accent.currentData()
        auto_scan = str(self.chk_auto_scan.isChecked())
        resume = str(self.chk_resume.isChecked())

        self.set_setting("theme_mode", theme_mode)
        self.set_setting("accent_color", accent)
        self.set_setting("auto_scan", auto_scan)
        self.set_setting("resume_session", resume)
        self.conn.commit()
        self.conn.close()

        apply_mint_theme(QApplication.instance(), theme_mode, accent)
        self.accept()


class FirstRunDialog(QDialog):
    setup_completed = pyqtSignal(str, str) # folder_path, m3u_path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎵 Selamat Datang di MintTune!")
        self.resize(520, 280)
        self.conn = get_connection()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        lbl_welcome = QLabel("<b>Selamat datang di MintTune!</b><br>Atur folder musik dan tema Anda untuk memulai:")
        lbl_welcome.setWordWrap(True)
        layout.addWidget(lbl_welcome)

        form = QFormLayout()

        default_music = str(Path.home() / "Music")
        self.txt_folder = QLineEdit(default_music if os.path.exists(default_music) else "")
        btn_browse_folder = QPushButton("Pilih...")
        btn_browse_folder.clicked.connect(self.browse_folder)
        row_folder = QHBoxLayout()
        row_folder.addWidget(self.txt_folder)
        row_folder.addWidget(btn_browse_folder)

        self.cmb_theme = QComboBox()
        for label, val in THEME_OPTIONS:
            self.cmb_theme.addItem(label, val)

        self.txt_m3u = QLineEdit()
        self.txt_m3u.setPlaceholderText("(Opsional) Pilih file playlist .m3u")
        btn_browse_m3u = QPushButton("Impor...")
        btn_browse_m3u.clicked.connect(self.browse_m3u)
        row_m3u = QHBoxLayout()
        row_m3u.addWidget(self.txt_m3u)
        row_m3u.addWidget(btn_browse_m3u)

        form.addRow("Folder Musik Utama:", row_folder)
        form.addRow("Tema Aplikasi:", self.cmb_theme)
        form.addRow("Impor Playlist M3U:", row_m3u)
        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_skip = QPushButton("Lewati")
        btn_skip.clicked.connect(self.skip_setup)
        btn_start = QPushButton("🚀 Mulai Sekarang")
        btn_start.clicked.connect(self.finish_setup)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_skip)
        btn_layout.addWidget(btn_start)
        layout.addLayout(btn_layout)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder Musik")
        if folder:
            self.txt_folder.setText(folder)

    def browse_m3u(self):
        m3u, _ = QFileDialog.getOpenFileName(self, "Pilih File Playlist M3U", "", "Playlist (*.m3u *.m3u8)")
        if m3u:
            self.txt_m3u.setText(m3u)

    def skip_setup(self):
        self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('first_run_done', 'True')")
        self.conn.commit()
        self.conn.close()
        self.reject()

    def finish_setup(self):
        folder = self.txt_folder.text().strip()
        theme_mode = self.cmb_theme.currentData()
        m3u = self.txt_m3u.text().strip()

        if folder and os.path.exists(folder):
            canonical = os.path.realpath(folder)
            self.conn.execute(
                "INSERT OR IGNORE INTO library_folders (path, type, enabled) VALUES (?, 'whitelist', 1)",
                (canonical,)
            )
        self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('theme_mode', ?)", (theme_mode,))
        self.conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('first_run_done', 'True')")
        self.conn.commit()
        self.conn.close()

        apply_mint_theme(QApplication.instance(), theme_mode, "")
        self.setup_completed.emit(folder, m3u)
        self.accept()
