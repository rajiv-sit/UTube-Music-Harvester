import importlib
from pathlib import Path

import utube.config as config_module


def _reload_config():
    importlib.reload(config_module)
    return config_module


def test_load_defaults_respects_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UTUBE_DOWNLOAD_DIR", str(tmp_path / "music"))
    monkeypatch.setenv("UTUBE_AUDIO_FORMAT", "opus")
    monkeypatch.setenv("UTUBE_STREAM_FORMAT", "highestaudio")

    reloaded = _reload_config()
    defaults = reloaded.load_defaults()
    assert defaults.download_dir == tmp_path / "music"
    assert defaults.audio_format == "opus"
    assert defaults.stream_format == "highestaudio"


def test_load_defaults_falls_back_to_defaults(monkeypatch) -> None:
    monkeypatch.delenv("UTUBE_DOWNLOAD_DIR", raising=False)
    monkeypatch.delenv("UTUBE_AUDIO_FORMAT", raising=False)
    monkeypatch.delenv("UTUBE_STREAM_FORMAT", raising=False)

    reloaded = _reload_config()
    defaults = reloaded.load_defaults()
    assert defaults.audio_format == "mp3"
    assert defaults.stream_format == "bestaudio/best"
    assert isinstance(defaults.download_dir, Path)
    assert defaults.remote_components == []
