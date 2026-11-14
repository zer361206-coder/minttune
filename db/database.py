import sqlite3
import os
from pathlib import Path

DATA_DIR = Path(os.getenv('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'minttune'
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'minttune.db'

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS library_folders (
        id INTEGER PRIMARY KEY, path TEXT UNIQUE, type TEXT, pattern TEXT, 
        enabled BOOLEAN DEFAULT 1, last_scanned_at REAL, status TEXT DEFAULT 'valid')''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS tracks (
        id INTEGER PRIMARY KEY, path TEXT UNIQUE, filename TEXT, title TEXT,
        artist TEXT, album_artist TEXT, album TEXT, genre TEXT, year INTEGER,
        track_no INTEGER, duration_ms INTEGER, codec TEXT, file_size INTEGER,
        mtime REAL, play_count INTEGER DEFAULT 0, last_played REAL DEFAULT 0,
        rating INTEGER DEFAULT 0, missing BOOLEAN DEFAULT 0,
        excluded BOOLEAN DEFAULT 0, artwork_id INTEGER)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS playlists (
        id INTEGER PRIMARY KEY, name TEXT UNIQUE, created_at REAL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS playlist_tracks (
        playlist_id INTEGER, track_id INTEGER, position INTEGER,
        FOREIGN KEY(playlist_id) REFERENCES playlists(id),
        FOREIGN KEY(track_id) REFERENCES tracks(id))''')

    # --- MIGRASI AMAN UNTUK DATABASE LAMA ---
    cursor.execute("PRAGMA table_info(tracks)")
    existing_cols = [col[1] for col in cursor.fetchall()]
    if 'rating' not in existing_cols:
        cursor.execute("ALTER TABLE tracks ADD COLUMN rating INTEGER DEFAULT 0")
    if 'last_played' not in existing_cols:
        cursor.execute("ALTER TABLE tracks ADD COLUMN last_played REAL DEFAULT 0")
    if 'play_count' not in existing_cols:
        cursor.execute("ALTER TABLE tracks ADD COLUMN play_count INTEGER DEFAULT 0")

    # --- INDEX UNTUK PERFORMA CEPAT (100K+ LAGU) ---
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_title ON tracks(title)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_path ON tracks(path)")

    conn.commit()
    conn.close()
