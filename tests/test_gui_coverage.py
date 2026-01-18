import base64
import os
from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QApplication, QMenu

from utube.extractor import TrackMetadata
from utube.gui import LibraryView, UTubeGui
from utube.services import SearchProgress
from utube.storage import StreamingLink


@pytest.fixture(scope="session", autouse=True)
def _qt_offscreen():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _track(video_id: str = "t1") -> TrackMetadata:
    return TrackMetadata(
        video_id=video_id,
        title="Track",
        uploader="Tester",
        duration_seconds=120,
        view_count=10,
        upload_date="20240101",
        webpage_url="https://example.com",
        channel_url=None,
        thumbnail="https://example.com/thumb.jpg",
        description="desc",
        tags=["tag"],
        file_type="mp3",
    )


class _ImmediatePool:
    def start(self, worker):
        worker.run()


def test_library_context_menu_actions(qapp, monkeypatch):
    view = LibraryView()
    track = _track()
    track_two = _track("t2")
    track_two = _track("t2")
    track_two = _track("t2")
    track_two = _track("t2")
    track_two = _track("t2")
    view.model.append_track(track)
    view.table.selectRow(0)

    fired = []
    view.playRequested.connect(lambda t: fired.append(("play", t.video_id)))
    view.playNextRequested.connect(lambda t: fired.append(("next", t.video_id)))
    view.queueRequested.connect(lambda t: fired.append(("queue", t.video_id)))
    view.downloadRequested.connect(
        lambda ts: fired.append(("download", ts[0].video_id))
    )
    view.copyTitleRequested.connect(lambda t: fired.append(("title", t.video_id)))
    view.copyUrlRequested.connect(lambda t: fired.append(("url", t.video_id)))

    def run_action(text):
        def fake_exec(self, _pos):
            for action in self.actions():
                if action.text() == text:
                    return action
            return None

        monkeypatch.setattr(QMenu, "exec", fake_exec)
        view._show_context_menu(QPoint(1, 1))

    for label in [
        "Play",
        "Play Next",
        "Add to Queue",
        "Download",
        "Copy Title",
        "Copy URL",
    ]:
        run_action(label)
    assert ("play", track.video_id) in fired
    assert ("next", track.video_id) in fired
    assert ("queue", track.video_id) in fired
    assert ("download", track.video_id) in fired
    assert ("title", track.video_id) in fired
    assert ("url", track.video_id) in fired


def test_gui_search_play_queue_and_favorites(qapp, monkeypatch, tmp_path: Path):
    gui = UTubeGui()
    gui.thread_pool = _ImmediatePool()
    gui._validate_stream_url = lambda _url: None
    gui.player_controller.play_track = lambda track, stream_url, prefer_video: setattr(
        gui.player_controller, "_current_track", track
    )

    track = _track()
    track_two = _track("t2")

    def fake_search(**kwargs):
        progress = kwargs.get("progress_callback")
        if progress:
            progress(SearchProgress(track=track, index=1, total_estimate=1))
            progress(SearchProgress(track=track_two, index=2, total_estimate=2))
        return [track, track_two]

    gui.search_service.search = fake_search
    gui.playback_service.resolve_stream = lambda **kwargs: StreamingLink(
        track=track,
        stream_url="http://example.com",
        format_id="best",
        ext="mp3",
        abr=160,
    )

    gui.genre_input.setText("ambient")
    gui._start_search()
    assert gui.tracks

    gui._enqueue_track(track)
    assert gui._queue

    gui._handle_song_activation(track)
    assert "Track" in gui.now_playing_label.text()
    gui._toggle_favorite()
    assert track.video_id in gui._favorites

    gui.tracks = [track, track_two]
    gui._play_all_voice_tracks()
    assert gui._queue

    gui._update_now_playing_duration(60000)
    gui._update_now_playing_progress(30000)
    assert "00:30" in gui.now_playing_time_label.text()

    gui.download_service.download = lambda *args, **kwargs: [tmp_path / "file.mp3"]
    gui._download_tracks_from_menu([track])
    gui._copy_track_title(track)
    gui._copy_track_url(track)


def test_gui_clear_filters_and_presets(qapp):
    gui = UTubeGui()
    gui._apply_preset("Ambient")
    assert gui.genre_input.text() == "ambient"
    gui._clear_filters()
    assert gui.genre_input.text() == ""


def test_gui_thumbnail_fetch(qapp, monkeypatch):
    gui = UTubeGui()
    gui.thread_pool = _ImmediatePool()

    def fake_download(_url):
        return base64.b64decode(
            b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
        )

    monkeypatch.setattr(gui, "_download_thumbnail_bytes", fake_download)
    gui.library_view.model.append_track(_track())
    index = gui.library_view.model.index(0, 1)
    gui.library_view.model.data(index, role=Qt.ItemDataRole.DecorationRole)
    gui._on_thumbnail_requested("https://example.com/thumb.jpg")
