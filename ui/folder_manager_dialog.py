import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTabWidget, QListWidget, QListWidgetItem, QFileDialog, 
                             QInputDialog, QMessageBox, QLabel, QWidget)
from PyQt6.QtCore import Qt, pyqtSignal
from db.database import get_connection

class FolderManagerDialog(QDialog):
    folders_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kelola Folder Musik (Whitelist & Blacklist)")
        self.resize(600, 420)
        self.conn = get_connection()
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()

        # --- TAB 1: WHITELIST (FOLDER TERMASUK) ---
        tab_whitelist = QWidget()
        wl_layout = QVBoxLayout(tab_whitelist)
        wl_info = QLabel("Folder di bawah ini akan dipindai secara otomatis ke daftar lagu:")
        wl_info.setWordWrap(True)
        self.list_whitelist = QListWidget()

        wl_btn_layout = QHBoxLayout()
        btn_add_wl = QPushButton("➕ Tambah Folder (Whitelist)")
        btn_add_wl.clicked.connect(self.add_whitelist_folder)
        btn_del_wl = QPushButton("🗑️ Hapus Terpilih")
        btn_del_wl.clicked.connect(self.delete_selected_whitelist)
        wl_btn_layout.addWidget(btn_add_wl)
        wl_btn_layout.addWidget(btn_del_wl)

        wl_layout.addWidget(wl_info)
        wl_layout.addWidget(self.list_whitelist)
        wl_layout.addLayout(wl_btn_layout)

        # --- TAB 2: BLACKLIST (FOLDER DIKECUALIKAN) ---
        tab_blacklist = QWidget()
        bl_layout = QVBoxLayout(tab_blacklist)
        bl_info = QLabel("Folder atau pola di bawah ini AKAN DILEWATI dan tidak akan muncul di aplikasi:")
        bl_info.setWordWrap(True)
        self.list_blacklist = QListWidget()

        bl_btn_layout = QHBoxLayout()
        btn_add_bl_folder = QPushButton("🚫 Tambah Folder Blacklist")
        btn_add_bl_folder.clicked.connect(self.add_blacklist_folder)
        btn_add_bl_pattern = QPushButton("⚙️ Tambah Pola (Pattern)")
        btn_add_bl_pattern.clicked.connect(self.add_blacklist_pattern)
        btn_del_bl = QPushButton("🗑️ Hapus")
        btn_del_bl.clicked.connect(self.delete_selected_blacklist)
        bl_btn_layout.addWidget(btn_add_bl_folder)
        bl_btn_layout.addWidget(btn_add_bl_pattern)
        bl_btn_layout.addWidget(btn_del_bl)

        bl_layout.addWidget(bl_info)
        bl_layout.addWidget(self.list_blacklist)
        bl_layout.addLayout(bl_btn_layout)

        self.tabs.addTab(tab_whitelist, "✅ Folder Musik (Whitelist)")
        self.tabs.addTab(tab_blacklist, "🚫 Pengecualian (Blacklist)")

        # Tombol Bawah
        bottom_layout = QHBoxLayout()
        btn_close = QPushButton("Tutup")
        btn_close.clicked.connect(self.accept)
        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_close)

        layout.addWidget(self.tabs)
        layout.addLayout(bottom_layout)

    def load_data(self):
        self.list_whitelist.clear()
        self.list_blacklist.clear()
        cursor = self.conn.cursor()

        # Ambil Whitelist
        cursor.execute("SELECT id, path FROM library_folders WHERE type='whitelist' AND enabled=1")
        for row in cursor.fetchall():
            item = QListWidgetItem(f"📁 {row['path']}")
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            self.list_whitelist.addItem(item)

        # Ambil Blacklist
        cursor.execute("SELECT id, path, pattern FROM library_folders WHERE type='blacklist' AND enabled=1")
        for row in cursor.fetchall():
            display = f"🚫 {row['path']}" if row['path'] else f"⚙️ Pola: {row['pattern']}"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            self.list_blacklist.addItem(item)

    def add_whitelist_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder Musik untuk Whitelist")
        if folder:
            canonical_path = os.path.realpath(folder)
            try:
                cursor = self.conn.cursor()
                cursor.execute(
                    "INSERT INTO library_folders (path, type, enabled) VALUES (?, 'whitelist', 1)", 
                    (canonical_path,)
                )
                self.conn.commit()
                self.load_data()
                self.folders_changed.emit()
            except Exception:
                QMessageBox.warning(self, "Peringatan", "Folder ini sudah ada di dalam daftar!")

    def delete_selected_whitelist(self):
        current_item = self.list_whitelist.currentItem()
        if not current_item: return
        folder_id = current_item.data(Qt.ItemDataRole.UserRole)
        
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM library_folders WHERE id=?", (folder_id,))
        self.conn.commit()
        self.load_data()
        self.folders_changed.emit()

    def add_blacklist_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Pilih Folder untuk Dikecualikan (Blacklist)")
        if folder:
            canonical_path = os.path.realpath(folder)
            try:
                cursor = self.conn.cursor()
                cursor.execute(
                    "INSERT INTO library_folders (path, type, enabled) VALUES (?, 'blacklist', 1)", 
                    (canonical_path,)
                )
                self.conn.commit()
                self.load_data()
                self.folders_changed.emit()
            except Exception:
                QMessageBox.warning(self, "Peringatan", "Folder ini sudah ada di daftar blacklist!")

    def add_blacklist_pattern(self):
        pattern, ok = QInputDialog.getText(
            self, "Tambah Pola Blacklist", 
            "Masukkan pola nama file/folder yang ingin diabaikan:\n(Contoh: *.bak, *sample*, .hidden)"
        )
        if ok and pattern.strip():
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO library_folders (pattern, type, enabled) VALUES (?, 'blacklist', 1)", 
                (pattern.strip(),)
            )
            self.conn.commit()
            self.load_data()
            self.folders_changed.emit()

    def delete_selected_blacklist(self):
        current_item = self.list_blacklist.currentItem()
        if not current_item: return
        folder_id = current_item.data(Qt.ItemDataRole.UserRole)
        
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM library_folders WHERE id=?", (folder_id,))
        self.conn.commit()
        self.load_data()
        self.folders_changed.emit()
