"""Playback and visualization widgets."""

from __future__ import annotations

from math import pi, sin
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QObject, QRectF, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer, QSoundEffect
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...extractor import TrackMetadata
from ..theme import ACCENT_COLOR, DIVIDER, SECONDARY_PANEL


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
        project_root = Path(__file__).resolve().parents[2]
        click = project_root / "assets" / "click.wav"
        if click.exists():
            self._load_effect("click", click)

    def _load_effect(self, name: str, path: Path) -> None:
        effect = QSoundEffect(self)
        effect.setSource(QUrl.fromLocalFile(str(path)))
        effect.setVolume(0.35)
        self.effects[name] = effect

    def play_click(self) -> None:
        if (effect := self.effects.get("click")):
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
        self._last_waveform_update_ms = 0

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
        if enabled:
            if self._visualizer_timer.isActive():
                self._visualizer_timer.stop()
        else:
            if self.controller.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                if not self._visualizer_timer.isActive():
                    self._visualizer_timer.start()

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
        self._last_waveform_update_ms = 0
        self.waveform.set_progress(0.0)
        self.elapsed_label.setText("00:00")
        self.duration_label.setText("00:00")
        self.set_video_mode(self.controller.is_video())
        self.seek_slider.setEnabled(False)

    def _on_position_changed(self, position: int) -> None:
        if abs(position - self._last_waveform_update_ms) >= 200:
            if self._duration_ms > 0:
                self.waveform.set_progress(min(position / max(1, self._duration_ms), 1.0))
            self._last_waveform_update_ms = position
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
            if self.video_stack.currentWidget() is self.visualizer:
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
