import asyncio
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Proxy, TelegramAccount
from app.services.crypto import decrypt_secret, encrypt_secret


def proxy_to_hydrogram(proxy: Proxy | None) -> dict | None:
    if not proxy or not proxy.is_active:
        return None
    data = {"scheme": proxy.proxy_type, "hostname": proxy.host, "port": proxy.port}
    if proxy.username:
        data["username"] = proxy.username
    if proxy.password:
        data["password"] = decrypt_secret(proxy.password)
    return data


def get_active_account(db: Session) -> TelegramAccount | None:
    now = datetime.utcnow()
    return (
        db.query(TelegramAccount)
        .filter(TelegramAccount.is_active.is_(True))
        .filter(
            (TelegramAccount.flood_wait_until.is_(None))
            | (TelegramAccount.flood_wait_until <= now)
        )
        .order_by(TelegramAccount.last_used_at.asc().nullsfirst())
        .first()
    )


def list_search_accounts(db: Session) -> list[TelegramAccount]:
    now = datetime.utcnow()
    from sqlalchemy.orm import joinedload
    return (
        db.query(TelegramAccount)
        .options(joinedload(TelegramAccount.proxy))
        .filter(TelegramAccount.is_active.is_(True))
        .filter(
            (TelegramAccount.flood_wait_until.is_(None))
            | (TelegramAccount.flood_wait_until <= now)
        )
        .order_by(TelegramAccount.last_used_at.asc().nullsfirst())
        .all()
    )


def list_proxy_fallbacks(db: Session, account: TelegramAccount) -> list[Proxy | None]:
    proxies: list[Proxy | None] = []
    if account.proxy and account.proxy.is_active:
        proxies.append(account.proxy)
    other_proxies = (
        db.query(Proxy)
        .filter(Proxy.is_active.is_(True))
        .order_by(Proxy.id.asc())
        .all()
    )
    for proxy in other_proxies:
        if proxy not in proxies:
            proxies.append(proxy)
    proxies.append(None)
    return proxies


def set_account_status(
    db: Session,
    account_id: int,
    status: str,
    last_error: str | None = None,
    is_active: bool | None = None,
    flood_wait_until: datetime | None = None,
) -> None:
    account = db.get(TelegramAccount, account_id)
    if not account:
        return
    account.status = status
    account.last_error = last_error
    if last_error:
        account.last_error_at = datetime.utcnow()
    account.last_checked_at = datetime.utcnow()
    account.flood_wait_until = flood_wait_until
    if is_active is not None:
        account.is_active = is_active


def set_proxy_error(db: Session, proxy_id: int, error: str | None) -> None:
    proxy = db.get(Proxy, proxy_id)
    if not proxy:
        return
    proxy.last_checked_at = datetime.utcnow()
    proxy.last_error = error


def add_account(
    db: Session,
    title: str,
    api_id: int,
    api_hash: str,
    phone: str,
    session_string: str,
) -> TelegramAccount:
    account = TelegramAccount(
        title=title,
        api_id=api_id,
        api_hash=encrypt_secret(api_hash),
        phone=phone,
        session_string=encrypt_secret(session_string),
        is_active=True,
    )
    db.add(account)
    db.flush()
    return account


def add_proxy(
    db: Session,
    title: str,
    proxy_type: str,
    host: str,
    port: int,
    username: str | None,
    password: str | None,
) -> Proxy:
    proxy = Proxy(
        title=title,
        proxy_type=proxy_type,
        host=host,
        port=port,
        username=username,
        password=encrypt_secret(password),
        is_active=True,
    )
    db.add(proxy)
    db.flush()
    return proxy


async def check_proxy_connection(proxy: Proxy, timeout: float = 8.0) -> tuple[bool, str | None]:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(proxy.host, proxy.port),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        reader.feed_eof()
        return True, None
    except Exception as exc:
        return False, str(exc)
