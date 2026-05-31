import asyncio
import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from hydrogram import Client, enums, raw, utils
from hydrogram.errors import (
    BadRequest,
    FloodWait,
    Forbidden,
    InternalServerError,
    RPCError,
    Unauthorized,
)

from app.db.models import SearchRun, TelegramAccount
from app.db.session import SessionLocal
from app.services.accounts import (
    list_proxy_fallbacks,
    list_search_accounts,
    proxy_to_hydrogram,
    set_account_status,
    set_proxy_error,
)
from app.services.crypto import decrypt_secret
from app.services.filters import classify_text
from app.services.posts import save_post
from app.services.settings import get_int
from app.services.tags import list_tags

logger = logging.getLogger(__name__)
MAX_FLOOD_WAIT_SECONDS = 900
INTERNAL_SERVER_RETRIES = 3
DEFAULT_RECENT_HOURS = 6
SEARCH_GLOBAL_PARAMS = inspect.signature(raw.functions.messages.SearchGlobal).parameters
SEARCH_POSTS_AVAILABLE = hasattr(raw.functions.channels, "SearchPosts")


@dataclass
class AccountSearchResult:
    found: int = 0
    saved: int = 0
    candidates: int = 0
    rate_limited: bool = False
    proxy_events: list[str] | None = None


class AccountDisabledError(RuntimeError):
    pass


def account_disabled_message(account: TelegramAccount) -> str:
    return (
        f"{account.title}: сессия слетела, аккаунт отключен. "
        "Он больше не участвует в парсинге. Удали его и добавь заново или добавь другой аккаунт."
    )


def build_client(account: TelegramAccount, proxy=None) -> Client:
    return Client(
        name=account.title,
        api_id=account.api_id,
        api_hash=decrypt_secret(account.api_hash),
        session_string=decrypt_secret(account.session_string),
        in_memory=True,
        proxy=proxy_to_hydrogram(proxy if proxy is not None else account.proxy),
        device_model="SM-G998B",
        system_version="Android 14",
        app_version="10.14.5",
        lang_code="ru",
    )


def mark_account(
    account_id: int,
    status: str,
    error: str | None = None,
    is_active: bool | None = None,
    flood_wait_until: datetime | None = None,
) -> None:
    with SessionLocal() as db:
        set_account_status(
            db,
            account_id,
            status,
            last_error=error,
            is_active=is_active,
            flood_wait_until=flood_wait_until,
        )
        account = db.get(TelegramAccount, account_id)
        if account and status == "active":
            account.last_used_at = datetime.utcnow()
        db.commit()


async def wait_flood(exc: FloodWait, tag: str) -> bool:
    wait_seconds = int(exc.value)
    logger.warning("FloodWait on tag %s: %s seconds", tag, wait_seconds)
    if wait_seconds > MAX_FLOOD_WAIT_SECONDS:
        return False
    await asyncio.sleep(wait_seconds)
    return True


async def iter_global_messages(client: Client, tag: str, limit: int):
    attempts = 0
    while True:
        try:
            async for message in client.search_global(tag, limit=limit):
                yield message
            return
        except InternalServerError:
            attempts += 1
            if attempts >= INTERNAL_SERVER_RETRIES:
                raise
            await asyncio.sleep(5 * attempts)


def utc_timestamp(value: datetime | None) -> int:
    if value is None:
        return 0
    return int(normalize_datetime(value).timestamp())


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def message_in_window(message, min_date: datetime | None, max_date: datetime | None) -> bool:
    if not message.date:
        return True
    published_at = normalize_datetime(message.date)
    if min_date and published_at < normalize_datetime(min_date):
        return False
    if max_date and published_at > normalize_datetime(max_date):
        return False
    return True


def get_recent_hours(db) -> int:
    recent_hours = get_int(db, "search_recent_hours", DEFAULT_RECENT_HOURS)
    if recent_hours > 0:
        return recent_hours
    recent_days = get_int(db, "search_recent_days", 1)
    return max(recent_days, 1) * 24


def search_global_request(
    tag: str,
    page_limit: int,
    min_date: datetime | None,
    max_date: datetime | None,
    offset_rate: int,
    offset_peer,
    offset_id: int,
):
    kwargs = {
        "q": tag,
        "filter": enums.MessagesFilter.EMPTY.value(),
        "min_date": utc_timestamp(min_date),
        "max_date": utc_timestamp(max_date),
        "offset_rate": offset_rate,
        "offset_peer": offset_peer,
        "offset_id": offset_id,
        "limit": page_limit,
    }
    if "broadcasts_only" in SEARCH_GLOBAL_PARAMS:
        kwargs["broadcasts_only"] = True
    return raw.functions.messages.SearchGlobal(**kwargs)


def search_posts_request(
    tag: str,
    page_limit: int,
    offset_rate: int,
    offset_peer,
    offset_id: int,
):
    return raw.functions.channels.SearchPosts(
        hashtag=tag.lstrip("#"),
        offset_rate=offset_rate,
        offset_peer=offset_peer,
        offset_id=offset_id,
        limit=page_limit,
    )


