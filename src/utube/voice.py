"""Voice control helpers that parse commands and wrap speech engines."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    import speech_recognition as sr
except ImportError:  # pragma: no cover - voice is optional
    sr = None

try:
    import sounddevice as sd
    import vosk
except ImportError:  # pragma: no cover - optional offline engine
    sd = None
    vosk = None


class VoiceCommandType(Enum):
    SEARCH = auto()
    PLAY_ALL = auto()
    PLAY_SPECIFIC = auto()
    CONTROL = auto()


@dataclass(frozen=True)
class VoiceCommand:
    command_type: VoiceCommandType
    query: Optional[str] = None
    index: Optional[int] = None
    action: Optional[str] = None


class VoiceParser:
    _control_map: Dict[str, str] = {
        "pause": "pause",
        "resume": "play",
        "continue": "play",
        "playback": "play",
        "stop": "stop",
        "next": "next",
        "next song": "next",
        "previous": "previous",
        "previous song": "previous",
    }
    _play_all_triggers = (
        "play all",
        "play everything",
        "start playing all",
        "play the whole list",
    )
    _search_prefixes = (
        "search youtube for ",
        "search for ",
        "find ",
        "play some ",
        "look up ",
    )
    _title_prefixes = (
        "play the song ",
        "play song ",
        "play the track ",
        "play track ",
        "play ",
    )
    _number_words: Dict[str, int] = {
        "zero": 0,
        "one": 1,
        "first": 1,
        "two": 2,
        "second": 2,
        "three": 3,
        "third": 3,
        "four": 4,
        "fourth": 4,
        "five": 5,
        "fifth": 5,
        "six": 6,
        "sixth": 6,
        "seven": 7,
        "seventh": 7,
        "eight": 8,
        "eighth": 8,
        "nine": 9,
        "ninth": 9,
        "ten": 10,
        "tenth": 10,
        "eleven": 11,
        "eleventh": 11,
        "twelve": 12,
        "twelfth": 12,
        "thirteen": 13,
        "thirteenth": 13,
        "fourteen": 14,
        "fourteenth": 14,
        "fifteen": 15,
        "fifteenth": 15,
        "sixteen": 16,
        "sixteenth": 16,
        "seventeen": 17,
        "seventeenth": 17,
        "eighteen": 18,
        "eighteenth": 18,
        "nineteen": 19,
        "nineteenth": 19,
        "twenty": 20,
        "twentieth": 20,
    }

    def parse(self, phrase: str) -> VoiceCommand:
        normalized = phrase.lower().strip()
        if not normalized:
            raise ValueError("empty voice phrase")

        if any(trigger in normalized for trigger in self._play_all_triggers):
            return VoiceCommand(command_type=VoiceCommandType.PLAY_ALL)

        for prefix in self._search_prefixes:
            if normalized.startswith(prefix):
                query = normalized[len(prefix) :].strip()
                if not query:
                    raise ValueError("no query supplied")
                return VoiceCommand(command_type=VoiceCommandType.SEARCH, query=query)

        number_match = re.match(
            r"play(?:\s+the)?\s+(?:track|song)?\s*(?:number\s*)?(\d+|[a-z-]+)",
            normalized,
        )
        if number_match:
            raw = number_match.group(1)
            try:
                number = self._parse_track_number(raw)
            except ValueError:
                pass
            else:
                index = number - 1
                if index < 0:
                    raise ValueError("invalid track number")
                return VoiceCommand(
                    command_type=VoiceCommandType.PLAY_SPECIFIC, index=index
                )

        for prefix in self._title_prefixes:
            if normalized.startswith(prefix):
                remainder = normalized[len(prefix) :].strip()
                if remainder:
                    return VoiceCommand(
                        command_type=VoiceCommandType.PLAY_SPECIFIC, query=remainder
                    )

        if normalized in self._control_map:
            return VoiceCommand(
                command_type=VoiceCommandType.CONTROL,
                action=self._control_map[normalized],
            )

        raise ValueError(f"unrecognized voice command: {phrase}")

    def _parse_track_number(self, token: str) -> int:
        cleaned = token.lower().strip()
        if cleaned.isdigit():
            return int(cleaned)
        if cleaned.endswith(("st", "nd", "rd", "th")) and cleaned[:-2].isdigit():
            return int(cleaned[:-2])
        if cleaned in self._number_words:
            return self._number_words[cleaned]
        raise ValueError("invalid track number")


class SpeechEngine:
    def recognize_once(
        self, *, language: str, timeout: float, phrase_time_limit: float
    ) -> str:
        raise NotImplementedError


class OfflineSpeechEngine(SpeechEngine):
    def __init__(self, sample_rate: int = 16000) -> None:
        if sr is None:
            raise RuntimeError("speech_recognition dependency not installed")
        self._recognizer = sr.Recognizer()
        self._sample_rate = sample_rate

    def recognize_once(
        self, *, language: str, timeout: float, phrase_time_limit: float
    ) -> str:
        with sr.Microphone(sample_rate=self._sample_rate) as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = self._recognizer.listen(
                source, timeout=timeout, phrase_time_limit=phrase_time_limit
            )
        try:
            return self._recognizer.recognize_sphinx(audio, language=language)
        except sr.UnknownValueError as exc:
            raise RuntimeError("could not understand speech") from exc
        except sr.RequestError as exc:
            raise RuntimeError("speech engine error") from exc


class VoskSpeechEngine(SpeechEngine):
    def __init__(self, model_path: str, sample_rate: Optional[int] = None) -> None:
        if vosk is None or sd is None:
            raise RuntimeError("Vosk dependencies are not installed")
        if not Path(model_path).exists():
            raise RuntimeError(f"Vosk model not found at {model_path}")
        self._model = vosk.Model(str(Path(model_path).resolve()))
        self._preferred_sample_rate = sample_rate
        self._resolved_device: Optional[int] = None
        self._resolved_sample_rate: Optional[int] = None

    def recognize_once(
        self, *, language: str, timeout: float, phrase_time_limit: float
    ) -> str:
        device, samplerate = self._resolve_audio_device()
        duration = max(0.1, phrase_time_limit)
        frames = int(samplerate * duration)
        try:
            audio = sd.rec(
                frames,
                samplerate=samplerate,
                channels=1,
                dtype="int16",
                device=device,
                blocking=True,
            )
        except Exception as exc:
            raise RuntimeError(f"unable to record audio: {exc}") from exc
        recognizer = vosk.KaldiRecognizer(self._model, samplerate)
        recognizer.AcceptWaveform(audio.tobytes())
        result = json.loads(recognizer.FinalResult())
        text = (result.get("text") or "").strip()
        if not text:
            raise RuntimeError("could not understand speech")
        return text

    def _resolve_audio_device(self) -> Tuple[int, int]:
        if self._resolved_device is not None and self._resolved_sample_rate is not None:
            return self._resolved_device, self._resolved_sample_rate
        try:
            device_index = self._choose_input_device()
            info = sd.query_devices(device_index)
        except Exception as exc:
            raise RuntimeError("unable to access an audio input device") from exc
        if info.get("max_input_channels", 0) < 1:
            raise RuntimeError("selected audio device has no input channels")
        default_samplerate = info.get("default_samplerate") or 16000
        samplerate = int(self._preferred_sample_rate or default_samplerate)
        self._resolved_device = device_index
        self._resolved_sample_rate = samplerate
        return device_index, samplerate

    def _choose_input_device(self) -> int:
        try:
            default_device = sd.default.device
        except Exception:
            default_device = None
        candidate = None
        if isinstance(default_device, (list, tuple)) and default_device:
            first = default_device[0]
            if first is not None and first >= 0:
                candidate = first
        if candidate is None:
            for index, info in enumerate(sd.query_devices()):
                if info.get("max_input_channels", 0) > 0:
                    candidate = index
                    break
        if candidate is None:
            raise RuntimeError("no input device is available")
        return candidate


class VoiceController:
    def __init__(
        self,
        *,
        enabled: bool,
        engine: str,
        language: str,
        model_path: Optional[str] = None,
    ) -> None:
        self.enabled = enabled
        self.language = language
        self.engine = self._build_engine(engine, model_path) if enabled else None
        self.parser = VoiceParser()

    def _build_engine(self, name: str, model_path: Optional[str]) -> SpeechEngine:
        if name == "offline_default":
            return OfflineSpeechEngine()
        if name == "vosk_offline":
            if not model_path:
                raise RuntimeError(
                    "UTUBE_VOICE_MODEL_PATH is required for the Vosk engine"
                )
            return VoskSpeechEngine(model_path=model_path)
        raise ValueError(f"unsupported voice engine: {name}")

    def _ensure_ready(self) -> None:
        if not self.enabled:
            raise RuntimeError("voice control is disabled")
        if self.engine is None:
            raise RuntimeError("voice engine not available")

    def listen_once(
        self, *, timeout: float = 5.0, phrase_time_limit: float = 5.0
    ) -> Tuple[VoiceCommand, str]:
        self._ensure_ready()
        phrase = self.engine.recognize_once(
            language=self.language, timeout=timeout, phrase_time_limit=phrase_time_limit
        )
        command = self.parser.parse(phrase)
        return command, phrase
