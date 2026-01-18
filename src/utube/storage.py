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
from .quality import (
    DEFAULT_PROFILE_NAME,
    build_audio_selector,
    build_video_audio_selector,
    get_quality_profile,
)

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
    ext: Optional[str] = None
    abr: Optional[float] = None
    height: Optional[int] = None
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    format_note: Optional[str] = None


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
        quality_profile: str = DEFAULT_PROFILE_NAME,
    ) -> None:
        self.base_dir = base_dir.expanduser()
        cleaned_format = audio_format.lstrip(".").lower()
        self.audio_format = cleaned_format
        self.bitrate = bitrate
        self.js_runtime = js_runtime
        self.remote_components = list(remote_components or [])
        self.is_video_output = cleaned_format == "mp4"
        self.quality_profile = get_quality_profile(quality_profile)
        self._audio_selector = build_audio_selector(self.quality_profile)
        self._video_audio_selector = build_video_audio_selector(self.quality_profile)

    def download_tracks(self, tracks: Iterable[TrackMetadata]) -> List[Path]:
        """Download the supplied tracks to `base_dir` and return stored paths."""
        saved = []
        for track in tracks:
            if not track.webpage_url:
                continue
            target = self.base_dir / build_track_filename(
                track, suffix=f".{self.audio_format}"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            self._download(track.webpage_url, target)
            saved.append(target)
        return saved

    def _download(self, url: str, target: Path) -> None:
        """Invoke `yt-dlp` to download and transcode a single track."""
        output_template = str(target.with_suffix(".%(ext)s"))
        format_selector = (
            self._video_audio_selector if self.is_video_output else self._audio_selector
        )
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
        format_selector: Optional[str] = None,
        js_runtime: Optional[str] = None,
        remote_components: Optional[List[str]] = None,
        prefer_video: bool = False,
        video_quality: Optional[str] = None,
        preferred_format: Optional[str] = None,
        quality_profile: str = DEFAULT_PROFILE_NAME,
    ) -> None:
        self.profile = get_quality_profile(quality_profile)
        self.prefer_video = prefer_video
        self.video_quality = (video_quality or "").strip().lower()
        self.preferred_format = preferred_format
        selector = format_selector
        if not selector:
            selector = (
                build_video_audio_selector(self.profile)
                if prefer_video
                else build_audio_selector(self.profile)
            )
        self.format_selector = selector
        self.js_runtime = js_runtime
        self.remote_components = list(remote_components or [])

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
                            ext=stream.get("ext"),
                            abr=stream.get("abr"),
                            height=stream.get("height"),
                            vcodec=stream.get("vcodec"),
                            acodec=stream.get("acodec"),
                            format_note=stream.get("format_note"),
                        )
                    )
        return links

    def _select_format(self, info: dict) -> Optional[dict]:
        formats = [
            candidate for candidate in info.get("formats", []) if candidate.get("url")
        ]
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
                        if candidate.get("vcodec") not in (None, "none")
                        and candidate.get("acodec") not in (None, "none")
                    ]
                    if preferred_video:
                        preferred_video.sort(key=self._video_score, reverse=True)
                        return preferred_video[0]
                for candidate in preferred_candidates:
                    if candidate.get("acodec") != "none":
                        return candidate
                return preferred_candidates[0]

        if self.prefer_video:
            if candidate := self._select_video_candidate(formats):
                return candidate

        return self._select_audio_candidate(formats)

    def _select_video_candidate(self, formats: List[dict]) -> Optional[dict]:
        video_candidates = [
            candidate
            for candidate in formats
            if candidate.get("vcodec") not in (None, "none")
            and candidate.get("acodec") not in (None, "none")
        ]
        if not video_candidates:
            return None
        profile = self._target_video_profile()
        cap = self._video_quality_cap(profile)
        for requirement in profile.video_requirements:
            matches = [
                candidate
                for candidate in video_candidates
                if self._meets_video_requirement(candidate, requirement)
            ]
            if matches:
                filtered = self._apply_quality_cap(matches, cap)
                selected = filtered if filtered else matches
                selected.sort(key=self._video_score, reverse=True)
                return selected[0]

        video_candidates.sort(key=self._video_score, reverse=True)
        if self.video_quality == "low":
            return video_candidates[-1]
        if self.video_quality == "medium":
            return video_candidates[len(video_candidates) // 2]
        return video_candidates[0]

    def _target_video_profile(self):
        if self.video_quality:
            return get_quality_profile(self.video_quality)
        return self.profile

    def _video_quality_cap(self, profile):
        if not self.video_quality:
            return None
        for requirement in profile.video_requirements:
            if requirement.min_height:
                return requirement.min_height
        return None

    def _apply_quality_cap(
        self, candidates: List[dict], cap: Optional[int]
    ) -> List[dict]:
        if not cap:
            return candidates
        filtered: List[dict] = []
        for candidate in candidates:
            height = candidate.get("height")
            if self._within_quality_cap(height, cap):
                filtered.append(candidate)
        return filtered

    def _within_quality_cap(self, height, cap: int) -> bool:
        if height is None:
            return True
        try:
            return int(height) <= cap
        except (TypeError, ValueError):
            return True

    def _select_audio_candidate(self, formats: List[dict]) -> Optional[dict]:
        audio_candidates = [
            candidate
            for candidate in formats
            if candidate.get("acodec") not in (None, "none")
        ]
        if not audio_candidates:
            return None

        for threshold in self.profile.audio_thresholds:
            matches = [
                candidate
                for candidate in audio_candidates
                if (candidate.get("abr") or 0) >= threshold
            ]
            if selected := self._prefer_audio_codecs(matches):
                return selected

        return self._prefer_audio_codecs(audio_candidates)

    def _prefer_audio_codecs(self, candidates: List[dict]) -> Optional[dict]:
        if not candidates:
            return None
        candidates.sort(key=self._audio_score, reverse=True)
        for codec in self.profile.preferred_audio_codecs:
            codec_lower = codec.lower()
            for candidate in candidates:
                if (candidate.get("acodec") or "").lower().startswith(codec_lower):
                    return candidate
        return candidates[0]

    def _meets_video_requirement(
        self, candidate: dict, requirement: "VideoRequirement"
    ) -> bool:
        height = candidate.get("height") or 0
        if height < requirement.min_height:
            return False
        if requirement.min_fps:
            fps = self._flexible_float(candidate.get("fps"))
            if fps < requirement.min_fps:
                return False
        return True

    def _audio_score(self, candidate: dict) -> Tuple[float, float]:
        abr = candidate.get("abr") or 0.0
        tbr = candidate.get("tbr") or 0.0
        return float(abr), float(tbr)

    def _flexible_float(self, value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

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
