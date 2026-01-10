from pathlib import Path

import pytest

from utube.extractor import TrackMetadata
from utube.services import (
    DownloadService,
    ErrorEvent,
    PlaybackEvent,
    PlaybackService,
    SearchProgress,
    SearchService,
)
from utube.storage import StreamingLink


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
        thumbnail=None,
        description=None,
        tags=[],
        file_type="mp3",
    )


def test_search_service_progress(monkeypatch):
    results = [_track("a"), _track("b")]

    def fake_search_tracks(*args, progress_callback=None, **kwargs):
        if progress_callback:
            for track in results:
                progress_callback(track)
        return results

    monkeypatch.setattr("utube.services.search_tracks", fake_search_tracks)
    seen = []

    def on_progress(progress: SearchProgress):
        seen.append(progress)

    service = SearchService()
    tracks = service.search(
        genre="ambient",
        artist=None,
        filters=None,
        order="relevance",
        max_results=2,
        js_runtime=None,
        remote_components=[],
        chunk_size=1,
        progress_callback=on_progress,
    )
    assert tracks == results
    assert [p.index for p in seen] == [1, 2]
    assert seen[0].track.video_id == "a"


def test_playback_service_resolves_first_link(monkeypatch):
    track = _track()
    expected = StreamingLink(track=track, stream_url="http://example.com", format_id="best")

    class FakeStreamer:
        def __init__(self, **kwargs):
            pass

        def stream_links(self, tracks):
            return [expected]

    monkeypatch.setattr("utube.services.Streamer", FakeStreamer)
    service = PlaybackService()
    link = service.resolve_stream(
        track=track,
        selector="bestaudio",
        js_runtime=None,
        remote_components=[],
        prefer_video=False,
        video_quality="",
        preferred_format=None,
        quality_profile="high",
    )
    assert link == expected


def test_playback_service_raises_when_empty(monkeypatch):
    track = _track()

    class FakeStreamer:
        def __init__(self, **kwargs):
            pass

        def stream_links(self, tracks):
            return []

    monkeypatch.setattr("utube.services.Streamer", FakeStreamer)
    service = PlaybackService()
    with pytest.raises(RuntimeError):
        service.resolve_stream(
            track=track,
            selector="bestaudio",
            js_runtime=None,
            remote_components=[],
            prefer_video=False,
            video_quality="",
            preferred_format=None,
            quality_profile="high",
        )


def test_download_service_uses_manager(monkeypatch, tmp_path: Path):
    track = _track()
    captured = {}

    class FakeManager:
        def __init__(self, base_dir, **kwargs):
            captured["base_dir"] = base_dir
            captured["kwargs"] = kwargs

        def download_tracks(self, tracks):
            return [tmp_path / "file.mp3"]

    monkeypatch.setattr("utube.services.DownloadManager", FakeManager)
    service = DownloadService()
    files = service.download(
        [track],
        download_dir=tmp_path,
        js_runtime="node",
        remote_components=["ejs:github"],
        quality_profile="high",
    )
    assert files == [tmp_path / "file.mp3"]
    assert captured["base_dir"] == tmp_path
    assert captured["kwargs"]["js_runtime"] == "node"


def test_service_events():
    track = _track()
    assert SearchProgress(track=track, index=1, total_estimate=2).index == 1
    assert PlaybackEvent(state="playing", track=track).state == "playing"
    assert ErrorEvent(context="x", user_message="y").context == "x"
