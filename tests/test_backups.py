import pytest
import sqlite3
import zipfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch
from app.services.backups import sqlite_path, cleanup_backups, make_sqlite_backup, send_database_backup
from app.config import Config

def test_sqlite_path():
    assert sqlite_path("sqlite:////tmp/db.sqlite") == Path("/tmp/db.sqlite")
    assert sqlite_path("sqlite:///data/db.sqlite") == Path("data/db.sqlite")
    assert sqlite_path("postgresql://user:pass@host/db") is None

def test_cleanup_backups(tmp_path):
    f1 = tmp_path / "db_backup_old.zip"
    f2 = tmp_path / "db_backup_new.zip"
    f1.write_text("a")
    f2.write_text("b")

    import time
    old_time = time.time() - 86400 * 10
    os.utime(f1, (old_time, old_time))

    cleanup_backups(tmp_path, 7)

    assert not f1.exists()
    assert f2.exists()

def test_make_sqlite_backup(tmp_path):
    db_file = tmp_path / "app.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.close()

    config = Config(bot_token="", admin_ids=set(), database_url=f"sqlite:///{db_file}", log_dir=str(tmp_path))

    zip_path = make_sqlite_backup(config)
    assert zip_path.exists()
    assert zip_path.suffix == ".zip"

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert names[0].endswith(".sqlite3")

@pytest.mark.asyncio
async def test_send_database_backup(tmp_path):
    db_file = tmp_path / "app.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE settings (id INTEGER, key TEXT, value TEXT, value_type TEXT, is_secret INTEGER, description TEXT, created_at DATETIME, updated_at DATETIME)")
    conn.close()

    config = Config(bot_token="", admin_ids={1}, database_url=f"sqlite:///{db_file}", log_dir=str(tmp_path))

    bot_mock = AsyncMock()
    with patch("app.services.backups.telegram_call", new_callable=AsyncMock) as call_mock:
        from app.db.session import SessionLocal
        with patch("app.services.backups.SessionLocal") as session_mock:
            # We don't want to actually connect to the memory DB from conftest, but use the real one or mock get_int
            pass

        with patch("app.services.backups.get_int", return_value=7):
            await send_database_backup(bot_mock, config)

            assert call_mock.call_count == 1
            await call_mock.call_args[0][1]()
            bot_mock.send_document.assert_awaited_once()
