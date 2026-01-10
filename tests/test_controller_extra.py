import utube.controller as controller
from utube.extractor import TrackMetadata
from utube.storage import StreamingLink


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


def test_fulfill_request_stream(monkeypatch):
    track = _track()

    def fake_search(*args, **kwargs):
        return [track]

    class FakeStreamer:
        def __init__(self, **kwargs):
            pass

        def stream_links(self, tracks):
            return [StreamingLink(track=track, stream_url="url", format_id="best")]

    monkeypatch.setattr(controller, "search_tracks", fake_search)
    monkeypatch.setattr(controller, "Streamer", FakeStreamer)
    request = controller.MediaRequest(genre="test", mode="stream")
    result = controller.fulfill_request(request)
    assert result.links[0].stream_url == "url"
