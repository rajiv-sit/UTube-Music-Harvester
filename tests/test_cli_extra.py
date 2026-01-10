import asyncio
import pytest

from utube import DownloadResult, StreamResult, TrackMetadata
from utube.cli import _parse_date, _print_download_result, _print_stream_result, cli_main, main
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


def test_parse_date_invalid():
    with pytest.raises(Exception):
        _parse_date("bad-date")


def test_print_download_result(capsys, tmp_path):
    track = _track()
    result = DownloadResult(metadata=[track], files=[tmp_path / "file.mp3"])
    _print_download_result(result)
    captured = capsys.readouterr().out
    assert "Downloaded tracks" in captured


def test_print_stream_result(capsys):
    track = _track()
    link = StreamingLink(track=track, stream_url="http://example", format_id="best")
    result = StreamResult(metadata=[track], links=[link])
    _print_stream_result(result)
    captured = capsys.readouterr().out
    assert "Stream URLs collected" in captured


def test_cli_main_download(monkeypatch, capsys, tmp_path):
    track = _track()
    result = DownloadResult(metadata=[track], files=[tmp_path / "file.mp3"])

    async def fake_to_thread(fn, *args, **kwargs):
        return result

    monkeypatch.setattr("utube.cli.asyncio.to_thread", fake_to_thread)
    asyncio.run(main(["ambient", "--mode", "download"]))
    captured = capsys.readouterr().out
    assert "Downloaded tracks" in captured


def test_cli_main_stream(monkeypatch, capsys):
    track = _track()
    link = StreamingLink(track=track, stream_url="http://example", format_id="best")
    result = StreamResult(metadata=[track], links=[link])

    async def fake_to_thread(fn, *args, **kwargs):
        return result

    monkeypatch.setattr("utube.cli.asyncio.to_thread", fake_to_thread)
    asyncio.run(main(["ambient", "--mode", "stream"]))
    captured = capsys.readouterr().out
    assert "Stream URLs collected" in captured


def test_cli_main_invokes_asyncio(monkeypatch):
    called = {}

    def fake_run(coro):
        called["ran"] = True
        coro.close()

    monkeypatch.setattr("utube.cli.asyncio.run", fake_run)
    cli_main()
    assert called["ran"] is True
