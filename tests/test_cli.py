import utube.cli as cli


def test_build_filters_from_args() -> None:
    args = cli.parse_args(
        [
            "trance",
            "--min-duration",
            "120",
            "--max-duration",
            "360",
            "--safe-for-work",
            "--keywords",
            "uplifting",
        ]
    )
    filters = cli._build_filters(args)
    assert filters is not None
    assert filters.min_duration == 120
    assert filters.max_duration == 360
    assert filters.safe_for_work
    assert filters.keywords == "uplifting"


def test_build_filters_returns_none_when_defaults() -> None:
    args = cli.parse_args(["ambient"])
    filters = cli._build_filters(args)
    assert filters is None


def test_parse_args_allows_artist_only() -> None:
    args = cli.parse_args(["--artist", "Deadmau5"])
    assert args.artist == "Deadmau5"
    assert args.genre is None


def test_parse_args_includes_js_runtime() -> None:
    args = cli.parse_args(["--artist", "Deadmau5", "--js-runtime", "node"])
    assert args.js_runtime == "node"


def test_parse_args_collector_remote_components() -> None:
    args = cli.parse_args(
        ["ambient", "--remote-components", "ejs:github", "--remote-components", "node:./bin/node"]
    )
    assert args.remote_components == ["ejs:github", "node:./bin/node"]


def test_parse_args_quality_profile_flag() -> None:
    args = cli.parse_args(["trance", "--quality-profile", "medium"])
    assert args.quality_profile == "medium"
