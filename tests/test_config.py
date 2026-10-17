from pathlib import Path

import pytest

from app.config import Settings


def test_env_vars_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_MODEL", "some-other-model")
    monkeypatch.setenv("DATABASE_PATH", "/tmp/test.db")

    # _env_file=None so a developer's local .env can't leak into the test.
    s = Settings(_env_file=None)

    assert s.chat_model == "some-other-model"
    assert s.database_path == Path("/tmp/test.db")


def test_api_key_is_optional_at_load_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert Settings(_env_file=None).gemini_api_key == ""
