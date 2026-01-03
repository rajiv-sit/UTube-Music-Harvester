"""Async wrapper around the harvester to expose a simple CLI."""

from __future__ import annotations

import argparse
import asyncio
import datetime
from pathlib import Path
from typing import List, Optional

from . import MediaRequest, SearchFilters, DownloadResult, StreamResult, fulfill_request
from .config import load_defaults
from .quality import QUALITY_PROFILE_MAP


def _parse_date(value: str) -> datetime.date:
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be provided as YYYY-MM-DD") from exc


def _build_filters(args: argparse.Namespace) -> Optional[SearchFilters]:
    if (
        args.min_duration is None
        and args.max_duration is None
        and args.min_views is None
        and args.max_views is None
        and args.upload_after is None
        and args.upload_before is None
        and not args.safe_for_work
        and not args.keywords
    ):
        return None

    return SearchFilters(
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        min_views=args.min_views,
        max_views=args.max_views,
        upload_after=args.upload_after,
        upload_before=args.upload_before,
        safe_for_work=args.safe_for_work,
        keywords=args.keywords,
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    defaults = load_defaults()
    parser = argparse.ArgumentParser(description="Fetch genre-aware tracks from YouTube")
    parser.add_argument("genre", nargs="?", default=None, help="Genre or mood to search for (optional when --artist is set).")
    parser.add_argument("--artist", help="Specify an artist name to bias the search.")
    parser.add_argument(
        "--mode",
        choices=("download", "stream"),
        default="download",
        help="Whether to download files or just gather stream URLs.",
    )
    parser.add_argument("--download-dir", type=Path, default=defaults.download_dir, help="Where to store downloads.")
    parser.add_argument(
        "--audio-format",
        default=defaults.audio_format,
        help="Target output format (mp3 for audio, mp4 for video) for downloads.",
    )
    parser.add_argument("--bitrate", default="192", help="Target bitrate (kbps) for downloads.")
    parser.add_argument("--stream-format", default=defaults.stream_format, help="Format selector when gathering streams.")
    parser.add_argument("--js-runtime", default=defaults.js_runtime, help="Hint for yt-dlp JS runtime (node, deno, etc.).")
    parser.add_argument(
        "--remote-components",
        action="extend",
        nargs="+",
        default=list(defaults.remote_components),
        help="Enable yt-dlp remote components (e.g., ejs:github).",
    )
    parser.add_argument("--max-results", type=int, default=8, help="How many YouTube hits to evaluate.")
    parser.add_argument("--order", choices=("relevance", "date", "longest", "shortest"), default="relevance", help="Search ordering strategy.")
    parser.add_argument("--min-duration", type=int, help="Minimum duration (seconds) to keep.")
    parser.add_argument("--max-duration", type=int, help="Maximum duration (seconds) to allow.")
    parser.add_argument("--min-views", type=int, help="Minimum view count filter.")
    parser.add_argument("--max-views", type=int, help="Maximum view count filter.")
    parser.add_argument("--upload-after", type=_parse_date, help="Earliest upload date (YYYY-MM-DD).")
    parser.add_argument("--upload-before", type=_parse_date, help="Latest upload date (YYYY-MM-DD).")
    parser.add_argument("--safe-for-work", action="store_true", help="Prefer non-age restricted content.")
    parser.add_argument("--keywords", help="Extra keywords to append to the genre term.")
    parser.add_argument(
        "--quality-profile",
        choices=QUALITY_PROFILE_MAP.keys(),
        default=defaults.quality_profile,
        help="Select a quality profile that drives audio/video selectors.",
    )
    return parser.parse_args(argv)


def _print_download_result(result: DownloadResult) -> None:
    print("Downloaded tracks:")
    for path in result.files:
        print(f"  - {path}")
    print(f"Captured {len(result.files)} files from {len(result.metadata)} candidates.")


def _print_stream_result(result: StreamResult) -> None:
    print("Stream URLs collected:")
    for link in result.links:
        print(f"  - {link.track.title or link.track.video_id}: {link.stream_url} [{link.format_id}]")
    print(f"Collected {len(result.links)} stream endpoints from {len(result.metadata)} candidates.")


async def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    filters = _build_filters(args)
    request = MediaRequest(
        genre=args.genre,
        artist=args.artist,
        mode=args.mode,
        filters=filters,
        order=args.order,
        max_results=args.max_results,
        download_dir=args.download_dir,
        audio_format=args.audio_format,
        stream_format=args.stream_format,
        js_runtime=args.js_runtime,
        remote_components=args.remote_components,
        quality_profile=args.quality_profile,
    )

    result = await asyncio.to_thread(fulfill_request, request)

    if isinstance(result, DownloadResult):
        _print_download_result(result)
    else:
        _print_stream_result(result)


def cli_main() -> None:
    asyncio.run(main())


__all__ = ["main", "cli_main", "parse_args"]
