from pathlib import Path

from utube import DownloadManager, Streamer, TrackMetadata, StreamingLink


def _track_metadata() -> TrackMetadata:
    return TrackMetadata(
        video_id="int123",
        title="Integration Track",
        uploader="tester",
        duration_seconds=240,
        view_count=999,
        upload_date="20250101",
        webpage_url="https://www.youtube.com/watch?v=int123",
        channel_url="https://www.youtube.com/channel/test",
        thumbnail=None,
        description="Integration test track",
        tags=["test"],
        file_type="mp3",
    )


def test_download_manager_invokes_yt_dlp(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    class DummyYDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def download(self, urls):
            captured.setdefault("calls", []).append(urls)

    monkeypatch.setattr("utube.storage.yt_dlp.YoutubeDL", DummyYDL)

    manager = DownloadManager(
        tmp_path, audio_format="ogg", bitrate="128", remote_components=["ejs:github"]
    )
    files = manager.download_tracks([_track_metadata()])

    assert files
    assert files[0].suffix == ".ogg"
    assert captured["calls"][0] == ["https://www.youtube.com/watch?v=int123"]
    assert captured["opts"]["postprocessors"][0]["key"] == "FFmpegExtractAudio"
    assert captured["opts"]["postprocessors"][0]["preferredcodec"] == "ogg"
    assert captured["opts"]["remote_components"] == ["ejs:github"]
    assert captured["opts"]["format"].startswith("bestaudio[abr>=256]")


def test_download_manager_video_format_sets_merge(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    class DummyYDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def download(self, urls):
            captured.setdefault("calls", []).append(urls)

    monkeypatch.setattr("utube.storage.yt_dlp.YoutubeDL", DummyYDL)

    manager = DownloadManager(tmp_path, audio_format="mp4")
    files = manager.download_tracks([_track_metadata()])

    assert files
    assert files[0].suffix == ".mp4"
    assert "height>=1080" in captured["opts"]["format"]
    assert "+bestaudio[abr>=256]" in captured["opts"]["format"]
    assert captured["opts"]["merge_output_format"] == "mp4"
    assert captured["opts"]["postprocessors"] == [{"key": "FFmpegMetadata"}]


def test_streamer_selects_best_audio(monkeypatch) -> None:
    captured = {}

    class DummyYDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def extract_info(self, url, download):
            captured.setdefault("urls", []).append(url)
            return {
                "formats": [
                    {
                        "acodec": "opus",
                        "abr": 192,
                        "url": "https://stream/opus",
                        "format_id": "opus-hi",
                    },
                    {
                        "acodec": "none",
                        "url": "https://stream/none",
                        "format_id": "video",
                    },
                ]
            }

    monkeypatch.setattr("utube.storage.yt_dlp.YoutubeDL", DummyYDL)

    stream_links = Streamer(
        format_selector="bestaudio/best", remote_components=["ejs:github"]
    ).stream_links([_track_metadata()])
    assert len(stream_links) == 1
    link = stream_links[0]
    assert isinstance(link, StreamingLink)
    assert link.stream_url == "https://stream/opus"
    assert captured["urls"][0] == "https://www.youtube.com/watch?v=int123"
    assert captured["opts"]["remote_components"] == ["ejs:github"]


def test_streamer_prefers_video_quality(monkeypatch) -> None:
    captured = {}

    class DummyYDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def extract_info(self, url, download):
            captured.setdefault("urls", []).append(url)
            return {
                "formats": [
                    {
                        "url": "low-stream",
                        "height": 360,
                        "vcodec": "avc1",
                        "acodec": "aac",
                    },
                    {
                        "url": "high-stream",
                        "height": 1080,
                        "vcodec": "avc1",
                        "acodec": "aac",
                    },
                    {
                        "url": "mid-stream",
                        "height": 720,
                        "vcodec": "avc1",
                        "acodec": "aac",
                    },
                ]
            }

    monkeypatch.setattr("utube.storage.yt_dlp.YoutubeDL", DummyYDL)

    streamer = Streamer(prefer_video=True, video_quality="medium")
    links = streamer.stream_links([_track_metadata()])

    assert len(links) == 1
    assert links[0].stream_url == "mid-stream"
