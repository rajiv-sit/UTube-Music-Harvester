from utube.quality import build_audio_selector, build_video_audio_selector, get_quality_profile


def test_build_audio_selector_prioritizes_high_bitrate() -> None:
    profile = get_quality_profile("high")
    selector = build_audio_selector(profile)
    assert "bestaudio[abr>=256]" in selector
    assert selector.endswith("bestaudio/best")


def test_build_video_audio_selector_combines_expectations() -> None:
    profile = get_quality_profile("high")
    selector = build_video_audio_selector(profile)
    assert selector.startswith("bestvideo[height>=1080][fps>=60]+bestaudio[abr>=256]")


def test_get_quality_profile_falls_back_to_default() -> None:
    profile = get_quality_profile("unsupported")
    assert profile.name == "high"
