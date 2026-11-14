import os
import subprocess
import time
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QSlider, QLabel, QTableView, QFrame,
                             QMessageBox, QLineEdit, QMenu, QApplication, 
                             QListWidget, QListWidgetItem, QInputDialog, QFileDialog,
                             QSystemTrayIcon, QStackedWidget, QHeaderView, QScrollArea)
from PyQt6.QtCore import Qt, QSortFilterProxyModel, QEvent, QSize, QTimer
from PyQt6.QtGui import QAction, QColor, QIcon, QPixmap, QPalette
from PyQt6.QtMultimedia import QMediaPlayer
from core.logger import setup_logger
from core.playback_service import PlaybackService
from core.library_scanner import LibraryScanner
from ui.settings_dialog import FirstRunDialog
from ui.settings_page import SettingsPage
from ui.widgets import (format_time, generate_fallback_cover, generate_playlist_badge,
                        get_cached_cover_pixmap, round_pixmap,
                        make_media_icon, make_playlist_icon, make_artist_icon, make_search_icon, make_refresh_icon,
                        make_settings_icon, make_folder_icon, make_album_icon, make_home_icon, make_songs_icon,
                        make_favorites_icon, render_favorites_svg_pixmap, make_fire_icon, render_fire_svg_pixmap,
                        TrackInfoDialog, TrackTableModel,
                        AmbientNowPlayingPage)
from db.database import get_connection

