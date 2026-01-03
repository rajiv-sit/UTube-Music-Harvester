import importlib
from pathlib import Path

import utube.config as config_module
from utube.quality import DEFAULT_PROFILE_NAME


def _reload_config():
    importlib.reload(config_module)
    return config_module


def test_load_defaults_respects_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UTUBE_DOWNLOAD_DIR", str(tmp_path / "music"))
    monkeypatch.setenv("UTUBE_MEDIA_FORMAT", "mp4")
    monkeypatch.setenv("UTUBE_AUDIO_FORMAT", "opus")
    monkeypatch.setenv("UTUBE_STREAM_FORMAT", "highestaudio")
    monkeypatch.setenv("UTUBE_QUALITY_PROFILE", "data_saving")
    monkeypatch.setenv("UTUBE_SKIP_DOTENV", "1")

    reloaded = _reload_config()
    defaults = reloaded.load_defaults()
    assert defaults.download_dir == tmp_path / "music"
    assert defaults.audio_format == "mp4"
    assert defaults.stream_format == "highestaudio"
    assert defaults.quality_profile == "data_saving"


def test_load_defaults_respects_legacy_audio_env(monkeypatch) -> None:
    monkeypatch.delenv("UTUBE_MEDIA_FORMAT", raising=False)
    monkeypatch.setenv("UTUBE_AUDIO_FORMAT", "aac")
    monkeypatch.setenv("UTUBE_SKIP_DOTENV", "1")

    reloaded = _reload_config()
    defaults = reloaded.load_defaults()
    assert defaults.audio_format == "aac"
    assert defaults.quality_profile == DEFAULT_PROFILE_NAME


def test_load_defaults_falls_back_to_defaults(monkeypatch) -> None:
    monkeypatch.delenv("UTUBE_DOWNLOAD_DIR", raising=False)
    monkeypatch.delenv("UTUBE_AUDIO_FORMAT", raising=False)
    monkeypatch.delenv("UTUBE_MEDIA_FORMAT", raising=False)
    monkeypatch.delenv("UTUBE_STREAM_FORMAT", raising=False)
    monkeypatch.delenv("UTUBE_REMOTE_COMPONENTS", raising=False)
    monkeypatch.setenv("UTUBE_SKIP_DOTENV", "1")

    reloaded = _reload_config()
    defaults = reloaded.load_defaults()
    assert defaults.audio_format == "mp3"
    assert defaults.stream_format == "bestaudio/best"
    assert isinstance(defaults.download_dir, Path)
    assert defaults.remote_components == []
    assert defaults.quality_profile == DEFAULT_PROFILE_NAME