def recent_search_request(
    tag: str,
    page_limit: int,
    min_date: datetime | None,
    max_date: datetime | None,
    offset_rate: int,
    offset_peer,
    offset_id: int,
):
    if SEARCH_POSTS_AVAILABLE:
        return search_posts_request(
            tag,
            page_limit,
            offset_rate,
            offset_peer,
            offset_id,
        )
    return search_global_request(
        tag,
        page_limit,
        min_date,
        max_date,
        offset_rate,
        offset_peer,
        offset_id,
    )


async def iter_recent_global_messages(
    client: Client,
    tag: str,
    limit: int,
    recent_hours: int,
):
    total = max(limit, 1)
    page_limit = min(100, total)
    current = 0
    now = datetime.utcnow()
    min_date = now - timedelta(hours=max(recent_hours, 1))
    offset_rate = 0
    offset_peer = raw.types.InputPeerEmpty()
    offset_id = 0

    while current < total:
        try:
            current_page_limit = min(page_limit, total - current)
            response = await invoke_recent_search(
                client,
                tag,
                current_page_limit,
                min_date,
                now,
                offset_rate,
                offset_peer,
                offset_id,
            )
            messages = await utils.parse_messages(client, response, replies=0)
        except InternalServerError:
            raise

        if not messages:
            return

        last = messages[-1]
        next_rate = getattr(response, "next_rate", None)
        offset_rate = (
            next_rate
            if next_rate is not None
            else int(last.date.timestamp())
        )
        if last.chat:
            offset_peer = await client.resolve_peer(last.chat.id)
        else:
            offset_peer = raw.types.InputPeerEmpty()
        offset_id = last.id

        for message in messages:
            if not message_in_window(message, min_date, now):
                continue
            yield message
            current += 1
            if current >= total:
                return
        if last.date and normalize_datetime(last.date) < min_date:
            return


async def invoke_recent_search(
    client: Client,
    tag: str,
    page_limit: int,
    min_date: datetime | None,
    max_date: datetime | None,
    offset_rate: int,
    offset_peer,
    offset_id: int,
):
    try:
        return await client.invoke(
            recent_search_request(
                tag,
                page_limit,
                min_date,
                max_date,
                offset_rate,
                offset_peer,
                offset_id,
            ),
            sleep_threshold=60,
        )
    except BadRequest:
        if not SEARCH_POSTS_AVAILABLE:
            raise
        logger.warning("channels.SearchPosts failed for %s, fallback to SearchGlobal", tag)
        return await client.invoke(
            search_global_request(
                tag,
                page_limit,
                min_date,
                max_date,
                offset_rate,
                offset_peer,
                offset_id,
            ),
            sleep_threshold=60,
        )


async def search_with_account(
    account: TelegramAccount,
    tags: list,
    limit: int,
    pause: int,
    run_id: int,
) -> AccountSearchResult:
    logger.info("Search run %s uses account %s", run_id, account.title)

    with SessionLocal() as db:
        account_db = db.get(TelegramAccount, account.id)
        proxy_fallbacks = list_proxy_fallbacks(db, account_db)

    last_network_error = None
    proxy_events = []
    for proxy in proxy_fallbacks:
        try:
            result = await search_with_account_proxy(
                account,
                proxy,
                tags,
                limit,
                pause,
                run_id,
            )
            result.proxy_events = proxy_events
            return result
        except Unauthorized as exc:
            message = account_disabled_message(account)
            mark_account(account.id, "unauthorized", str(exc), False)
            logger.exception("Unauthorized Telegram account %s", account.title)
            raise AccountDisabledError(message) from exc
        except (OSError, TimeoutError, ConnectionError) as exc:
            last_network_error = exc
            proxy_name = proxy.title if proxy else "без прокси"
            logger.warning("Network error with %s via %s: %s", account.title, proxy_name, exc)
            proxy_events.append(f"{proxy_name}: {exc}")
            if proxy:
                with SessionLocal() as db:
                    set_proxy_error(db, proxy.id, str(exc))
                    db.commit()
            continue
    raise ConnectionError(f"Не сработал ни один прокси и прямое подключение: {last_network_error}")


