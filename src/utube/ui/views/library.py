"""Library view that hosts the results table and filters."""

from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import QModelIndex, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ...extractor import TrackMetadata
from ..models import TrackFilterProxyModel, TrackTableModel


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
        self.search_input.setPlaceholderText("Filter title, artist, tags...")
        self.search_input.textChanged.connect(self.proxy.set_search_filter)
        controls.addWidget(self.search_input)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["All", "Audio", "Video"])
        self.type_combo.currentTextChanged.connect(lambda value: self.proxy.set_type_filter(value))
        controls.addWidget(self.type_combo)
        self.count_label = QLabel("0 tracks")
        controls.addWidget(self.count_label)
        controls.addStretch()

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        if hasattr(self.table, "setUniformRowHeights"):
            self.table.setUniformRowHeights(True)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("QTableView { alternate-background-color: #1A1A1A; }")
        self.table.verticalHeader().setDefaultSectionSize(30)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 26)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(2, 180)
        for col in (3, 4, 5, 6, 7, 8, 9, 10):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self._emit_selected_track)
        self.table.activated.connect(self._emit_selected_track)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        self.empty_label = QLabel("No tracks yet. Run a search.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #8F9AA5;")
        self.empty_label.setWordWrap(True)
        self.table_stack = QStackedWidget()
        self.table_stack.addWidget(self.empty_label)
        self.table_stack.addWidget(self.table)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self.table_stack)
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
        if total == 0:
            self.table_stack.setCurrentWidget(self.empty_label)
        else:
            self.table_stack.setCurrentWidget(self.table)

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
        return self.model._normalize_file_type(track.file_type) == "mp4"

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
