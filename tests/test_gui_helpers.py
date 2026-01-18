import tempfile
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QTabWidget

from utube.extractor import TrackMetadata
from utube.gui import LibraryView, TrackFilterProxyModel, TrackTableModel, UTubeGui
from utube.storage import StreamingLink


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _track(
    *, title: str, file_type: str, description: str = "", tags=None
) -> TrackMetadata:
    return TrackMetadata(
        video_id=title.lower().replace(" ", "_"),
        title=title,
        uploader="tester",
        duration_seconds=120,
        view_count=10,
        upload_date="20240101",
        webpage_url="https://example.com",
        channel_url=None,
        thumbnail=None,
        description=description,
        tags=tags or [],
        file_type=file_type,
    )


def test_filter_proxy_type_and_text(qapp):
    model = TrackTableModel()
    proxy = TrackFilterProxyModel()
    proxy.setSourceModel(model)

    track_a = _track(title="Ambient Focus", file_type="mp3", tags=["focus"])
    track_b = _track(title="Video Demo", file_type="mp4", description="sample")
    model.append_track(track_a)
    model.append_track(track_b)

    proxy.set_type_filter("audio")
    assert proxy.filterAcceptsRow(0, proxy.index(0, 0))
    assert not proxy.filterAcceptsRow(1, proxy.index(1, 0))

    proxy.set_type_filter("video")
    assert not proxy.filterAcceptsRow(0, proxy.index(0, 0))
    assert proxy.filterAcceptsRow(1, proxy.index(1, 0))

    proxy.set_type_filter("all")
    proxy.set_search_filter("focus")
    assert proxy.filterAcceptsRow(0, proxy.index(0, 0))
    assert not proxy.filterAcceptsRow(1, proxy.index(1, 0))


def test_preferred_format_and_should_prefer_video(qapp):
    gui = UTubeGui.__new__(UTubeGui)
    gui.format_tab = QTabWidget()
    for label in ("Any", "MP3", "MP4"):
        gui.format_tab.addTab(QTabWidget(), label)
    gui.library_view = LibraryView()

    track_audio = _track(title="Audio", file_type="mp3")
    track_video = _track(title="Video", file_type="mp4")

    gui.format_tab.setCurrentIndex(0)
    assert gui._preferred_format() is None
    assert gui._should_prefer_video(track_audio) is False
    assert gui._should_prefer_video(track_video) is True

    gui.format_tab.setCurrentIndex(1)
    assert gui._preferred_format() == "mp3"
    assert gui._should_prefer_video(track_video) is False

    gui.format_tab.setCurrentIndex(2)
    assert gui._preferred_format() == "mp4"
    assert gui._should_prefer_video(track_audio) is True


def test_cleanup_temp_files_removes_unpreserved():
    gui = UTubeGui.__new__(UTubeGui)
    with (
        tempfile.NamedTemporaryFile(delete=False) as tmp_a,
        tempfile.NamedTemporaryFile(delete=False) as tmp_b,
    ):
        gui._temp_media_files = {tmp_a.name, tmp_b.name}
        gui._cleanup_temp_files(preserve=tmp_b.name)
        assert tmp_b.name in gui._temp_media_files
        assert tmp_a.name not in gui._temp_media_files
        gui._cleanup_temp_files()
        assert not gui._temp_media_files


def test_cap_temp_cache_removes_overflow(tmp_path):
    gui = UTubeGui.__new__(UTubeGui)
    gui._temp_media_files = set()
    paths = []
    for idx in range(8):
        path = tmp_path / f"file{idx}.tmp"
        path.write_text("x")
        gui._temp_media_files.add(str(path))
        paths.append(str(path))
    gui._cap_temp_cache()
    assert len(gui._temp_media_files) <= 6


def test_stream_selector_and_details(qapp):
    gui = UTubeGui.__new__(UTubeGui)
    gui.defaults = type("Defaults", (), {"stream_format": "bestaudio/best"})()
    selector = gui._build_stream_selector(
        prefer_video=False, stream_format="", preferred_format=None
    )
    assert "bestaudio" in selector
    selector_video = gui._build_stream_selector(
        prefer_video=True, stream_format="", preferred_format="mp4"
    )
    assert "mp4" in selector_video

    track = _track(title="Audio", file_type="mp3")
    link = StreamingLink(
        track=track,
        stream_url="http://example",
        format_id="best",
        ext="mp3",
        abr=128,
        height=0,
    )
    details = gui._format_stream_details(link)
    assert "MP3" in details


def test_validate_stream_url_rejects_localhost():
    gui = UTubeGui.__new__(UTubeGui)
    with pytest.raises(RuntimeError):
        gui._validate_stream_url("http://localhost/test")


def test_preflight_checks(monkeypatch):
    gui = UTubeGui.__new__(UTubeGui)
    gui._set_status = lambda _msg: None
    gui._current_js_runtime = lambda: "missing"
    monkeypatch.setattr("utube.gui.shutil.which", lambda _name: None)
    monkeypatch.setattr("utube.gui.Path.exists", lambda _self: False)
    assert gui._check_js_runtime() is False

    gui._current_js_runtime = lambda: ""
    monkeypatch.setattr(
        "utube.gui.socket.create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError()),
    )
    assert gui._check_network() is False


def test_resolve_voice_enabled(monkeypatch):
    gui = UTubeGui.__new__(UTubeGui)
    gui.defaults = type("Defaults", (), {"voice_enabled": True})()
    monkeypatch.setenv("UTUBE_VOICE_ENABLED", "1")
    assert gui._resolve_voice_enabled() is True
    monkeypatch.delenv("UTUBE_VOICE_ENABLED", raising=False)
    gui._discover_voice_models = lambda: {"model": Path(".")}
    assert gui._resolve_voice_enabled() is True