async def search_with_account_proxy(
    account: TelegramAccount,
    proxy,
    tags: list,
    limit: int,
    pause: int,
    run_id: int,
) -> AccountSearchResult:
    result = AccountSearchResult()
    client = build_client(account, proxy)
    proxy_name = proxy.title if proxy else "без прокси"
    logger.info("Search run %s uses account %s via %s", run_id, account.title, proxy_name)

    async with client:
        with SessionLocal() as db:
            recent_hours = get_recent_hours(db)
            from app.db.models import BlacklistedChannel, Source
            blacklisted_ids = {row[0] for row in db.query(BlacklistedChannel.channel_id).all()}
            blacklisted_ids.update(
                row[0]
                for row in db.query(Source.channel_id)
                .filter(Source.is_blacklisted.is_(True))
                .all()
            )
        for tag in tags:
            logger.info("Searching Telegram global posts by tag %s", tag.tag)
            try:
                async for message in iter_recent_global_messages(
                    client,
                    tag.tag,
                    limit,
                    recent_hours,
                ):
                    result.found += 1
                    text = (getattr(message.text, "html", message.text) if message.text else None) or (getattr(message.caption, "html", message.caption) if message.caption else None) or ""
                    if not message.chat:
                        continue

                    status = None
                    reason = None
                    priority = None
                    label = None

                    if not text.strip():
                        status = "filtered_out"
                        reason = "empty_message"
                    elif message.chat.id in blacklisted_ids:
                        status = "filtered_out"
                        reason = "blacklisted_source"
                    else:
                        with SessionLocal() as db:
                            filter_result = classify_text(db, text)
                            status = filter_result.status
                            reason = filter_result.reason
                            priority = filter_result.priority
                            label = filter_result.label

                    with SessionLocal() as db:
                        post, created = save_post(
                            db,
                            channel_id=message.chat.id,
                            channel_name=message.chat.title,
                            username=message.chat.username,
                            message_id=message.id,
                            published_at=message.date,
                            hashtag=tag.tag,
                            text=text,
                            status=status,
                            reason=reason,
                            priority=priority,
                            label=label,
                            account_id=account.id,
                        )
                        if created:
                            result.saved += 1
                            if post and post.status == "candidate":
                                result.candidates += 1
                                logger.info("Candidate post saved: %s", post.id)
                        db.commit()
            except FloodWait as exc:
                if await wait_flood(exc, tag.tag):
                    continue
                until = datetime.utcnow() + timedelta(seconds=int(exc.value))
                mark_account(account.id, "rate_limited", str(exc), True, until)
                result.rate_limited = True
                return result
            except Unauthorized as exc:
                mark_account(account.id, "unauthorized", str(exc), False)
                raise
            except Forbidden as exc:
                logger.warning("Telegram forbidden on tag %s: %s", tag.tag, exc)
                continue
            except BadRequest as exc:
                logger.warning("Telegram bad request on tag %s: %s", tag.tag, exc)
                continue
            except InternalServerError as exc:
                logger.warning("Telegram server error on tag %s: %s", tag.tag, exc)
                continue
            except (ConnectionError, TimeoutError, OSError) as exc:
                logger.warning("Temporary network error on tag %s: %s", tag.tag, exc)
                continue
            except RPCError as exc:
                mark_account(account.id, "rpc_error", str(exc), True)
                raise RuntimeError(f"Telegram RPC error: {exc}") from exc
            await asyncio.sleep(pause)

    mark_account(account.id, "active")
    return result


async def run_global_search() -> dict:
    with SessionLocal() as db:
        accounts = list_search_accounts(db)
        if not accounts:
            raise RuntimeError("Нет активного TG аккаунта")

        tags = list_tags(db, active_only=True)
        limit = get_int(db, "search_limit_per_tag", 20)
        pause = get_int(db, "search_pause_seconds", 3)
        run = SearchRun(tags_count=len(tags))
        db.add(run)
        db.commit()
        run_id = run.id

    found = 0
    saved = 0
    candidates = 0
    errors = []
    account_events = []
    rate_limited = 0
    used_account_id = None

    for account in accounts:
        try:
            result = await search_with_account(account, tags, limit, pause, run_id)
            found += result.found
            saved += result.saved
            candidates += result.candidates
            used_account_id = account.id
            if result.rate_limited:
                rate_limited += 1
                account_events.append(f"{account.title}: rate_limited")
                continue
            for event in result.proxy_events or []:
                account_events.append(f"{account.title}: proxy fallback {event}")
            break
        except AccountDisabledError as exc:
            errors.append(str(exc))
            account_events.append(str(exc))
            continue
        except (OSError, TimeoutError, ConnectionError) as exc:
            mark_account(account.id, "network_error", str(exc), True)
            logger.exception("Network error with account %s", account.title)
            errors.append(f"{account.title}: network {exc}")
            account_events.append(f"{account.title}: network_error")
            continue
        except Exception as exc:
            logger.exception("Search failed with account %s", account.title)
            errors.append(f"{account.title}: {exc}")
            account_events.append(f"{account.title}: {exc}")
            continue

    status = "done"
    error = None
    if not used_account_id and rate_limited:
        status = "rate_limited"
        error = "Все доступные аккаунты получили FloodWait"
    elif not used_account_id:
        status = "error"
        error = "; ".join(errors) or "Нет доступного аккаунта для поиска"

    with SessionLocal() as db:
        run = db.get(SearchRun, run_id)
        if run:
            run.account_id = used_account_id
            run.status = status
            run.finished_at = datetime.utcnow()
            run.found_count = found
            run.saved_count = saved
            run.candidate_count = candidates
            run.error = error
            run.last_error = error
        db.commit()

    if error:
        raise RuntimeError(error)
    logger.info(
        "Global search run finished: found=%s saved=%s candidates=%s",
        found,
        saved,
        candidates,
    )
    return {
        "run_id": run_id,
        "found": found,
        "saved": saved,
        "candidates": candidates,
        "account_events": account_events,
    }
