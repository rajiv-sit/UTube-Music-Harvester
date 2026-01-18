"""Qt table models for search results."""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    Qt,
    QSortFilterProxyModel,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap

from ..extractor import TrackMetadata
from .theme import ACCENT_COLOR


class TrackTableModel(QAbstractTableModel):
    HEADERS = [
        "",
        "Title",
        "Uploader",
        "Duration",
        "Views",
        "Likes",
        "Uploaded",
        "Type",
        "Format",
        "Bitrate",
        "Resolution",
    ]

    thumbnailRequested = pyqtSignal(str)
    THUMBNAIL_SIZE = 48

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._tracks: List[TrackMetadata] = []
        self._icon_cache: dict[str, QIcon] = {}
        self._search_cache: dict[str, str] = {}
        self._thumbnail_cache: dict[str, QPixmap] = {}
        self._thumbnail_pending: set[str] = set()
        self._thumbnail_rows: dict[str, set[str]] = {}
        self._thumbnail_failed: set[str] = set()

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
                    return track.upload_date or "N/A"
                case 7:
                    return self._file_type_label(
                        self._normalize_file_type(track.file_type)
                    )
                case 8:
                    return self._format_format(
                        self._normalize_file_type(track.file_type)
                    )
                case 9:
                    return self._format_bitrate(track.audio_bitrate)
                case 10:
                    return self._format_resolution(track.resolution_height)
        if role == Qt.ItemDataRole.ToolTipRole:
            return track.description or track.title
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
        ):
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
        self._thumbnail_failed.clear()
        self.endResetModel()

    def track_at(self, row: int) -> TrackMetadata:
        return self._tracks[row]

    def search_blob(self, row: int) -> str:
        track = self._tracks[row]
        key = self._track_key(track)
        cached = self._search_cache.get(key)
        if cached is not None:
            return cached
        description = (track.description or "").strip()
        if len(description) > 240:
            description = f"{description[:240]}..."
        tags = " ".join(track.tags[:10]) if track.tags else ""
        blob = " ".join(
            filter(None, (track.title, track.uploader, description, tags))
        ).lower()
        self._search_cache[key] = blob
        return blob

    def set_thumbnail_data(self, url: str, payload: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(payload):
            self._thumbnail_pending.discard(url)
            self._thumbnail_failed.add(url)
            return
        scaled = pixmap.scaled(
            self.THUMBNAIL_SIZE,
            self.THUMBNAIL_SIZE,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._thumbnail_cache[url] = scaled
        self._thumbnail_pending.discard(url)
        track_keys = self._thumbnail_rows.get(url, set())
        if not track_keys:
            return
        for row, track in enumerate(self._tracks):
            if self._track_key(track) in track_keys:
                idx = self.index(row, 1)
                self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DecorationRole])

    def mark_thumbnail_failed(self, url: str) -> None:
        self._thumbnail_pending.discard(url)
        self._thumbnail_failed.add(url)

    def _thumbnail_for_track(self, track: TrackMetadata, row: int) -> Optional[QIcon]:
        url = track.thumbnail
        if not url:
            return None
        if url in self._thumbnail_failed:
            return None
        if url in self._thumbnail_cache:
            return QIcon(self._thumbnail_cache[url])
        self._thumbnail_rows.setdefault(url, set()).add(self._track_key(track))
        if url not in self._thumbnail_pending:
            self._thumbnail_pending.add(url)
            self.thumbnailRequested.emit(url)
        return None

    def _icon_for_track(self, track: TrackMetadata) -> QIcon:
        normalized = self._normalize_file_type(track.file_type)
        label = "V" if normalized == "mp4" else "A"
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
            return "N/A"
        mins, secs = divmod(duration, 60)
        return f"{mins}:{secs:02}"

    @staticmethod
    def _format_views(views: Optional[int]) -> str:
        return f"{views:,}" if views else "N/A"

    @staticmethod
    def _normalize_file_type(value: str) -> str:
        cleaned = value.lower().strip().lstrip(".")
        return cleaned or "unknown"

    @staticmethod
    def _file_type_label(normalized: str) -> str:
        if normalized == "unknown":
            return "Unknown"
        label = "Video" if normalized == "mp4" else "Audio"
        return f"{label} ({normalized.upper()})"

    @staticmethod
    def _format_format(normalized: str) -> str:
        return normalized.upper() if normalized != "unknown" else "N/A"

    @staticmethod
    def _format_bitrate(abr: Optional[float]) -> str:
        if not abr:
            return "N/A"
        try:
            return f"{int(abr)} kbps"
        except (TypeError, ValueError):
            return "N/A"

    @staticmethod
    def _format_resolution(height: Optional[int]) -> str:
        if not height:
            return "N/A"
        return f"{height}p"

    @staticmethod
    def _track_key(track: TrackMetadata) -> str:
        return track.video_id or f"id:{id(track)}"


class TrackFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._filter_text = ""
        self._filter_type = "all"

    def set_search_filter(self, text: str) -> None:
        self._filter_text = text.strip().lower()
        self.invalidateFilter()

    def set_type_filter(self, file_type: str) -> None:
        self._filter_type = file_type.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model: TrackTableModel = self.sourceModel()  # type: ignore[assignment]
        track = model.track_at(source_row)
        if self._filter_type not in ("all", ""):
            normalized = model._normalize_file_type(track.file_type)
            if self._filter_type == "audio" and normalized == "mp4":
                return False
            if self._filter_type == "video" and normalized != "mp4":
                return False
        if self._filter_text:
            haystack = model.search_blob(source_row)
            if self._filter_text not in haystack:
                return False
        return True
