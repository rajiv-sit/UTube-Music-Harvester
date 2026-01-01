"""Utilities for genre-driven YouTube queries using ``yt_dlp``."""

from __future__ import annotations

import datetime
import os
import shutil
from dataclasses import dataclass
from typing import Iterable, List, Optional

import yt_dlp
from yt_dlp.utils import DownloadError

SEARCH_PREFIXES = {
    "relevance": "ytsearch",
    "date": "ytsearchdate",
    "longest": "ytsearchlong",
    "shortest": "ytsearchshort",
}


@dataclass(frozen=True)
class SearchFilters:
    """User-facing constraints for filtering search results."""

    min_duration: Optional[int] = None
    max_duration: Optional[int] = None
    min_views: Optional[int] = None
    max_views: Optional[int] = None
    upload_after: Optional[datetime.date] = None
    upload_before: Optional[datetime.date] = None
    require_non_live: bool = True
    safe_for_work: bool = False
    keywords: Optional[str] = None


@dataclass(frozen=True)
class TrackMetadata:
    """Canonical metadata emitted by ``search_tracks``."""

    video_id: str
    title: str
    uploader: str
    duration_seconds: Optional[int]
    view_count: Optional[int]
    upload_date: Optional[str]
    webpage_url: str
    channel_url: Optional[str]
    thumbnail: Optional[str]
    description: Optional[str]
    tags: List[str]


def search_tracks(
    genre: Optional[str] = None,
    *,
    artist: Optional[str] = None,
    filters: Optional[SearchFilters] = None,
    max_results: int = 100,
    order: str = "relevance",
    js_runtime: Optional[str] = None,
    remote_components: Optional[List[str]] = None,
) -> List[TrackMetadata]:
    """
    Search YouTube for the requested genre and return metadata entries.

    Args:
        genre: High-level genre (e.g., "trance", "ambient study").
        artist: Optional artist name to bias results (e.g., "Daft Punk").
        filters: Optional post-search filters (duration, views, date ranges).
        max_results: Number of results to request from ``yt_dlp``.
        order: Search ordering hint (supported: ``relevance``, ``date``, ``longest``, ``shortest``).

    Raises:
        ValueError: If ``genre`` is empty.
        RuntimeError: When ``yt_dlp`` cannot complete the search.
    """
    terms: List[str] = []
    if genre and genre.strip():
        terms.append(genre.strip())
    if artist and artist.strip():
        terms.append(artist.strip())
    if filters and filters.keywords:
        terms.append(filters.keywords.strip())
    merged_terms = " ".join(terms).strip()

    if not merged_terms:
        raise ValueError("genre or artist must be provided")
    prefix = SEARCH_PREFIXES.get(order.lower(), "ytsearch")
    query = f"{prefix}{max_results}:{merged_terms}"

    ydl_opts = {
        "default_search": prefix,
        "noplaylist": True,
        "skip_download": True,
        "quiet": True,
        "cachedir": False,
    }
    if js_runtime:
        entry = _js_runtime_entry(js_runtime)
        ydl_opts["js_runtime"] = entry["name"]
        entry_config = {"path": entry["path"]} if entry.get("path") else {}
        ydl_opts["js_runtimes"] = {entry["name"]: entry_config}
    if remote_components:
        ydl_opts["remote_components"] = remote_components

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            raw_result = ydl.extract_info(query, download=False)
    except DownloadError as exc:
        raise RuntimeError("YouTube search failed") from exc

    entries = _unwrap_entries(raw_result)
    if filters:
        entries = [entry for entry in entries if _matches_filters(entry, filters)]

    return [_entry_to_metadata(entry) for entry in entries]


def _unwrap_entries(raw_result: dict) -> Iterable[dict]:
    """Normalize the search payload into a list of dictionaries."""
    if not raw_result:
        return []
    entries = raw_result.get("entries") or []
    return [entry for entry in entries if isinstance(entry, dict)]


def _matches_filters(entry: dict, filters: SearchFilters) -> bool:
    duration = entry.get("duration")
    if filters.min_duration is not None and (duration is None or duration < filters.min_duration):
        return False
    if filters.max_duration is not None and duration is not None and duration > filters.max_duration:
        return False

    views = entry.get("view_count")
    if filters.min_views is not None and (views is None or views < filters.min_views):
        return False
    if filters.max_views is not None and views is not None and views > filters.max_views:
        return False

    upload_date = entry.get("upload_date")
    if upload_date:
        upload_date_value = int(upload_date)
        if filters.upload_after and upload_date_value < _to_ymd(filters.upload_after):
            return False
        if filters.upload_before and upload_date_value > _to_ymd(filters.upload_before):
            return False

    if filters.require_non_live and entry.get("is_live"):
        return False

    if filters.safe_for_work and entry.get("age_limit", 0) > 0:
        # avoid flagged or mature content when a clean feed is requested.
        return False

    return True


def _entry_to_metadata(entry: dict) -> TrackMetadata:
    return TrackMetadata(
        video_id=entry.get("id", ""),
        title=entry.get("title", ""),
        uploader=entry.get("uploader") or entry.get("channel") or "unknown",
        duration_seconds=entry.get("duration"),
        view_count=entry.get("view_count"),
        upload_date=entry.get("upload_date"),
        webpage_url=entry.get("webpage_url") or entry.get("url") or "",
        channel_url=entry.get("uploader_url"),
        thumbnail=_select_thumbnail(entry.get("thumbnails")),
        description=entry.get("description"),
        tags=list(entry.get("tags") or []),
    )


def _select_thumbnail(thumbnails: Optional[List[dict]]) -> Optional[str]:
    if not thumbnails:
        return None
    for candidate in thumbnails:
        if candidate.get("url"):
            return candidate["url"]
    return thumbnails[-1].get("url")


def _to_ymd(value: datetime.date) -> int:
    return int(value.strftime("%Y%m%d"))


def _js_runtime_entry(runtime: str) -> dict:
    name = os.path.splitext(os.path.basename(runtime))[0]
    entry = {"name": name}
    if os.path.isabs(runtime):
        entry["path"] = runtime
    else:
        lookup = shutil.which(runtime)
        if lookup:
            entry["path"] = lookup
    return entry
