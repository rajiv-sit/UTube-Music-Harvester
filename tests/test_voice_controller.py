from pathlib import Path

import pytest

import utube.voice as voice


def test_offline_engine_requires_dependency(monkeypatch):
    monkeypatch.setattr(voice, "sr", None)
    with pytest.raises(RuntimeError):
        voice.OfflineSpeechEngine()


def test_vosk_engine_requires_model(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(voice, "vosk", object())
    monkeypatch.setattr(voice, "sd", object())
    with pytest.raises(RuntimeError):
        voice.VoskSpeechEngine(model_path=str(tmp_path / "missing"))


def test_voice_controller_listen_once(monkeypatch):
    class FakeEngine(voice.SpeechEngine):
        def recognize_once(
            self, *, language: str, timeout: float, phrase_time_limit: float
        ) -> str:
            return "Play all"

    controller = voice.VoiceController.__new__(voice.VoiceController)
    controller.enabled = True
    controller.language = "en-US"
    controller.engine = FakeEngine()
    controller.parser = voice.VoiceParser()
    command, phrase = controller.listen_once()
    assert phrase == "Play all"
    assert command.command_type == voice.VoiceCommandType.PLAY_ALL


def test_voice_controller_errors():
    controller = voice.VoiceController.__new__(voice.VoiceController)
    controller.enabled = False
    controller.engine = None
    with pytest.raises(RuntimeError):
        controller._ensure_ready()

    controller.enabled = True
    controller.engine = None
    with pytest.raises(RuntimeError):
        controller._ensure_ready()


def test_voice_controller_build_engine_invalid():
    controller = voice.VoiceController.__new__(voice.VoiceController)
    with pytest.raises(ValueError):
        controller._build_engine("invalid", None)


def test_parse_track_number_variants():
    parser = voice.VoiceParser()
    assert parser._parse_track_number("3rd") == 3
    assert parser._parse_track_number("7") == 7
    with pytest.raises(ValueError):
        parser._parse_track_number("zero-zero")


def test_voice_parser_empty_phrase():
    parser = voice.VoiceParser()
    with pytest.raises(ValueError):
        parser.parse("   ")


def test_voice_controller_build_engine_variants(monkeypatch, tmp_path):
    controller = voice.VoiceController.__new__(voice.VoiceController)
    monkeypatch.setattr(
        voice,
        "sr",
        type(
            "SR",
            (),
            {"Recognizer": lambda *_: object(), "Microphone": lambda *_: object()},
        ),
    )
    engine = controller._build_engine("offline_default", None)
    assert isinstance(engine, voice.OfflineSpeechEngine)

    monkeypatch.setattr(voice, "vosk", type("V", (), {"Model": lambda _p: object()}))
    monkeypatch.setattr(voice, "sd", object())
    model_path = tmp_path / "model"
    model_path.mkdir()
    engine = controller._build_engine("vosk_offline", str(model_path))
    assert isinstance(engine, voice.VoskSpeechEngine)


def test_vosk_engine_flow(monkeypatch, tmp_path):
    class FakeModel:
        def __init__(self, _path):
            pass

    class FakeRecognizer:
        def __init__(self, _model, _sr):
            pass

        def AcceptWaveform(self, _data):
            return True

        def FinalResult(self):
            return '{"text": "play all"}'

    class FakeAudio:
        def tobytes(self):
            return b"\x00"

    class FakeSD:
        default = type("D", (), {"device": (0, None)})

        @staticmethod
        def query_devices(index=None):
            if index is None:
                return [{"max_input_channels": 1, "default_samplerate": 16000}]
            return {"max_input_channels": 1, "default_samplerate": 16000}

        @staticmethod
        def rec(*args, **kwargs):
            return FakeAudio()

    monkeypatch.setattr(
        voice,
        "vosk",
        type("V", (), {"Model": FakeModel, "KaldiRecognizer": FakeRecognizer}),
    )
    monkeypatch.setattr(voice, "sd", FakeSD)
    model_path = tmp_path / "model"
    model_path.mkdir()
    engine = voice.VoskSpeechEngine(model_path=str(model_path))
    phrase = engine.recognize_once(language="en-US", timeout=1, phrase_time_limit=1)
    assert phrase == "play all"


def test_offline_engine_recognize_errors(monkeypatch):
    class FakeRecognizer:
        def adjust_for_ambient_noise(self, source, duration=0.5):
            pass

        def listen(self, source, timeout=1, phrase_time_limit=1):
            return object()

        def recognize_sphinx(self, audio, language="en-US"):
            raise FakeSR.UnknownValueError()

    class FakeMic:
        def __init__(self, sample_rate=None):
            pass

        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeSR:
        Recognizer = FakeRecognizer
        Microphone = FakeMic

        class UnknownValueError(Exception):
            pass

        class RequestError(Exception):
            pass

    monkeypatch.setattr(voice, "sr", FakeSR)
    engine = voice.OfflineSpeechEngine()
    with pytest.raises(RuntimeError):
        engine.recognize_once(language="en-US", timeout=1, phrase_time_limit=1)


def test_vosk_choose_input_device_errors(monkeypatch, tmp_path):
    class FakeModel:
        def __init__(self, _path):
            pass

    class FakeSD:
        default = type("D", (), {"device": (None, None)})

        @staticmethod
        def query_devices(index=None):
            return []

    monkeypatch.setattr(voice, "vosk", type("V", (), {"Model": FakeModel}))
    monkeypatch.setattr(voice, "sd", FakeSD)
    model_path = tmp_path / "model"
    model_path.mkdir()
    engine = voice.VoskSpeechEngine(model_path=str(model_path))
    with pytest.raises(RuntimeError):
        engine._choose_input_device()
