from pathlib import Path

from utube import TrackMetadata, build_track_filename, sanitize_filename


def _example_track() -> TrackMetadata:
    return TrackMetadata(
        video_id="abc123",
        title="Dream / Trance Mix",
        uploader="DJ Test",
        duration_seconds=360,
        view_count=1234,
        upload_date="20240101",
        webpage_url="https://www.youtube.com/watch?v=abc123",
        channel_url="https://www.youtube.com/channel/test",
        thumbnail=None,
        description=None,
        tags=["trance", "chill"],
        file_type="mp3",
    )


def test_sanitize_filename_strips_invalid() -> None:
    assert sanitize_filename("Trance/Break<>Beat 2024!") == "TranceBreakBeat 2024"


def test_build_track_filename_includes_id() -> None:
    track = _example_track()
    name = build_track_filename(track, suffix=".mp3")
    assert "abc123" in name
    assert name.endswith(".mp3")
