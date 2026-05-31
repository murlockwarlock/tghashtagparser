import logging
import re
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from hydrogram import Client
from hydrogram.errors import (
    FloodWait,
    PasswordHashInvalid,
    PhoneCodeExpired,
    PhoneCodeInvalid,
    RPCError,
    SessionPasswordNeeded,
)

from app.bot.guards import admin_callback, admin_message
from app.bot.keyboards import back, kb
from app.bot.states import AddAccount, AddProxy, DelAccount
from app.db.models import Proxy, TelegramAccount
from app.db.session import SessionLocal
from app.services.accounts import add_account, add_proxy, check_proxy_connection
from app.services.crypto import decrypt_secret

logger = logging.getLogger(__name__)
router = Router()
active_clients: dict[int, Client] = {}


def normalize_login_code(value: str) -> str:
    return re.sub(r"\D", "", value)


async def close_active_client(user_id: int) -> None:
    client = active_clients.pop(user_id, None)
    if client and client.is_connected:
        await client.disconnect()


def accounts_kb():
    return kb([
        [("Добавить аккаунт", "acc:add"), ("Удалить аккаунт", "acc:del_start")],
        [("Назад", "menu:main")],
    ])


def proxies_kb():
    return kb([[("Добавить прокси", "proxy:add")], [("Назад", "menu:main")]])


def accounts_menu_text(db) -> str:
    accounts = db.query(TelegramAccount).order_by(TelegramAccount.id.asc()).all()
    lines = ["<b>TG аккаунты</b>", ""]
    for acc in accounts:
        if acc.is_active and acc.status == "active":
            icon = "✅"
        elif acc.is_active and acc.status == "rate_limited":
            icon = "🟡"
        else:
            icon = "🔴"
        lines.append(
            f"{icon} #{acc.id} <code>{acc.title}</code> {acc.phone}\n"
            f"   Статус: <code>{acc.status}</code>"
        )
        if acc.last_error:
            lines.append(f"   Ошибка: <code>{acc.last_error}</code>")
    return "\n".join(lines) if accounts else "<b>TG аккаунты</b>\n\nПока нет аккаунтов"

@router.callback_query(F.data == "menu:accounts")
async def accounts_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        text = accounts_menu_text(db)
        await callback.message.edit_text(text, reply_markup=accounts_kb())
    await callback.answer()


@router.callback_query(F.data == "acc:add")
async def acc_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddAccount.title)
    await callback.message.edit_text(
        "Введи имя сессии.\n\n"
        "Это просто короткое имя аккаунта внутри бота. Например: <code>main_acc</code>.",
        reply_markup=back("menu:accounts"),
    )
    await callback.answer()


@router.message(AddAccount.title)
async def acc_title(message: Message, state: FSMContext) -> None:
    try:
        await message.delete()
    except Exception:
        pass
    if (message.text or "").startswith("/"):
        await state.clear()
        return
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(AddAccount.api_id)

    with SessionLocal() as db:
        has_accounts = db.query(TelegramAccount).first() is not None

    extra = "\n\nЕсли хочешь использовать ключи от предыдущего аккаунта, отправь <code>-</code>." if has_accounts else ""
    await message.answer(
        f"Введи API_ID числом.\n\n"
        f"Взять можно тут: <code>my.telegram.org</code>, раздел <code>API development tools</code>.{extra}",
        reply_markup=back("menu:accounts"),
    )


