"""PyQt6-based GUI that delivers a dark, high-contrast experience for the harvester."""

from __future__ import annotations

import os
import shutil
import socket
import sys
import tempfile
import traceback
import urllib.parse
import urllib.request
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from ipaddress import ip_address
from pathlib import Path
from typing import Dict, List, Optional, Union

from math import cos, pi, sin

from PyQt6.QtCore import (
    QModelIndex,
    QAbstractTableModel,
    QRunnable,
    QThreadPool,
    QRectF,
    QTimer,
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
    QPen,
    QPainterPath,
    QKeySequence,
    QShortcut,
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
    QListWidget,
    QMainWindow,
    QMenu,
    QPushButton,
    QProgressBar,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QTabWidget,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QSizePolicy,
)

from .config import load_defaults
from .extractor import SearchFilters, TrackMetadata
from .quality import DEFAULT_PROFILE_NAME, QUALITY_PROFILE_MAP
from .voice import VoiceCommand, VoiceCommandType, VoiceController
from .storage import StreamingLink
from .services import DownloadService, PlaybackService, SearchProgress, SearchService

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


@dataclass(frozen=True)
class WorkerError:
    context: Optional[str]
    message: str
    exc_type: str
    traceback: str

class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(object)
    progress = pyqtSignal(object)


class Worker(QRunnable):
    def __init__(self, fn, *args, progress=False, context: Optional[str] = None, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.progress = progress
        self.signals = WorkerSignals()
        self.context = context

    def run(self) -> None:
        try:
            kwargs = dict(self.kwargs)
            if self.progress:
                kwargs['progress_callback'] = self.signals.progress.emit
            result = self.fn(*self.args, **kwargs)
        except Exception as exc:
            self.signals.error.emit(
                WorkerError(
                    context=self.context,
                    message=str(exc),
                    exc_type=exc.__class__.__name__,
                    traceback=traceback.format_exc(),
                )
            )
        else:
            self.signals.finished.emit(result)


class TrackTableModel(QAbstractTableModel):
    HEADERS = [
        '',
        'Title',
        'Uploader',
        'Duration',
        'Views',
        'Likes',
        'Uploaded',
        'Type',
        'Format',
        'Bitrate',
        'Resolution',
    ]

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._tracks: List[TrackMetadata] = []
        self._icon_cache: dict[str, QIcon] = {}
        self._search_cache: dict[int, str] = {}
        self._thumbnail_cache: dict[str, QPixmap] = {}
        self._thumbnail_pending: set[str] = set()
        self._thumbnail_rows: dict[str, set[int]] = {}

    thumbnailRequested = pyqtSignal(str)

    THUMBNAIL_SIZE = 48

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
        if role == Qt.ItemDataRole.DecorationRole and column == 1:
            return self._thumbnail_for_track(track, index.row())
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
                    return self._format_views(track.like_count)
                case 6:
                    return track.upload_date or 'N/A'
                case 7:
                    return self._file_type_label(self._normalize_file_type(track.file_type))
                case 8:
                    return self._format_format(self._normalize_file_type(track.file_type))
                case 9:
                    return self._format_bitrate(track.audio_bitrate)
                case 10:
                    return self._format_resolution(track.resolution_height)
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
        self._search_cache.clear()
        self._thumbnail_cache.clear()
        self._thumbnail_pending.clear()
        self._thumbnail_rows.clear()
        self.endResetModel()

    def track_at(self, row: int) -> TrackMetadata:
        return self._tracks[row]

    def search_blob(self, row: int) -> str:
        track = self._tracks[row]
        key = id(track)
        cached = self._search_cache.get(key)
        if cached is not None:
            return cached
        blob = " ".join(
            filter(None, (track.title, track.uploader, track.description or "", " ".join(track.tags)))
        ).lower()
        self._search_cache[key] = blob
        return blob

    def set_thumbnail_data(self, url: str, payload: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(payload):
            self._thumbnail_pending.discard(url)
            return
        scaled = pixmap.scaled(
            self.THUMBNAIL_SIZE,
            self.THUMBNAIL_SIZE,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._thumbnail_cache[url] = scaled
        self._thumbnail_pending.discard(url)
        rows = self._thumbnail_rows.get(url, set())
        for row in rows:
            idx = self.index(row, 1)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])

    def _thumbnail_for_track(self, track: TrackMetadata, row: int) -> Optional[QIcon]:
        url = track.thumbnail
        if not url:
            return None
        if url in self._thumbnail_cache:
            return QIcon(self._thumbnail_cache[url])
        self._thumbnail_rows.setdefault(url, set()).add(row)
        if url not in self._thumbnail_pending:
            self._thumbnail_pending.add(url)
            self.thumbnailRequested.emit(url)
        return None

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

    @staticmethod
    def _format_format(normalized: str) -> str:
        return normalized.upper() if normalized != 'unknown' else 'N/A'

    @staticmethod
    def _format_bitrate(abr: Optional[float]) -> str:
        if not abr:
            return 'N/A'
        try:
            return f"{int(abr)} kbps"
        except (TypeError, ValueError):
            return 'N/A'

    @staticmethod
    def _format_resolution(height: Optional[int]) -> str:
        if not height:
            return 'N/A'
        return f"{height}p"


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
            haystack = model.search_blob(source_row)
            if self._filter_text not in haystack:
                return False
        return True


class LibraryView(QWidget):
    songActivated = pyqtSignal(TrackMetadata)
    playRequested = pyqtSignal(TrackMetadata)
    playNextRequested = pyqtSignal(TrackMetadata)
    queueRequested = pyqtSignal(TrackMetadata)
    downloadRequested = pyqtSignal(list)
    copyTitleRequested = pyqtSignal(TrackMetadata)
    copyUrlRequested = pyqtSignal(TrackMetadata)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.model = TrackTableModel(self)
        self.proxy = TrackFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Filter title, artist, tags...')
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
        if hasattr(self.table, "setUniformRowHeights"):
            self.table.setUniformRowHeights(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self._emit_selected_track)
        self.table.activated.connect(self._emit_selected_track)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.model.rowsInserted.connect(self._update_count)
        self.model.modelReset.connect(self._update_count)
        self.proxy.rowsInserted.connect(self._update_count)
        self.proxy.rowsRemoved.connect(self._update_count)
        self.proxy.modelReset.connect(self._update_count)
        self.proxy.layoutChanged.connect(self._update_count)
        self.proxy.dataChanged.connect(self._update_count)

    def _emit_selected_track(self, index: QModelIndex) -> None:
        source_index = self.proxy.mapToSource(index)
        track = self.model.track_at(source_index.row())
        self.songActivated.emit(track)

    def _update_count(self, *_):
        total = self.model.rowCount()
        visible = self.proxy.rowCount()
        if visible == total:
            self.count_label.setText(f"{total} tracks")
        else:
            self.count_label.setText(f"{total} tracks ({visible} shown)")

    def add_track(self, track: TrackMetadata) -> None:
        self.model.append_track(track)

    def clear(self) -> None:
        self.model.clear()

    def selected_tracks(self) -> List[TrackMetadata]:
        selected: List[TrackMetadata] = []
        for index in self.table.selectionModel().selectedRows():
            selected.append(self.model.track_at(self.proxy.mapToSource(index).row()))
        return selected

    def selected_track(self) -> Optional[TrackMetadata]:
        tracks = self.selected_tracks()
        return tracks[0] if tracks else None

    def is_video(self, track: TrackMetadata) -> bool:
        return self.model._normalize_file_type(track.file_type) == 'mp4'

    def _show_context_menu(self, position) -> None:
        track = self.selected_track()
        if not track:
            return
        menu = QMenu(self)
        play_action = menu.addAction("Play")
        play_next_action = menu.addAction("Play Next")
        queue_action = menu.addAction("Add to Queue")
        download_action = menu.addAction("Download")
        menu.addSeparator()
        copy_title_action = menu.addAction("Copy Title")
        copy_url_action = menu.addAction("Copy URL")
        action = menu.exec(self.table.viewport().mapToGlobal(position))
        if action == play_action:
            self.playRequested.emit(track)
        elif action == play_next_action:
            self.playNextRequested.emit(track)
        elif action == queue_action:
            self.queueRequested.emit(track)
        elif action == download_action:
            self.downloadRequested.emit([track])
        elif action == copy_title_action:
            self.copyTitleRequested.emit(track)
        elif action == copy_url_action:
            self.copyUrlRequested.emit(track)


class WaveformView(QWidget):
    seekRequested = pyqtSignal(float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._progress = 0.0
        self._peaks = [abs(sin(i / 3.5)) * 0.8 + 0.1 for i in range(160)]
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(28)
        self.setMaximumHeight(42)

    def set_progress(self, fraction: float) -> None:
        self._progress = max(0.0, min(1.0, fraction))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(SECONDARY_PANEL))
        width = max(1, self.width())
        height = self.height()
        if not self._peaks:
            painter.end()
            return

        spacing = 1.0
        total_spacing = spacing * (len(self._peaks) - 1)
        available_width = max(width - total_spacing, len(self._peaks))
        bar_width = available_width / len(self._peaks)
        mid_y = height / 2
        max_bar = max(1.0, mid_y - 2)

        for idx, peak in enumerate(self._peaks):
            x = idx * (bar_width + spacing)
            normalized = min(1.0, abs(peak))
            bar_height = normalized * max_bar
            rect_top = QRectF(x, mid_y - bar_height, bar_width, bar_height)
            rect_bottom = QRectF(x, mid_y, bar_width, bar_height)
            highlight = idx / len(self._peaks) < self._progress
            color = QColor(ACCENT_COLOR if highlight else DIVIDER)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect_top, 1.5, 1.5)
            painter.drawRoundedRect(rect_bottom, 1.5, 1.5)

        center_pen = QPen(QColor(DIVIDER))
        center_pen.setWidth(1)
        painter.setPen(center_pen)
        painter.drawLine(0, int(mid_y), width, int(mid_y))

        cursor = int(width * self._progress)
        pointer_pen = QPen(QColor(ACCENT_COLOR))
        pointer_pen.setWidth(2)
        painter.setPen(pointer_pen)
        painter.drawLine(cursor, 0, cursor, height)
        painter.end()

    def mousePressEvent(self, event) -> None:
        if self.width() <= 0:
            return
        fraction = max(0.0, min(1.0, event.position().x() / self.width()))
        self.seekRequested.emit(fraction)


class VisualizerWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._phase = 0.0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def refresh(self) -> None:
        self._phase += 0.08
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(SECONDARY_PANEL))
        width = self.width()
        height = self.height()
        if width <= 0 or height <= 0:
            painter.end()
            return

        mid_y = height / 2
        steps = max(32, width // 8)
        layers = 5
        for layer in range(layers):
            path = QPainterPath()
            hue = 200 + layer * 5
            color = QColor(ACCENT_COLOR).lighter(110 + layer * 10)
            pen = QPen(color)
            pen.setWidthF(1.2)
            painter.setPen(pen)
            amplitude = height * 0.12 + layer * 6
            for step in range(steps + 1):
                angle = (step / steps) * pi * 2
                offset = sin(angle * (1 + layer * 0.2) + self._phase) * amplitude
                x = (step / steps) * width
                y = mid_y + offset
                if step == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.drawPath(path)

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
        self._duration_ms = 0
        self._stream_details = ""

        self.title_label = QLabel("Select a track to play")
        self.title_label.setStyleSheet("font-weight: 600; font-size: 18px;")
        self.artist_label = QLabel("")
        self.info_label = QLabel("Waiting for playback")
        self.elapsed_label = QLabel("00:00")
        self.duration_label = QLabel("00:00")

        meta_layout = QVBoxLayout()
        meta_layout.addWidget(self.title_label)
        meta_layout.addWidget(self.artist_label)
        meta_layout.addWidget(self.info_label)

        self.play_button = QToolButton()
        self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_button.setToolTip("Play")
        self.play_button.clicked.connect(self._toggle_play)
        self.stop_button = QToolButton()
        self.stop_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
        self.stop_button.setToolTip("Stop")
        self.stop_button.clicked.connect(self._stop)
        control_style = (
            f"QToolButton {{ background-color: {ACCENT_COLOR}; color: white; "
            f"border: 1px solid {ACCENT_COLOR}; border-radius: 6px; padding: 4px 8px; }}"
            f"QToolButton:hover {{ background-color: #6BB6FF; border-color: #6BB6FF; }}"
        )
        self.play_button.setStyleSheet(control_style)
        self.stop_button.setStyleSheet(control_style)
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderMoved.connect(self.controller.set_position)
        self.seek_slider.sliderReleased.connect(
            lambda: self.controller.set_position(self.seek_slider.value())
        )
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.valueChanged.connect(self.controller.set_volume)

        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.stop_button)
        controls.addStretch()
        controls.addWidget(QLabel("Vol"))
        controls.addWidget(self.volume_slider)

        seek_layout = QHBoxLayout()
        seek_layout.setContentsMargins(0, 4, 0, 0)
        seek_layout.addWidget(self.elapsed_label)
        seek_layout.addWidget(self.seek_slider)
        seek_layout.addWidget(self.duration_label)

        self.waveform = WaveformView()
        self.waveform.seekRequested.connect(self._seek_to_fraction)
        self.visualizer = VisualizerWidget()
        self.equalizer = EqualizerPanel()
        self.queue_list = QListWidget()
        self.queue_list.setMinimumWidth(180)
        self.queue_list.setToolTip("Upcoming tracks")
        self._visualizer_timer = QTimer(self)
        self._visualizer_timer.setInterval(33)
        self._visualizer_timer.timeout.connect(self.visualizer.refresh)

        self.video_stack = QStackedWidget()
        self.video_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_stack.setMinimumHeight(220)
        self.video_stack.addWidget(self.controller.video_widget)
        self.video_stack.addWidget(self.visualizer)
        self.video_stack.setCurrentWidget(self.visualizer)

        video_frame = QFrame()
        video_frame.setFrameShape(QFrame.Shape.StyledPanel)
        video_frame.setFrameShadow(QFrame.Shadow.Raised)
        video_layout = QHBoxLayout()
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.addWidget(self.video_stack, 3)
        right_panel = QVBoxLayout()
        right_panel.addWidget(QLabel("Queue"))
        right_panel.addWidget(self.queue_list, 1)
        right_panel.addWidget(QLabel("Equalizer"))
        right_panel.addWidget(self.equalizer, 2)
        video_layout.addLayout(right_panel, 1)
        video_frame.setLayout(video_layout)

        layout = QVBoxLayout()
        layout.addLayout(meta_layout)
        layout.addLayout(controls)
        layout.addLayout(seek_layout)
        layout.addWidget(self.waveform)
        layout.addWidget(video_frame)
        self.setLayout(layout)

        self.controller.trackChanged.connect(self._on_track_changed)
        self.controller.positionChanged.connect(self._on_position_changed)
        self.controller.durationChanged.connect(self._on_duration_changed)
        self.controller.stateChanged.connect(self._on_state_changed)

    def set_video_mode(self, enabled: bool) -> None:
        target = self.controller.video_widget if enabled else self.visualizer
        self.video_stack.setCurrentWidget(target)

    def _toggle_play(self) -> None:
        self.sounds.play_click()
        self.controller.toggle_playback()

    def _stop(self) -> None:
        self.sounds.play_click()
        self.controller.stop()

    def _on_track_changed(self, track: TrackMetadata) -> None:
        self.title_label.setText(track.title)
        self.artist_label.setText(track.uploader)
        self.info_label.setText("Resolving stream...")
        self._stream_details = ""
        self.waveform.set_progress(0.0)
        self.elapsed_label.setText("00:00")
        self.duration_label.setText("00:00")
        self.set_video_mode(self.controller.is_video())
        self.seek_slider.setEnabled(False)

    def _on_position_changed(self, position: int) -> None:
        if self._duration_ms > 0:
            self.waveform.set_progress(min(position / max(1, self._duration_ms), 1.0))
        self.seek_slider.blockSignals(True)
        self.seek_slider.setValue(position)
        self.seek_slider.blockSignals(False)
        self.elapsed_label.setText(self._format_time(position))
        self.duration_label.setText(self._format_time(self._duration_ms))

    def _on_duration_changed(self, duration: int) -> None:
        self._duration_ms = duration
        self.seek_slider.setRange(0, duration)
        self.seek_slider.setEnabled(duration > 0)
        self.duration_label.setText(self._format_time(duration))

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
            self.play_button.setToolTip("Pause")
            suffix = f" ({self._stream_details})" if self._stream_details else ""
            self.info_label.setText(f"Playing{suffix}")
            if not self._visualizer_timer.isActive():
                self._visualizer_timer.start()
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            self.play_button.setToolTip("Play")
            self.info_label.setText("Paused")
            if self._visualizer_timer.isActive():
                self._visualizer_timer.stop()
        else:
            self.play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            self.play_button.setToolTip("Play")
            self.info_label.setText("Stopped")
            if self._visualizer_timer.isActive():
                self._visualizer_timer.stop()

    def _format_time(self, milliseconds: int) -> str:
        seconds = max(0, int(milliseconds // 1000))
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def set_stream_details(self, details: str) -> None:
        self._stream_details = details

    def set_queue(self, tracks: List[TrackMetadata]) -> None:
        self.queue_list.clear()
        for track in tracks:
            title = track.title or track.video_id
            self.queue_list.addItem(title)

    def _seek_to_fraction(self, fraction: float) -> None:
        if self._duration_ms <= 0:
            return
        position = int(self._duration_ms * fraction)
        self.controller.set_position(position)



SEARCH_CHUNK_SIZE = 20
MAX_FALLBACK_BYTES = 200 * 1024 * 1024
MAX_TEMP_FILES = 6

class UTubeGui(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("UTube Music Harvester")
        self.thread_pool = QThreadPool()
        self.defaults = load_defaults()
        self._voice_enabled = self._resolve_voice_enabled()
        try:
            self.voice_controller = VoiceController(
                enabled=self._voice_enabled,
                engine=self.defaults.voice_engine,
                language=self.defaults.voice_language,
                model_path=self.defaults.voice_model_path,
            )
            self._voice_engine_warning: Optional[str] = None
        except RuntimeError as exc:
            self.voice_controller = VoiceController(
                enabled=False,
                engine=self.defaults.voice_engine,
                language=self.defaults.voice_language,
                model_path=self.defaults.voice_model_path,
            )
            self._voice_engine_warning = str(exc)
        self._voice_listening = False
        self._queue: List[TrackMetadata] = []
        self._history: List[TrackMetadata] = []
        self._favorites: set[str] = set()
        self._now_playing_duration_ms = 0
        self.search_service = SearchService()
        self.playback_service = PlaybackService()
        self.download_service = DownloadService()
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
        self.library_view.playRequested.connect(self._handle_song_activation)
        self.library_view.playNextRequested.connect(lambda track: self._enqueue_track(track, next_up=True))
        self.library_view.queueRequested.connect(self._enqueue_track)
        self.library_view.downloadRequested.connect(self._download_tracks_from_menu)
        self.library_view.copyTitleRequested.connect(self._copy_track_title)
        self.library_view.copyUrlRequested.connect(self._copy_track_url)
        self.player_controller.trackChanged.connect(self._on_track_changed)
        self.player_controller.stateChanged.connect(self._on_player_state_updated)
        self.player_controller.errorOccurred.connect(self._handle_player_error)
        self.player_controller.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player_controller.positionChanged.connect(self._update_now_playing_progress)
        self.player_controller.durationChanged.connect(self._update_now_playing_duration)
        self.library_view.model.thumbnailRequested.connect(self._on_thumbnail_requested)
        self._play_attempts: Dict[str, int] = {}
        self._temp_media_files: set[str] = set()
        self._loop_enabled = False
        self._last_streams: Dict[str, str] = {}
        self._build_ui()
        self.tracks: List[TrackMetadata] = []
        self._set_search_validation_state(True)
        self._wire_shortcuts()

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
        QApplication.instance().aboutToQuit.connect(self._cleanup_temp_files)

    @staticmethod
    def _has_search_terms(genre: str, artist: str, keywords: str) -> bool:
        return bool(genre or artist or keywords)

    def _spawn_worker(
        self,
        fn,
        *args,
        progress: bool = False,
        context: Optional[str] = None,
        on_finished=None,
        on_error=None,
        on_progress=None,
        **kwargs,
    ) -> Worker:
        worker = Worker(fn, *args, progress=progress, context=context, **kwargs)
        if on_finished:
            worker.signals.finished.connect(on_finished)
        if on_error:
            worker.signals.error.connect(on_error)
        else:
            worker.signals.error.connect(self._on_worker_error)
        if on_progress:
            worker.signals.progress.connect(on_progress)
        self.thread_pool.start(worker)
        return worker

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
        top_grid.addWidget(QLabel("Preset"), 0, 0)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(
            [
                "Select preset",
                "Ambient",
                "Chill",
                "Focus",
                "Lo-fi",
                "Trance",
                "Workout",
            ]
        )
        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        top_grid.addWidget(self.preset_combo, 0, 1, 1, 3)
        top_grid.addWidget(QLabel("Genre"), 1, 0)
        self.genre_input = QLineEdit()
        self.genre_input.setPlaceholderText("e.g., trance")
        top_grid.addWidget(self.genre_input, 1, 1)
        top_grid.addWidget(QLabel("Artist"), 1, 2)
        self.artist_input = QLineEdit()
        self.artist_input.setPlaceholderText("optional")
        top_grid.addWidget(self.artist_input, 1, 3)
        top_grid.addWidget(QLabel("Order"), 2, 0)
        self.order_combo = QComboBox()
        self.order_combo.addItems(["relevance", "date", "longest", "shortest"])
        top_grid.addWidget(self.order_combo, 2, 1)
        top_grid.addWidget(QLabel("Stream format"), 2, 2)
        self.stream_format_input = QLineEdit(self.defaults.stream_format)
        top_grid.addWidget(self.stream_format_input, 2, 3)
        top_grid.addWidget(QLabel("Video quality"), 3, 0)
        self.video_quality_combo = QComboBox()
        self.video_quality_combo.addItems(["Any", "high", "medium", "low"])
        default_quality = self.defaults.video_quality if self.defaults.video_quality in ["high", "medium", "low"] else "Any"
        self.video_quality_combo.setCurrentText(default_quality)
        top_grid.addWidget(self.video_quality_combo, 3, 1)
        top_grid.addWidget(QLabel("JS runtime"), 3, 2)
        self.js_runtime_input = QLineEdit(self.defaults.js_runtime or "")
        self.js_runtime_input.setPlaceholderText("node, deno, etc.")
        top_grid.addWidget(self.js_runtime_input, 3, 3)
        top_grid.addWidget(QLabel("Remote components"), 4, 0)
        self.remote_components_input = QLineEdit(
            ", ".join(self.defaults.remote_components) if self.defaults.remote_components else ""
        )
        self.remote_components_input.setPlaceholderText("ejs:github")
        top_grid.addWidget(self.remote_components_input, 4, 1, 1, 3)
        top_grid.addWidget(QLabel("Quality profile"), 5, 0)
        self.quality_profile_combo = QComboBox()
        for profile in QUALITY_PROFILE_MAP:
            self.quality_profile_combo.addItem(profile.replace("_", " ").title(), profile)
        default_profile = self.defaults.quality_profile if self.defaults.quality_profile in QUALITY_PROFILE_MAP else DEFAULT_PROFILE_NAME
        idx = self.quality_profile_combo.findData(default_profile)
        if idx >= 0:
            self.quality_profile_combo.setCurrentIndex(idx)
        top_grid.addWidget(self.quality_profile_combo, 5, 1)
        voice_layout = QHBoxLayout()
        self.voice_button = QPushButton("🎙️ Voice")
        self.voice_button.setCheckable(True)
        self.voice_button.clicked.connect(self._toggle_voice_listening)
        voice_layout.addWidget(self.voice_button)
        voice_layout.addWidget(QLabel("Model"))
        self.voice_model_combo = QComboBox()
        voice_layout.addWidget(self.voice_model_combo)
        self.voice_status_label = QLabel()
        voice_layout.addWidget(self.voice_status_label)
        self._refresh_voice_status_label()
        voice_layout.addStretch()
        top_grid.addLayout(voice_layout, 6, 0, 1, 4)
        self._populate_voice_model_combo()
        self.voice_model_combo.currentIndexChanged.connect(lambda *_: self._on_voice_model_selected())
        self._reset_voice_controller(self._current_voice_model_path())

        layout.addLayout(top_grid)

        filter_grid = QGridLayout()
        filter_grid.setHorizontalSpacing(12)
        filter_grid.setVerticalSpacing(8)
        filter_grid.addWidget(QLabel("Max entries"), 0, 0, 1, 1)
        self.max_entries_slider = QSlider(Qt.Orientation.Horizontal)
        self.max_entries_slider.setRange(1, 5000)
        self.max_entries_slider.setValue(50)
        self.max_entries_slider.setTickInterval(100)
        self.max_entries_slider.setToolTip(str(self.max_entries_slider.value()))
        filter_grid.addWidget(self.max_entries_slider, 0, 1, 1, 3)
        self.max_entries_slider.valueChanged.connect(self._on_max_entries_slider_changed)
        filter_grid.addWidget(QLabel("Format filter"), 1, 2, 1, 2)
        self.format_tab = QTabWidget()
        for label in ("Any", "MP3", "MP4"):
            page = QWidget()
            self.format_tab.addTab(page, label)
        filter_grid.addWidget(self.format_tab, 2, 0, 1, 4)

        # slider drives the max entries value which is read directly in _start_search
        filter_grid.addWidget(QLabel("Min duration"), 3, 0)
        self.min_duration_spin = QSpinBox()
        self.min_duration_spin.setSuffix(" sec")
        self.min_duration_spin.setRange(0, 3600)
        self.min_duration_spin.setSpecialValueText("Any")
        filter_grid.addWidget(self.min_duration_spin, 3, 1)
        filter_grid.addWidget(QLabel("Max duration"), 3, 2)
        self.max_duration_spin = QSpinBox()
        self.max_duration_spin.setSuffix(" sec")
        self.max_duration_spin.setRange(0, 3600)
        self.max_duration_spin.setSpecialValueText("Any")
        filter_grid.addWidget(self.max_duration_spin, 3, 3)
        filter_grid.addWidget(QLabel("Min views"), 4, 0)
        self.min_views_spin = QSpinBox()
        self.min_views_spin.setRange(0, 10_000_000)
        self.min_views_spin.setSpecialValueText("Any")
        filter_grid.addWidget(self.min_views_spin, 4, 1)
        filter_grid.addWidget(QLabel("Max views"), 4, 2)
        self.max_views_spin = QSpinBox()
        self.max_views_spin.setRange(0, 10_000_000)
        self.max_views_spin.setSpecialValueText("Any")
        filter_grid.addWidget(self.max_views_spin, 4, 3)
        filter_grid.addWidget(QLabel("Keywords"), 5, 0)
        self.keywords_input = QLineEdit()
        self.keywords_input.setPlaceholderText("optional terms")
        filter_grid.addWidget(self.keywords_input, 5, 1, 1, 3)
        self.sfw_checkbox = QCheckBox("Safe-for-work")
        filter_grid.addWidget(self.sfw_checkbox, 6, 0)
        layout.addLayout(filter_grid)

        self.search_button = QPushButton("Search")
        self.search_button.setProperty("primary", True)
        self.search_button.clicked.connect(self._start_search)
        actions = QHBoxLayout()
        actions.addStretch()
        self.clear_filters_button = QPushButton("Clear Filters")
        self.clear_filters_button.clicked.connect(self._clear_filters)
        actions.addWidget(self.clear_filters_button)
        actions.addWidget(self.search_button)
        layout.addLayout(actions)

        self.last_search_summary_label.setStyleSheet("color: #8F9AA5;")
        layout.addWidget(self.last_search_summary_label)
        self.search_progress = QProgressBar()
        self.search_progress.setRange(0, 0)
        self.search_progress.setTextVisible(False)
        self.search_progress.setVisible(False)
        self.search_progress.setFixedHeight(6)
        layout.addWidget(self.search_progress)

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

        self.genre_input.textChanged.connect(self._maybe_clear_search_validation)
        self.artist_input.textChanged.connect(self._maybe_clear_search_validation)
        self.keywords_input.textChanged.connect(self._maybe_clear_search_validation)

        card.setLayout(layout)
        return card

    def _voice_status_text(self) -> str:
        if self._voice_listening:
            return "Listening..."
        if self._voice_engine_warning:
            return f"Voice unavailable ({self._voice_engine_warning})"
        return "Voice ready" if self.voice_controller.enabled else "Voice disabled"

    def _refresh_voice_status_label(self) -> None:
        if not hasattr(self, "voice_status_label"):
            return
        self.voice_status_label.setText(self._voice_status_text())
        self.voice_status_label.setToolTip(self._voice_engine_warning or "")

    def _discover_voice_models(self) -> Dict[str, Path]:
        models_dir = self.defaults.voice_models_dir
        if not models_dir.is_absolute():
            models_dir = (Path.cwd() / models_dir).resolve()
        entries: dict[str, Path] = {}
        if models_dir.exists():
            for child in sorted(models_dir.iterdir()):
                if child.is_dir():
                    entries[child.name] = child
        return entries

    def _populate_voice_model_combo(self) -> None:
        self.voice_model_combo.clear()
        models = self._discover_voice_models()
        override_path = self.defaults.voice_model_path
        default_name = self.defaults.voice_model_name
        if default_name not in models and override_path.exists():
            models[override_path.name] = override_path
        elif not models and override_path.exists():
            models[override_path.name] = override_path
        self._voice_model_map = models
        entries = list(models.items())
        for name, path in entries:
            self.voice_model_combo.addItem(name, str(path))
        if entries:
            default_index = next((index for index, (name, _) in enumerate(entries) if name == default_name), 0)
            self.voice_model_combo.setCurrentIndex(default_index)

    def _current_voice_model_path(self) -> Path:
        data = self.voice_model_combo.currentData()
        if data:
            return Path(str(data))
        return self.defaults.voice_model_path

    def _build_voice_controller(self, model_path: str) -> VoiceController:
        try:
            controller = VoiceController(
                enabled=self._voice_enabled,
                engine=self.defaults.voice_engine,
                language=self.defaults.voice_language,
                model_path=model_path,
            )
            self._voice_engine_warning = None
        except RuntimeError as exc:
            controller = VoiceController(
                enabled=False,
                engine=self.defaults.voice_engine,
                language=self.defaults.voice_language,
                model_path=model_path,
            )
            self._voice_engine_warning = str(exc)
        return controller

    def _resolve_voice_enabled(self) -> bool:
        env_value = os.getenv("UTUBE_VOICE_ENABLED")
        if env_value is not None:
            return self.defaults.voice_enabled
        try:
            models = self._discover_voice_models()
        except Exception:
            models = {}
        return bool(models)

    def _reset_voice_controller(self, model_path: Path) -> None:
        if self._voice_listening:
            self._set_voice_listening(False)
        controller = self._build_voice_controller(str(model_path))
        self.voice_controller = controller
        self.voice_button.setEnabled(controller.enabled)
        self._refresh_voice_status_label()

    def _on_voice_model_selected(self) -> None:
        self._reset_voice_controller(self._current_voice_model_path())

    def _toggle_voice_listening(self) -> None:
        if not self.voice_controller.enabled:
            self._set_status("Voice control is disabled. Check UTUBE_VOICE_ENABLED.")
            return
        if self._voice_listening:
            self._set_voice_listening(False)
            return
        self._start_voice_listening()

    def _start_voice_listening(self) -> None:
        self._set_voice_listening(True)
        self._spawn_worker(
            self.voice_controller.listen_once,
            on_finished=lambda payload: (self._on_voice_result(payload), self._set_voice_listening(False)),
            on_error=lambda message: (self._on_voice_error(message), self._set_voice_listening(False)),
            context="voice_listen",
        )

    def _set_voice_listening(self, listening: bool) -> None:
        self._voice_listening = listening
        self.voice_button.setChecked(listening)
        self._refresh_voice_status_label()

    def _on_voice_result(self, payload) -> None:
        command, phrase = payload
        self._set_status(f"Heard: '{phrase}'")
        self._dispatch_voice_command(command)

    def _on_voice_error(self, error: Union[WorkerError, str]) -> None:
        if isinstance(error, WorkerError):
            message = error.message
        else:
            message = error
        self._set_status(f"Voice error: {message}")

    def _dispatch_voice_command(self, command: VoiceCommand) -> None:
        if command.command_type == VoiceCommandType.SEARCH and command.query:
            self.genre_input.setText(command.query)
            self._start_search()
        elif command.command_type == VoiceCommandType.PLAY_ALL:
            self._play_all_voice_tracks()
        elif command.command_type == VoiceCommandType.PLAY_SPECIFIC:
            if command.index is not None:
                self._play_voice_track_by_index(command.index)
            elif command.query:
                self._play_voice_track_by_title(command.query)
        elif command.command_type == VoiceCommandType.CONTROL and command.action:
            self._handle_voice_control(command.action)

    def _play_all_voice_tracks(self) -> None:
        if not self.tracks:
            self._set_status("No tracks are available to play.")
            return
        self._queue = list(self.tracks[1:])
        self._update_queue_view()
        self._handle_song_activation(self.tracks[0])

    def _play_voice_track_by_index(self, index: int) -> None:
        if index < 0 or index >= len(self.tracks):
            self._set_status(f"Track number {index + 1} is out of range.")
            return
        self._handle_song_activation(self.tracks[index])

    def _play_voice_track_by_title(self, title: str) -> None:
        lowered = title.lower()
        for track in self.tracks:
            if lowered in (track.title or "").lower():
                self._handle_song_activation(track)
                return
        self._set_status(f"Could not find '{title}' in the current results.")

    def _handle_voice_control(self, action: str) -> None:
        player = self.player_controller.player
        if action == "pause":
            player.pause()
        elif action == "play":
            player.play()
        elif action == "stop":
            player.stop()
        else:
            self._set_status(f"Voice control '{action}' is not supported yet.")

    def _build_now_playing_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        layout.addWidget(QLabel("Now playing:"))
        layout.addWidget(self.now_playing_label)
        self.now_playing_time_label = QLabel("00:00 / 00:00")
        self.now_playing_time_label.setStyleSheet("color: #8F9AA5;")
        layout.addWidget(self.now_playing_time_label)
        self.now_playing_progress = QProgressBar()
        self.now_playing_progress.setRange(0, 1000)
        self.now_playing_progress.setTextVisible(False)
        self.now_playing_progress.setFixedWidth(160)
        layout.addWidget(self.now_playing_progress)
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
        self.favorite_button = QPushButton("♡")
        self.favorite_button.setCheckable(True)
        self.favorite_button.clicked.connect(self._toggle_favorite)
        self.history_button = QPushButton("History")
        self.history_button.clicked.connect(self._show_history_menu)
        layout.addWidget(play_btn)
        layout.addWidget(stop_btn)
        layout.addWidget(open_btn)
        layout.addWidget(self.loop_button)
        layout.addWidget(self.favorite_button)
        layout.addWidget(self.history_button)
        layout.addWidget(self.status_label)
        bar.setLayout(layout)
        return bar

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    @staticmethod
    def _format_time(milliseconds: int) -> str:
        seconds = max(0, int(milliseconds // 1000))
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def _check_js_runtime(self) -> bool:
        runtime = self._current_js_runtime()
        if not runtime:
            return True
        runtime_path = Path(runtime)
        if runtime_path.exists():
            return True
        if shutil.which(runtime):
            return True
        self._set_status(f"JS runtime '{runtime}' not found. Update JS runtime in filters.")
        return False

    def _check_network(self) -> bool:
        try:
            with socket.create_connection(("www.youtube.com", 443), timeout=1.5):
                return True
        except OSError:
            return False

    def _preflight_playback(self, prefer_video: bool, preferred_format: Optional[str]) -> bool:
        if not self._check_js_runtime():
            return False
        if not self._check_network():
            self._set_status("Network appears offline; playback may fail.")
        if prefer_video and sys.platform == "win32" and preferred_format not in (None, "mp4"):
            self._set_status("Windows playback is most reliable with MP4 streams.")
        return True

    def _is_default_stream_format(self, stream_format: str) -> bool:
        return not stream_format.strip() or stream_format.strip() == self.defaults.stream_format

    def _build_stream_selector(
        self,
        *,
        prefer_video: bool,
        stream_format: str,
        preferred_format: Optional[str],
    ) -> str:
        if stream_format and not self._is_default_stream_format(stream_format):
            return stream_format
        if prefer_video:
            if preferred_format == "mp4" or (preferred_format is None and sys.platform == "win32"):
                return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            return "bestvideo+bestaudio/best"
        if preferred_format == "mp3":
            return "bestaudio[ext=mp3]/bestaudio"
        return "bestaudio[abr>=160][ext=webm]/bestaudio[abr>=160]/bestaudio/best"

    def _format_stream_details(self, link: StreamingLink) -> str:
        parts: List[str] = []
        if link.ext:
            parts.append(link.ext.upper())
        if link.abr:
            parts.append(f"{int(link.abr)} kbps")
        if link.height:
            parts.append(f"{link.height}p")
        codecs: List[str] = []
        if link.vcodec and link.vcodec != "none":
            codecs.append(link.vcodec)
        if link.acodec and link.acodec != "none":
            codecs.append(link.acodec)
        if codecs:
            parts.append("/".join(codecs))
        if link.format_note:
            parts.append(link.format_note)
        if not parts:
            parts.append(f"format {link.format_id}")
        return ", ".join(parts)

    def _on_thumbnail_requested(self, url: str) -> None:
        self._spawn_worker(
            self._download_thumbnail_bytes,
            url,
            context="thumbnail_fetch",
            on_finished=lambda payload, u=url: self.library_view.model.set_thumbnail_data(u, payload),
        )

    def _download_thumbnail_bytes(self, url: str) -> bytes:
        self._validate_stream_url(url)
        headers = {"User-Agent": "Mozilla/5.0"}
        request = urllib.request.Request(url, headers=headers)
        max_bytes = 2 * 1024 * 1024
        with urllib.request.urlopen(request, timeout=10) as response:
            content_length = response.getheader("Content-Length")
            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        raise RuntimeError("Thumbnail is too large to download.")
                except ValueError:
                    pass
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise RuntimeError("Thumbnail exceeded the size limit.")
            return data

    def _validate_stream_url(self, url: str) -> None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise RuntimeError("Unsupported stream URL scheme.")
        host = parsed.hostname
        if not host:
            raise RuntimeError("Stream URL is missing a hostname.")
        if host.lower() == "localhost":
            raise RuntimeError("Stream URL host is not allowed.")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise RuntimeError("Unable to resolve stream host.") from exc
        for _, _, _, _, sockaddr in infos:
            ip = sockaddr[0]
            try:
                addr = ip_address(ip)
            except ValueError:
                continue
            if any(
                [
                    addr.is_loopback,
                    addr.is_private,
                    addr.is_link_local,
                    addr.is_multicast,
                    addr.is_reserved,
                ]
            ):
                raise RuntimeError("Stream URL resolves to a disallowed network address.")

    def _toggle_now_playback(self) -> None:
        self.sound_manager.play_click()
        self.player_controller.toggle_playback()

    def _toggle_loop_mode(self, checked: bool) -> None:
        self._loop_enabled = checked
        self.loop_button.setText("Loop On" if checked else "Loop Off")

    def _toggle_favorite(self) -> None:
        track = self.player_controller.current_track()
        if not track:
            return
        if track.video_id in self._favorites:
            self._favorites.discard(track.video_id)
            self.favorite_button.setText("♡")
        else:
            self._favorites.add(track.video_id)
            self.favorite_button.setText("♥")

    def _show_history_menu(self) -> None:
        if not self._history:
            self._set_status("History is empty.")
            return
        menu = QMenu(self)
        for track in list(reversed(self._history))[:10]:
            title = track.title or track.video_id
            action = menu.addAction(title)
            action.triggered.connect(lambda _, t=track: self._handle_song_activation(t))
        menu.exec(self.history_button.mapToGlobal(self.history_button.rect().bottomLeft()))

    def _enqueue_track(self, track: TrackMetadata, next_up: bool = False) -> None:
        if next_up:
            self._queue.insert(0, track)
        else:
            self._queue.append(track)
        self._update_queue_view()
        self._set_status(f"Queued: {track.title or track.video_id}")

    def _update_queue_view(self) -> None:
        self.player_view.set_queue(self._queue)

    def _play_selected_from_library(self) -> None:
        track = self.library_view.selected_track()
        if not track:
            self._set_status("Select a track to play.")
            return
        self._handle_song_activation(track)

    def _seek_relative(self, delta_ms: int) -> None:
        current = int(self.player_controller.player.position())
        target = max(0, current + delta_ms)
        self.player_controller.set_position(target)

    def _wire_shortcuts(self) -> None:
        QShortcut(QKeySequence("Space"), self, activated=self.player_controller.toggle_playback)
        QShortcut(QKeySequence("J"), self, activated=lambda: self._seek_relative(-10_000))
        QShortcut(QKeySequence("L"), self, activated=lambda: self._seek_relative(10_000))
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.library_view.search_input.setFocus)
        QShortcut(QKeySequence("Return"), self, activated=self._play_selected_from_library)
        QShortcut(QKeySequence("Enter"), self, activated=self._play_selected_from_library)

    def _download_tracks_from_menu(self, tracks: List[TrackMetadata]) -> None:
        if not tracks:
            return
        download_dir = Path(self.download_dir_label.text())
        self._set_status("Downloading tracks...")
        self._spawn_worker(
            self._download_tracks,
            tracks,
            download_dir,
            self._current_js_runtime(),
            self._current_remote_components(),
            self._current_quality_profile(),
            on_finished=lambda files: self._set_status(f"Downloaded {len(files)} files."),
            context="download_tracks",
        )

    def _copy_track_title(self, track: TrackMetadata) -> None:
        QApplication.clipboard().setText(track.title or track.video_id)
        self._set_status("Title copied to clipboard.")

    def _copy_track_url(self, track: TrackMetadata) -> None:
        if not track.webpage_url:
            self._set_status("No URL available for this track.")
            return
        QApplication.clipboard().setText(track.webpage_url)
        self._set_status("URL copied to clipboard.")

    def _update_now_playing_progress(self, position: int) -> None:
        if self._now_playing_duration_ms > 0:
            percent = int((position / max(1, self._now_playing_duration_ms)) * 1000)
            self.now_playing_progress.setValue(max(0, min(1000, percent)))
        else:
            self.now_playing_progress.setValue(0)
        elapsed = self._format_time(position)
        total = self._format_time(self._now_playing_duration_ms)
        self.now_playing_time_label.setText(f"{elapsed} / {total}")

    def _update_now_playing_duration(self, duration: int) -> None:
        self._now_playing_duration_ms = duration

    def _on_track_changed(self, track: TrackMetadata) -> None:
        self._update_now_playing_label(track)
        self._history.append(track)
        if len(self._history) > 50:
            self._history = self._history[-50:]
        if track.video_id in self._favorites:
            self.favorite_button.setChecked(True)
            self.favorite_button.setText("♥")
        else:
            self.favorite_button.setChecked(False)
            self.favorite_button.setText("♡")
    def _handle_song_activation(self, track: TrackMetadata) -> None:
        prefer_video = self.library_view.is_video(track)
        preferred_format = self._preferred_format()
        if not self._preflight_playback(prefer_video, preferred_format):
            return
        self._set_status(f"Resolving {'video' if prefer_video else 'audio'} stream...")
        self._spawn_worker(
            self._resolve_stream_url,
            track,
            self.stream_format_input.text().strip(),
            prefer_video,
            self._current_video_quality(),
            preferred_format,
            context="resolve_stream",
            on_finished=lambda link, t=track: self._route_media_playback(t, link),
        )
        self.stack.setCurrentWidget(self.player_view)

    def _route_media_playback(self, track: TrackMetadata, link: StreamingLink) -> None:
        self._cleanup_temp_files()
        self.player_controller.play_track(track, link.stream_url, self._should_prefer_video(track))
        self._update_now_playing_label(track)
        self._play_attempts.pop(track.video_id, None)
        self._last_streams[track.video_id] = link.stream_url
        self.player_view.set_stream_details(self._format_stream_details(link))

    def _handle_player_error(self, message: str) -> None:
        track = self.player_controller.current_track()
        if not track:
            return
        self._set_status(f"Playback error: {message}")
        attempts = self._play_attempts.get(track.video_id, 0) + 1
        self._play_attempts[track.video_id] = attempts
        if attempts == 1:
            self._set_status("Retrying stream after transient error...")
            self._retry_stream(track)
        elif attempts == 2:
            self._set_status("Caching stream locally because live playback keeps failing.")
            self._start_local_fallback(track)
        else:
            self._set_status("Playback failed multiple times; track has been paused.")

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        if self._loop_enabled:
            track = self.player_controller.current_track()
            if not track:
                return
            last_stream = self._last_streams.get(track.video_id)
            if not last_stream:
                return
            self._set_status("Looping current track...")
            self.player_controller.play_track(track, last_stream, self.library_view.is_video(track))
            return
        if self._queue:
            next_track = self._queue.pop(0)
            self._update_queue_view()
            self._set_status(f"Playing next track: {next_track.title}")
            self._handle_song_activation(next_track)

    def _retry_stream(self, track: TrackMetadata) -> None:
        prefer_video = self._should_prefer_video(track)
        self._spawn_worker(
            self._resolve_stream_url,
            track,
            self.stream_format_input.text().strip(),
            prefer_video,
            self._current_video_quality(),
            self._preferred_format(),
            context="resolve_stream",
            on_finished=lambda link, t=track: self._route_media_playback(t, link),
        )

    def _start_local_fallback(self, track: TrackMetadata) -> None:
        prefer_video = self._should_prefer_video(track)
        self._spawn_worker(
            self._download_stream_to_temp,
            track,
            prefer_video,
            self._current_video_quality(),
            self.stream_format_input.text().strip(),
            self._preferred_format(),
            context="download_fallback",
            on_finished=lambda path, t=track, pv=prefer_video: self._play_local_media(t, path, pv),
        )

    def _download_stream_to_temp(
        self,
        track: TrackMetadata,
        prefer_video: bool,
        video_quality: str,
        stream_format: str,
        preferred_format: Optional[str],
    ) -> str:
        effective_preferred = preferred_format
        if prefer_video and effective_preferred is None and sys.platform == "win32":
            effective_preferred = "mp4"
        selector = self._build_stream_selector(
            prefer_video=prefer_video,
            stream_format=stream_format or self.defaults.stream_format,
            preferred_format=effective_preferred,
        )
        link = self.playback_service.resolve_stream(
            track=track,
            selector=selector,
            js_runtime=self._current_js_runtime(),
            remote_components=self._current_remote_components(),
            prefer_video=prefer_video,
            video_quality=video_quality,
            preferred_format=effective_preferred,
            quality_profile=self._current_quality_profile(),
        )
        stream_url = link.stream_url
        self._validate_stream_url(stream_url)

        suffix = ".mp4" if prefer_video else ".m4a"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_file_path = temp_file.name
        temp_file.close()
        headers = {"User-Agent": "Mozilla/5.0"}
        request = urllib.request.Request(stream_url, headers=headers)
        with urllib.request.urlopen(request, timeout=60) as response, open(temp_file_path, "wb") as out:
            content_length = response.getheader("Content-Length")
            if content_length:
                try:
                    if int(content_length) > MAX_FALLBACK_BYTES:
                        raise RuntimeError("Stream is too large for fallback caching.")
                except ValueError:
                    pass
            bytes_written = 0
            while True:
                chunk = response.read(1024 * 64)
                if not chunk:
                    break
                out.write(chunk)
                bytes_written += len(chunk)
                if bytes_written > MAX_FALLBACK_BYTES:
                    raise RuntimeError("Stream exceeded the fallback cache size limit.")
        return temp_file_path

    def _play_local_media(self, track: TrackMetadata, path: str, prefer_video: bool) -> None:
        self._cleanup_temp_files(preserve=path)
        self._temp_media_files.add(path)
        self._cap_temp_cache()
        self._last_streams[track.video_id] = path
        self._play_attempts.pop(track.video_id, None)
        self.player_controller.play_track(track, path, prefer_video)
        self._update_now_playing_label(track)
        self.player_view.set_stream_details("cached")
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

    def _cap_temp_cache(self) -> None:
        if len(self._temp_media_files) <= MAX_TEMP_FILES:
            return
        overflow = len(self._temp_media_files) - MAX_TEMP_FILES
        for tmp in list(self._temp_media_files):
            if overflow <= 0:
                break
            try:
                os.remove(tmp)
            except OSError:
                pass
            self._temp_media_files.discard(tmp)
            overflow -= 1

    def _resolve_stream_url(
        self, track: TrackMetadata, stream_format: str, prefer_video: bool, video_quality: str,
        preferred_format: Optional[str]
    ) -> StreamingLink:
        effective_preferred = preferred_format
        if prefer_video and effective_preferred is None and sys.platform == "win32":
            effective_preferred = "mp4"
        selector = self._build_stream_selector(
            prefer_video=prefer_video,
            stream_format=stream_format or self.defaults.stream_format,
            preferred_format=effective_preferred,
        )
        return self.playback_service.resolve_stream(
            track=track,
            selector=selector,
            js_runtime=self._current_js_runtime(),
            remote_components=self._current_remote_components(),
            prefer_video=prefer_video,
            video_quality=video_quality,
            preferred_format=effective_preferred,
            quality_profile=self._current_quality_profile(),
        )

    def _preferred_format(self) -> Optional[str]:
        page = self.format_tab.tabText(self.format_tab.currentIndex()).lower()
        return None if page == "any" else page

    def _should_prefer_video(self, track: TrackMetadata) -> bool:
        preferred = self._preferred_format()
        if preferred == "mp4":
            return True
        if preferred == "mp3":
            return False
        return self.library_view.is_video(track)

    def _current_video_quality(self) -> str:
        value = self.video_quality_combo.currentText().lower()
        return "" if value == "any" else value

    def _current_js_runtime(self) -> Optional[str]:
        value = self.js_runtime_input.text().strip()
        return value or self.defaults.js_runtime

    def _current_remote_components(self) -> List[str]:
        text = self.remote_components_input.text().strip()
        if text:
            return [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]
        return self.defaults.remote_components

    def _current_quality_profile(self) -> str:
        data = self.quality_profile_combo.currentData()
        if data:
            return data
        return self.defaults.quality_profile or DEFAULT_PROFILE_NAME

    def _start_search(self) -> None:
        genre = self.genre_input.text().strip()
        artist = self.artist_input.text().strip()
        keywords = self.keywords_input.text().strip()
        if not self._has_search_terms(genre, artist, keywords):
            self._set_search_validation_state(False)
            self._set_status("Enter a genre, artist, or keywords before searching.")
            return
        self._set_search_validation_state(True)
        self.library_view.clear()
        self.tracks = []
        self.last_search_summary_label.setText("Streaming results...")
        self.search_button.setEnabled(False)
        self.search_progress.setVisible(True)
        self._set_status("Searching YouTube...")
        filters = self._build_filters()
        self._spawn_worker(
            self.search_service.search,
            genre=genre or None,
            artist=artist or None,
            filters=filters,
            order=self.order_combo.currentText(),
            js_runtime=self._current_js_runtime(),
            remote_components=self._current_remote_components(),
            chunk_size=SEARCH_CHUNK_SIZE,
            max_results=self.max_entries_slider.value(),
            progress=True,
            on_progress=self._on_track_discovered,
            on_finished=lambda tracks: (self._on_search_finished(tracks), self.search_button.setEnabled(True)),
            context="search",
        )
        self.stack.setCurrentWidget(self.library_view)

    def _on_max_entries_slider_changed(self, value: int) -> None:
        self.max_entries_slider.setToolTip(str(value))

    def _on_track_discovered(self, progress: SearchProgress) -> None:
        track = progress.track
        self.tracks.append(track)
        self.library_view.add_track(track)
        if progress.total_estimate:
            self.last_search_summary_label.setText(
                f"Streaming {progress.index} of {progress.total_estimate} tracks"
            )
        else:
            self.last_search_summary_label.setText(f"Streaming {len(self.tracks)} tracks")

    def _on_search_finished(self, tracks: List[TrackMetadata]) -> None:
        self._set_status(f"Found {len(tracks)} tracks.")
        self.last_search_summary_label.setText(f"Search complete: {len(tracks)} results")
        self.search_progress.setVisible(False)

    def _on_worker_error(self, error: Union[WorkerError, str]) -> None:
        if isinstance(error, WorkerError):
            context = f"{error.context}: " if error.context else ""
            message = f"{context}{error.exc_type}: {error.message}"
        else:
            message = error
        self._set_status(f"Error: {message}")
        self.search_button.setEnabled(True)
        self.search_progress.setVisible(False)

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
        self._spawn_worker(
            self._download_tracks,
            tracks,
            download_dir,
            self._current_js_runtime(),
            self._current_remote_components(),
            self._current_quality_profile(),
            on_finished=lambda files: self._set_status(f"Downloaded {len(files)} files."),
            context="download_tracks",
        )

    def _download_tracks(
        self,
        tracks: List[TrackMetadata],
        download_dir: Path,
        js_runtime: Optional[str],
        remote_components: List[str],
        quality_profile: str,
    ) -> List[Path]:
        return self.download_service.download(
            tracks,
            download_dir=download_dir,
            js_runtime=js_runtime,
            remote_components=remote_components,
            quality_profile=quality_profile,
        )

    def _select_download_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Download folder", str(self.defaults.download_dir))
        if directory:
            self.download_dir_label.setText(directory)
            self._set_status(f"Download folder set to {directory}")

    def _apply_preset(self, preset: str) -> None:
        if preset == "Select preset":
            return
        preset_map = {
            "Ambient": ("ambient", ""),
            "Chill": ("chill", ""),
            "Focus": ("focus", "study"),
            "Lo-fi": ("lofi", "beats"),
            "Trance": ("trance", ""),
            "Workout": ("workout", "energy"),
        }
        genre, keywords = preset_map.get(preset, ("", ""))
        if genre:
            self.genre_input.setText(genre)
        if keywords:
            self.keywords_input.setText(keywords)
        self._set_search_validation_state(True)

    def _clear_filters(self) -> None:
        self.preset_combo.setCurrentIndex(0)
        self.genre_input.clear()
        self.artist_input.clear()
        self.keywords_input.clear()
        self.order_combo.setCurrentText("relevance")
        self.stream_format_input.setText(self.defaults.stream_format)
        default_quality = self.defaults.video_quality if self.defaults.video_quality in ["high", "medium", "low"] else "Any"
        self.video_quality_combo.setCurrentText(default_quality)
        self.js_runtime_input.setText(self.defaults.js_runtime or "")
        self.remote_components_input.setText(
            ", ".join(self.defaults.remote_components) if self.defaults.remote_components else ""
        )
        default_profile = self.defaults.quality_profile if self.defaults.quality_profile in QUALITY_PROFILE_MAP else DEFAULT_PROFILE_NAME
        idx = self.quality_profile_combo.findData(default_profile)
        if idx >= 0:
            self.quality_profile_combo.setCurrentIndex(idx)
        self.format_tab.setCurrentIndex(0)
        self.max_entries_slider.setValue(50)
        self.min_duration_spin.setValue(0)
        self.max_duration_spin.setValue(0)
        self.min_views_spin.setValue(0)
        self.max_views_spin.setValue(0)
        self.sfw_checkbox.setChecked(False)
        self._set_search_validation_state(True)

    def _set_search_validation_state(self, valid: bool) -> None:
        border = "" if valid else "border: 1px solid #D05050;"
        for field in (self.genre_input, self.artist_input, self.keywords_input):
            field.setStyleSheet(border)

    def _maybe_clear_search_validation(self) -> None:
        if self._has_search_terms(
            self.genre_input.text().strip(),
            self.artist_input.text().strip(),
            self.keywords_input.text().strip(),
        ):
            self._set_search_validation_state(True)

    def _update_now_playing_label(self, track: TrackMetadata) -> None:
        self.now_playing_label.setText(f"{track.title} - {track.uploader}")

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
