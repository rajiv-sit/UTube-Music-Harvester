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


def test_voice_play_all_command(parser: VoiceParser) -> None:
    command = parser.parse("Play all songs")
    assert command.command_type == VoiceCommandType.PLAY_ALL


def test_voice_play_by_index(parser: VoiceParser) -> None:
    command = parser.parse("Play track number three")
    assert command.command_type == VoiceCommandType.PLAY_SPECIFIC
    assert command.index == 2


def test_voice_play_by_title(parser: VoiceParser) -> None:
    command = parser.parse("Play Riverflows in You")
    assert command.command_type == VoiceCommandType.PLAY_SPECIFIC
    assert command.query == "riverflows in you"


def test_voice_control_command(parser: VoiceParser) -> None:
    command = parser.parse("Pause")
    assert command.command_type == VoiceCommandType.CONTROL
    assert command.action == "pause"


def test_voice_unrecognized_command(parser: VoiceParser) -> None:
    with pytest.raises(ValueError):
        parser.parse("Turn up the volume")
