"""Basic smoke tests for the extractor helpers."""

import pytest

from utube import SearchFilters, search_tracks


def test_search_filters_defaults() -> None:
    filters = SearchFilters()
    assert filters.require_non_live is True
    assert filters.safe_for_work is False
    assert filters.min_duration is None


def test_search_tracks_rejects_empty_terms() -> None:
    with pytest.raises(ValueError):
        search_tracks()


def test_search_tracks_includes_artist_term(monkeypatch) -> None:
    captured = {}

    class DummyYTDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, query, download):
            captured["query"] = query
            return {"entries": []}

    monkeypatch.setattr("yt_dlp.YoutubeDL", DummyYTDL)
    search_tracks("techno", artist="Deadmau5", max_results=1)
    assert "Deadmau5" in captured["query"]


def test_search_tracks_honors_js_runtime(monkeypatch) -> None:
    captured = {}

    class DummyYTDL:
        def __init__(self, opts):
            captured["opts"] = opts

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, query, download):
            captured["query"] = query
            return {"entries": []}

    monkeypatch.setattr("yt_dlp.YoutubeDL", DummyYTDL)
    search_tracks("ambient", js_runtime="node", remote_components=["ejs:github"], max_results=1)
    assert captured["opts"]["js_runtime"] == "node"
    assert captured["opts"]["remote_components"] == ["ejs:github"]
