import pytest
from datetime import datetime, timedelta
from app.db.models import Proxy, TelegramAccount
from app.services.accounts import (
    add_account,
    add_proxy,
    get_active_account,
    list_proxy_fallbacks,
    list_search_accounts,
    proxy_to_hydrogram,
    set_account_status,
    set_proxy_error,
    check_proxy_connection,
)
from app.db.session import SessionLocal

@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session

def test_proxy_to_hydrogram():
    proxy = Proxy(proxy_type="socks5", host="127.0.0.1", port=1080, is_active=True)
    assert proxy_to_hydrogram(proxy) == {"scheme": "socks5", "hostname": "127.0.0.1", "port": 1080}

    proxy.username = "user"
    proxy.password = "enc:pass"
    import unittest.mock
    with unittest.mock.patch("app.services.accounts.decrypt_secret", return_value="pass"):
        assert proxy_to_hydrogram(proxy) == {"scheme": "socks5", "hostname": "127.0.0.1", "port": 1080, "username": "user", "password": "pass"}

    proxy.is_active = False
    assert proxy_to_hydrogram(proxy) is None
    assert proxy_to_hydrogram(None) is None

def test_add_account_and_proxy(db):
    proxy = add_proxy(db, "Test Proxy", "socks5", "localhost", 1080, None, None)
    assert proxy.id is not None

    account = add_account(db, "Test Account", 123, "hash", "phone", "session")
    assert account.id is not None
    account.proxy_id = proxy.id
    db.commit()

def test_list_proxy_fallbacks(db):
    proxy1 = add_proxy(db, "Proxy 1", "socks5", "localhost", 1080, None, None)
    proxy2 = add_proxy(db, "Proxy 2", "socks5", "localhost", 1081, None, None)
    account = add_account(db, "Acc1", 123, "h", "p", "s")
    account.proxy = proxy1

    fallbacks = list_proxy_fallbacks(db, account)
    assert fallbacks[0] == proxy1
    assert proxy2 in fallbacks
    assert fallbacks[-1] is None

def test_set_account_status(db):
    account = add_account(db, "StatusAcc", 123, "h", "p", "s")
    set_account_status(db, account.id, "banned", "error", False, datetime.utcnow())
    db.commit()

    acc = db.get(TelegramAccount, account.id)
    assert acc.status == "banned"
    assert acc.last_error == "error"
    assert acc.is_active is False
    assert acc.flood_wait_until is not None

def test_set_proxy_error(db):
    proxy = add_proxy(db, "ErrProxy", "socks5", "localhost", 1080, None, None)
    set_proxy_error(db, proxy.id, "timeout")
    db.commit()

    p = db.get(Proxy, proxy.id)
    assert p.last_error == "timeout"
    assert p.last_checked_at is not None

def test_get_active_account(db):
    db.query(TelegramAccount).delete()
    db.commit()

    account = add_account(db, "ActiveAcc", 123, "h", "p", "s")
    assert get_active_account(db).id == account.id

    account.flood_wait_until = datetime.utcnow() + timedelta(hours=1)
    db.commit()
    assert get_active_account(db) is None

    assert len(list_search_accounts(db)) == 0

@pytest.mark.asyncio
async def test_check_proxy_connection():
    proxy = Proxy(proxy_type="socks5", host="127.0.0.1", port=1)
    ok, error = await check_proxy_connection(proxy, timeout=0.1)
    assert ok is False
    assert error is not None
