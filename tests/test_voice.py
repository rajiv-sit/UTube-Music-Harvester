"""Unit tests for the voice command parser."""

import pytest

from utube.voice import VoiceCommandType, VoiceParser


@pytest.fixture
def parser() -> VoiceParser:
    return VoiceParser()


def test_voice_search_command(parser: VoiceParser) -> None:
    command = parser.parse("Search for ambient study")
    assert command.command_type == VoiceCommandType.SEARCH
    assert command.query == "ambient study"


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("Search for trance", "trance"),
        ("Search for rock songs", "rock songs"),
        ("Find jazz music", "jazz music"),
        ("Play some ambient", "ambient"),
        ("Look up Beatles songs", "beatles songs"),
        ("Search YouTube for classical music", "classical music"),
    ],
)
def test_voice_search_variations(parser: VoiceParser, phrase: str, expected: str) -> None:
    command = parser.parse(phrase)
    assert command.command_type == VoiceCommandType.SEARCH
    assert command.query == expected


@pytest.mark.parametrize(
    "phrase",
    ["Play all songs", "Play all", "Play everything", "Start playing all", "Play the whole list"],
)
def test_voice_play_all_variations(parser: VoiceParser, phrase: str) -> None:
    command = parser.parse(phrase)
    assert command.command_type == VoiceCommandType.PLAY_ALL


@pytest.mark.parametrize(
    ("phrase", "expected_index"),
    [
        ("Play track number one", 0),
        ("Play track number five", 4),
        ("Play the third song", 2),
        ("Play song number four", 3),
    ],
)
def test_voice_play_by_index(parser: VoiceParser, phrase: str, expected_index: int) -> None:
    command = parser.parse(phrase)
    assert command.command_type == VoiceCommandType.PLAY_SPECIFIC
    assert command.index == expected_index


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("Play Shape of You", "shape of you"),
        ("Play the song Shape of You", "shape of you"),
        ("Play Blinding Lights", "blinding lights"),
        ("Play the track Rolling in the Deep", "rolling in the deep"),
    ],
)
def test_voice_play_by_title(parser: VoiceParser, phrase: str, expected: str) -> None:
    command = parser.parse(phrase)
    assert command.command_type == VoiceCommandType.PLAY_SPECIFIC
    assert command.query == expected
@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("Pause", "pause"),
        ("Resume", "play"),
        ("Continue", "play"),
        ("Next song", "next"),
        ("Previous song", "previous"),
        ("Stop", "stop"),
    ],
)
def test_voice_control_variations(parser: VoiceParser, phrase: str, expected: str) -> None:
    command = parser.parse(phrase)
    assert command.command_type == VoiceCommandType.CONTROL
    assert command.action == expected


def test_voice_unrecognized_command(parser: VoiceParser) -> None:
    with pytest.raises(ValueError):
        parser.parse("Turn up the volume")
