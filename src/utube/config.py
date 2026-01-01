"""Configuration helpers that read runtime defaults from the environment."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

if os.getenv("UTUBE_SKIP_DOTENV") != "1":
    load_dotenv()


def _env_path(env_var: str, fallback: Path) -> Path:
    value = os.getenv(env_var)
    return Path(value).expanduser() if value else fallback


def _env_list(env_var: str) -> List[str]:
    value = os.getenv(env_var)
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _detect_js_runtime() -> Optional[str]:
    for candidate in ("node", "deno"):
        if shutil.which(candidate):
            return candidate
    return None


@dataclass(frozen=True)
class CliDefaults:
    download_dir: Path
    audio_format: str
    stream_format: str
    js_runtime: Optional[str]
    remote_components: List[str]
    video_quality: str


def load_defaults() -> CliDefaults:
    env_runtime = os.getenv("UTUBE_JS_RUNTIME")
    return CliDefaults(
        download_dir=_env_path("UTUBE_DOWNLOAD_DIR", Path.cwd() / "downloads"),
        audio_format=os.getenv("UTUBE_MEDIA_FORMAT", os.getenv("UTUBE_AUDIO_FORMAT", "mp3")),
        stream_format=os.getenv("UTUBE_STREAM_FORMAT", "bestaudio/best"),
        js_runtime=env_runtime or _detect_js_runtime(),
        remote_components=_env_list("UTUBE_REMOTE_COMPONENTS"),
        video_quality=os.getenv("UTUBE_VIDEO_QUALITY", "high"),
    )
