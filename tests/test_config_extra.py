from pathlib import Path

import utube.config as config


def test_env_helpers(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("UTUBE_TEST_LIST", "a, b, ,c")
    assert config._env_list("UTUBE_TEST_LIST") == ["a", "b", "c"]

    monkeypatch.setenv("UTUBE_TEST_BOOL", "yes")
    assert config._env_bool("UTUBE_TEST_BOOL") is True
    monkeypatch.setenv("UTUBE_TEST_BOOL", "0")
    assert config._env_bool("UTUBE_TEST_BOOL") is False

    monkeypatch.setenv("UTUBE_TEST_PATH", "relative")
    path = config._env_path("UTUBE_TEST_PATH", tmp_path)
    assert path.is_absolute()


def test_guess_user_root_prefers_cwd(monkeypatch, tmp_path: Path):
    (tmp_path / ".env").write_text("x")
    monkeypatch.setattr(config.Path, "cwd", lambda: tmp_path)
    assert config._guess_user_root() == tmp_path


def test_guess_user_root_falls_back(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config.Path, "cwd", lambda: tmp_path)
    assert config._guess_user_root() == config.PACKAGE_ROOT


def test_detect_js_runtime(monkeypatch):
    monkeypatch.setattr(config.shutil, "which", lambda name: "/bin/node" if name == "node" else None)
    assert config._detect_js_runtime() == "node"
    monkeypatch.setattr(config.shutil, "which", lambda name: None)
    assert config._detect_js_runtime() is None


def test_default_vosk_models_dir_prefers_user(monkeypatch, tmp_path: Path):
    user_root = tmp_path / "root"
    models_dir = user_root / "vosk-models"
    models_dir.mkdir(parents=True)
    monkeypatch.setattr(config, "USER_ROOT", user_root)
    assert config._default_vosk_models_dir() == models_dir


def test_default_vosk_models_dir_falls_back(monkeypatch, tmp_path: Path):
    user_root = tmp_path / "root"
    user_root.mkdir()
    monkeypatch.setattr(config, "USER_ROOT", user_root)
    assert config._default_vosk_models_dir() == config.PACKAGE_ROOT / "vosk-models"
