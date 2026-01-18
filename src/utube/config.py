"""Configuration helpers that read runtime defaults from the environment."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

from .quality import DEFAULT_PROFILE_NAME

PACKAGE_ROOT = Path(__file__).resolve().parents[1]

PROXY_ENV_VARS = (
    "ALL_PROXY",
    "all_proxy",
    "FTP_PROXY",
    "ftp_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "NO_PROXY",
    "no_proxy",
)


def _clear_proxy_env_vars() -> None:
    # Make sure yt-dlp/requests never pick up a stale proxy that cannot be reached.
    for var in PROXY_ENV_VARS:
        os.environ.pop(var, None)


_clear_proxy_env_vars()


def _guess_user_root() -> Path:
    cwd = Path.cwd().resolve()
    if (cwd / ".env").exists() or (cwd / "vosk-models").exists():
        return cwd
    return PACKAGE_ROOT


USER_ROOT = _guess_user_root()

if os.getenv("UTUBE_SKIP_DOTENV") != "1":
    load_dotenv(dotenv_path=USER_ROOT / ".env")


def _env_path(env_var: str, fallback: Path) -> Path:
    value = os.getenv(env_var)
    if not value:
        return fallback
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate
    return (USER_ROOT / candidate).resolve()


def _env_list(env_var: str) -> List[str]:
    value = os.getenv(env_var)
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(env_var: str, default: bool = False) -> bool:
    value = os.getenv(env_var)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


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
    quality_profile: str
    voice_enabled: bool
    voice_engine: str
    voice_models_dir: Path
    voice_model_name: str
    voice_model_path: Path
    voice_language: str


def _default_vosk_models_dir() -> Path:
    candidate = USER_ROOT / "vosk-models"
    if candidate.exists():
        return candidate
    return PACKAGE_ROOT / "vosk-models"


def load_defaults() -> CliDefaults:
    env_runtime = os.getenv("UTUBE_JS_RUNTIME")
    models_dir = _env_path("UTUBE_VOICE_MODELS_DIR", _default_vosk_models_dir())
    model_name = os.getenv("UTUBE_VOICE_MODEL_NAME", "vosk-model-small-en-us-0.15")
    voice_model_path = _env_path("UTUBE_VOICE_MODEL_PATH", models_dir / model_name)
    return CliDefaults(
        download_dir=_env_path("UTUBE_DOWNLOAD_DIR", Path.cwd() / "downloads"),
        audio_format=os.getenv(
            "UTUBE_MEDIA_FORMAT", os.getenv("UTUBE_AUDIO_FORMAT", "mp3")
        ),
        stream_format=os.getenv("UTUBE_STREAM_FORMAT", "bestaudio/best"),
        js_runtime=env_runtime or _detect_js_runtime(),
        remote_components=_env_list("UTUBE_REMOTE_COMPONENTS"),
        video_quality=os.getenv("UTUBE_VIDEO_QUALITY", "high"),
        quality_profile=os.getenv("UTUBE_QUALITY_PROFILE", DEFAULT_PROFILE_NAME),
        voice_enabled=_env_bool("UTUBE_VOICE_ENABLED", False),
        voice_engine=os.getenv("UTUBE_VOICE_ENGINE", "vosk_offline"),
        voice_models_dir=models_dir,
        voice_model_name=model_name,
        voice_model_path=voice_model_path,
        voice_language=os.getenv("UTUBE_VOICE_LANGUAGE", "en-US"),
    )