@router.message(AddAccount.api_id)
async def acc_api_id(message: Message, state: FSMContext) -> None:
    try:
        await message.delete()
    except Exception:
        pass
    text = (message.text or "").strip()
    if text == "-":
        with SessionLocal() as db:
            last_acc = db.query(TelegramAccount).order_by(TelegramAccount.id.desc()).first()
            if not last_acc:
                await message.answer("Нет предыдущих аккаунтов. Введи API_ID числом.", reply_markup=back("menu:accounts"))
                return
            await state.update_data(api_id=last_acc.api_id, api_hash=decrypt_secret(last_acc.api_hash))
            await state.set_state(AddAccount.phone)
            await message.answer(
                "Ключи скопированы.\n\nВведи телефон в формате <code>+79990000000</code>.\n\n"
                "Код придет в Telegram на этот аккаунт, не в SMS.",
                reply_markup=back("menu:accounts"),
            )
            return

    try:
        api_id = int(text)
    except ValueError:
        await message.answer("API_ID только числом (или <code>-</code>).", reply_markup=back("menu:accounts"))
        return
    await state.update_data(api_id=api_id)
    await state.set_state(AddAccount.api_hash)
    await message.answer(
        "Введи API_HASH.\n\n"
        "Он лежит рядом с API_ID на <code>my.telegram.org</code>.",
        reply_markup=back("menu:accounts"),
    )


@router.message(AddAccount.api_hash)
async def acc_api_hash(message: Message, state: FSMContext) -> None:
    try:
        await message.delete()
    except Exception:
        pass
    await state.update_data(api_hash=(message.text or "").strip())
    await state.set_state(AddAccount.phone)
    await message.answer(
        "Введи телефон в формате <code>+79990000000</code>.\n\n"
        "Код придет в Telegram на этот аккаунт, не в SMS.",
        reply_markup=back("menu:accounts"),
    )


@router.message(AddAccount.phone)
async def acc_phone(message: Message, state: FSMContext) -> None:
    try:
        await message.delete()
    except Exception:
        pass
    with SessionLocal() as db:
        if not await admin_message(message, db):
            return
    data = await state.get_data()
    phone = (message.text or "").strip()
    client = Client(
        name=data["title"],
        api_id=data["api_id"],
        api_hash=data["api_hash"],
        in_memory=True,
        device_model="SM-G998B",
        system_version="Android 14",
        app_version="10.14.5",
        lang_code="ru"
    )
    try:
        await client.connect()
        sent = await client.send_code(phone)
        active_clients[message.from_user.id] = client
        await state.update_data(phone=phone, phone_code_hash=sent.phone_code_hash)
        await state.set_state(AddAccount.code)
        await message.answer(
            "Код отправил. Введи код из Telegram.\n\n"
            "⚠️ ВАЖНО: Telegram моментально блокирует код, если отправить его боту цифрами! "
            "Введи код через пробел, тире или с буквой (например: <code>12 345</code> или <code>A12345</code>).\n"
            "Бот сам уберет лишние символы.",
            reply_markup=back("menu:accounts"),
        )
    except FloodWait as exc:
        logger.warning("FloodWait during account login: %s", exc.value)
        if client.is_connected:
            await client.disconnect()
        await message.answer(
            f"❌ Telegram просит подождать <code>{exc.value}</code> сек.",
            reply_markup=back("menu:accounts"),
        )
    except (OSError, TimeoutError, ConnectionError, RPCError) as exc:
        logger.exception("Cannot send login code")
        if client.is_connected:
            await client.disconnect()
        await message.answer(
            f"❌ Не смог подключить аккаунт: <code>{exc}</code>",
            reply_markup=back("menu:accounts"),
        )


async def _save_authorized_client(message: Message, state: FSMContext, client: Client) -> None:
    data = await state.get_data()
    session_string = await client.export_session_string()
    with SessionLocal() as db:
        add_account(
            db,
            title=data["title"],
            api_id=data["api_id"],
            api_hash=data["api_hash"],
            phone=data["phone"],
            session_string=session_string,
        )
        db.commit()
        text = "✅ Аккаунт добавлен.\n\n" + accounts_menu_text(db)
    active_clients.pop(message.from_user.id, None)
    if client.is_connected:
        await client.disconnect()
    await state.clear()
    await message.answer(text, reply_markup=accounts_kb())


