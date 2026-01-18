"""Shared quality profiles for audio/video selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class VideoRequirement:
    """Minimum requirements for a video stream."""

    min_height: int
    min_fps: Optional[int] = None


@dataclass(frozen=True)
class QualityProfile:
    """Defines bitrate and resolution targets that drive yt-dlp selectors."""

    name: str
    audio_thresholds: Tuple[int, ...]
    video_requirements: Tuple[VideoRequirement, ...]
    preferred_audio_codecs: Tuple[str, ...] = ("opus", "aac")

    @property
    def audio_selectors(self) -> Tuple[str, ...]:
        selectors: List[str] = []
        seen: set[str] = set()
        for threshold in self.audio_thresholds:
            selector = f"bestaudio[abr>={threshold}]"
            if selector not in seen:
                selectors.append(selector)
                seen.add(selector)
        for fallback in ("bestaudio", "bestaudio/best"):
            if fallback not in seen:
                selectors.append(fallback)
                seen.add(fallback)
        return tuple(selectors)

    @property
    def video_selectors(self) -> Tuple[str, ...]:
        selectors: List[str] = []
        seen: set[str] = set()
        for requirement in self.video_requirements:
            selector = "bestvideo"
            for segment in (
                f"height>={requirement.min_height}" if requirement.min_height else None,
                f"fps>={requirement.min_fps}" if requirement.min_fps else None,
            ):
                if segment:
                    selector = f"{selector}[{segment}]"
            if selector not in seen:
                selectors.append(selector)
                seen.add(selector)
        for fallback in ("bestvideo", "bestvideo+bestaudio/best"):
            if fallback not in seen:
                selectors.append(fallback)
                seen.add(fallback)
        return tuple(selectors)


DEFAULT_PROFILE_NAME = "high"


QUALITY_PROFILE_MAP: Mapping[str, QualityProfile] = {
    "high": QualityProfile(
        name="high",
        audio_thresholds=(256, 160, 128),
        video_requirements=(
            VideoRequirement(1080, 60),
            VideoRequirement(1080),
            VideoRequirement(720, 60),
            VideoRequirement(720),
        ),
    ),
    "medium": QualityProfile(
        name="medium",
        audio_thresholds=(160, 128),
        video_requirements=(
            VideoRequirement(720),
            VideoRequirement(480, 60),
            VideoRequirement(480),
        ),
    ),
    "data_saving": QualityProfile(
        name="data_saving",
        audio_thresholds=(128, 96),
        video_requirements=(
            VideoRequirement(480),
            VideoRequirement(360),
        ),
    ),
}


QUALITY_PROFILES = tuple(QUALITY_PROFILE_MAP.keys())


def get_quality_profile(name: Optional[str]) -> QualityProfile:
    if not name:
        name = DEFAULT_PROFILE_NAME
    return QUALITY_PROFILE_MAP.get(
        name.lower(), QUALITY_PROFILE_MAP[DEFAULT_PROFILE_NAME]
    )


def build_audio_selector(profile: QualityProfile) -> str:
    return "/".join(profile.audio_selectors)


def build_video_audio_selector(profile: QualityProfile) -> str:
    combos: List[str] = []
    seen: set[str] = set()
    for video_selector in profile.video_selectors:
        for audio_selector in profile.audio_selectors:
            combo = f"{video_selector}+{audio_selector}"
            if combo not in seen:
                combos.append(combo)
                seen.add(combo)
    for fallback in ("bestvideo+bestaudio", "bestvideo+bestaudio/best"):
        if fallback not in seen:
            combos.append(fallback)
            seen.add(fallback)
    return "/".join(combos)
