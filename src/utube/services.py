"""Service wrappers that separate UI logic from core operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from .extractor import SearchFilters, TrackMetadata, search_tracks
from .storage import DownloadManager, StreamingLink, Streamer


@dataclass(frozen=True)
class SearchProgress:
    track: TrackMetadata
    index: int
    total_estimate: Optional[int] = None


@dataclass(frozen=True)
class PlaybackEvent:
    state: str
    track: Optional[TrackMetadata] = None
    details: Optional[str] = None


@dataclass(frozen=True)
class ErrorEvent:
    context: str
    user_message: str
    debug_message: Optional[str] = None


class SearchService:
    def search(
        self,
        *,
        genre: Optional[str],
        artist: Optional[str],
        filters: Optional[SearchFilters],
        order: str,
        max_results: int,
        js_runtime: Optional[str],
        remote_components: List[str],
        chunk_size: int,
        progress_callback: Optional[Callable[[SearchProgress], None]] = None,
    ) -> List[TrackMetadata]:
        counter = {"idx": 0}

        def _progress(track: TrackMetadata) -> None:
            counter["idx"] += 1
            if progress_callback:
                progress_callback(
                    SearchProgress(track=track, index=counter["idx"], total_estimate=max_results)
                )

        return search_tracks(
            genre,
            artist=artist,
            filters=filters,
            order=order,
            max_results=max_results,
            js_runtime=js_runtime,
            remote_components=remote_components,
            chunk_size=chunk_size,
            progress_callback=_progress if progress_callback else None,
        )


class PlaybackService:
    def resolve_stream(
        self,
        *,
        track: TrackMetadata,
        selector: str,
        js_runtime: Optional[str],
        remote_components: List[str],
        prefer_video: bool,
        video_quality: str,
        preferred_format: Optional[str],
        quality_profile: str,
    ) -> StreamingLink:
        links = Streamer(
            format_selector=selector,
            js_runtime=js_runtime,
            remote_components=remote_components,
            prefer_video=prefer_video,
            video_quality=video_quality,
            preferred_format=preferred_format,
            quality_profile=quality_profile,
        ).stream_links([track])
        if not links:
            raise RuntimeError("No stream URL available for the selected track.")
        return links[0]


class DownloadService:
    def download(
        self,
        tracks: Iterable[TrackMetadata],
        *,
        download_dir: Path,
        js_runtime: Optional[str],
        remote_components: List[str],
        quality_profile: str,
    ) -> List[Path]:
        manager = DownloadManager(
            download_dir,
            js_runtime=js_runtime,
            remote_components=remote_components,
            quality_profile=quality_profile,
        )
        return manager.download_tracks(list(tracks))
