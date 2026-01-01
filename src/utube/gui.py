"""PyQt6-based GUI that delivers a dark, high-contrast experience for the harvester."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QRunnable, QThreadPool, Qt, QUrl, pyqtSignal, QObject
from PyQt6.QtGui import QFont
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QHeaderView,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QAbstractItemView,
    QSizePolicy,
    QSpacerItem,
)

from .config import load_defaults
from .controller import DownloadManager, Streamer
from .extractor import SearchFilters, TrackMetadata, search_tracks

ACCENT_COLOR = "#4DA3FF"
BACKGROUND = "#121212"
PANEL = "#1E1E1E"
SECONDARY_PANEL = "#242424"
DIVIDER = "#333333"
TEXT_PRIMARY = "#E0E0E0"
TEXT_SECONDARY = "#A0A0A0"
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
}}
QFrame#navPanel {{
    background-color: {PANEL};
    border-right: 1px solid {DIVIDER};
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
QPushButton[primary='true'] {{
    background-color: {ACCENT_COLOR};
    color: #121212;
    border-color: {ACCENT_COLOR};
}}
QPushButton[nav='true'] {{
    background-color: transparent;
    border: none;
    text-align: left;
    padding: 10px 16px;
    border-radius: 8px;
}}
QPushButton[nav='true']:hover {{
    background-color: {SECONDARY_PANEL};
}}
QPushButton[nav='true'][selected='true'] {{
    background-color: {ACCENT_COLOR};
    color: #121212;
}}
QLineEdit, QComboBox, QSpinBox {{
    background-color: {SECONDARY_PANEL};
    border: 1px solid {DIVIDER};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 4px 8px;
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QLabel.disabled {{
    color: {DISABLED_TEXT};
}}
QTableWidget {{
    background-color: {SECONDARY_PANEL};
    gridline-color: {DIVIDER};
    border: none;
}}
QTableWidget::item:selected {{
    background-color: {ACCENT_COLOR};
    color: #121212;
}}
QHeaderView::section {{
    background-color: {SECONDARY_PANEL};
    border: 1px solid {DIVIDER};
    padding: 4px;
    font-weight: 600;
}}
QScrollBar:vertical {{
    background-color: {SECONDARY_PANEL};
    width: 8px;
}}
QLabel {{
    color: {TEXT_PRIMARY};
}}
QCheckBox {{
    color: {TEXT_PRIMARY};
}}
"""


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)


class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        else:
            self.signals.finished.emit(result)


