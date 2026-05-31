import os
import pytest

from app.config import Config, _parse_admin_ids, load_config

def test_parse_admin_ids():
    assert _parse_admin_ids("123, 456,789") == {123, 456, 789}
    assert _parse_admin_ids("") == set()
    assert _parse_admin_ids("  , ") == set()

def test_load_config_valid(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test_token:123")
    monkeypatch.setenv("ADMIN_IDS", "1,2")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("LOG_DIR", "/tmp/logs")

    cfg = load_config()
    assert cfg.bot_token == "test_token:123"
    assert cfg.admin_ids == {1, 2}
    assert cfg.database_url == "sqlite:///:memory:"
    assert cfg.log_dir == "/tmp/logs"

def test_load_config_defaults(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test_token:123")
    monkeypatch.setenv("ADMIN_IDS", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("LOG_DIR", raising=False)

    cfg = load_config()
    assert cfg.database_url == "sqlite:///data/app.db"
    assert cfg.log_dir == "logs"

def test_load_config_missing_bot_token(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "")
    monkeypatch.setenv("ADMIN_IDS", "1")
    with pytest.raises(RuntimeError, match="BOT_TOKEN is required"):
        load_config()

def test_load_config_missing_admin_ids(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "token")
    monkeypatch.setenv("ADMIN_IDS", "")
    with pytest.raises(RuntimeError, match="ADMIN_IDS is required"):
        load_config()
