"""Settings come from .env when the app runs locally, but never inside tests."""
from matcher import settings


def test_env_file_is_read_without_overriding(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("MATCHER_TEST_ONLY_A=from-file\nMATCHER_TEST_ONLY_B=from-file\n")
    monkeypatch.delenv("MATCHER_TEST_ONLY_A", raising=False)
    monkeypatch.setenv("MATCHER_TEST_ONLY_B", "already-set")
    monkeypatch.setenv("MATCHER_DOTENV", "1")
    settings.load_env_file(env)
    import os
    assert os.environ["MATCHER_TEST_ONLY_A"] == "from-file" and os.environ["MATCHER_TEST_ONLY_B"] == "already-set"
    monkeypatch.delenv("MATCHER_TEST_ONLY_A")


def test_tests_never_read_env_files(tmp_path, monkeypatch):
    import os
    env = tmp_path / ".env"
    env.write_text("SMTP_HOST=smtp.real.example\n")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert os.environ["MATCHER_DOTENV"] == "0"                  # conftest sets this before anything is imported
    settings.load_env_file(env)
    assert "SMTP_HOST" not in os.environ and settings.smtp() is None