logger = setup_logger()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MintTune")
        self.resize(1240, 770)
        self.setWindowIcon(QIcon.fromTheme("multimedia-audio-player"))

        self.conn = get_connection()
        self.playback = PlaybackService()
        self.tracks = []
        self.recent_tracks = []
        self.current_duration = 0
        self.current_position_ms = 0
        self.is_playing = False
        self.is_muted = False
        self.view_mode = 'home'
        self.view_param = None
        self.active_dock_btn = None
        
        self.init_ui()
        self.set_active_dock(self.btn_nav_home)
        self.refresh_player_icons()
        self.setup_system_tray()
        self.load_settings()
        self.load_playlists()
        self.load_library()
        self.refresh_home_view()
        self.restore_last_session()
        
        self.playback.track_changed.connect(self.update_now_playing)
        self.playback.track_played.connect(self.record_play_stats)
        self.playback.position_changed.connect(self.update_progress)
        self.playback.state_changed.connect(self.update_play_button_text)
        self.playback.queue_updated.connect(self.update_queue_ui)
        self.playback.playback_error.connect(self.on_playback_error)

        QApplication.instance().installEventFilter(self)
        QTimer.singleShot(300, self.startup_tasks)

    def startup_tasks(self):
        wl_count = self.conn.execute("SELECT COUNT(*) FROM library_folders WHERE type='whitelist'").fetchone()[0]
        first_done = self.get_setting("first_run_done", "False") == "True"
        if wl_count == 0 and not first_done:
            dlg = FirstRunDialog(self)
            dlg.setup_completed.connect(self.on_first_run_completed)
            dlg.exec()
            self.settings_page.load_all_data()
            self.refresh_player_icons()
        elif self.get_setting("auto_scan", "True") == "True" and wl_count > 0:
            self.run_scanner(False)

    def on_first_run_completed(self, folder_path, m3u_path):
        self.run_scanner(False)
        if m3u_path and os.path.exists(m3u_path):
            self._import_m3u_file(m3u_path)

    def setup_system_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon.fromTheme("multimedia-audio-player"))
        tray_menu = QMenu()
        tray_menu.addAction(QAction("Tampilkan Aplikasi", self, triggered=self.showNormal))
        tray_menu.addSeparator()
        tray_menu.addAction(QAction("⏯ Play / Pause", self, triggered=self.playback.play_pause))
        tray_menu.addAction(QAction("⏭ Next Track", self, triggered=self.playback.next_track))
        tray_menu.addSeparator()
        tray_menu.addAction(QAction("❌ Keluar MintTune", self, triggered=self.quit_app))
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.on_tray_activated)

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def closeEvent(self, event):
        self.save_last_session()
        if self.tray_icon.isVisible():
            self.hide()
            self.tray_icon.showMessage("MintTune", "Berjalan di latar belakang.", QSystemTrayIcon.MessageIcon.Information, 2000)
            event.ignore()
        else:
            event.accept()

    def quit_app(self):
        self.save_last_session()
        self.tray_icon.hide()
        QApplication.quit()

    def save_setting(self, key, value):
        self.conn.cursor().execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        self.conn.commit()

    def get_setting(self, key, default):
        row = self.conn.cursor().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row['value'] if row else default

    def save_last_session(self):
        if self.playback.current_track:
            self.save_setting("last_track_id", self.playback.current_track.get('id', ''))
            self.save_setting("last_position_ms", self.current_position_ms)

    def restore_last_session(self):
        if self.get_setting("resume_session", "True") != "True":
            return
        last_id = self.get_setting("last_track_id", "")
        last_pos = int(self.get_setting("last_position_ms", 0))
        if last_id:
            row = self.conn.cursor().execute("SELECT * FROM tracks WHERE id = ?", (last_id,)).fetchone()
            if row:
                track = dict(row)
                self.playback.queue = self.tracks
                for i, t in enumerate(self.tracks):
                    if t['id'] == track['id']:
                        self.playback.current_index = i
                        break
                self.playback.prepare_track(track, last_pos)

    def load_settings(self):
        vol = int(self.get_setting("volume", 100))
        self.slider_volume.setValue(vol)
        self.playback.set_volume(vol)
        if self.get_setting("shuffle", "False") == "True":
            self.on_toggle_shuffle()
        for _ in range(int(self.get_setting("repeat", 0))):
            self.on_toggle_repeat()

    def init_ui(self):
        self.main_stack = QStackedWidget()
        self.setCentralWidget(self.main_stack)

        workspace = QWidget()
        ws_layout = QHBoxLayout(workspace)
        ws_layout.setContentsMargins(10, 10, 10, 10)
        ws_layout.setSpacing(10)

        # =========================================================
        # 1. FAR-LEFT SLIM ICON DOCK
        # =========================================================
        dock_col = QVBoxLayout()
        dock_col.setSpacing(8)

        nav_card = QFrame()
        nav_card.setObjectName("bentoCard")
        nav_card.setFixedWidth(60)
        nav_l = QVBoxLayout(nav_card)
        nav_l.setContentsMargins(6, 8, 6, 8)
        nav_l.setSpacing(6)

        self.btn_nav_home = QPushButton()
        self.btn_nav_home.setIconSize(QSize(24, 24))
        self.btn_nav_home.setToolTip("Beranda (Home)")
        self.btn_nav_songs = QPushButton()
        self.btn_nav_songs.setIconSize(QSize(24, 24))
        self.btn_nav_songs.setToolTip("Semua Lagu")
        self.btn_nav_albums = QPushButton()
        self.btn_nav_albums.setIconSize(QSize(24, 24))
        self.btn_nav_albums.setToolTip("Galeri Album")
        self.btn_nav_artists = QPushButton()
        self.btn_nav_artists.setIconSize(QSize(24, 24))
        self.btn_nav_artists.setToolTip("Artis")

        # TAB PLAYLIST DENGAN IKON SVG VEKTOR DARI FILE .TXT!
        self.btn_nav_playlists = QPushButton()
        self.btn_nav_playlists.setIconSize(QSize(24, 24))
        self.btn_nav_playlists.setToolTip("Daftar Playlist")

        self.btn_nav_search = QPushButton()
        self.btn_nav_search.setIconSize(QSize(24, 24))
        self.btn_nav_search.setToolTip("Cari Lagu (Ctrl+F)")

        for b in (self.btn_nav_home, self.btn_nav_songs, self.btn_nav_albums,
                  self.btn_nav_artists, self.btn_nav_playlists, self.btn_nav_search):
            b.setObjectName("dockBtn")
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setFixedSize(44, 40)
            nav_l.addWidget(b, alignment=Qt.AlignmentFlag.AlignCenter)

        self.btn_nav_home.clicked.connect(self.show_home_view)
        self.btn_nav_songs.clicked.connect(self.show_all_songs)
        self.btn_nav_albums.clicked.connect(self.show_albums_view)
        self.btn_nav_artists.clicked.connect(self.show_artists_view)
        self.btn_nav_playlists.clicked.connect(self.show_playlists_page)
        self.btn_nav_search.clicked.connect(lambda: (self.show_all_songs(), self.search_bar.setFocus(), self.search_bar.selectAll()))

        pl_card = QFrame()
        pl_card.setObjectName("bentoCard")
        pl_card.setFixedWidth(60)
        pl_l = QVBoxLayout(pl_card)
        pl_l.setContentsMargins(4, 8, 4, 8)
        pl_l.setSpacing(6)

        self.btn_nav_fav = QPushButton()
        self.btn_nav_fav.setIconSize(QSize(24, 24))
        self.btn_nav_fav.setObjectName("dockBtn")
        self.btn_nav_fav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_nav_fav.setFixedSize(44, 40)
        self.btn_nav_fav.setToolTip("Lagu Favorit")
        self.btn_nav_fav.clicked.connect(self.show_favorites_view)

        self.btn_nav_hot = QPushButton()
        self.btn_nav_hot.setIconSize(QSize(24, 24))
        self.btn_nav_hot.setObjectName("dockBtn")
        self.btn_nav_hot.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_nav_hot.setFixedSize(44, 40)
        self.btn_nav_hot.setToolTip("Sering Diputar (Top 50)")
        self.btn_nav_hot.clicked.connect(self.show_most_played_view)

        self.list_playlists = QListWidget()
        self.list_playlists.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_playlists.setIconSize(QSize(38, 38))
        self.list_playlists.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_playlists.itemClicked.connect(self.on_playlist_clicked)
        self.list_playlists.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_playlists.customContextMenuRequested.connect(self.show_playlist_context_menu)

        btn_add_pl = QPushButton("＋")
        btn_add_pl.setObjectName("dockBtn")
        btn_add_pl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_add_pl.setFixedSize(44, 36)
        btn_add_pl.setToolTip("Buat Playlist Baru / Impor M3U")
        btn_add_pl.clicked.connect(self.show_create_or_import_menu)

        pl_l.addWidget(self.btn_nav_fav, alignment=Qt.AlignmentFlag.AlignCenter)
        pl_l.addWidget(self.btn_nav_hot, alignment=Qt.AlignmentFlag.AlignCenter)
        pl_l.addWidget(self.list_playlists)
        pl_l.addWidget(btn_add_pl, alignment=Qt.AlignmentFlag.AlignCenter)

        sys_card = QFrame()
        sys_card.setObjectName("bentoCard")
        sys_card.setFixedWidth(60)
        sys_l = QVBoxLayout(sys_card)
        sys_l.setContentsMargins(6, 8, 6, 8)
        sys_l.setSpacing(6)

        self.btn_nav_folders = QPushButton()
        self.btn_nav_folders.setObjectName("dockBtn")
        self.btn_nav_folders.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_nav_folders.setFixedSize(44, 38)
        self.btn_nav_folders.setIconSize(QSize(22, 22))
        self.btn_nav_folders.setToolTip("Kelola Folder (Whitelist & Blacklist)")
        self.btn_nav_folders.clicked.connect(lambda: self.show_settings_view(1))

        self.btn_nav_settings = QPushButton()
        self.btn_nav_settings.setObjectName("dockBtn")
        self.btn_nav_settings.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_nav_settings.setFixedSize(44, 38)
        self.btn_nav_settings.setIconSize(QSize(22, 22))
        self.btn_nav_settings.setToolTip("Pengaturan Tema & Aplikasi")
        self.btn_nav_settings.clicked.connect(lambda: self.show_settings_view(0))

        self.btn_rescan = QPushButton()
        self.btn_rescan.setObjectName("dockBtn")
        self.btn_rescan.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_rescan.setFixedSize(44, 38)
        self.btn_rescan.setIconSize(QSize(22, 22))
        self.btn_rescan.setToolTip("Pindai Ulang Library")
        self.btn_rescan.clicked.connect(lambda: self.run_scanner(False))

        self.dock_nav_buttons = [
            self.btn_nav_home, self.btn_nav_songs, self.btn_nav_albums,
            self.btn_nav_artists, self.btn_nav_playlists, self.btn_nav_search,
            self.btn_nav_fav, self.btn_nav_hot, self.btn_nav_folders,
            self.btn_nav_settings
        ]

        for b in (self.btn_nav_folders, self.btn_nav_settings, self.btn_rescan):
            sys_l.addWidget(b, alignment=Qt.AlignmentFlag.AlignCenter)

        dock_col.addWidget(nav_card)
        dock_col.addWidget(pl_card, stretch=1)
        dock_col.addWidget(sys_card)

        # =========================================================
        # 2. LEFT-CENTER NOW PLAYING SIDEBAR CARD
        # =========================================================
        np_card = QFrame()
        np_card.setObjectName("bentoCard")
        np_card.setFixedWidth(264)
        np_l = QVBoxLayout(np_card)
        np_l.setContentsMargins(14, 14, 14, 14)
        np_l.setSpacing(10)

        self.lbl_side_cover = QLabel()
        self.lbl_side_cover.setFixedSize(234, 234)
        self.lbl_side_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_side_cover.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_side_cover.setToolTip("Klik untuk membuka Mode Layar Penuh")
        self.lbl_side_cover.mousePressEvent = lambda e: self.open_ambient_now_playing()
        self.lbl_side_cover.setPixmap(generate_fallback_cover(234, 12))

        title_row = QHBoxLayout()
        title_info = QVBoxLayout()
        title_info.setSpacing(2)
        self.lbl_side_title = QLabel("Belum ada lagu")
        self.lbl_side_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.lbl_side_title.setWordWrap(True)
        self.lbl_side_artist = QLabel("-")
        self.lbl_side_artist.setStyleSheet("font-size: 12px;")
        title_info.addWidget(self.lbl_side_title)
        title_info.addWidget(self.lbl_side_artist)

        self.btn_favorite = QPushButton()
        self.btn_favorite.setObjectName("circleBtn")
        self.btn_favorite.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_favorite.setFixedSize(36, 36)
        self.btn_favorite.setIconSize(QSize(22, 22))
        self.btn_favorite.setToolTip("Tandai sebagai Lagu Favorit")
        self.btn_favorite.setIcon(make_favorites_icon(QApplication.palette().color(QPalette.ColorRole.WindowText), 22))
        self.btn_favorite.clicked.connect(self.toggle_current_favorite)

        title_row.addLayout(title_info, stretch=1)
        title_row.addWidget(self.btn_favorite)

        info_box = QFrame()
        info_box.setObjectName("innerCard")
        ib_l = QVBoxLayout(info_box)
        ib_l.setContentsMargins(12, 10, 12, 10)
        ib_l.setSpacing(6)

        ib_header = QHBoxLayout()
        lbl_q_hdr = QLabel("Antrean Putar")
        lbl_q_hdr.setStyleSheet("font-weight: bold; font-size: 12px;")
        btn_clear_q = QPushButton("Bersihkan")
        btn_clear_q.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_clear_q.setStyleSheet("font-size: 11px; padding: 2px 10px;")
        btn_clear_q.clicked.connect(self.playback.clear_queue)
        ib_header.addWidget(lbl_q_hdr)
        ib_header.addStretch()
        ib_header.addWidget(btn_clear_q)

        self.list_queue = QListWidget()
        self.list_queue.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_queue.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_queue.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list_queue.itemDoubleClicked.connect(self.on_queue_item_clicked)

        ib_l.addLayout(ib_header)
        ib_l.addWidget(self.list_queue, stretch=1)

        np_l.addWidget(self.lbl_side_cover)
        np_l.addLayout(title_row)
        np_l.addWidget(info_box, stretch=1)

        # =========================================================
        # 3. MAIN CONTENT BENTO CARD + FLOATING PILL PLAYER
        # =========================================================
        main_card = QFrame()
        main_card.setObjectName("bentoCard")
        mc_layout = QVBoxLayout(main_card)
        mc_layout.setContentsMargins(16, 14, 16, 12)
        mc_layout.setSpacing(10)

        top_header = QHBoxLayout()
        self.btn_back = QPushButton("←")
        self.btn_back.setObjectName("circleBtn")
        self.btn_back.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_back.setFixedSize(36, 36)
        self.btn_back.setToolTip("Kembali ke Beranda")
        self.btn_back.clicked.connect(self.show_home_view)

        self.lbl_view_title = QLabel("Beranda")
        self.lbl_view_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-left: 6px;")

        self.lbl_view_icon = QLabel()
        self.lbl_view_icon.setFixedSize(20, 20)
        self.lbl_view_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_view_icon.hide()

        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("pillSearch")
        self.search_bar.setFixedWidth(300)
        self.search_bar.setPlaceholderText("🔍 Cari lagu, artis, atau album... (Ctrl+F)")
        self.search_bar.textChanged.connect(self.filter_tracks)

        top_header.addWidget(self.btn_back)
        top_header.addWidget(self.lbl_view_icon)
        top_header.addWidget(self.lbl_view_title)
        top_header.addStretch()
        top_header.addWidget(self.search_bar)

        self.right_stack = QStackedWidget()

        # --- Halaman 0: HOME VIEW ---
        self.page_home = QScrollArea()
        self.page_home.setWidgetResizable(True)
        home_container = QWidget()
        home_l = QVBoxLayout(home_container)
        home_l.setContentsMargins(2, 6, 6, 8)
        home_l.setSpacing(14)

        lbl_home_playlists = QLabel("Playlist & Koleksi Cepat")
        lbl_home_playlists.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.home_pl_grid = QListWidget()
        self.home_pl_grid.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.home_pl_grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.home_pl_grid.setFlow(QListWidget.Flow.LeftToRight)
        self.home_pl_grid.setWrapping(False)
        self.home_pl_grid.setIconSize(QSize(102, 102))
        self.home_pl_grid.setGridSize(QSize(134, 152))
        self.home_pl_grid.setFixedHeight(172)
        self.home_pl_grid.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.home_pl_grid.setMovement(QListWidget.Movement.Static)
        self.home_pl_grid.itemClicked.connect(self.on_home_pl_clicked)

        lbl_home_recent = QLabel("Terakhir Kali Didengarkan")
        lbl_home_recent.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 4px;")

        self.recent_container = QWidget()
        self.recent_layout = QVBoxLayout(self.recent_container)
        self.recent_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_layout.setSpacing(8)

        home_l.addWidget(lbl_home_playlists)
        home_l.addWidget(self.home_pl_grid)
        home_l.addWidget(lbl_home_recent)
        home_l.addWidget(self.recent_container)
        home_l.addStretch()
        self.page_home.setWidget(home_container)

        # --- Halaman 1: Tracklist + Album Detail Header ---
        self.page_tracks = QWidget()
        pt_l = QVBoxLayout(self.page_tracks)
        pt_l.setContentsMargins(0, 0, 0, 0)
        pt_l.setSpacing(10)

        self.album_header = QFrame()
        self.album_header.setObjectName("innerCard")
        ah_l = QHBoxLayout(self.album_header)
        ah_l.setContentsMargins(16, 14, 16, 14)
        ah_l.setSpacing(16)

        self.lbl_ah_cover = QLabel()
        self.lbl_ah_cover.setFixedSize(110, 110)
        ah_info = QVBoxLayout()
        lbl_ah_type = QLabel("Album")
        lbl_ah_type.setStyleSheet("font-size: 12px;")
        self.lbl_ah_title = QLabel("Album Title")
        self.lbl_ah_title.setStyleSheet("font-size: 26px; font-weight: bold;")
        self.lbl_ah_meta = QLabel("Artist • 0 Lagu")
        self.lbl_ah_meta.setStyleSheet("font-size: 12px;")
        ah_info.addWidget(lbl_ah_type)
        ah_info.addWidget(self.lbl_ah_title)
        ah_info.addWidget(self.lbl_ah_meta)

        self.btn_ah_play = QPushButton()
        self.btn_ah_play.setObjectName("accentCircleBtn")
        self.btn_ah_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_ah_play.setFixedSize(46, 46)
        self.btn_ah_play.setIconSize(QSize(40, 40))
        self.btn_ah_play.setToolTip("Putar Album Ini")
        self.btn_ah_play.clicked.connect(self.play_current_view_tracks)

        ah_l.addWidget(self.lbl_ah_cover)
        ah_l.addLayout(ah_info, stretch=1)
        ah_l.addWidget(self.btn_ah_play)
        self.album_header.hide()

        self.table_view = QTableView()
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table_view.setSortingEnabled(True)
        self.table_view.setShowGrid(False)
        self.table_view.setIconSize(QSize(16, 16))
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.verticalHeader().setDefaultSectionSize(38)
        self.table_view.doubleClicked.connect(self.on_track_double_clicked)
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_track_context_menu)

        pt_l.addWidget(self.album_header)
        pt_l.addWidget(self.table_view, stretch=1)

        # --- Halaman 2: Galeri Album Penuh ---
        self.page_albums = QWidget()
        pa_l = QVBoxLayout(self.page_albums)
        pa_l.setContentsMargins(0, 0, 0, 0)
        self.album_grid = QListWidget()
        self.album_grid.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.album_grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.album_grid.setIconSize(QSize(136, 136))
        self.album_grid.setGridSize(QSize(160, 196))
        self.album_grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.album_grid.setMovement(QListWidget.Movement.Static)
        self.album_grid.itemClicked.connect(self.on_album_opened)
        pa_l.addWidget(self.album_grid)

        # --- Halaman 3: Daftar Artis ---
        self.page_artists = QWidget()
        par_l = QVBoxLayout(self.page_artists)
        par_l.setContentsMargins(0, 0, 0, 0)
        self.artist_list = QListWidget()
        self.artist_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.artist_list.setStyleSheet("font-size: 14px;")
        self.artist_list.itemClicked.connect(self.on_artist_opened)
        par_l.addWidget(self.artist_list)

        # --- Halaman 4: Settings & Tools Bento Terpadu ---
        self.settings_page = SettingsPage()
        self.settings_page.folders_changed.connect(lambda: self.run_scanner(False))
        self.settings_page.library_updated.connect(lambda: (self.load_library(), self.refresh_home_view()))
        self.settings_page.full_rescan_requested.connect(lambda: self.run_scanner(True))
        self.settings_page.theme_changed.connect(self.refresh_player_icons)

        # --- Halaman 5: Halaman Daftar Playlist Lengkap ---
        self.page_playlists = QWidget()
        ppl_l = QVBoxLayout(self.page_playlists)
        ppl_l.setContentsMargins(0, 4, 0, 0)
        ppl_l.setSpacing(12)

        ppl_actions = QHBoxLayout()
        btn_ppl_new = QPushButton("➕ Buat Playlist Baru")
        btn_ppl_new.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_ppl_new.clicked.connect(self.create_playlist)
        btn_ppl_imp = QPushButton("📥 Impor M3U / M3U8")
        btn_ppl_imp.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_ppl_imp.clicked.connect(self.import_playlist_m3u)
        ppl_actions.addWidget(btn_ppl_new)
        ppl_actions.addWidget(btn_ppl_imp)
        ppl_actions.addStretch()

        self.playlists_page_grid = QListWidget()
        self.playlists_page_grid.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.playlists_page_grid.setViewMode(QListWidget.ViewMode.IconMode)
        self.playlists_page_grid.setIconSize(QSize(124, 124))
        self.playlists_page_grid.setGridSize(QSize(156, 184))
        self.playlists_page_grid.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.playlists_page_grid.setMovement(QListWidget.Movement.Static)
        self.playlists_page_grid.itemClicked.connect(self.on_home_pl_clicked)
        self.playlists_page_grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlists_page_grid.customContextMenuRequested.connect(self.show_playlists_page_context_menu)

        ppl_l.addLayout(ppl_actions)
        ppl_l.addWidget(self.playlists_page_grid, stretch=1)

        self.right_stack.addWidget(self.page_home)       # 0
        self.right_stack.addWidget(self.page_tracks)     # 1
        self.right_stack.addWidget(self.page_albums)     # 2
        self.right_stack.addWidget(self.page_artists)    # 3
        self.right_stack.addWidget(self.settings_page)   # 4
        self.right_stack.addWidget(self.page_playlists)  # 5

        # =========================================================
        # FLOATING PILL PLAYER BAR (IKON VECTOR ALA VECTEEZY)
        # =========================================================
        pill_wrapper = QHBoxLayout()
        pill_frame = QFrame()
        pill_frame.setObjectName("floatingPill")
        pill_frame.setMinimumWidth(600)
        pill_frame.setMaximumWidth(880)
        pill_l = QVBoxLayout(pill_frame)
        pill_l.setContentsMargins(16, 10, 16, 8)
        pill_l.setSpacing(6)

        pill_top = QHBoxLayout()
        pill_top.setSpacing(10)

        self.lbl_pill_cover = QLabel()
        self.lbl_pill_cover.setFixedSize(46, 46)
        self.lbl_pill_cover.setPixmap(generate_fallback_cover(46, 10))

        pill_info = QVBoxLayout()
        pill_info.setSpacing(1)
        self.lbl_pill_title = QLabel("Belum ada lagu")
        self.lbl_pill_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.lbl_pill_artist = QLabel("-")
        self.lbl_pill_artist.setStyleSheet("font-size: 11px;")
        pill_info.addWidget(self.lbl_pill_title)
        pill_info.addWidget(self.lbl_pill_artist)

        self.btn_shuffle = QPushButton()
        self.btn_shuffle.setObjectName("pillBtn")
        self.btn_shuffle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_shuffle.setFixedSize(38, 38)
        self.btn_shuffle.setIconSize(QSize(34, 34))
        self.btn_shuffle.setToolTip("Acak Lagu (Shuffle)")
        self.btn_shuffle.clicked.connect(self.on_toggle_shuffle)

        self.btn_prev = QPushButton()
        self.btn_prev.setObjectName("pillBtn")
        self.btn_prev.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_prev.setFixedSize(38, 38)
        self.btn_prev.setIconSize(QSize(34, 34))
        self.btn_prev.setToolTip("Lagu Sebelumnya (Ctrl+Kiri)")
        self.btn_prev.clicked.connect(self.playback.prev_track)

        self.btn_play = QPushButton()
        self.btn_play.setObjectName("pillPlayBtn")
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_play.setFixedSize(44, 44)
        self.btn_play.setIconSize(QSize(40, 40))
        self.btn_play.setToolTip("Putar / Jeda (Spasi)")
        self.btn_play.clicked.connect(self.playback.play_pause)

        self.btn_next = QPushButton()
        self.btn_next.setObjectName("pillBtn")
        self.btn_next.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_next.setFixedSize(38, 38)
        self.btn_next.setIconSize(QSize(34, 34))
        self.btn_next.setToolTip("Lagu Berikutnya (Ctrl+Kanan)")
        self.btn_next.clicked.connect(self.playback.next_track)

        self.btn_repeat = QPushButton()
        self.btn_repeat.setObjectName("pillBtn")
        self.btn_repeat.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_repeat.setFixedSize(38, 38)
        self.btn_repeat.setIconSize(QSize(34, 34))
        self.btn_repeat.setToolTip("Ulangi Lagu (Repeat)")
        self.btn_repeat.clicked.connect(self.on_toggle_repeat)

        self.btn_mute = QPushButton()
        self.btn_mute.setObjectName("pillBtn")
        self.btn_mute.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_mute.setFixedSize(38, 38)
        self.btn_mute.setIconSize(QSize(34, 34))
        self.btn_mute.setToolTip("Mute / Unmute")
        self.btn_mute.clicked.connect(self.on_toggle_mute)

        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setFixedWidth(85)
        self.slider_volume.valueChanged.connect(self.on_volume_changed)

        self.btn_expand = QPushButton()
        self.btn_expand.setObjectName("pillBtn")
        self.btn_expand.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_expand.setFixedSize(38, 38)
        self.btn_expand.setIconSize(QSize(34, 34))
        self.btn_expand.setToolTip("Mode Layar Penuh Now Playing")
        self.btn_expand.clicked.connect(self.open_ambient_now_playing)

        pill_top.addWidget(self.lbl_pill_cover)
        pill_top.addLayout(pill_info, stretch=1)
        pill_top.addWidget(self.btn_shuffle)
        pill_top.addWidget(self.btn_prev)
        pill_top.addWidget(self.btn_play)
        pill_top.addWidget(self.btn_next)
        pill_top.addWidget(self.btn_repeat)
        pill_top.addSpacing(8)
        pill_top.addWidget(self.btn_mute)
        pill_top.addWidget(self.slider_volume)
        pill_top.addWidget(self.btn_expand)

        pill_bottom = QHBoxLayout()
        self.lbl_time_pos = QLabel("00:00")
        self.lbl_time_pos.setStyleSheet("font-size: 11px;")
        self.slider_progress = QSlider(Qt.Orientation.Horizontal)
        self.slider_progress.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.slider_progress.sliderMoved.connect(self.playback.seek)
        self.lbl_time_dur = QLabel("00:00")
        self.lbl_time_dur.setStyleSheet("font-size: 11px;")
        pill_bottom.addWidget(self.lbl_time_pos)
        pill_bottom.addWidget(self.slider_progress)
        pill_bottom.addWidget(self.lbl_time_dur)

        pill_l.addLayout(pill_top)
        pill_l.addLayout(pill_bottom)

        pill_wrapper.addStretch(1)
        pill_wrapper.addWidget(pill_frame, stretch=8)
        pill_wrapper.addStretch(1)

        mc_layout.addLayout(top_header)
        mc_layout.addWidget(self.right_stack, stretch=1)
        mc_layout.addLayout(pill_wrapper)

        ws_layout.addLayout(dock_col)
        ws_layout.addWidget(np_card)
        ws_layout.addWidget(main_card, stretch=1)

        self.ambient_page = AmbientNowPlayingPage()
        self.ambient_page.close_requested.connect(lambda: self.main_stack.setCurrentIndex(0))
        self.ambient_page.play_pause_clicked.connect(self.playback.play_pause)
        self.ambient_page.next_clicked.connect(self.playback.next_track)
        self.ambient_page.prev_clicked.connect(self.playback.prev_track)
        self.ambient_page.shuffle_clicked.connect(self.on_toggle_shuffle)
        self.ambient_page.repeat_clicked.connect(self.on_toggle_repeat)
        self.ambient_page.seek_moved.connect(self.playback.seek)

        self.main_stack.addWidget(workspace)
        self.main_stack.addWidget(self.ambient_page)

    def refresh_player_icons(self):
        pal = QApplication.palette()
        fg = pal.color(QPalette.ColorRole.WindowText)
        hi_fg = pal.color(QPalette.ColorRole.HighlightedText)

        # Ikon Tab Playlist di Dock Kiri menggunakan file SVG .txt Abang!
        pl_color = hi_fg if (self.active_dock_btn is self.btn_nav_playlists) else fg
        self.btn_nav_playlists.setIcon(make_playlist_icon(pl_color, 24))
        home_color = hi_fg if (self.active_dock_btn is self.btn_nav_home) else fg
        self.btn_nav_home.setIcon(make_home_icon(home_color, 24))
        songs_color = hi_fg if (self.active_dock_btn is self.btn_nav_songs) else fg
        self.btn_nav_songs.setIcon(make_songs_icon(songs_color, 24))
        fav_color = hi_fg if (self.active_dock_btn is self.btn_nav_fav) else fg
        self.btn_nav_fav.setIcon(make_favorites_icon(fav_color, 24))
        hot_color = hi_fg if (self.active_dock_btn is self.btn_nav_hot) else fg
        self.btn_nav_hot.setIcon(make_fire_icon(hot_color, 24))
        album_color = hi_fg if (self.active_dock_btn is self.btn_nav_albums) else fg
        self.btn_nav_albums.setIcon(make_album_icon(album_color, 24))
        art_color = hi_fg if (self.active_dock_btn is self.btn_nav_artists) else fg
        self.btn_nav_artists.setIcon(make_artist_icon(art_color, 24))
        search_color = hi_fg if (self.active_dock_btn is self.btn_nav_search) else fg
        self.btn_nav_search.setIcon(make_search_icon(search_color, 24))
        self.btn_rescan.setIcon(make_refresh_icon(fg, 22))
        folders_color = hi_fg if (self.active_dock_btn is self.btn_nav_folders) else fg
        self.btn_nav_folders.setIcon(make_folder_icon(folders_color, 22))
        settings_color = hi_fg if (self.active_dock_btn is self.btn_nav_settings) else fg
        self.btn_nav_settings.setIcon(make_settings_icon(settings_color, 22))

        self.btn_prev.setIcon(make_media_icon("prev", fg, 34))
        self.btn_next.setIcon(make_media_icon("next", fg, 34))
        self.btn_expand.setIcon(make_media_icon("expand", fg, 34))
        self.btn_mute.setIcon(make_media_icon("mute" if self.is_muted else "volume", fg, 34))
        self.btn_play.setIcon(make_media_icon("pause" if self.is_playing else "play", hi_fg, 40))
        self.btn_ah_play.setIcon(make_media_icon("play", hi_fg, 40))

        self.btn_shuffle.setIcon(make_media_icon("shuffle", hi_fg if self.playback.is_shuffle else fg, 34))
        rep_kind = "repeat_one" if self.playback.repeat_mode == 2 else "repeat"
        self.btn_repeat.setIcon(make_media_icon(rep_kind, hi_fg if self.playback.repeat_mode in (1, 2) else fg, 34))

        if self.playback.current_track:
            self.update_favorite_icon((self.playback.current_track.get('rating') or 0) > 0)
        if self.view_mode == 'favorites':
            self.set_view_title("Lagu Favorit", render_favorites_svg_pixmap(pal.color(QPalette.ColorRole.Highlight), 18))
        elif self.view_mode == 'most_played':
            self.set_view_title("Sering Diputar (Top 50)", render_fire_svg_pixmap(pal.color(QPalette.ColorRole.Highlight), 18))

        if self.view_mode == 'home':
            self.refresh_home_view()

    def set_active_dock(self, active_btn):
        self.active_dock_btn = active_btn
        for b in self.dock_nav_buttons:
            b.setObjectName("dockBtnActive" if b is active_btn else "dockBtn")
            b.style().unpolish(b)
            b.style().polish(b)
        pal = QApplication.palette()
        pl_color = pal.color(QPalette.ColorRole.HighlightedText if active_btn is self.btn_nav_playlists else QPalette.ColorRole.WindowText)
        self.btn_nav_playlists.setIcon(make_playlist_icon(pl_color, 24))
        home_color = pal.color(QPalette.ColorRole.HighlightedText if active_btn is self.btn_nav_home else QPalette.ColorRole.WindowText)
        self.btn_nav_home.setIcon(make_home_icon(home_color, 24))
        songs_color = pal.color(QPalette.ColorRole.HighlightedText if active_btn is self.btn_nav_songs else QPalette.ColorRole.WindowText)
        self.btn_nav_songs.setIcon(make_songs_icon(songs_color, 24))
        fav_color = pal.color(QPalette.ColorRole.HighlightedText if active_btn is self.btn_nav_fav else QPalette.ColorRole.WindowText)
        self.btn_nav_fav.setIcon(make_favorites_icon(fav_color, 24))
        hot_color = pal.color(QPalette.ColorRole.HighlightedText if active_btn is self.btn_nav_hot else QPalette.ColorRole.WindowText)
        self.btn_nav_hot.setIcon(make_fire_icon(hot_color, 24))
        album_color = pal.color(QPalette.ColorRole.HighlightedText if active_btn is self.btn_nav_albums else QPalette.ColorRole.WindowText)
        self.btn_nav_albums.setIcon(make_album_icon(album_color, 24))
        art_color = pal.color(QPalette.ColorRole.HighlightedText if active_btn is self.btn_nav_artists else QPalette.ColorRole.WindowText)
        self.btn_nav_artists.setIcon(make_artist_icon(art_color, 24))
        search_color = pal.color(QPalette.ColorRole.HighlightedText if active_btn is self.btn_nav_search else QPalette.ColorRole.WindowText)
        self.btn_nav_search.setIcon(make_search_icon(search_color, 24))
        folders_color = pal.color(QPalette.ColorRole.HighlightedText if active_btn is self.btn_nav_folders else QPalette.ColorRole.WindowText)
        self.btn_nav_folders.setIcon(make_folder_icon(folders_color, 22))
        settings_color = pal.color(QPalette.ColorRole.HighlightedText if active_btn is self.btn_nav_settings else QPalette.ColorRole.WindowText)
        self.btn_nav_settings.setIcon(make_settings_icon(settings_color, 22))

    def set_view_title(self, text, pixmap=None):
        self.lbl_view_title.setText(text)
        if pixmap is not None and not pixmap.isNull():
            self.lbl_view_icon.setPixmap(pixmap)
            self.lbl_view_icon.show()
        else:
            self.lbl_view_icon.hide()

    def open_ambient_now_playing(self):
        self.main_stack.setCurrentIndex(1)

    def show_playlists_page(self):
        self.list_playlists.clearSelection()
        self.set_active_dock(self.btn_nav_playlists)
        self.view_mode = 'playlists_page'
        self.set_view_title("Daftar Playlist")
        self.search_bar.clear()
        self.right_stack.setCurrentIndex(5)
        self.refresh_playlists_page()

    def refresh_playlists_page(self):
        self.playlists_page_grid.clear()
        cursor = self.conn.cursor()

        fav_item = QListWidgetItem("Lagu Favorit")
        fav_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        fav_item.setIcon(QIcon(generate_playlist_badge("♥", 124, "♥")))
        fav_item.setData(Qt.ItemDataRole.UserRole, ("favorites", None, "Lagu Favorit"))
        self.playlists_page_grid.addItem(fav_item)

        hot_item = QListWidgetItem("Sering Diputar")
        hot_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        hot_item.setIcon(QIcon(generate_playlist_badge("Sering Diputar", 124, "fire")))
        hot_item.setData(Qt.ItemDataRole.UserRole, ("most_played", None, "Sering Diputar"))
        self.playlists_page_grid.addItem(hot_item)

        for row in cursor.execute("SELECT id, name FROM playlists ORDER BY name ASC").fetchall():
            cnt = cursor.execute("SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id=?", (row['id'],)).fetchone()[0]
            item = QListWidgetItem(f"{row['name']}\n{cnt} Lagu")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setIcon(QIcon(generate_playlist_badge(row['name'], 124)))
            item.setData(Qt.ItemDataRole.UserRole, ("playlist", row['id'], row['name']))
            self.playlists_page_grid.addItem(item)

    def show_playlists_page_context_menu(self, pos):
        item = self.playlists_page_grid.itemAt(pos)
        if not item: return
        mode, pl_id, pl_name = item.data(Qt.ItemDataRole.UserRole)
        if mode != "playlist": return
        menu = QMenu(self)
        menu.addAction(QAction(f"📤 Ekspor '{pl_name}' ke M3U", self, triggered=lambda: self.export_playlist_m3u(pl_id, pl_name)))
        menu.addSeparator()
        menu.addAction(QAction(f"🗑️ Hapus Playlist '{pl_name}'", self, triggered=lambda: self.delete_playlist(pl_id)))
        menu.exec(self.playlists_page_grid.mapToGlobal(pos))

    def show_settings_view(self, tab_index=0):
        self.list_playlists.clearSelection()
        if tab_index == 1:
            self.set_active_dock(self.btn_nav_folders)
            self.set_view_title("Kelola Folder Musik")
        else:
            self.set_active_dock(self.btn_nav_settings)
            self.set_view_title("Pengaturan MintTune")
        self.view_mode = 'settings'
        self.settings_page.load_all_data()
        self.settings_page.switch_tab(tab_index)
        self.right_stack.setCurrentIndex(4)

    def show_create_or_import_menu(self):
        menu = QMenu(self)
        menu.addAction(QAction("➕ Buat Playlist Baru", self, triggered=self.create_playlist))
        menu.addAction(QAction("📥 Impor Playlist (.m3u / .m3u8)", self, triggered=self.import_playlist_m3u))
        menu.exec(self.cursor().pos())

    def refresh_home_view(self):
        cursor = self.conn.cursor()

        self.home_pl_grid.clear()
        fav_item = QListWidgetItem("Lagu Favorit")
        fav_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        fav_item.setIcon(QIcon(generate_playlist_badge("♥", 102, "♥")))
        fav_item.setData(Qt.ItemDataRole.UserRole, ("favorites", None, "Lagu Favorit"))
        self.home_pl_grid.addItem(fav_item)

        hot_item = QListWidgetItem("Sering Diputar")
        hot_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        hot_item.setIcon(QIcon(generate_playlist_badge("Sering Diputar", 102, "fire")))
        hot_item.setData(Qt.ItemDataRole.UserRole, ("most_played", None, "Sering Diputar"))
        self.home_pl_grid.addItem(hot_item)

        for row in cursor.execute("SELECT id, name FROM playlists ORDER BY name ASC").fetchall():
            item = QListWidgetItem(row['name'])
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setIcon(QIcon(generate_playlist_badge(row['name'], 102)))
            item.setData(Qt.ItemDataRole.UserRole, ("playlist", row['id'], row['name']))
            self.home_pl_grid.addItem(item)

        while self.recent_layout.count():
            child = self.recent_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        rows = cursor.execute('''SELECT * FROM tracks 
                                 WHERE missing=0 AND excluded=0 AND last_played > 0 
                                 ORDER BY last_played DESC LIMIT 12''').fetchall()
        self.recent_tracks = [dict(r) for r in rows]

        if not self.recent_tracks:
            empty_card = QFrame()
            empty_card.setObjectName("innerCard")
            el = QVBoxLayout(empty_card)
            el.setContentsMargins(16, 18, 16, 18)
            lbl_e = QLabel("Belum ada riwayat pemutaran. Putar lagu pertama Anda dari tab Semua Lagu atau Galeri Album!")
            lbl_e.setWordWrap(True)
            el.addWidget(lbl_e)
            self.recent_layout.addWidget(empty_card)
            return

        pal = QApplication.palette()
        hi_fg = pal.color(QPalette.ColorRole.HighlightedText)
        play_icon = make_media_icon("play", hi_fg, 32)
        fallback_cov = generate_fallback_cover(42, 8)

        for idx, track in enumerate(self.recent_tracks):
            card = QFrame()
            card.setObjectName("innerCard")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(12, 8, 12, 8)
            cl.setSpacing(12)

            lbl_cov = QLabel()
            lbl_cov.setFixedSize(42, 42)
            pix = get_cached_cover_pixmap(track['path'], 42, 8)
            lbl_cov.setPixmap(pix if pix else fallback_cov)

            info_col = QVBoxLayout()
            info_col.setSpacing(1)
            lbl_t = QLabel(track.get('title') or track.get('filename'))
            lbl_t.setStyleSheet("font-weight: bold; font-size: 13px;")
            lbl_a = QLabel(f"{track.get('artist') or 'Unknown'}  •  {track.get('album') or 'Unknown'}")
            lbl_a.setStyleSheet("font-size: 11px;")
            info_col.addWidget(lbl_t)
            info_col.addWidget(lbl_a)

            lbl_dur = QLabel(format_time(track.get('duration_ms') or 0))
            lbl_dur.setStyleSheet("font-size: 12px;")

            btn_r_play = QPushButton()
            btn_r_play.setObjectName("accentCircleBtn")
            btn_r_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn_r_play.setFixedSize(34, 34)
            btn_r_play.setIconSize(QSize(30, 30))
            btn_r_play.setIcon(play_icon)
            btn_r_play.setToolTip("Putar Lagu Ini")
            btn_r_play.clicked.connect(lambda _, i=idx: self.play_recent_track(i))

            cl.addWidget(lbl_cov)
            cl.addLayout(info_col, stretch=1)
            cl.addWidget(lbl_dur)
            cl.addSpacing(6)
            cl.addWidget(btn_r_play)

            self.recent_layout.addWidget(card)

    def play_recent_track(self, idx):
        if 0 <= idx < len(self.recent_tracks):
            self.playback.queue = list(self.recent_tracks)
            self.playback.current_index = idx
            self.playback.play_track(self.recent_tracks[idx])
            self.update_queue_ui()

    def on_home_pl_clicked(self, item):
        mode, param, name = item.data(Qt.ItemDataRole.UserRole)
        if mode == "favorites":
            self.show_favorites_view()
        elif mode == "most_played":
            self.show_most_played_view()
        elif mode == "playlist":
            self.set_active_dock(self.btn_nav_playlists)
            self.view_mode, self.view_param = 'playlist', param
            self.set_view_title(f"Playlist: {name}")
            self.album_header.hide()
            self.right_stack.setCurrentIndex(1)
            self.load_library()

    def play_current_view_tracks(self):
        if self.tracks:
            self.play_selected_track(0)

    def on_playback_error(self, message):
        logger.error(f"Playback error: {message}")
        QMessageBox.warning(self, "Error Playback / Codec", message)

    def record_play_stats(self, track):
        try:
            now = time.time()
            self.conn.cursor().execute(
                "UPDATE tracks SET play_count = COALESCE(play_count, 0) + 1, last_played = ? WHERE id = ?",
                (now, track['id'])
            )
            self.conn.commit()
            new_count = (track.get('play_count') or 0) + 1
            track['play_count'] = new_count
            for t in self.tracks:
                if t['id'] == track['id']:
                    t['play_count'] = new_count
            if self.tracks:
                self.source_model.dataChanged.emit(self.source_model.index(0, 0), self.source_model.index(len(self.tracks) - 1, 6))
            if self.view_mode == 'home':
                QTimer.singleShot(0, self.refresh_home_view)
        except Exception as e:
            logger.error(f"Gagal update play stats: {e}")

    def set_tracks_favorite(self, tracks, make_favorite: bool):
        rating_val = 1 if make_favorite else 0
        cursor = self.conn.cursor()
        ids = {t['id'] for t in tracks}
        for tid in ids:
            cursor.execute("UPDATE tracks SET rating = ? WHERE id = ?", (rating_val, tid))
        self.conn.commit()

        for t in self.tracks:
            if t['id'] in ids:
                t['rating'] = rating_val
        if self.playback.current_track and self.playback.current_track['id'] in ids:
            self.playback.current_track['rating'] = rating_val
            self.update_favorite_icon(make_favorite)

        if self.view_mode == 'favorites' and not make_favorite:
            self.load_library()
        elif self.tracks:
            self.source_model.dataChanged.emit(self.source_model.index(0, 0), self.source_model.index(len(self.tracks) - 1, 6))

    def toggle_current_favorite(self):
        track = self.playback.current_track
        if not track: return
        is_fav = (track.get('rating') or 0) > 0
        self.set_tracks_favorite([track], not is_fav)

    def update_favorite_icon(self, is_fav):
        color = QApplication.palette().color(
            QPalette.ColorRole.Highlight if is_fav else QPalette.ColorRole.WindowText)
        self.btn_favorite.setIcon(make_favorites_icon(color, 22))
        self.btn_favorite.setToolTip("Hapus dari Lagu Favorit" if is_fav else "Tandai sebagai Lagu Favorit")

    def show_home_view(self):
        self.list_playlists.clearSelection()
        self.set_active_dock(self.btn_nav_home)
        self.view_mode = 'home'
        self.set_view_title("Beranda")
        self.right_stack.setCurrentIndex(0)
        self.refresh_home_view()

    def show_all_songs(self):
        self.list_playlists.clearSelection()
        self.set_active_dock(self.btn_nav_songs)
        self.view_mode, self.view_param = 'all', None
        self.set_view_title("Semua Lagu")
        self.album_header.hide()
        self.right_stack.setCurrentIndex(1)
        self.search_bar.clear()
        self.load_library()

    def show_favorites_view(self):
        self.list_playlists.clearSelection()
        self.set_active_dock(self.btn_nav_fav)
        self.view_mode, self.view_param = 'favorites', None
        self.set_view_title("Lagu Favorit", render_favorites_svg_pixmap(
            QApplication.palette().color(QPalette.ColorRole.Highlight), 18))
        self.album_header.hide()
        self.right_stack.setCurrentIndex(1)
        self.search_bar.clear()
        self.load_library()

    def show_most_played_view(self):
        self.list_playlists.clearSelection()
        self.set_active_dock(self.btn_nav_hot)
        self.view_mode, self.view_param = 'most_played', None
        self.set_view_title("Sering Diputar (Top 50)", render_fire_svg_pixmap(
            QApplication.palette().color(QPalette.ColorRole.Highlight), 18))
        self.album_header.hide()
        self.right_stack.setCurrentIndex(1)
        self.search_bar.clear()
        self.load_library()

    def show_albums_view(self):
        self.list_playlists.clearSelection()
        self.set_active_dock(self.btn_nav_albums)
        self.view_mode = 'albums'
        self.set_view_title("Galeri Album")
        self.search_bar.clear()
        self.right_stack.setCurrentIndex(2)
        self.album_grid.clear()
        
        cursor = self.conn.cursor()
        cursor.execute('''SELECT album, artist, MIN(path) as path 
                          FROM tracks WHERE missing=0 AND excluded=0 
                          GROUP BY album ORDER BY album ASC''')
        fallback_icon = QIcon(generate_fallback_cover(136, 12))
        for row in cursor.fetchall():
            album_name = row['album'] or "Unknown Album"
            artist_name = row['artist'] or "Unknown Artist"
            item = QListWidgetItem(f"{album_name}\n{artist_name}")
            item.setToolTip(f"{album_name} — {artist_name}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            pix = get_cached_cover_pixmap(row['path'], 136, 12)
            item.setIcon(QIcon(pix) if pix else fallback_icon)
            item.setData(Qt.ItemDataRole.UserRole, album_name)
            self.album_grid.addItem(item)

    def on_album_opened(self, item):
        album_name = item.data(Qt.ItemDataRole.UserRole)
        self.view_mode, self.view_param = 'album', album_name
        self.set_active_dock(self.btn_nav_albums)
        self.set_view_title("Detail Album")
        self.right_stack.setCurrentIndex(1)
        self.search_bar.clear()
        self.load_library()

        self.lbl_ah_title.setText(album_name)
        if self.tracks:
            first = self.tracks[0]
            total_min = sum((t.get('duration_ms') or 0) for t in self.tracks) // 60000
            self.lbl_ah_meta.setText(f"{first.get('artist') or 'Unknown'}  •  {len(self.tracks)} Lagu  •  {total_min} mnt")
            pix = get_cached_cover_pixmap(first['path'], 110, 10)
            self.lbl_ah_cover.setPixmap(pix if pix else generate_fallback_cover(110, 10))
        self.album_header.show()

    def show_artists_view(self):
        self.list_playlists.clearSelection()
        self.set_active_dock(self.btn_nav_artists)
        self.view_mode = 'artists'
        self.set_view_title("Daftar Artis")
        self.search_bar.clear()
        self.right_stack.setCurrentIndex(3)
        self.artist_list.clear()

        cursor = self.conn.cursor()
        cursor.execute('''SELECT artist, COUNT(*) as track_count, COUNT(DISTINCT album) as album_count
                          FROM tracks WHERE missing=0 AND excluded=0
                          GROUP BY artist ORDER BY artist ASC''')
        fg = QApplication.palette().color(QPalette.ColorRole.WindowText)
        art_icon = make_artist_icon(fg, 22)
        for row in cursor.fetchall():
            artist_name = row['artist'] or "Unknown Artist"
            item = QListWidgetItem(f"{artist_name}   —   {row['album_count']} Album • {row['track_count']} Lagu")
            item.setIcon(art_icon)
            item.setData(Qt.ItemDataRole.UserRole, artist_name)
            self.artist_list.addItem(item)

    def on_artist_opened(self, item):
        artist_name = item.data(Qt.ItemDataRole.UserRole)
        self.view_mode, self.view_param = 'artist', artist_name
        self.set_view_title(f"Artis: {artist_name}")
        self.album_header.hide()
        self.right_stack.setCurrentIndex(1)
        self.search_bar.clear()
        self.load_library()

    def update_queue_ui(self):
        self.list_queue.clear()
        for i, track in enumerate(self.playback.queue):
            prefix = "▶ " if i == self.playback.current_index else f"{i+1}. "
            item = QListWidgetItem(f"{prefix}{track['title']}")
            item.setToolTip(f"{track['title']} — {track['artist']}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            if i == self.playback.current_index:
                item.setForeground(QColor(135, 186, 120))
            self.list_queue.addItem(item)

    def on_queue_item_clicked(self, item):
        idx = item.data(Qt.ItemDataRole.UserRole)
        self.playback.current_index = idx
        self.playback.play_track(self.playback.queue[idx])
        self.update_queue_ui()

    def on_volume_changed(self, value):
        self.playback.set_volume(value)
        self.save_setting("volume", value)

    def export_playlist_m3u(self, pl_id, pl_name):
        cursor = self.conn.cursor()
        cursor.execute('''SELECT tracks.path, tracks.title, tracks.artist, tracks.duration_ms 
                          FROM tracks JOIN playlist_tracks ON tracks.id = playlist_tracks.track_id 
                          WHERE playlist_tracks.playlist_id = ? ORDER BY playlist_tracks.position ASC''', (pl_id,))
        tracks = cursor.fetchall()
        if not tracks: 
            return QMessageBox.information(self, "Info", "Playlist ini masih kosong!")
        file_path, _ = QFileDialog.getSaveFileName(self, "Simpan File M3U", f"{pl_name}.m3u", "M3U Playlist (*.m3u)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("#EXTM3U\n")
                    for t in tracks: 
                        f.write(f"#EXTINF:{max(0, (t['duration_ms'] or 0) // 1000)},{t['artist']} - {t['title']}\n{t['path']}\n")
                QMessageBox.information(self, "Berhasil", f"Playlist diekspor ke:\n{file_path}")
            except Exception as e: 
                logger.error(f"Gagal ekspor M3U: {e}")
                QMessageBox.critical(self, "Error", f"Gagal mengekspor: {e}")

    def import_playlist_m3u(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Pilih File Playlist M3U", "", "Playlist Files (*.m3u *.m3u8)")
        if file_path:
            self._import_m3u_file(file_path, show_popup=True)

    def _import_m3u_file(self, file_path, show_popup=False):
        pl_name = os.path.splitext(os.path.basename(file_path))[0]
        cursor = self.conn.cursor()
        try:
            cursor.execute("INSERT INTO playlists (name, created_at) VALUES (?, ?)", (pl_name, time.time()))
            pl_id = cursor.lastrowid
        except Exception:
            cursor.execute("INSERT INTO playlists (name, created_at) VALUES (?, ?)", (f"{pl_name}_{int(time.time())}", time.time()))
            pl_id = cursor.lastrowid
        added_count = 0
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                pos = 1
                for line in f.readlines():
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    target_path = line if os.path.isabs(line) else os.path.normpath(os.path.join(os.path.dirname(file_path), line))
                    cursor.execute("SELECT id FROM tracks WHERE path = ?", (target_path,))
                    t_row = cursor.fetchone()
                    if t_row:
                        cursor.execute("INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?, ?, ?)", (pl_id, t_row['id'], pos))
                        pos += 1
                        added_count += 1
            self.conn.commit()
            self.load_playlists()
            if self.view_mode == 'home':
                self.refresh_home_view()
            elif self.view_mode == 'playlists_page':
                self.refresh_playlists_page()
            if show_popup:
                QMessageBox.information(self, "Selesai", f"Playlist diimpor dengan {added_count} lagu cocok!")
        except Exception as e: 
            logger.error(f"Gagal impor M3U: {e}")
            if show_popup:
                QMessageBox.critical(self, "Error", f"Gagal membaca file M3U: {e}")

    def load_playlists(self):
        self.list_playlists.clear()
        for row in self.conn.cursor().execute("SELECT id, name FROM playlists ORDER BY name ASC").fetchall():
            item = QListWidgetItem()
            item.setIcon(QIcon(generate_playlist_badge(row['name'], 38)))
            item.setToolTip(f"Playlist: {row['name']} (Klik kanan untuk Ekspor/Hapus)")
            item.setData(Qt.ItemDataRole.UserRole, row['id'])
            item.setData(Qt.ItemDataRole.UserRole + 1, row['name'])
            self.list_playlists.addItem(item)

    def create_playlist(self):
        name, ok = QInputDialog.getText(self, "Buat Playlist", "Nama Playlist Baru:")
        if ok and name.strip():
            try:
                self.conn.cursor().execute("INSERT INTO playlists (name, created_at) VALUES (?, ?)", (name.strip(), time.time()))
                self.conn.commit()
                self.load_playlists()
                if self.view_mode == 'home':
                    self.refresh_home_view()
                elif self.view_mode == 'playlists_page':
                    self.refresh_playlists_page()
            except Exception: 
                QMessageBox.warning(self, "Peringatan", "Nama playlist sudah digunakan!")

    def on_playlist_clicked(self, item):
        self.set_active_dock(self.btn_nav_playlists)
        self.view_mode = 'playlist'
        self.view_param = item.data(Qt.ItemDataRole.UserRole)
        self.set_view_title(f"Playlist: {item.data(Qt.ItemDataRole.UserRole + 1)}")
        self.album_header.hide()
        self.right_stack.setCurrentIndex(1)
        self.load_library()

    def show_playlist_context_menu(self, pos):
        item = self.list_playlists.itemAt(pos)
        if not item: return
        pl_id, pl_name = item.data(Qt.ItemDataRole.UserRole), item.data(Qt.ItemDataRole.UserRole + 1)
        menu = QMenu(self)
        menu.addAction(QAction(f"📤 Ekspor '{pl_name}' ke M3U", self, triggered=lambda: self.export_playlist_m3u(pl_id, pl_name)))
        menu.addSeparator()
        menu.addAction(QAction(f"🗑️ Hapus Playlist '{pl_name}'", self, triggered=lambda: self.delete_playlist(pl_id)))
        menu.exec(self.list_playlists.mapToGlobal(pos))

    def delete_playlist(self, pl_id):
        if QMessageBox.question(self, "Hapus Playlist", "Yakin ingin menghapus playlist ini?") == QMessageBox.StandardButton.Yes:
            self.conn.cursor().execute("DELETE FROM playlist_tracks WHERE playlist_id=?", (pl_id,))
            self.conn.cursor().execute("DELETE FROM playlists WHERE id=?", (pl_id,))
            self.conn.commit()
            self.load_playlists()
            if self.view_mode == 'home':
                self.refresh_home_view()
            elif self.view_mode == 'playlists_page':
                self.refresh_playlists_page()
            if self.view_mode == 'playlist' and self.view_param == pl_id:
                self.show_home_view()

    def add_multiple_to_playlist(self, tracks, playlist_id):
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT MAX(position) FROM playlist_tracks WHERE playlist_id=?", (playlist_id,))
            pos = (cursor.fetchone()[0] or 0) + 1
            for track in tracks:
                cursor.execute("INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?, ?, ?)", (playlist_id, track['id'], pos))
                pos += 1
            self.conn.commit()
        except Exception as e:
            logger.error(f"Gagal tambah track ke playlist: {e}")

    def remove_multiple_from_current_playlist(self, tracks):
        if self.view_mode != 'playlist': return
        cursor = self.conn.cursor()
        for track in tracks:
            cursor.execute("DELETE FROM playlist_tracks WHERE playlist_id=? AND track_id=?", (self.view_param, track['id']))
        self.conn.commit()
        self.load_library()

    def load_library(self):
        cursor = self.conn.cursor()
        if self.view_mode == 'playlist':
            cursor.execute('''SELECT tracks.* FROM tracks JOIN playlist_tracks ON tracks.id = playlist_tracks.track_id 
                              WHERE playlist_tracks.playlist_id = ? AND tracks.missing = 0 ORDER BY playlist_tracks.position ASC''', (self.view_param,))
        elif self.view_mode == 'favorites':
            cursor.execute("SELECT * FROM tracks WHERE missing=0 AND excluded=0 AND rating > 0 ORDER BY title ASC")
        elif self.view_mode == 'most_played':
            cursor.execute("SELECT * FROM tracks WHERE missing=0 AND excluded=0 AND play_count > 0 ORDER BY play_count DESC LIMIT 50")
        elif self.view_mode == 'album':
            cursor.execute("SELECT * FROM tracks WHERE missing=0 AND excluded=0 AND album = ? ORDER BY filename ASC", (self.view_param,))
        elif self.view_mode == 'artist':
            cursor.execute("SELECT * FROM tracks WHERE missing=0 AND excluded=0 AND artist = ? ORDER BY album ASC, filename ASC", (self.view_param,))
        else:
            cursor.execute("SELECT * FROM tracks WHERE missing=0 AND excluded=0")
            
        self.tracks = [dict(row) for row in cursor.fetchall()]
        
        self.source_model = TrackTableModel(self.tracks)
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)
        self.table_view.setModel(self.proxy_model)
        
        header = self.table_view.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table_view.setColumnWidth(2, 160)
        self.table_view.setColumnWidth(3, 160)

    def show_track_context_menu(self, pos):
        selected_indexes = self.table_view.selectionModel().selectedRows()
        if not selected_indexes: return
        tracks_to_process = [self.tracks[self.proxy_model.mapToSource(idx).row()] for idx in selected_indexes]
        menu = QMenu(self)
        
        if len(tracks_to_process) == 1:
            real_row = self.proxy_model.mapToSource(self.table_view.indexAt(pos)).row()
            menu.addAction(QAction("▶️ Putar Lagu Ini", self, triggered=lambda: self.play_selected_track(real_row)))
        else:
            menu.addAction(QAction(f"▶️ Ganti Antrean & Putar {len(tracks_to_process)} Lagu", self, triggered=lambda: self.play_specific_tracks(tracks_to_process)))
            
        menu.addAction(QAction("⏭️ Putar Selanjutnya", self, triggered=lambda: self.playback.insert_next(tracks_to_process)))
        menu.addAction(QAction("⏬ Tambahkan ke Antrean", self, triggered=lambda: self.playback.append_queue(tracks_to_process)))
        
        menu.addSeparator()
        all_fav = all((t.get('rating') or 0) > 0 for t in tracks_to_process)
        pal = QApplication.palette()
        if all_fav:
            act_fav = QAction("Hapus dari Favorit", self, triggered=lambda: self.set_tracks_favorite(tracks_to_process, False))
            act_fav.setIcon(make_favorites_icon(pal.color(QPalette.ColorRole.WindowText), 16))
        else:
            act_fav = QAction("Tandai sebagai Favorit", self, triggered=lambda: self.set_tracks_favorite(tracks_to_process, True))
            act_fav.setIcon(make_favorites_icon(pal.color(QPalette.ColorRole.Highlight), 16))
        menu.addAction(act_fav)

        all_pls = self.conn.cursor().execute("SELECT id, name FROM playlists ORDER BY name ASC").fetchall()
        if all_pls:
            sub_pl = menu.addMenu(f"➕ Masukkan {len(tracks_to_process)} Lagu ke Playlist")
            for pl in all_pls: 
                sub_pl.addAction(QAction(f"📑 {pl['name']}", self, triggered=lambda ch, pid=pl['id']: self.add_multiple_to_playlist(tracks_to_process, pid)))
                
        if self.view_mode == 'playlist':
            menu.addAction(QAction(f"❌ Hapus {len(tracks_to_process)} Lagu dari Playlist Ini", self, triggered=lambda: self.remove_multiple_from_current_playlist(tracks_to_process)))
        
        if len(tracks_to_process) == 1:
            menu.addSeparator()
            menu.addAction(QAction("ℹ️ Rincian Info Lagu", self, triggered=lambda: TrackInfoDialog(tracks_to_process[0], self).exec()))
            menu.addAction(QAction("📂 Buka Lokasi File", self, triggered=lambda: subprocess.Popen(['xdg-open', os.path.dirname(tracks_to_process[0]['path'])])))
        
        menu.addSeparator()
        menu.addAction(QAction(f"🗑️ Hapus {len(tracks_to_process)} Lagu dari Library", self, triggered=lambda: self.remove_multiple_from_db(tracks_to_process)))
        menu.exec(self.table_view.viewport().mapToGlobal(pos))

    def play_selected_track(self, real_row):
        self.playback.queue = self.tracks
        self.playback.current_index = real_row
        self.playback.play_track(self.tracks[real_row])
        self.update_queue_ui()
        
    def play_specific_tracks(self, tracks):
        self.playback.queue = tracks
        self.playback.current_index = 0
        self.playback.play_track(tracks[0])
        self.update_queue_ui()

    def remove_multiple_from_db(self, tracks):
        if QMessageBox.question(self, "Konfirmasi", f"Hapus {len(tracks)} lagu ini dari aplikasi?") == QMessageBox.StandardButton.Yes:
            for track in tracks:
                self.conn.cursor().execute("DELETE FROM playlist_tracks WHERE track_id = ?", (track['id'],))
                self.conn.cursor().execute("DELETE FROM tracks WHERE id = ?", (track['id'],))
            self.conn.commit()
            self.load_library()
            if self.view_mode == 'home':
                self.refresh_home_view()

    def filter_tracks(self, text):
        if text and self.right_stack.currentIndex() != 1:
            self.view_mode, self.view_param = 'all', None
            self.set_active_dock(self.btn_nav_songs)
            self.set_view_title("Hasil Pencarian")
            self.album_header.hide()
            self.right_stack.setCurrentIndex(1)
            self.load_library()
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.setFilterFixedString(text)

    def on_track_double_clicked(self, proxy_index):
        self.play_selected_track(self.proxy_model.mapToSource(proxy_index).row())

    def run_scanner(self, full_rescan=False):
        logger.info(f"Memulai pemindaian library (full_rescan={full_rescan})")
        self.scanner = LibraryScanner(full_rescan=full_rescan)
        self.scanner.finished.connect(self.on_scan_finished)
        self.scanner.start()

    def on_scan_finished(self, stats):
        logger.info(f"Pemindaian selesai: {stats}")
        self.load_library()
        if self.view_mode == 'home':
            self.refresh_home_view()
        elif self.view_mode == 'settings':
            self.settings_page.refresh_diagnostics()

    def on_toggle_shuffle(self):
        is_on = self.playback.toggle_shuffle()
        self.btn_shuffle.setObjectName("pillBtnActive" if is_on else "pillBtn")
        self.btn_shuffle.style().unpolish(self.btn_shuffle)
        self.btn_shuffle.style().polish(self.btn_shuffle)
        self.ambient_page.btn_shuffle.setStyleSheet(
            "background-color: rgba(255,255,255,60); border: none; border-radius: 20px; padding: 0px;" if is_on
            else "background: transparent; border: none; border-radius: 20px; padding: 0px;"
        )
        self.refresh_player_icons()
        self.save_setting("shuffle", str(is_on))

    def on_toggle_repeat(self):
        mode = self.playback.toggle_repeat()
        is_active = mode in (1, 2)
        self.btn_repeat.setObjectName("pillBtnActive" if is_active else "pillBtn")
        self.btn_repeat.style().unpolish(self.btn_repeat)
        self.btn_repeat.style().polish(self.btn_repeat)
        rep_kind = "repeat_one" if mode == 2 else "repeat"
        self.ambient_page.btn_repeat.setIcon(make_media_icon(rep_kind, QColor(255, 255, 255), 34))
        self.ambient_page.btn_repeat.setStyleSheet(
            "background-color: rgba(255,255,255,60); border: none; border-radius: 20px; padding: 0px;" if is_active
            else "background: transparent; border: none; border-radius: 20px; padding: 0px;"
        )
        self.refresh_player_icons()
        self.save_setting("repeat", mode)

    def on_toggle_mute(self):
        self.is_muted = self.playback.toggle_mute()
        self.refresh_player_icons()

    def update_play_button_text(self, state):
        self.is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.refresh_player_icons()
        white = QColor(255, 255, 255)
        self.ambient_page.btn_play.setIcon(make_media_icon("pause" if self.is_playing else "play", white, 44))

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape and self.main_stack.currentIndex() == 1:
                self.main_stack.setCurrentIndex(0); return True
            if event.key() == Qt.Key.Key_Space and not self.search_bar.hasFocus():
                self.playback.play_pause(); return True
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                if event.key() == Qt.Key.Key_F:
                    if self.main_stack.currentIndex() == 1: self.main_stack.setCurrentIndex(0)
                    self.search_bar.setFocus(); self.search_bar.selectAll(); return True
                if event.key() == Qt.Key.Key_Right: self.playback.next_track(); return True
                if event.key() == Qt.Key.Key_Left: self.playback.prev_track(); return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self.search_bar.hasFocus():
                if self.main_stack.currentIndex() == 0 and self.right_stack.currentIndex() == 1:
                    current = self.table_view.currentIndex()
                    if current.isValid(): self.on_track_double_clicked(current)
                return True
        return super().eventFilter(source, event)

    def update_now_playing(self, track):
        title = track.get('title') or "Unknown"
        artist = track.get('artist') or "Unknown Artist"
        self.current_duration = track.get('duration_ms') or 0

        self.lbl_side_title.setText(title)
        self.lbl_side_artist.setText(artist)
        self.lbl_pill_title.setText(title)
        self.lbl_pill_artist.setText(artist)

        self.slider_progress.setRange(0, self.current_duration)
        self.lbl_time_pos.setText("00:00")
        self.lbl_time_dur.setText(format_time(self.current_duration))

        is_fav = (track.get('rating') or 0) > 0
        self.update_favorite_icon(is_fav)

        pix_large = get_cached_cover_pixmap(track['path'], 300, 14)
        if pix_large:
            self.lbl_side_cover.setPixmap(round_pixmap(pix_large, 234, 12))
            self.lbl_pill_cover.setPixmap(round_pixmap(pix_large, 46, 10))
            self.ambient_page.set_track_info(title, artist, self.current_duration, pix_large)
        else:
            self.lbl_side_cover.setPixmap(generate_fallback_cover(234, 12))
            self.lbl_pill_cover.setPixmap(generate_fallback_cover(46, 10))
            self.ambient_page.set_track_info(title, artist, self.current_duration, QPixmap())

        if self.tray_icon.isVisible():
            self.tray_icon.showMessage("Sedang Diputar 🎵", f"{title} - {artist}", QSystemTrayIcon.MessageIcon.NoIcon, 3000)

        self.update_queue_ui()

    def update_progress(self, ms):
        self.current_position_ms = ms
        self.ambient_page.update_position(ms)
        if not self.slider_progress.isSliderDown():
            self.slider_progress.setValue(ms)
            self.lbl_time_pos.setText(format_time(ms))
