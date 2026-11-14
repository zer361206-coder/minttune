import random
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtCore import QUrl, QObject, pyqtSignal

class PlaybackService(QObject):
    track_changed = pyqtSignal(dict)
    track_played = pyqtSignal(dict)
    position_changed = pyqtSignal(int)
    state_changed = pyqtSignal(QMediaPlayer.PlaybackState)
    queue_updated = pyqtSignal()
    playback_error = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        self.player.positionChanged.connect(self.position_changed.emit)
        self.player.mediaStatusChanged.connect(self._handle_media_status)
        self.player.playbackStateChanged.connect(self.state_changed.emit)
        
        self.queue = []
        self.current_index = -1
        self.current_track = None
        
        self.is_shuffle = False
        self.repeat_mode = 0  

    def play_track(self, track: dict):
        self.current_track = track
        self.player.setSource(QUrl.fromLocalFile(track['path']))
        self.player.play()
        self.track_changed.emit(track)
        self.track_played.emit(track)

    def prepare_track(self, track: dict, position_ms: int = 0):
        self.current_track = track
        self.player.setSource(QUrl.fromLocalFile(track['path']))
        if position_ms > 0:
            self.player.setPosition(position_ms)
        self.track_changed.emit(track)
        self.position_changed.emit(position_ms)
        
    def play_pause(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def set_volume(self, value):
        self.audio_output.setVolume(value / 100.0)
        
    def toggle_mute(self):
        is_muted = not self.audio_output.isMuted()
        self.audio_output.setMuted(is_muted)
        return is_muted

    def seek(self, ms):
        self.player.setPosition(ms)

    def toggle_shuffle(self):
        self.is_shuffle = not self.is_shuffle
        return self.is_shuffle

    def toggle_repeat(self):
        self.repeat_mode = (self.repeat_mode + 1) % 3
        return self.repeat_mode

    def _handle_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.repeat_mode == 2:
                self.seek(0)
                self.player.play()
            else:
                self.next_track()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            name = self.current_track['filename'] if self.current_track else "File ini"
            self.playback_error.emit(
                f"Codec untuk '{name}' tidak tersedia atau file rusak.\n"
                "Instal paket GStreamer yang sesuai (plugins-good/bad/ugly/libav)."
            )

    def insert_next(self, tracks: list):
        if not self.queue:
            self.queue = tracks
            self.current_index = 0
            self.play_track(self.queue[0])
        else:
            idx = max(0, self.current_index)
            for i, track in enumerate(tracks):
                self.queue.insert(idx + 1 + i, track)
        self.queue_updated.emit()

    def append_queue(self, tracks: list):
        if not self.queue:
            self.queue = tracks
            self.current_index = 0
            self.play_track(self.queue[0])
        else:
            self.queue.extend(tracks)
        self.queue_updated.emit()

    def clear_queue(self):
        if self.current_track:
            self.queue = [self.current_track]
            self.current_index = 0
        else:
            self.queue = []
            self.current_index = -1
        self.queue_updated.emit()

    def next_track(self):
        if not self.queue: return

        if self.is_shuffle and len(self.queue) > 1:
            next_idx = self.current_index
            while next_idx == self.current_index:
                next_idx = random.randint(0, len(self.queue) - 1)
            self.current_index = next_idx
            self.play_track(self.queue[self.current_index])
            return

        if self.current_index < len(self.queue) - 1:
            self.current_index += 1
            self.play_track(self.queue[self.current_index])
        elif self.repeat_mode == 1:
            self.current_index = 0
            self.play_track(self.queue[0])

    def prev_track(self):
        if not self.queue: return
        if self.player.position() > 3000:
            self.seek(0)
            return

        if self.current_index > 0:
            self.current_index -= 1
            self.play_track(self.queue[self.current_index])
        elif self.repeat_mode == 1:
            self.current_index = len(self.queue) - 1
            self.play_track(self.queue[self.current_index])
