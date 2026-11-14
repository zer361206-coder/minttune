import os
import fnmatch
from PyQt6.QtCore import QThread, pyqtSignal
import mutagen
from db.database import get_connection

class LibraryScanner(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict) # Mengirim statistik lengkap

    def __init__(self, full_rescan=False):
        super().__init__()
        self.full_rescan = full_rescan
        self.conn = get_connection()
        self.stats = {'added': 0, 'updated': 0, 'missing': 0, 'errors': 0}

    def is_blacklisted(self, filepath, blacklists):
        # Evaluasi aturan blacklist (folder dan glob pattern)
        for bl in blacklists:
            if bl['path'] and filepath.startswith(bl['path']):
                return True
            if bl['pattern'] and fnmatch.fnmatch(os.path.basename(filepath), bl['pattern']):
                return True
        return False

    def run(self):
        cursor = self.conn.cursor()

        # 1. Ambil folder Whitelist dan Blacklist dari database
        cursor.execute("SELECT * FROM library_folders WHERE type='whitelist' AND enabled=1")
        whitelists = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM library_folders WHERE type='blacklist' AND enabled=1")
        blacklists = [dict(r) for r in cursor.fetchall()]

        # Jika belum ada whitelist sama sekali
        if not whitelists:
            self.finished.emit(self.stats)
            return

        all_audio_files = []

        # 2. Telusuri folder whitelist
        for wl in whitelists:
            folder_path = wl['path']
            if not os.path.exists(folder_path):
                continue

            for root, dirs, files in os.walk(folder_path):
                # Potong direktori yang masuk blacklist agar tidak ditelusuri (hemat I/O)
                dirs[:] = [d for d in dirs if not self.is_blacklisted(os.path.join(root, d), blacklists) and not d.startswith('.')]

                for file in files:
                    if file.lower().endswith(('.mp3', '.flac', '.m4a', '.wav', '.ogg', '.opus')):
                        full_path = os.path.join(root, file)
                        if not self.is_blacklisted(full_path, blacklists):
                            all_audio_files.append((full_path, file))

        # 3. Proses file secara incremental
        for i, (filepath, filename) in enumerate(all_audio_files):
            try:
                stat = os.stat(filepath)
                mtime = stat.st_mtime
                file_size = stat.st_size

                # Cek database apakah file ini sudah ada dan belum berubah
                cursor.execute("SELECT id, mtime, file_size FROM tracks WHERE path=?", (filepath,))
                existing = cursor.fetchone()

                if existing and not self.full_rescan:
                    if existing['mtime'] == mtime and existing['file_size'] == file_size:
                        continue  # File tidak berubah, skip pembacaan mutagen (Cepat!)
                    else:
                        self.stats['updated'] += 1
                else:
                    self.stats['added'] += 1

                # Baca metadata dengan Mutagen
                audio = mutagen.File(filepath, easy=True)
                if audio is None: continue

                title = audio.get('title', [os.path.splitext(filename)[0]])[0]
                artist = audio.get('artist', ['Unknown Artist'])[0]
                album = audio.get('album', ['Unknown Album'])[0]
                duration = int(audio.info.length * 1000) if hasattr(audio.info, 'length') else 0

                cursor.execute('''INSERT INTO tracks (path, filename, title, artist, album, duration_ms, mtime, file_size, missing, excluded) 
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
                                  ON CONFLICT(path) DO UPDATE SET 
                                  title=excluded.title, artist=excluded.artist, album=excluded.album, 
                                  duration_ms=excluded.duration_ms, mtime=excluded.mtime, file_size=excluded.file_size, missing=0''',
                               (filepath, filename, title, artist, album, duration, mtime, file_size))

                if i % 15 == 0:
                    self.progress.emit(f"Memindai: {title}")
                    self.conn.commit()

            except Exception:
                self.stats['errors'] += 1

        # 4. Deteksi file yang hilang atau sekarang masuk blacklist
        cursor.execute("SELECT id, path FROM tracks WHERE missing=0")
        for track in cursor.fetchall():
            if not os.path.exists(track['path']) or self.is_blacklisted(track['path'], blacklists):
                cursor.execute("UPDATE tracks SET missing=1 WHERE id=?", (track['id'],))
                self.stats['missing'] += 1

        self.conn.commit()
        self.finished.emit(self.stats)