@router.message(AddAccount.code)
async def acc_code(message: Message, state: FSMContext) -> None:
    try:
        await message.delete()
    except Exception:
        pass
    data = await state.get_data()
    client = active_clients.get(message.from_user.id)
    if not client:
        await state.clear()
        await message.answer("Сессия входа устарела. Начни заново.", reply_markup=accounts_kb())
        return
    try:
        await client.sign_in(
            phone_number=data["phone"],
            phone_code_hash=data["phone_code_hash"],
            phone_code=normalize_login_code(message.text or ""),
        )
        await _save_authorized_client(message, state, client)
    except SessionPasswordNeeded:
        await state.set_state(AddAccount.password)
        await message.answer("Введи пароль 2FA.", reply_markup=back("menu:accounts"))
    except (PhoneCodeInvalid, PhoneCodeExpired) as exc:
        await close_active_client(message.from_user.id)
        await state.clear()
        await message.answer(f"❌ Код не подошел: <code>{exc}</code>", reply_markup=accounts_kb())
    except FloodWait as exc:
        await close_active_client(message.from_user.id)
        await state.clear()
        await message.answer(
            f"❌ Telegram просит подождать <code>{exc.value}</code> сек.",
            reply_markup=accounts_kb(),
        )
    except RPCError as exc:
        logger.exception("Account sign in failed")
        await close_active_client(message.from_user.id)
        await state.clear()
        await message.answer(f"❌ Не смог войти: <code>{exc}</code>", reply_markup=accounts_kb())


@router.message(AddAccount.password)
async def acc_password(message: Message, state: FSMContext) -> None:
    try:
        await message.delete()
    except Exception:
        pass
    client = active_clients.get(message.from_user.id)
    if not client:
        await state.clear()
        await message.answer("Сессия входа устарела. Начни заново.", reply_markup=accounts_kb())
        return
    try:
        await client.check_password((message.text or "").strip())
        await _save_authorized_client(message, state, client)
    except PasswordHashInvalid:
        await message.answer(
            "Пароль не подошел. Введи еще раз.",
            reply_markup=back("menu:accounts"),
        )
    except RPCError as exc:
        logger.exception("2FA check failed")
        await close_active_client(message.from_user.id)
        await state.clear()
        await message.answer(
            f"❌ Не смог проверить 2FA: <code>{exc}</code>",
            reply_markup=accounts_kb(),
        )


def proxies_menu_text(db) -> str:
    proxies = db.query(Proxy).order_by(Proxy.id.asc()).all()
    lines = ["<b>Прокси</b>", ""]
    lines.extend(
        f"{'✅' if item.is_active else '❌'} #{item.id} "
        f"<code>{item.proxy_type}://{item.host}:{item.port}</code>"
        for item in proxies
    )
    return "\n".join(lines) if proxies else "<b>Прокси</b>\n\nПока нет прокси"

@router.callback_query(F.data == "acc:del_start")
async def acc_del_start(callback: CallbackQuery, state: FSMContext) -> None:
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        accounts = db.query(TelegramAccount).order_by(TelegramAccount.id.asc()).all()
    if not accounts:
        await callback.message.edit_text(
            "Нет аккаунтов для удаления.", reply_markup=accounts_kb()
        )
        await callback.answer()
        return
    lines = ["<b>Удалить аккаунт</b>\n"]
    lines.extend(
        f"#{acc.id} <code>{acc.title}</code> {acc.phone}"
        for acc in accounts
    )
    lines.append("\nВведи ID аккаунта для удаления.")
    await state.set_state(DelAccount.acc_id)
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=back("menu:accounts")
    )
    await callback.answer()