class UTubeGui(QMainWindow):
    NAV_ITEMS = [
        "Dashboard",
        "Processing / Pipelines",
        "Data Manager",
        "Visualization",
        "Settings",
        "About",
    ]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("UTube Music Harvester")
        self.thread_pool = QThreadPool()
        self.defaults = load_defaults()
        self.nav_buttons: List[QPushButton] = []

        self._build_ui()
        self.tracks: List[TrackMetadata] = []
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Navigation sidebar
        nav_frame = QFrame()
        nav_frame.setObjectName("navPanel")
        nav_frame.setFixedWidth(260)
        nav_layout = QVBoxLayout()
        nav_layout.setContentsMargins(16, 16, 16, 16)
        nav_layout.setSpacing(8)
        nav_label = QLabel("Sections")
        nav_label.setStyleSheet("font-weight: 600;")
        nav_layout.addWidget(nav_label)
        for name in self.NAV_ITEMS:
            button = QPushButton(name)
            button.setCheckable(True)
            button.setProperty("nav", True)
            button.clicked.connect(lambda checked, b=button: self._select_nav(b))
            nav_layout.addWidget(button)
            self.nav_buttons.append(button)
        nav_layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        nav_frame.setLayout(nav_layout)
        main_layout.addWidget(nav_frame)

        # Primary workspace
        workspace = QWidget()
        workspace_layout = QVBoxLayout()
        workspace_layout.setContentsMargins(20, 20, 20, 20)
        workspace_layout.setSpacing(16)

        # Search + filter card
        search_card = QFrame()
        search_card.setObjectName("card")
        search_layout = QVBoxLayout()
        search_layout.setSpacing(12)
        top_row = QGridLayout()
        top_row.setHorizontalSpacing(12)
        top_row.setVerticalSpacing(8)
        top_row.addWidget(QLabel("Genre"), 0, 0)
        self.genre_input = QLineEdit()
        self.genre_input.setPlaceholderText("e.g., trance")
        top_row.addWidget(self.genre_input, 0, 1)
        top_row.addWidget(QLabel("Artist"), 0, 2)
        self.artist_input = QLineEdit()
        self.artist_input.setPlaceholderText("optional")
        top_row.addWidget(self.artist_input, 0, 3)
        top_row.addWidget(QLabel("Order"), 1, 0)
        self.order_combo = QComboBox()
        self.order_combo.addItems(["relevance", "date", "longest", "shortest"])
        top_row.addWidget(self.order_combo, 1, 1)
        top_row.addWidget(QLabel("Stream format"), 1, 2)
        self.stream_format_input = QLineEdit(self.defaults.stream_format)
        top_row.addWidget(self.stream_format_input, 1, 3)
        top_row.addWidget(QLabel("JS runtime"), 2, 0)
        self.js_runtime_input = QLineEdit(self.defaults.js_runtime or "")
        self.js_runtime_input.setPlaceholderText("node, deno, etc.")
        top_row.addWidget(self.js_runtime_input, 2, 1)
        top_row.addWidget(QLabel("Remote components"), 2, 2)
        self.remote_components_input = QLineEdit(
            ", ".join(self.defaults.remote_components) if self.defaults.remote_components else ""
        )
        self.remote_components_input.setPlaceholderText("ejs:github")
        top_row.addWidget(self.remote_components_input, 2, 3)
        top_row.addWidget(QLabel("Max entries"), 3, 0)
        self.max_entries_spin = QSpinBox()
        self.max_entries_spin.setRange(1, 500)
        self.max_entries_spin.setValue(10)
        top_row.addWidget(self.max_entries_spin, 3, 1)
        search_layout.addLayout(top_row)
        filter_grid = QGridLayout()
        filter_grid.setHorizontalSpacing(12)
        filter_grid.setVerticalSpacing(8)
        filter_grid.addWidget(QLabel("Min duration"), 0, 0)
        self.min_duration_spin = QSpinBox()
        self.min_duration_spin.setSuffix(" sec")
        self.min_duration_spin.setRange(0, 3600)
        self.min_duration_spin.setSpecialValueText("Any")
        filter_grid.addWidget(self.min_duration_spin, 0, 1)
        filter_grid.addWidget(QLabel("Max duration"), 0, 2)
        self.max_duration_spin = QSpinBox()
        self.max_duration_spin.setSuffix(" sec")
        self.max_duration_spin.setRange(0, 3600)
        self.max_duration_spin.setSpecialValueText("Any")
        filter_grid.addWidget(self.max_duration_spin, 0, 3)
        filter_grid.addWidget(QLabel("Min views"), 1, 0)
        self.min_views_spin = QSpinBox()
        self.min_views_spin.setRange(0, 10_000_000)
        self.min_views_spin.setSingleStep(1000)
        self.min_views_spin.setSpecialValueText("Any")
        filter_grid.addWidget(self.min_views_spin, 1, 1)
        filter_grid.addWidget(QLabel("Max views"), 1, 2)
        self.max_views_spin = QSpinBox()
        self.max_views_spin.setRange(0, 10_000_000)
        self.max_views_spin.setSingleStep(1000)
        self.max_views_spin.setSpecialValueText("Any")
        filter_grid.addWidget(self.max_views_spin, 1, 3)
        filter_grid.addWidget(QLabel("Additional keywords"), 2, 0)
        self.keywords_input = QLineEdit()
        self.keywords_input.setPlaceholderText("optional terms")
        filter_grid.addWidget(self.keywords_input, 2, 1, 1, 3)
        self.sfw_checkbox = QCheckBox("Safe-for-work")
        filter_grid.addWidget(self.sfw_checkbox, 3, 0)
        search_layout.addLayout(filter_grid)
        self.search_button = QPushButton("Search")
        self.search_button.setObjectName("searchButton")
        self.search_button.setProperty("primary", True)
        self.search_button.clicked.connect(self._start_search)
        search_layout.addWidget(self.search_button, alignment=Qt.AlignmentFlag.AlignRight)
        search_card.setLayout(search_layout)
        workspace_layout.addWidget(search_card)

        # Track table card
        table_card = QFrame()
        table_card.setObjectName("card")
        table_layout = QVBoxLayout()
        self.track_table = QTableWidget(0, 5)
        self.track_table.setHorizontalHeaderLabels(["Title", "Uploader", "Duration", "Views", "Upload Date"])
        self.track_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.track_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.track_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.track_table.setSortingEnabled(True)
        table_layout.addWidget(self.track_table)
        table_card.setLayout(table_layout)
        workspace_layout.addWidget(table_card)

        # Actions row
        actions_frame = QWidget()
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)
        self.rewind_button = QPushButton("Rewind")
        self.rewind_button.clicked.connect(self._rewind_playback)
        self.play_button = QPushButton("Play Selected")
        self.play_button.clicked.connect(self._play_selected_track)
        self.forward_button = QPushButton("Forward")
        self.forward_button.clicked.connect(self._fast_forward_playback)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._stop_playback)
        self.download_button = QPushButton("Download Selected")
        self.download_button.clicked.connect(self._download_selected_tracks)
        self.choose_dir_button = QPushButton("Change download folder")
        self.choose_dir_button.clicked.connect(self._select_download_dir)
        self.download_dir_label = QLabel(str(self.defaults.download_dir))
        actions_layout.addWidget(self.rewind_button)
        actions_layout.addWidget(self.play_button)
        actions_layout.addWidget(self.forward_button)
        actions_layout.addWidget(self.stop_button)
        actions_layout.addWidget(self.download_button)
        actions_layout.addWidget(self.choose_dir_button)
        actions_layout.addStretch()
        actions_layout.addWidget(self.download_dir_label)
        actions_frame.setLayout(actions_layout)
        workspace_layout.addWidget(actions_frame)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #A0A0A0;")
        workspace_layout.addWidget(self.status_label)

        workspace.setLayout(workspace_layout)
        main_layout.addWidget(workspace)

        central.setLayout(main_layout)
        self._select_nav(self.nav_buttons[0])

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _current_js_runtime(self) -> Optional[str]:
        value = self.js_runtime_input.text().strip()
        return value or self.defaults.js_runtime

    def _current_remote_components(self) -> List[str]:
        text = self.remote_components_input.text().strip()
        if text:
            parts = [item.strip() for item in text.replace(";", ",").split(",") if item.strip()]
            return parts
        return self.defaults.remote_components

    def _select_nav(self, button: QPushButton) -> None:
        for btn in self.nav_buttons:
            btn.setProperty("selected", btn is button)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._set_status(f"Viewing {button.text()}")

    def _start_search(self) -> None:
        genre = self.genre_input.text().strip()
        artist = self.artist_input.text().strip()
        if not genre and not artist:
            self._set_status("Enter a genre or artist before searching.")
            return

        filters = self._build_filters()
        self.search_button.setEnabled(False)
        self._set_status("Searching YouTube...")
        worker = Worker(
            search_tracks,
            genre or None,
            artist=artist or None,
            filters=filters,
            order=self.order_combo.currentText(),
            js_runtime=self._current_js_runtime(),
            remote_components=self._current_remote_components(),
            max_results=self.max_entries_spin.value(),
        )
        worker.signals.finished.connect(self._on_search_finished)
        worker.signals.finished.connect(lambda _: self.search_button.setEnabled(True))
        worker.signals.error.connect(self._on_worker_error)
        self.thread_pool.start(worker)

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

    def _on_search_finished(self, tracks: List[TrackMetadata]) -> None:
        self.tracks = tracks
        self._populate_track_table()
        self._set_status(f"Found {len(tracks)} tracks.")

    def _on_worker_error(self, message: str) -> None:
        self._set_status(f"Error: {message}")
        self.search_button.setEnabled(True)

    def _populate_track_table(self) -> None:
        self.track_table.setRowCount(0)
        for track in self.tracks:
            row = self.track_table.rowCount()
            self.track_table.insertRow(row)
            title_item = QTableWidgetItem(track.title)
            title_item.setData(Qt.ItemDataRole.UserRole, track)
            self.track_table.setItem(row, 0, title_item)
            self.track_table.setItem(row, 1, QTableWidgetItem(track.uploader))
            self.track_table.setItem(row, 2, QTableWidgetItem(self._format_duration(track.duration_seconds)))
            self.track_table.setItem(row, 3, QTableWidgetItem(self._format_views(track.view_count)))
            self.track_table.setItem(row, 4, QTableWidgetItem(track.upload_date or "N/A"))

    def _format_duration(self, duration: Optional[int]) -> str:
        if not duration:
            return "N/A"
        mins, secs = divmod(duration, 60)
        return f"{mins}:{secs:02}"

    def _format_views(self, views: Optional[int]) -> str:
        return f"{views:,}" if views else "N/A"

    def _selected_tracks(self) -> List[TrackMetadata]:
        tracks = []
        for selected in self.track_table.selectionModel().selectedRows():
            item = self.track_table.item(selected.row(), 0)
            if item:
                track = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(track, TrackMetadata):
                    tracks.append(track)
        return tracks

    def _play_selected_track(self) -> None:
        tracks = self._selected_tracks()
        if not tracks:
            self._set_status("Select a track to preview.")
            return
        track = tracks[0]
        self._set_status("Resolving stream...")
        worker = Worker(self._resolve_stream_url, track, self.stream_format_input.text().strip())
        worker.signals.finished.connect(self._start_playback)
        worker.signals.error.connect(self._on_worker_error)
        self.thread_pool.start(worker)

    def _resolve_stream_url(self, track: TrackMetadata, stream_format: str) -> str:
        links = Streamer(
            format_selector=stream_format or self.defaults.stream_format,
            js_runtime=self._current_js_runtime(),
            remote_components=self._current_remote_components(),
        ).stream_links([track])
        if not links:
            raise RuntimeError("No stream URL available for the selected track.")
        return links[0].stream_url

    def _start_playback(self, stream_url: str) -> None:
        self.player.setSource(QUrl(stream_url))
        self.player.play()
        self._set_status("Playing stream.")

    def _stop_playback(self) -> None:
        self.player.stop()
        self._set_status("Playback stopped.")

    def _rewind_playback(self) -> None:
        new_position = max(0, self.player.position() - 5000)
        self.player.setPosition(new_position)
        self._set_status(f"Rewind to {new_position // 1000}s.")

    def _fast_forward_playback(self) -> None:
        duration = self.player.duration()
        if duration <= 0:
            duration = 0
        new_position = min(duration, self.player.position() + 5000)
        self.player.setPosition(new_position)
        self._set_status(f"Fast-forward to {new_position // 1000}s.")

    def _download_selected_tracks(self) -> None:
        tracks = self._selected_tracks()
        if not tracks:
            self._set_status("Select at least one track to download.")
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
        directory = QFileDialog.getExistingDirectory(self, "Select download directory", str(self.defaults.download_dir))
        if directory:
            self.download_dir_label.setText(directory)
            self._set_status(f"Download folder set to {directory}")


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
