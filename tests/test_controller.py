from pathlib import Path

from utube import DownloadResult, MediaRequest, StreamResult, StreamingLink, TrackMetadata, fulfill_request


def _stub_track() -> TrackMetadata:
    return TrackMetadata(
        video_id="stub",
        title="Stub Mix",
        uploader="Test",
        duration_seconds=180,
        view_count=100,
        upload_date="20250101",
        webpage_url="https://www.youtube.com/watch?v=stub",
        channel_url=None,
        thumbnail=None,
        description=None,
        tags=[],
    )


def test_fulfill_request_download_path(monkeypatch, tmp_path: Path) -> None:
    request = MediaRequest(genre="trance", mode="download", download_dir=tmp_path)
    track_list = [_stub_track()]

    monkeypatch.setattr("utube.controller.search_tracks", lambda *args, **kwargs: track_list)

    class DummyDownloader:
        def __init__(self, *args, **kwargs) -> None:
            self.requested = []

        def download_tracks(self, tracks):
            self.requested.append(list(tracks))
            return [tmp_path / "fake.mp3"]

    monkeypatch.setattr("utube.controller.DownloadManager", lambda *args, **kwargs: DummyDownloader())

    result = fulfill_request(request)
    assert isinstance(result, DownloadResult)
    assert result.files == [tmp_path / "fake.mp3"]
    assert result.metadata == track_list


def test_fulfill_request_stream_path(monkeypatch) -> None:
    request = MediaRequest(genre="ambient", mode="stream")
    track_list = [_stub_track()]

    monkeypatch.setattr("utube.controller.search_tracks", lambda *args, **kwargs: track_list)

    class DummyStreamer:
        def __init__(self, *args, **kwargs) -> None:
            self.requested = []

        def stream_links(self, tracks):
            self.requested.append(list(tracks))
            return [StreamingLink(track=tracks[0], stream_url="link", format_id="best")]

    monkeypatch.setattr("utube.controller.Streamer", lambda *args, **kwargs: DummyStreamer())

    result = fulfill_request(request)
    assert isinstance(result, StreamResult)
    assert len(result.links) == 1
    assert result.links[0].stream_url == "link"
    assert result.links[0].track is track_list[0]
    assert result.metadata == track_list
