"""Orchestrates user requests by combining extraction, filtering, and output handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Literal, Optional, Union

from .extractor import SearchFilters, TrackMetadata, search_tracks
from .quality import DEFAULT_PROFILE_NAME
from .storage import DownloadManager, StreamingLink, Streamer

Mode = Literal["download", "stream"]


@dataclass(frozen=True)
class MediaRequest:
    """Describes the user's intent for genre extraction and the desired output type."""

    genre: Optional[str] = None
    artist: Optional[str] = None
    mode: Mode = "download"
    filters: Optional[SearchFilters] = None
    order: str = "relevance"
    max_results: int = 12
    download_dir: Optional[Path] = None
    audio_format: str = "mp3"
    js_runtime: Optional[str] = None
    remote_components: List[str] = field(default_factory=list)
    stream_format: str = "bestaudio/best"
    quality_profile: str = DEFAULT_PROFILE_NAME


@dataclass(frozen=True)
class DownloadResult:
    """Summary produced when tracks are downloaded."""

    metadata: List[TrackMetadata]
    files: List[Path]


@dataclass(frozen=True)
class StreamResult:
    """Summary produced when stream URLs are collected."""

    metadata: List[TrackMetadata]
    links: List[StreamingLink]


def fulfill_request(request: MediaRequest) -> Union[DownloadResult, StreamResult]:
    """Execute the given request, returning either download paths or stream links."""

    tracks = search_tracks(
        request.genre,
        artist=request.artist,
        filters=request.filters,
        max_results=request.max_results,
        order=request.order,
        js_runtime=request.js_runtime,
        remote_components=request.remote_components,
    )

    if request.mode == "download":
        download_dir = Path(request.download_dir or Path.cwd() / "downloads")
        manager = DownloadManager(
            download_dir,
            audio_format=request.audio_format,
            js_runtime=request.js_runtime,
            remote_components=request.remote_components,
            quality_profile=request.quality_profile,
        )
        files = manager.download_tracks(tracks)
        return DownloadResult(metadata=tracks, files=files)

    links = Streamer(
        format_selector=request.stream_format,
        js_runtime=request.js_runtime,
        remote_components=request.remote_components,
        quality_profile=request.quality_profile,
    ).stream_links(tracks)
    return StreamResult(metadata=tracks, links=links)
