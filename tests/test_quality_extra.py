from utube.quality import QualityProfile, VideoRequirement


def test_quality_selectors_deduplicate():
    profile = QualityProfile(
        name="custom",
        audio_thresholds=(128, 128),
        video_requirements=(VideoRequirement(720), VideoRequirement(720)),
    )
    assert profile.audio_selectors.count("bestaudio[abr>=128]") == 1
    assert profile.video_selectors.count("bestvideo[height>=720]") == 1


def test_quality_profile_none_falls_back():
    from utube.quality import get_quality_profile

    assert get_quality_profile(None).name == "high"


def test_build_video_audio_selector_fallback():
    from utube.quality import build_video_audio_selector

    class DummyProfile:
        audio_selectors = ()
        video_selectors = ()

    selector = build_video_audio_selector(DummyProfile())
    assert "bestvideo+bestaudio" in selector
