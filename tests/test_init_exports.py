import utube


def test_init_exports() -> None:
    for name in utube.__all__:
        assert hasattr(utube, name)
