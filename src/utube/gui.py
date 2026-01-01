"""PyQt6-based GUI that delivers a dark, high-contrast experience for the harvester."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import urllib.request
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Dict, List, Optional

from math import sin

from PyQt6.QtCore import (
    QModelIndex,
    QAbstractTableModel,
    QRunnable,
    QThreadPool,
    QRectF,
    Qt,
    QUrl,
    pyqtSignal,
    QObject,
    QSortFilterProxyModel,
)
from PyQt6.QtGui import (
    QFont,
    QIcon,
    QPainter,
    QPixmap,
    QColor,
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QSoundEffect
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QHeaderView,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

from .config import load_defaults
from .controller import DownloadManager, Streamer
from .extractor import SearchFilters, TrackMetadata, search_tracks

try:
    import yt_dlp
except ImportError:  # pragma: no cover - runtime may not have yt-dlp installed yet
    yt_dlp = None

ACCENT_COLOR = "#4DA3FF"
BACKGROUND = "#121212"
PANEL = "#1E1E1E"
SECONDARY_PANEL = "#242424"
DIVIDER = "#333333"
TEXT_PRIMARY = "#E0E0E0"
DISABLED_TEXT = "#6A6A6A"

STYLE_SHEET = f"""
QWidget {{
    background-color: {BACKGROUND};
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI', 'Roboto', sans-serif;
}}
QFrame#card {{
    background-color: {PANEL};
    border: 1px solid {DIVIDER};
    border-radius: 8px;
    padding: 12px;
}}
QPushButton {{
    background-color: transparent;
    color: {TEXT_PRIMARY};
    border: 1px solid {DIVIDER};
    border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover, QPushButton:focus {{
    border-color: {ACCENT_COLOR};
}}
QLineEdit, QComboBox, QSpinBox {{
    background-color: {SECONDARY_PANEL};
    border: 1px solid {DIVIDER};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 4px 8px;
}}
QLabel {{
    color: {TEXT_PRIMARY};
}}
"""

try:
    APP_VERSION = version("utube-music-harvester")
except (PackageNotFoundError, FileNotFoundError):
    APP_VERSION = "0.1.0"
PYQT_VERSION = getattr(sys.modules.get("PyQt6.QtCore"), "PYQT_VERSION_STR", "Unknown")
YT_DLP_VERSION = getattr(yt_dlp, "__version__", "not installed")
FFMPEG_PATH = shutil.which("ffmpeg") or "not on PATH"

class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(object)


class Worker(QRunnable):
    def __init__(self, fn, *args, progress=False, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.progress = progress
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            kwargs = dict(self.kwargs)
            if self.progress:
                kwargs['progress_callback'] = self.signals.progress.emit
            result = self.fn(*self.args, **kwargs)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        else:
            self.signals.finished.emit(result)


class TrackTableModel(QAbstractTableModel):
    HEADERS = ['', 'Title', 'Uploader', 'Duration', 'Views', 'Uploaded', 'Type']

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._tracks: List[TrackMetadata] = []
        self._icon_cache: dict[str, QIcon] = {}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._tracks)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        track = self._tracks[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DecorationRole and column == 0:
            return self._icon_for_track(track)
        if role == Qt.ItemDataRole.DisplayRole:
            match column:
                case 1:
                    return track.title
                case 2:
                    return track.uploader
                case 3:
                    return self._format_duration(track.duration_seconds)
                case 4:
                    return self._format_views(track.view_count)
                case 5:
                    return track.upload_date or 'N/A'
                case 6:
                    return self._file_type_label(self._normalize_file_type(track.file_type))
        if role == Qt.ItemDataRole.ToolTipRole:
            return track.description or track.title
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

    def append_track(self, track: TrackMetadata) -> None:
        self.beginInsertRows(QModelIndex(), len(self._tracks), len(self._tracks))
        self._tracks.append(track)
        self.endInsertRows()

    def clear(self) -> None:
        self.beginResetModel()
        self._tracks.clear()
        self.endResetModel()

    def track_at(self, row: int) -> TrackMetadata:
        return self._tracks[row]

    def _icon_for_track(self, track: TrackMetadata) -> QIcon:
        normalized = self._normalize_file_type(track.file_type)
        label = 'V' if normalized == 'mp4' else 'A'
        if normalized in self._icon_cache:
            return self._icon_cache[normalized]
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(ACCENT_COLOR))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 16, 16)
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, label)
        painter.end()
        icon = QIcon(pixmap)
        self._icon_cache[normalized] = icon
        return icon

    @staticmethod
    def _format_duration(duration: Optional[int]) -> str:
        if not duration:
            return 'N/A'
        mins, secs = divmod(duration, 60)
        return f'{mins}:{secs:02}'

    @staticmethod
    def _format_views(views: Optional[int]) -> str:
        return f'{views:,}' if views else 'N/A'

    @staticmethod
    def _normalize_file_type(value: str) -> str:
        cleaned = value.lower().strip().lstrip('.')
        return cleaned or 'unknown'

    @staticmethod
    def _file_type_label(normalized: str) -> str:
        if normalized == 'unknown':
            return 'Unknown'
        label = 'Video' if normalized == 'mp4' else 'Audio'
        return f"{label} ({normalized.upper()})"


class TrackFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._filter_text = ''
        self._filter_type = 'all'

    def set_search_filter(self, text: str) -> None:
        self._filter_text = text.strip().lower()
        self.invalidateFilter()

    def set_type_filter(self, file_type: str) -> None:
        self._filter_type = file_type.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model: TrackTableModel = self.sourceModel()  # type: ignore[assignment]
        track = model.track_at(source_row)
        if self._filter_type not in ('all', ''):
            normalized = model._normalize_file_type(track.file_type)
            if self._filter_type == 'audio' and normalized == 'mp4':
                return False
            if self._filter_type == 'video' and normalized != 'mp4':
                return False
        if self._filter_text:
            haystack = ' '.join(
                filter(None, (track.title, track.uploader, track.description or '', ' '.join(track.tags)))
            ).lower()
            if self._filter_text not in haystack:
                return False
        return True


class LibraryView(QWidget):
    songActivated = pyqtSignal(TrackMetadata)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.model = TrackTableModel(self)
        self.proxy = TrackFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Filter title, artist, tagsâ€¦')
        self.search_input.textChanged.connect(self.proxy.set_search_filter)
        controls.addWidget(self.search_input)
        self.type_combo = QComboBox()
        self.type_combo.addItems(['All', 'Audio', 'Video'])
        self.type_combo.currentTextChanged.connect(lambda value: self.proxy.set_type_filter(value))
        controls.addWidget(self.type_combo)
        self.count_label = QLabel('0 tracks')
        controls.addWidget(self.count_label)
        controls.addStretch()

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self._emit_selected_track)
        self.table.activated.connect(self._emit_selected_track)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.model.rowsInserted.connect(self._update_count)
        self.model.modelReset.connect(self._update_count)

    def _emit_selected_track(self, index: QModelIndex) -> None:
        source_index = self.proxy.mapToSource(index)
        track = self.model.track_at(source_index.row())
        self.songActivated.emit(track)

    def _update_count(self, *_):
        self.count_label.setText(f"{self.model.rowCount()} tracks")

    def add_track(self, track: TrackMetadata) -> None:
        self.model.append_track(track)

    def clear(self) -> None:
        self.model.clear()

    def selected_tracks(self) -> List[TrackMetadata]:
        selected: List[TrackMetadata] = []
        for index in self.table.selectionModel().selectedRows():
            selected.append(self.model.track_at(self.proxy.mapToSource(index).row()))
        return selected

    def is_video(self, track: TrackMetadata) -> bool:
        return self.model._normalize_file_type(track.file_type) == 'mp4'


class WaveformView(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._progress = 0.0
        self._peaks = [abs(sin(i / 3.5)) * 0.8 + 0.1 for i in range(120)]

    def set_progress(self, fraction: float) -> None:
        self._progress = max(0.0, min(1.0, fraction))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(SECONDARY_PANEL))
        width = self.width()
        height = self.height()
        if not self._peaks:
            painter.end()
            return
        bar_width = width / len(self._peaks)
        for idx, peak in enumerate(self._peaks):
            x = idx * bar_width
            bar_height = peak * height
            rect = QRectF(x, height - bar_height, bar_width * 0.8, bar_height)
            painter.setBrush(QColor(ACCENT_COLOR if idx / len(self._peaks) < self._progress else DIVIDER))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 2, 2)
        cursor = int(width * self._progress)
        painter.setPen(QColor(ACCENT_COLOR))
        painter.drawLine(cursor, 0, cursor, height)
        painter.end()


class EqualizerPanel(QWidget):
    FREQUENCIES = [60, 250, 1000, 4000, 16000]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QGridLayout()
        for idx, freq in enumerate(self.FREQUENCIES):
            slider = QSlider(Qt.Orientation.Vertical)
            slider.setRange(-12, 12)
            slider.setValue(0)
            slider.setTickInterval(3)
            label = QLabel(f"{freq}Hz")
            frame = QVBoxLayout()
            frame.addWidget(slider)
            frame.addWidget(label)
            layout.addLayout(frame, 0, idx)
        self.setLayout(layout)


class SoundManager(QObject):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.effects: dict[str, QSoundEffect] = {}
        project_root = Path(__file__).resolve().parents[1]
        click = project_root / 'assets' / 'click.wav'
        if click.exists():
            self._load_effect('click', click)

    def _load_effect(self, name: str, path: Path) -> None:
        effect = QSoundEffect(self)
        effect.setSource(QUrl.fromLocalFile(str(path)))
        effect.setVolume(0.35)
        self.effects[name] = effect

    def play_click(self) -> None:
        if (effect := self.effects.get('click')):
            effect.play()


class PlayerController(QObject):
    trackChanged = pyqtSignal(TrackMetadata)
    stateChanged = pyqtSignal(QMediaPlayer.PlaybackState)
    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    errorOccurred = pyqtSignal(str)
    mediaStatusChanged = pyqtSignal(QMediaPlayer.MediaStatus)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.video_widget = QVideoWidget()
        self.player.setVideoOutput(self.video_widget)
        self._current_track: Optional[TrackMetadata] = None
        self._is_video = False
        self.player.playbackStateChanged.connect(self.stateChanged)
        self.player.positionChanged.connect(lambda pos: self.positionChanged.emit(int(pos)))
        self.player.durationChanged.connect(lambda duration: self.durationChanged.emit(int(duration)))
        self.player.errorOccurred.connect(self._on_media_error)
        self.player.mediaStatusChanged.connect(self.mediaStatusChanged)

    def play_track(self, track: TrackMetadata, stream_url: str, prefer_video: bool) -> None:
        self._current_track = track
        self._is_video = prefer_video
        self.video_widget.setVisible(prefer_video)
        source_url = QUrl.fromLocalFile(stream_url) if Path(stream_url).exists() else QUrl(stream_url)
        self.player.setSource(source_url)
        self.player.play()
        self.trackChanged.emit(track)

    def toggle_playback(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def stop(self) -> None:
        self.player.stop()

    def set_position(self, position: int) -> None:
        self.player.setPosition(position)

    def set_volume(self, value: int) -> None:
        self.audio_output.setVolume(value / 100)

    def current_track(self) -> Optional[TrackMetadata]:
        return self._current_track

    def is_video(self) -> bool:
        return self._is_video

    def _on_media_error(self, error: QMediaPlayer.Error) -> None:
        if error != QMediaPlayer.Error.NoError:
            self.errorOccurred.emit(self.player.errorString())


class PlayerView(QWidget):
    def __init__(self, controller: PlayerController, sounds: SoundManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.sounds = sounds

        self.title_label = QLabel('Select a track to play')
        self.title_label.setStyleSheet('font-weight: 600; font-size: 18px;')
        self.artist_label = QLabel('')
        self.info_label = QLabel('Waiting for playback')

        meta_layout = QVBoxLayout()
        meta_layout.addWidget(self.title_label)
        meta_layout.addWidget(self.artist_label)
        meta_layout.addWidget(self.info_label)

        video_frame = QFrame()
        video_frame.setFrameShape(QFrame.Shape.StyledPanel)
        video_layout = QVBoxLayout()
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.addWidget(self.controller.video_widget)
        video_frame.setLayout(video_layout)

        self.waveform = WaveformView()
        self.equalizer = EqualizerPanel()

        controls = QHBoxLayout()
        self.play_button = QPushButton('Play')
        self.play_button.clicked.connect(self._toggle_play)
        self.stop_button = QPushButton('Stop')
        self.stop_button.clicked.connect(self._stop)
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderMoved.connect(self.controller.set_position)
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.valueChanged.connect(self.controller.set_volume)
        controls.addWidget(self.play_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(QLabel('Seek'))
        controls.addWidget(self.seek_slider)
        controls.addWidget(QLabel('Vol'))
        controls.addWidget(self.volume_slider)

        center = QHBoxLayout()
        center.addWidget(video_frame, 2)
        center.addWidget(self.waveform, 3)
        center.addWidget(self.equalizer, 2)

        layout = QVBoxLayout()
        layout.addLayout(meta_layout)
        layout.addLayout(center)
        layout.addLayout(controls)
        self.setLayout(layout)

        self.controller.trackChanged.connect(self._on_track_changed)
        self.controller.positionChanged.connect(self._on_position_changed)
        self.controller.durationChanged.connect(self._on_duration_changed)
        self.controller.stateChanged.connect(self._on_state_changed)

    def _toggle_play(self) -> None:
        self.sounds.play_click()
        self.controller.toggle_playback()

    def _stop(self) -> None:
        self.sounds.play_click()
        self.controller.stop()

    def _on_track_changed(self, track: TrackMetadata) -> None:
        self.title_label.setText(track.title)
        self.artist_label.setText(track.uploader)
        self.info_label.setText('Resolving streamâ€¦')
        self.waveform.set_progress(0.0)

    def _on_position_changed(self, position: int) -> None:
        duration = self.controller.player.duration()
        if duration > 0:
            self.waveform.set_progress(min(position / duration, 1.0))
        self.seek_slider.blockSignals(True)
        self.seek_slider.setValue(position)
        self.seek_slider.blockSignals(False)

    def _on_duration_changed(self, duration: int) -> None:
        self.seek_slider.setRange(0, duration)

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_button.setText('Pause')
            self.info_label.setText('Playing')
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.play_button.setText('Play')
            self.info_label.setText('Paused')
        else:
            self.play_button.setText('Play')
            self.info_label.setText('Stopped')


SEARCH_CHUNK_SIZE = 20

class UTubeGui(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("UTube Music Harvester")
        self.thread_pool = QThreadPool()
        self.defaults = load_defaults()
        self.sound_manager = SoundManager(self)
        self.player_controller = PlayerController(self)
        self.library_view = LibraryView(self)
        self.player_view = PlayerView(self.player_controller, self.sound_manager, self)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.library_view)
        self.stack.addWidget(self.player_view)
        self.status_label = QLabel("Ready")
        self.now_playing_label = QLabel("No track playing")
        self.last_search_summary_label = QLabel("No search yet")
        self.library_view.songActivated.connect(self._handle_song_activation)
        self.player_controller.trackChanged.connect(self._update_now_playing_label)
        self.player_controller.stateChanged.connect(self._on_player_state_updated)
        self.player_controller.errorOccurred.connect(self._handle_player_error)
        self.player_controller.mediaStatusChanged.connect(self._on_media_status_changed)
        self._play_attempts: Dict[str, int] = {}
        self._temp_media_files: set[str] = set()
        self._loop_enabled = False
        self._last_streams: Dict[str, str] = {}
        self._build_ui()
        self.tracks: List[TrackMetadata] = []

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_navigation_bar())
        layout.addWidget(self.stack)
        layout.addWidget(self._build_now_playing_bar())
        central.setLayout(layout)
        self.setCentralWidget(central)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._build_filters_dock())

    def _build_navigation_bar(self) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        library_btn = QPushButton("Library")
        library_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.library_view))
        player_btn = QPushButton("Player")
        player_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.player_view))
        layout.addWidget(library_btn)
        layout.addWidget(player_btn)
        layout.addStretch()
        layout.addWidget(self.last_search_summary_label)
        container.setLayout(layout)
        return container

    def _build_filters_dock(self) -> QDockWidget:
        dock = QDockWidget("Filters", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setWidget(self._build_search_card())
        return dock

    def _build_search_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout()
        layout.setSpacing(12)

        top_grid = QGridLayout()
        top_grid.setHorizontalSpacing(12)
        top_grid.setVerticalSpacing(8)
        top_grid.addWidget(QLabel("Genre"), 0, 0)
        self.genre_input = QLineEdit()
        self.genre_input.setPlaceholderText("e.g., trance")
        top_grid.addWidget(self.genre_input, 0, 1)
        top_grid.addWidget(QLabel("Artist"), 0, 2)
        self.artist_input = QLineEdit()
        self.artist_input.setPlaceholderText("optional")
        top_grid.addWidget(self.artist_input, 0, 3)
        top_grid.addWidget(QLabel("Order"), 1, 0)
        self.order_combo = QComboBox()
        self.order_combo.addItems(["relevance", "date", "longest", "shortest"])
        top_grid.addWidget(self.order_combo, 1, 1)
        top_grid.addWidget(QLabel("Stream format"), 1, 2)
        self.stream_format_input = QLineEdit(self.defaults.stream_format)
        top_grid.addWidget(self.stream_format_input, 1, 3)
        top_grid.addWidget(QLabel("Video quality"), 2, 0)
        self.video_quality_combo = QComboBox()
        self.video_quality_combo.addItems(["high", "medium", "low"])
        self.video_quality_combo.setCurrentText(self.defaults.video_quality)
        top_grid.addWidget(self.video_quality_combo, 2, 1)
        top_grid.addWidget(QLabel("JS runtime"), 2, 2)
        self.js_runtime_input = QLineEdit(self.defaults.js_runtime or "")
        self.js_runtime_input.setPlaceholderText("node, deno, etc.")
        top_grid.addWidget(self.js_runtime_input, 2, 3)
        top_grid.addWidget(QLabel("Remote components"), 3, 0)
        self.remote_components_input = QLineEdit(
            ", ".join(self.defaults.remote_components) if self.defaults.remote_components else ""
        )
        self.remote_components_input.setPlaceholderText("ejs:github")
        top_grid.addWidget(self.remote_components_input, 3, 1, 1, 3)

        layout.addLayout(top_grid)

        filter_grid = QGridLayout()
        filter_grid.setHorizontalSpacing(12)
        filter_grid.setVerticalSpacing(8)
        filter_grid.addWidget(QLabel("Max entries"), 0, 0)
        self.max_entries_spin = QSpinBox()
        self.max_entries_spin.setRange(1, 500)
        self.max_entries_spin.setValue(50)
        filter_grid.addWidget(self.max_entries_spin, 0, 1)
        filter_grid.addWidget(QLabel("Min duration"), 1, 0)
        self.min_duration_spin = QSpinBox()
        self.min_duration_spin.setSuffix(" sec")
        self.min_duration_spin.setRange(0, 3600)
        self.min_duration_spin.setSpecialValueText("Any")
        filter_grid.addWidget(self.min_duration_spin, 1, 1)
        filter_grid.addWidget(QLabel("Max duration"), 1, 2)
        self.max_duration_spin = QSpinBox()
        self.max_duration_spin.setSuffix(" sec")
        self.max_duration_spin.setRange(0, 3600)
        self.max_duration_spin.setSpecialValueText("Any")
        filter_grid.addWidget(self.max_duration_spin, 1, 3)
        filter_grid.addWidget(QLabel("Min views"), 2, 0)
        self.min_views_spin = QSpinBox()
        self.min_views_spin.setRange(0, 10_000_000)
        self.min_views_spin.setSpecialValueText("Any")
        filter_grid.addWidget(self.min_views_spin, 2, 1)
        filter_grid.addWidget(QLabel("Max views"), 2, 2)
        self.max_views_spin = QSpinBox()
        self.max_views_spin.setRange(0, 10_000_000)
        self.max_views_spin.setSpecialValueText("Any")
        filter_grid.addWidget(self.max_views_spin, 2, 3)
        filter_grid.addWidget(QLabel("Keywords"), 3, 0)
        self.keywords_input = QLineEdit()
        self.keywords_input.setPlaceholderText("optional terms")
        filter_grid.addWidget(self.keywords_input, 3, 1, 1, 3)
        self.sfw_checkbox = QCheckBox("Safe-for-work")
        filter_grid.addWidget(self.sfw_checkbox, 4, 0)
        layout.addLayout(filter_grid)

        self.search_button = QPushButton("Search")
        self.search_button.setProperty("primary", True)
        self.search_button.clicked.connect(self._start_search)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.search_button)
        layout.addLayout(actions)

        self.last_search_summary_label.setStyleSheet("color: #8F9AA5;")
        layout.addWidget(self.last_search_summary_label)

        download_layout = QHBoxLayout()
        self.download_button = QPushButton("Download Selected")
        self.download_button.clicked.connect(self._download_selected_tracks)
        self.choose_dir_button = QPushButton("Change download folder")
        self.choose_dir_button.clicked.connect(self._select_download_dir)
        self.download_dir_label = QLabel(str(self.defaults.download_dir))
        download_layout.addWidget(self.download_button)
        download_layout.addWidget(self.choose_dir_button)
        download_layout.addStretch()
        download_layout.addWidget(self.download_dir_label)
        layout.addLayout(download_layout)

        card.setLayout(layout)
        return card

    def _build_now_playing_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        layout.addWidget(QLabel("Now playing:"))
        layout.addWidget(self.now_playing_label)
        layout.addStretch()
        play_btn = QPushButton("Play/Pause")
        play_btn.clicked.connect(self._toggle_now_playback)
        stop_btn = QPushButton("Stop")
        stop_btn.clicked.connect(self.player_controller.stop)
        open_btn = QPushButton("Open Player")
        open_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.player_view))
        self.loop_button = QPushButton("Loop Off")
        self.loop_button.setCheckable(True)
        self.loop_button.clicked.connect(self._toggle_loop_mode)
        layout.addWidget(play_btn)
        layout.addWidget(stop_btn)
        layout.addWidget(open_btn)
        layout.addWidget(self.loop_button)
        layout.addWidget(self.status_label)
        bar.setLayout(layout)
        return bar

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _toggle_now_playback(self) -> None:
        self.sound_manager.play_click()
        self.player_controller.toggle_playback()

    def _toggle_loop_mode(self, checked: bool) -> None:
        self._loop_enabled = checked
        self.loop_button.setText("Loop On" if checked else "Loop Off")

    def _handle_song_activation(self, track: TrackMetadata) -> None:
        prefer_video = self.library_view.is_video(track)
        self._set_status(f"Resolving {'video' if prefer_video else 'audio'} stream...")
        worker = Worker(
            self._resolve_stream_url,
            track,
            self.stream_format_input.text().strip(),
            prefer_video,
            self._current_video_quality(),
        )
        worker.signals.finished.connect(lambda url, t=track: self._route_media_playback(t, url))
        worker.signals.error.connect(self._on_worker_error)
        self.thread_pool.start(worker)
        self.stack.setCurrentWidget(self.player_view)

    def _route_media_playback(self, track: TrackMetadata, stream_url: str) -> None:
        self._cleanup_temp_files()
        self.player_controller.play_track(track, stream_url, self.library_view.is_video(track))
        self._update_now_playing_label(track)
        self._play_attempts.pop(track.video_id, None)
        self._last_streams[track.video_id] = stream_url

    def _handle_player_error(self, message: str) -> None:
        track = self.player_controller.current_track()
        if not track:
            return
        self._set_status(f"Playback error: {message}")
        attempts = self._play_attempts.get(track.video_id, 0) + 1
        self._play_attempts[track.video_id] = attempts
        if attempts <= 1:
            self._set_status("Retrying stream after transient error...")
            self._retry_stream(track)
        else:
            self._set_status("Caching stream locally because live playback keeps failing.")
            self._start_local_fallback(track)

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status != QMediaPlayer.MediaStatus.EndOfMedia or not self._loop_enabled:
            return
        track = self.player_controller.current_track()
        if not track:
            return
        last_stream = self._last_streams.get(track.video_id)
        if not last_stream:
            return
        self._set_status("Looping current track...")
        self.player_controller.play_track(track, last_stream, self.library_view.is_video(track))

    def _retry_stream(self, track: TrackMetadata) -> None:
        prefer_video = self.library_view.is_video(track)
        worker = Worker(
            self._resolve_stream_url,
            track,
            self.stream_format_input.text().strip(),
            prefer_video,
            self._current_video_quality(),
        )
        worker.signals.finished.connect(lambda url, t=track: self._route_media_playback(t, url))
        worker.signals.error.connect(self._on_worker_error)
        self.thread_pool.start(worker)

    def _start_local_fallback(self, track: TrackMetadata) -> None:
        prefer_video = self.library_view.is_video(track)
        worker = Worker(
            self._download_stream_to_temp,
            track,
            prefer_video,
            self._current_video_quality(),
            self.stream_format_input.text().strip(),
        )
        worker.signals.finished.connect(lambda path, t=track, pv=prefer_video: self._play_local_media(t, path, pv))
        worker.signals.error.connect(self._on_worker_error)
        self.thread_pool.start(worker)

    def _download_stream_to_temp(
        self,
        track: TrackMetadata,
        prefer_video: bool,
        video_quality: str,
        stream_format: str,
    ) -> str:
        selector = "bestvideo+bestaudio/best" if prefer_video else stream_format or self.defaults.stream_format
        links = Streamer(
            format_selector=selector,
            js_runtime=self._current_js_runtime(),
            remote_components=self._current_remote_components(),
            prefer_video=prefer_video,
            video_quality=video_quality,
        ).stream_links([track])
        if not links:
            raise RuntimeError("Unable to acquire fallback stream link.")
        stream_url = links[0].stream_url

        suffix = ".mp4" if prefer_video else ".m4a"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_file_path = temp_file.name
        temp_file.close()
        headers = {"User-Agent": "Mozilla/5.0"}
        request = urllib.request.Request(stream_url, headers=headers)
        with urllib.request.urlopen(request, timeout=60) as response, open(temp_file_path, "wb") as out:
            shutil.copyfileobj(response, out)
        return temp_file_path

    def _play_local_media(self, track: TrackMetadata, path: str, prefer_video: bool) -> None:
        self._cleanup_temp_files(preserve=path)
        self._temp_media_files.add(path)
        self._last_streams[track.video_id] = path
        self.player_controller.play_track(track, path, prefer_video)
        self._update_now_playing_label(track)
        self.stack.setCurrentWidget(self.player_view)

    def _cleanup_temp_files(self, preserve: Optional[str] = None) -> None:
        for tmp in list(self._temp_media_files):
            if preserve and tmp == preserve:
                continue
            try:
                os.remove(tmp)
            except OSError:
                pass
            self._temp_media_files.discard(tmp)

    def _resolve_stream_url(
        self, track: TrackMetadata, stream_format: str, prefer_video: bool, video_quality: str
    ) -> str:
        selector = "bestvideo+bestaudio/best" if prefer_video else stream_format or self.defaults.stream_format
        links = Streamer(
            format_selector=selector,
            js_runtime=self._current_js_runtime(),
            remote_components=self._current_remote_components(),
            prefer_video=prefer_video,
            video_quality=video_quality,
        ).stream_links([track])
        if not links:
            raise RuntimeError("No stream URL available for the selected track.")
        return links[0].stream_url

    def _current_video_quality(self) -> str:
        return self.video_quality_combo.currentText().lower()

    def _current_js_runtime(self) -> Optional[str]:
        value = self.js_runtime_input.text().strip()
        return value or self.defaults.js_runtime

    def _current_remote_components(self) -> List[str]:
        text = self.remote_components_input.text().strip()
        if text:
            return [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]
        return self.defaults.remote_components

    def _start_search(self) -> None:
        genre = self.genre_input.text().strip()
        artist = self.artist_input.text().strip()
        if not genre and not artist:
            self._set_status("Enter a genre or artist before searching.")
            return
        self.library_view.clear()
        self.tracks = []
        self.last_search_summary_label.setText("Streaming resultsâ€¦")
        self.search_button.setEnabled(False)
        self._set_status("Searching YouTube...")
        filters = self._build_filters()
        worker = Worker(
            search_tracks,
            genre or None,
            artist=artist or None,
            filters=filters,
            order=self.order_combo.currentText(),
            js_runtime=self._current_js_runtime(),
            remote_components=self._current_remote_components(),
            chunk_size=SEARCH_CHUNK_SIZE,
            progress=True,
            max_results=self.max_entries_spin.value(),
        )
        worker.signals.progress.connect(self._on_track_discovered)
        worker.signals.finished.connect(self._on_search_finished)
        worker.signals.finished.connect(lambda _: self.search_button.setEnabled(True))
        worker.signals.error.connect(self._on_worker_error)
        self.thread_pool.start(worker)
        self.stack.setCurrentWidget(self.library_view)

    def _on_track_discovered(self, track: TrackMetadata) -> None:
        self.tracks.append(track)
        self.library_view.add_track(track)
        self.last_search_summary_label.setText(f"Streaming {len(self.tracks)} tracks")

    def _on_search_finished(self, tracks: List[TrackMetadata]) -> None:
        self._set_status(f"Found {len(tracks)} tracks.")
        self.last_search_summary_label.setText(f"Search complete: {len(tracks)} results")

    def _on_worker_error(self, message: str) -> None:
        self._set_status(f"Error: {message}")
        self.search_button.setEnabled(True)

    def _build_filters(self) -> Optional[SearchFilters]:
        min_duration = self.min_duration_spin.value() or None
        max_duration = self.max_duration_spin.value() or None
        min_views = self.min_views_spin.value() or None
        max_views = self.max_views_spin.value() or None
        safe_for_work = self.sfw_checkbox.isChecked()
        keywords = self.keywords_input.text().strip() or None
        if not any([min_duration, max_duration, min_views, max_views, safe_for_work, keywords]):
            return None
        return SearchFilters(
            min_duration=min_duration,
            max_duration=max_duration,
            min_views=min_views,
            max_views=max_views,
            upload_after=None,
            upload_before=None,
            safe_for_work=safe_for_work,
            keywords=keywords,
        )

    def _download_selected_tracks(self) -> None:
        tracks = self.library_view.selected_tracks()
        if not tracks:
            self._set_status("Select a track to download.")
            return
        download_dir = Path(self.download_dir_label.text())
        self._set_status("Downloading tracks...")
        worker = Worker(
            self._download_tracks,
            tracks,
            download_dir,
            self._current_js_runtime(),
            self._current_remote_components(),
        )
        worker.signals.finished.connect(lambda files: self._set_status(f"Downloaded {len(files)} files."))
        worker.signals.error.connect(self._on_worker_error)
        self.thread_pool.start(worker)

    def _download_tracks(
        self,
        tracks: List[TrackMetadata],
        download_dir: Path,
        js_runtime: Optional[str],
        remote_components: List[str],
    ) -> List[Path]:
        manager = DownloadManager(
            download_dir,
            js_runtime=js_runtime,
            remote_components=remote_components,
        )
        return manager.download_tracks(tracks)

    def _select_download_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Download folder", str(self.defaults.download_dir))
        if directory:
            self.download_dir_label.setText(directory)
            self._set_status(f"Download folder set to {directory}")

    def _update_now_playing_label(self, track: TrackMetadata) -> None:
        self.now_playing_label.setText(f"{track.title} â€” {track.uploader}")

    def _on_player_state_updated(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._set_status("Playing")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self._set_status("Paused")
        else:
            self._set_status("Stopped")

def apply_dark_theme(app: QApplication) -> None:
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE_SHEET)


def run_gui() -> None:
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    window = UTubeGui()
    window.show()
    app.exec()


if __name__ == "__main__":
    run_gui()