@router.message(DelAccount.acc_id)
async def acc_del_confirm(message: Message, state: FSMContext) -> None:
    try:
        acc_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("ID только числом.", reply_markup=back("menu:accounts"))
        return
    with SessionLocal() as db:
        account = db.query(TelegramAccount).filter_by(id=acc_id).first()
        if not account:
            await state.clear()
            await message.answer(
                f"❌ Аккаунт #{acc_id} не найден.", reply_markup=accounts_kb()
            )
            return
        title = account.title
        phone = account.phone
        db.delete(account)
        db.commit()
        text = f"✅ Аккаунт #{acc_id} <code>{title}</code> ({phone}) удален.\n\n" + accounts_menu_text(db)
    await state.clear()
    await message.answer(text, reply_markup=accounts_kb())

@router.callback_query(F.data == "menu:proxies")
async def proxies_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        text = proxies_menu_text(db)
        await callback.message.edit_text(text, reply_markup=proxies_kb())
    await callback.answer()


@router.callback_query(F.data == "proxy:add")
async def proxy_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddProxy.title)
    await callback.message.edit_text(
        "Название прокси.\n\n"
        "Например: <code>us_proxy_1</code>. Это имя только для удобства.",
        reply_markup=back("menu:proxies"),
    )
    await callback.answer()


@router.message(AddProxy.title)
async def proxy_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(AddProxy.proxy_type)
    await message.answer(
        "Тип: <code>socks5</code> или <code>http</code>.\n\n"
        "Для TG аккаунтов чаще всего нужен <code>socks5</code>.",
        reply_markup=back("menu:proxies"),
    )


@router.message(AddProxy.proxy_type)
async def proxy_type(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip().lower()
    if value not in {"socks5", "http"}:
        await message.answer(
            "Введи <code>socks5</code> или <code>http</code>.",
            reply_markup=back("menu:proxies"),
        )
        return
    await state.update_data(proxy_type=value)
    await state.set_state(AddProxy.host)
    await message.answer(
        "Host прокси.\n\n"
        "Введи только хост или IP, без <code>socks5://</code>.",
        reply_markup=back("menu:proxies"),
    )


@router.message(AddProxy.host)
async def proxy_host(message: Message, state: FSMContext) -> None:
    await state.update_data(host=(message.text or "").strip())
    await state.set_state(AddProxy.port)
    await message.answer(
        "Port числом.\n\n"
        "Например: <code>1080</code>.",
        reply_markup=back("menu:proxies"),
    )


@router.message(AddProxy.port)
async def proxy_port(message: Message, state: FSMContext) -> None:
    try:
        port = int((message.text or "").strip())
    except ValueError:
        await message.answer("Порт только числом.", reply_markup=back("menu:proxies"))
        return
    await state.update_data(port=port)
    await state.set_state(AddProxy.username)
    await message.answer(
        "Логин или <code>-</code>.\n\n"
        "Если у прокси нет логина, отправь <code>-</code>.",
        reply_markup=back("menu:proxies"),
    )


@router.message(AddProxy.username)
async def proxy_username(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    await state.update_data(username=None if value == "-" else value)
    await state.set_state(AddProxy.password)
    await message.answer(
        "Пароль или <code>-</code>.\n\n"
        "Если у прокси нет пароля, отправь <code>-</code>.",
        reply_markup=back("menu:proxies"),
    )


@router.message(AddProxy.password)
async def proxy_password(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    value = (message.text or "").strip()
    with SessionLocal() as db:
        proxy = add_proxy(
            db,
            title=data["title"],
            proxy_type=data["proxy_type"],
            host=data["host"],
            port=data["port"],
            username=data["username"],
            password=None if value == "-" else value,
        )
        ok, error = await check_proxy_connection(proxy)
        proxy.last_checked_at = datetime.utcnow()
        proxy.last_error = error
        proxy.is_active = ok
        db.commit()
        if ok:
            text = "✅ Ок, прокси добавил\n\n" + proxies_menu_text(db)
        else:
            text = f"⚠️ Прокси сохранен, но он не отвечает: <code>{error}</code>\n\n" + proxies_menu_text(db)
    await state.clear()
    await message.answer(text, reply_markup=proxies_kb())
