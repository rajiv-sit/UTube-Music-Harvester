import datetime

import pytest

import utube.extractor as extractor
from utube.extractor import SearchFilters, TrackMetadata


def test_matches_filters_duration_and_views():
    entry = {"duration": 300, "view_count": 1000}
    filters = SearchFilters(
        min_duration=200, max_duration=400, min_views=500, max_views=2000
    )
    assert extractor._matches_filters(entry, filters) is True

    filters = SearchFilters(min_duration=400)
    assert extractor._matches_filters(entry, filters) is False

    filters = SearchFilters(max_views=500)
    assert extractor._matches_filters(entry, filters) is False


def test_matches_filters_dates_and_live_safe():
    entry = {"upload_date": "20240115", "is_live": True, "age_limit": 18}
    filters = SearchFilters(
        upload_after=datetime.date(2024, 1, 1), require_non_live=True
    )
    assert extractor._matches_filters(entry, filters) is False

    entry["is_live"] = False
    filters = SearchFilters(upload_before=datetime.date(2024, 1, 10))
    assert extractor._matches_filters(entry, filters) is False

    filters = SearchFilters(upload_after=datetime.date(2024, 2, 1))
    assert extractor._matches_filters(entry, filters) is False

    filters = SearchFilters(safe_for_work=True)
    assert extractor._matches_filters(entry, filters) is False


def test_infer_file_type_sources():
    entry = {"ext": "mp3"}
    assert extractor._infer_file_type(entry) == "mp3"
    entry = {"mime_type": "audio/webm"}
    assert extractor._infer_file_type(entry) == "webm"
    entry = {"webpage_url": "https://example.com/video.mp4"}
    assert extractor._infer_file_type(entry) == "mp4"


def test_extension_from_url_invalid():
    assert extractor._extension_from_url("://bad") is None


def test_select_thumbnail():
    assert extractor._select_thumbnail(None) is None
    thumbs = [{"url": ""}, {"url": "http://img"}]
    assert extractor._select_thumbnail(thumbs) == "http://img"
    assert extractor._select_thumbnail([{"no": "url"}]) is None


def test_unwrap_entries():
    assert list(extractor._unwrap_entries(None)) == []
    assert list(extractor._unwrap_entries({"entries": ["bad", {"id": "1"}]})) == [
        {"id": "1"}
    ]


def test_normalize_file_type():
    assert extractor._normalize_file_type(".MP3") == "mp3"
    assert extractor._normalize_file_type("audio/webm") == "webm"
    assert extractor._normalize_file_type("") is None


def test_to_ymd():
    date = datetime.date(2024, 1, 2)
    assert extractor._to_ymd(date) == 20240102


def test_entry_to_metadata():
    entry = {
        "id": "x",
        "title": "Title",
        "uploader": "Uploader",
        "duration": 10,
        "view_count": 1,
        "upload_date": "20240101",
        "webpage_url": "url",
        "uploader_url": "channel",
        "thumbnails": [{"url": "thumb"}],
        "description": "desc",
        "tags": ["a"],
        "ext": "mp3",
        "abr": 128,
        "height": 720,
    }
    metadata = extractor._entry_to_metadata(entry)
    assert metadata.video_id == "x"
    assert metadata.thumbnail == "thumb"
    assert metadata.audio_bitrate == 128
    assert metadata.resolution_height == 720


def test_search_tracks_download_error(monkeypatch):
    class DummyYTDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, query, download):
            raise extractor.DownloadError("fail")

    monkeypatch.setattr(extractor.yt_dlp, "YoutubeDL", DummyYTDL)
    with pytest.raises(RuntimeError):
        extractor.search_tracks("ambient", max_results=1)


def test_js_runtime_entry_resolution(monkeypatch, tmp_path):
    runtime = tmp_path / "node.exe"
    runtime.write_text("")
    entry = extractor._js_runtime_entry(str(runtime))
    assert entry["path"] == str(runtime)

    monkeypatch.setattr(extractor.shutil, "which", lambda name: "/usr/bin/node")
    entry = extractor._js_runtime_entry("node")
    assert entry["path"] == "/usr/bin/node"


def test_search_tracks_filters_and_progress(monkeypatch):
    calls = []
    entries = [
        {
            "id": "1",
            "title": "One",
            "duration": 60,
            "view_count": 100,
            "webpage_url": "url1",
        },
        {
            "id": "1",
            "title": "Dup",
            "duration": 60,
            "view_count": 100,
            "webpage_url": "url1",
        },
        {
            "id": "2",
            "title": "Two",
            "duration": 500,
            "view_count": 100,
            "webpage_url": "url2",
        },
    ]

    class DummyYTDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, query, download):
            return {"entries": entries}

    monkeypatch.setattr(extractor.yt_dlp, "YoutubeDL", DummyYTDL)
    filters = SearchFilters(max_duration=300)

    def on_progress(track: TrackMetadata):
        calls.append(track.video_id)

    tracks = extractor.search_tracks(
        "ambient",
        filters=filters,
        max_results=1,
        chunk_size=2,
        progress_callback=on_progress,
    )
    assert len(tracks) == 1
    assert calls == ["1"]


def test_search_tracks_keywords_and_short_chunk(monkeypatch):
    entries = [
        {
            "id": "1",
            "title": "One",
            "duration": 60,
            "view_count": 100,
            "webpage_url": "url1",
        },
    ]

    class DummyYTDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, query, download):
            return {"entries": entries}

    monkeypatch.setattr(extractor.yt_dlp, "YoutubeDL", DummyYTDL)
    tracks = extractor.search_tracks("ambient", max_results=3, chunk_size=2)
    assert len(tracks) == 1


def test_extension_from_url_exception(monkeypatch):
    monkeypatch.setattr(
        extractor, "urlparse", lambda _url: (_ for _ in ()).throw(ValueError())
    )
    assert extractor._extension_from_url("http://example") is None
