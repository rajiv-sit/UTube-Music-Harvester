"""Download and stream helpers used by the harvester orchestration layer."""

from __future__ import annotations

import re
from dataclasses import dataclass
import os
import shutil
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import yt_dlp

from .extractor import TrackMetadata

_VALID_FILENAME = re.compile(r"[^A-Za-z0-9 _\-.]")


def sanitize_filename(value: str) -> str:
    cleaned = _VALID_FILENAME.sub("", value).strip(" .-_")
    return cleaned or "track"


def build_track_filename(track: TrackMetadata, *, suffix: str = ".mp3") -> str:
    base = sanitize_filename(track.title or track.video_id)
    extension = suffix if suffix.startswith(".") else f".{suffix}"
    return f"{base}_{track.video_id}{extension}"


@dataclass(frozen=True)
class StreamingLink:
    """Stream metadata returned for each track."""

    track: TrackMetadata
    stream_url: str
    format_id: str


class DownloadManager:
    """Handles persistent storage for downloaded tracks."""

    def __init__(
        self,
        base_dir: Path,
        *,
        audio_format: str = "mp3",
        bitrate: str = "192",
        js_runtime: Optional[str] = None,
        remote_components: Optional[List[str]] = None,
    ) -> None:
        self.base_dir = base_dir.expanduser()
        cleaned_format = audio_format.lstrip(".").lower()
        self.audio_format = cleaned_format
        self.bitrate = bitrate
        self.js_runtime = js_runtime
        self.remote_components = list(remote_components or [])
        self.is_video_output = cleaned_format == "mp4"

    def download_tracks(self, tracks: Iterable[TrackMetadata]) -> List[Path]:
        """Download the supplied tracks to `base_dir` and return stored paths."""
        saved = []
        for track in tracks:
            if not track.webpage_url:
                continue
            target = self.base_dir / build_track_filename(track, suffix=f".{self.audio_format}")
            target.parent.mkdir(parents=True, exist_ok=True)
            self._download(track.webpage_url, target)
            saved.append(target)
        return saved

    def _download(self, url: str, target: Path) -> None:
        """Invoke `yt-dlp` to download and transcode a single track."""
        output_template = str(target.with_suffix(".%(ext)s"))
        format_selector = "bestvideo+bestaudio/best" if self.is_video_output else "bestaudio/best"
        ydl_opts = {
            "format": format_selector,
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
        }
        postprocessors = []
        if not self.is_video_output:
            postprocessors.append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": self.audio_format,
                    "preferredquality": self.bitrate,
                }
            )
        postprocessors.append({"key": "FFmpegMetadata"})
        if postprocessors:
            ydl_opts["postprocessors"] = postprocessors
        if self.is_video_output:
            ydl_opts["merge_output_format"] = self.audio_format
        if self.js_runtime:
            entry = _js_runtime_entry(self.js_runtime)
            ydl_opts["js_runtime"] = entry["name"]
            entry_config = {"path": entry["path"]} if entry.get("path") else {}
            ydl_opts["js_runtimes"] = {entry["name"]: entry_config}
        if self.remote_components:
            ydl_opts["remote_components"] = self.remote_components
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])


class Streamer:
    """Collect stream URLs for a batch of tracks."""

    def __init__(
        self,
        *,
        format_selector: str = "bestaudio/best",
        js_runtime: Optional[str] = None,
        remote_components: Optional[List[str]] = None,
        prefer_video: bool = False,
        video_quality: str = "high",
        preferred_format: Optional[str] = None,
    ) -> None:
        self.format_selector = format_selector
        self.js_runtime = js_runtime
        self.remote_components = list(remote_components or [])
        self.prefer_video = prefer_video
        self.video_quality = video_quality
        self.preferred_format = preferred_format

    def stream_links(self, tracks: Iterable[TrackMetadata]) -> List[StreamingLink]:
        links = []
        opts = {"quiet": True, "noplaylist": True, "format": self.format_selector}
        if self.js_runtime:
            entry = _js_runtime_entry(self.js_runtime)
            opts["js_runtime"] = entry["name"]
            entry_config = {"path": entry["path"]} if entry.get("path") else {}
            opts["js_runtimes"] = {entry["name"]: entry_config}
        if self.remote_components:
            opts["remote_components"] = self.remote_components
        with yt_dlp.YoutubeDL(opts) as ydl:
            for track in tracks:
                if not track.webpage_url:
                    continue
                info = ydl.extract_info(track.webpage_url, download=False)
                stream = self._select_format(info)
                if stream:
                    links.append(
                        StreamingLink(
                            track=track,
                            stream_url=stream.get("url"),
                            format_id=stream.get("format_id", "unknown"),
                        )
                    )
        return links

    def _select_format(self, info: dict) -> Optional[dict]:
        formats = [candidate for candidate in info.get("formats", []) if candidate.get("url")]
        if not formats:
            return None

        if self.preferred_format:
            preferred_candidates = [
                candidate
                for candidate in formats
                if (candidate.get("ext") or "").lower() == self.preferred_format
            ]
            if preferred_candidates:
                if self.preferred_format == "mp4":
                    preferred_video = [
                        candidate
                        for candidate in preferred_candidates
                        if candidate.get("vcodec") not in (None, "none") and candidate.get("acodec") not in (None, "none")
                    ]
                    if preferred_video:
                        preferred_video.sort(key=self._video_score, reverse=True)
                        return preferred_video[0]
                for candidate in preferred_candidates:
                    if candidate.get("acodec") != "none":
                        return candidate
                return preferred_candidates[0]

        if self.prefer_video:
            video_candidates = [
                candidate
                for candidate in formats
                if candidate.get("vcodec") not in (None, "none") and candidate.get("acodec") not in (None, "none")
            ]
            if video_candidates:
                video_candidates.sort(key=self._video_score, reverse=True)
                if self.video_quality == "low":
                    return video_candidates[-1]
                if self.video_quality == "medium":
                    return video_candidates[len(video_candidates) // 2]
                return video_candidates[0]

        for candidate in formats:
            if candidate.get("acodec") != "none":
                return candidate
        return None

    def _video_score(self, candidate: dict) -> Tuple[int, float]:
        height = candidate.get("height") or 0
        tbr = candidate.get("tbr") or 0.0
        return height, float(tbr)

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
