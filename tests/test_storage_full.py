from pathlib import Path

import pytest

import utube.storage as storage
from dataclasses import replace

from utube.extractor import TrackMetadata
from utube.storage import DownloadManager, Streamer


def _track() -> TrackMetadata:
    return TrackMetadata(
        video_id="abc",
        title="Title",
        uploader="Uploader",
        duration_seconds=60,
        view_count=10,
        upload_date="20240101",
        webpage_url="https://example.com",
        channel_url=None,
        thumbnail=None,
        description=None,
        tags=[],
        file_type="mp3",
    )


def test_js_runtime_entry_absolute(tmp_path: Path):
    runtime = tmp_path / "node.exe"
    runtime.write_text("")
    entry = storage._js_runtime_entry(str(runtime))
    assert entry["path"] == str(runtime)


def test_streamer_select_format_preferred():
    streamer = Streamer(prefer_video=False, preferred_format="mp4")
    formats = [
        {
            "ext": "mp4",
            "vcodec": "avc1",
            "acodec": "aac",
            "format_id": "v1",
            "url": "u1",
        },
        {
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "aac",
            "format_id": "a1",
            "url": "u2",
        },
    ]
    info = {"formats": formats}
    selected = streamer._select_format(info)
    assert selected["format_id"] == "v1"


def test_streamer_select_format_audio():
    streamer = Streamer(prefer_video=False)
    formats = [
        {"ext": "webm", "acodec": "opus", "format_id": "a1", "url": "u1", "abr": 128},
        {"ext": "m4a", "acodec": "aac", "format_id": "a2", "url": "u2", "abr": 96},
    ]
    info = {"formats": formats}
    selected = streamer._select_format(info)
    assert selected["format_id"] in ("a1", "a2")


def test_streamer_select_video_candidate_with_cap():
    streamer = Streamer(prefer_video=True, video_quality="medium")
    formats = [
        {
            "ext": "mp4",
            "vcodec": "avc1",
            "acodec": "aac",
            "format_id": "v1",
            "url": "u1",
            "height": 1080,
            "fps": 60,
        },
        {
            "ext": "mp4",
            "vcodec": "avc1",
            "acodec": "aac",
            "format_id": "v2",
            "url": "u2",
            "height": 720,
            "fps": 30,
        },
    ]
    info = {"formats": formats}
    selected = streamer._select_format(info)
    assert selected["format_id"] in ("v1", "v2")


def test_streamer_quality_helpers():
    streamer = Streamer(prefer_video=True)
    assert streamer._within_quality_cap("bad", 720) is True
    assert streamer._within_quality_cap(480, 720) is True
    assert streamer._within_quality_cap(1080, 720) is False
    assert streamer._flexible_float("1.5") == 1.5
    assert streamer._flexible_float("bad") == 0.0
    assert streamer._audio_score({"abr": 128, "tbr": 256}) == (128.0, 256.0)
    assert streamer._video_score({"height": 720, "tbr": 1000}) == (720, 1000.0)


def test_streamer_prefer_audio_codecs():
    streamer = Streamer(prefer_video=False)
    candidates = [
        {"acodec": "aac", "abr": 96},
        {"acodec": "opus", "abr": 128},
    ]
    selected = streamer._prefer_audio_codecs(candidates)
    assert selected["acodec"] == "opus"


def test_streamer_apply_quality_cap():
    streamer = Streamer(prefer_video=True)
    candidates = [
        {"height": 1080},
        {"height": 720},
        {"height": None},
    ]
    capped = streamer._apply_quality_cap(candidates, 720)
    assert len(capped) == 2


def test_download_manager_builds_filename(tmp_path: Path):
    manager = DownloadManager(tmp_path)
    track = _track()
    name = storage.build_track_filename(track)
    assert name.endswith(".mp3")
    assert track.video_id in name


def test_sanitize_filename_default():
    assert storage.sanitize_filename("!!!") == "track"


def test_download_manager_download_invokes_ytdlp(tmp_path: Path, monkeypatch):
    captured = {}

    class DummyYTDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def download(self, urls):
            captured["urls"] = urls

    monkeypatch.setattr(storage, "yt_dlp", type("Y", (), {"YoutubeDL": DummyYTDL}))
    manager = DownloadManager(
        tmp_path,
        audio_format="mp3",
        js_runtime="node",
        remote_components=["ejs:github"],
    )
    manager._download("http://example.com", tmp_path / "file.mp3")
    assert "format" in captured["opts"]
    assert captured["urls"] == ["http://example.com"]


def test_download_tracks_skips_missing_url(tmp_path: Path):
    manager = DownloadManager(tmp_path)
    track = _track()
    track = replace(track, webpage_url="")
    assert manager.download_tracks([track]) == []


def test_streamer_stream_links_with_js_runtime(monkeypatch):
    track = _track()
    track = replace(track, webpage_url="")
    captured = {}

    class DummyYTDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download=False):
            return {"formats": []}

    monkeypatch.setattr(storage, "yt_dlp", type("Y", (), {"YoutubeDL": DummyYTDL}))
    monkeypatch.setattr(
        storage, "_js_runtime_entry", lambda _name: {"name": "node", "path": "node"}
    )
    streamer = Streamer(js_runtime="node", remote_components=["ejs:github"])
    links = streamer.stream_links([track])
    assert links == []
    assert captured["opts"]["js_runtime"] == "node"
    assert captured["opts"]["remote_components"] == ["ejs:github"]


def test_select_format_no_formats():
    streamer = Streamer()
    assert streamer._select_format({"formats": []}) is None


def test_select_format_preferred_audio_path():
    streamer = Streamer(preferred_format="m4a")
    formats = [
        {"ext": "m4a", "acodec": "aac", "format_id": "a1", "url": "u1"},
        {"ext": "m4a", "acodec": "none", "format_id": "a2", "url": "u2"},
    ]
    selected = streamer._select_format({"formats": formats})
    assert selected["format_id"] == "a1"


def test_select_video_candidate_quality_branches():
    streamer = Streamer(prefer_video=True, video_quality="low")
    formats = [
        {"vcodec": "avc1", "acodec": "aac", "height": 720, "tbr": 100, "url": "u1"},
        {"vcodec": "avc1", "acodec": "aac", "height": 1080, "tbr": 200, "url": "u2"},
    ]
    selected = streamer._select_video_candidate(formats)
    assert selected["height"] == 1080
