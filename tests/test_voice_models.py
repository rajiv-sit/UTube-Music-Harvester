from pathlib import Path

import pytest

from utube.config import load_defaults
from utube.voice import VoiceController


@pytest.fixture(scope="module")
def defaults():
    return load_defaults()


def test_vosk_models_exist(defaults):
    models_dir = defaults.voice_models_dir
    assert models_dir.exists(), f"{models_dir} should exist"
    model_dirs = [child for child in models_dir.iterdir() if child.is_dir()]
    assert model_dirs, "No Vosk models found in the models directory"
    expected = {"vosk-model-small-en-us-0.15", "vosk-model-en-us-0.22", "vosk-model-en-us-0.22-lgraph"}
    available = {child.name for child in model_dirs}
    assert expected.issubset(available), f"Expected models {expected} to exist inside {models_dir}"


def test_voice_controller_builds_for_each_model(defaults):
    pytest.importorskip("vosk")
    pytest.importorskip("sounddevice")
    for model_dir in sorted(defaults.voice_models_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        controller = VoiceController(
            enabled=True,
            engine="vosk_offline",
            language=defaults.voice_language,
            model_path=str(model_dir),
        )
        assert controller.enabled
