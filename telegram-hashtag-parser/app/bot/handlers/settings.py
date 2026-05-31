from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.guards import admin_callback
from app.bot.keyboards import back, kb
from app.bot.states import AddChannel, SetAi, SetBingX, SetSetting
from app.db.models import AiProvider, Exchange, PublishChannel, Setting
from app.db.session import SessionLocal
from app.services.crypto import encrypt_secret, mask_secret
from app.services.settings import set_setting
from app.utils.text import parse_duration_minutes

router = Router()


SETTING_LABELS = {
    "search_pause_seconds": "Пауза между поисками (сек)",
    "search_limit_per_tag": "Лимит постов на тег",
    "search_recent_hours": "Свежесть постов (часов)",
    "ai_enabled": "ИИ анализ включен",
    "backup_hour": "Час бекапа БД",
    "backup_retention_days": "Хранить бекапы (дней)",
    "bingx_sync_enabled": "Синхронизация BingX",
    "search_auto_interval_minutes": "Интервал автопоиска (мин)",
}
HIDDEN_SETTINGS = {"search_recent_days"}
INT_SETTINGS = {
    "backup_hour",
    "backup_retention_days",
    "search_auto_interval_minutes",
    "search_limit_per_tag",
    "search_pause_seconds",
    "search_recent_hours",
}
MIN_INT_VALUES = {
    "backup_hour": 0,
    "backup_retention_days": 1,
    "search_auto_interval_minutes": 0,
    "search_limit_per_tag": 1,
    "search_pause_seconds": 0,
    "search_recent_hours": 1,
}

@router.callback_query(F.data == "menu:settings")
async def settings_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        rows = db.query(Setting).order_by(Setting.key.asc()).all()
        text = "<b>Настройки</b>\n\nВыберите настройку для изменения:"

        buttons = []
        for item in rows:
            if item.key in HIDDEN_SETTINGS:
                continue
            label = SETTING_LABELS.get(item.key, item.key)
            if item.key in ("ai_enabled", "bingx_sync_enabled"):
                icon = "🟢" if item.value.lower() == "true" else "🔴"
                buttons.append([(f"{icon} {label}", f"setting:set:{item.key}")])
            else:
                display_value = item.value if len(item.value) < 15 else item.value[:12] + "..."
                buttons.append([(f"⚙️ {label} = {display_value}", f"setting:set:{item.key}")])
        buttons.append([("🤖 Настройки AI (OpenAI)", "menu:ai")])
        buttons.append([("📈 Настройки BingX", "menu:bingx")])
        buttons.append([("Назад", "menu:main")])

    await callback.message.edit_text(
        text,
        reply_markup=kb(buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setting:set:"))
async def setting_key(callback: CallbackQuery, state: FSMContext) -> None:
    key = callback.data.split(":", 2)[2]

    if key in ("ai_enabled", "bingx_sync_enabled"):
        with SessionLocal() as db:
            setting = db.query(Setting).filter(Setting.key == key).first()
            current = setting.value if setting else "false"
            new_val = "true" if current.lower() == "false" else "false"
            set_setting(db, key, new_val)
            db.commit()
        await settings_menu(callback, state)
        return

    await state.set_state(SetSetting.value)
    await state.update_data(key=key)
    prompt = f"Введи новое значение для <code>{key}</code>:"
    if key == "search_auto_interval_minutes":
        prompt += "\n\nМожно указать число (в минутах) или формат: <code>1h 30m</code>, <code>2ч</code>."
        
    await callback.message.edit_text(
        prompt,
        reply_markup=back("menu:settings"),
    )
    await callback.answer()


@router.message(SetSetting.value)
async def setting_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    key = data["key"]
    value = (message.text or "").strip()
    if value.startswith("/"):
        await message.answer("Введи значение, а не команду.", reply_markup=back("menu:settings"))
        return
    if key in INT_SETTINGS:
        try:
            if key == "search_auto_interval_minutes":
                int_value = parse_duration_minutes(value)
            else:
                int_value = int(value)
        except ValueError:
            msg = "Нужно ввести число (в минутах) или формат вроде 1h 30m." if key == "search_auto_interval_minutes" else "Нужно ввести число."
            await message.answer(msg, reply_markup=back("menu:settings"))
            return
        min_value = MIN_INT_VALUES.get(key)
        if min_value is not None and int_value < min_value:
            await message.answer(
                f"Минимальное значение: <code>{min_value}</code>.",
                reply_markup=back("menu:settings"),
            )
            return
        value = str(int_value)
    with SessionLocal() as db:
        set_setting(db, key, value, "int" if key in INT_SETTINGS else "str")
        db.commit()
    await state.clear()
    await message.answer("✅ Ок, сохранил", reply_markup=back("menu:settings"))


@router.callback_query(F.data == "menu:ai")
async def ai_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    with SessionLocal() as db:
        provider = db.query(AiProvider).filter(AiProvider.provider == "openai").first()
        key_state = mask_secret(provider.api_key) if provider else "не задан"
        model = provider.selected_model if provider else "-"
    await callback.message.edit_text(
        f"<b>AI / OpenAI</b>\n\nAPI key: <code>{key_state}</code>\nМодель: <code>{model}</code>",
        reply_markup=kb([[("Изменить", "ai:set")], [("Назад", "menu:settings")]]),
    )
    await callback.answer()


@router.callback_query(F.data == "ai:set")
async def ai_key(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SetAi.api_key)
    await callback.message.edit_text(
        "Введи OpenAI API key.\n\n"
        "Брать в OpenAI Platform, раздел API keys. Подписка ChatGPT Plus тут не подходит.",
        reply_markup=back("menu:ai"),
    )
    await callback.answer()


@router.message(SetAi.api_key)
async def ai_model_start(message: Message, state: FSMContext) -> None:
    try:
        await message.delete()
    except Exception:
        pass
    await state.update_data(api_key=(message.text or "").strip())
    await state.set_state(SetAi.model)
    await message.answer(
        "Введи модель, например <code>gpt-4.1-mini</code>.\n\n"
        "Позже список моделей можно будет подтягивать через API.",
        reply_markup=back("menu:ai"),
    )


@router.message(SetAi.model)
async def ai_model(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    with SessionLocal() as db:
        provider = db.query(AiProvider).filter(AiProvider.provider == "openai").first()
        if not provider:
            provider = AiProvider(provider="openai")
            db.add(provider)
        provider.api_key = encrypt_secret(data["api_key"])
        provider.selected_model = (message.text or "").strip()
        provider.is_active = True
        db.commit()
    await state.clear()
    await message.answer("✅ Ок, OpenAI сохранил", reply_markup=back("menu:ai"))


@router.callback_query(F.data == "menu:bingx")
async def bingx_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    with SessionLocal() as db:
        exchange = db.query(Exchange).filter(Exchange.name == "bingx").first()
        key_state = mask_secret(exchange.api_key) if exchange else "не задан"
        ref = exchange.referral_link if exchange and exchange.referral_link else "-"
    await callback.message.edit_text(
        f"<b>BingX</b>\n\nAPI key: <code>{key_state}</code>\nReferral: <code>{ref}</code>",
        reply_markup=kb([[("Изменить", "bingx:set")], [("Назад", "menu:settings")]]),
    )
    await callback.answer()


@router.callback_query(F.data == "bingx:set")
async def bingx_key(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SetBingX.api_key)
    await callback.message.edit_text(
        "Введи BingX API key.\n\n"
        "Брать в BingX API Management. Для MVP можно оставить тестовый ключ.",
        reply_markup=back("menu:bingx"),
    )
    await callback.answer()


@router.message(SetBingX.api_key)
async def bingx_secret_start(message: Message, state: FSMContext) -> None:
    try:
        await message.delete()
    except Exception:
        pass
    await state.update_data(api_key=(message.text or "").strip())
    await state.set_state(SetBingX.api_secret)
    await message.answer(
        "Введи BingX API secret.\n\n"
        "Это пара к API key из BingX API Management.",
        reply_markup=back("menu:bingx"),
    )


@router.message(SetBingX.api_secret)
async def bingx_ref_start(message: Message, state: FSMContext) -> None:
    try:
        await message.delete()
    except Exception:
        pass
    await state.update_data(api_secret=(message.text or "").strip())
    await state.set_state(SetBingX.referral)
    await message.answer(
        "Введи referral link или <code>-</code>.\n\n"
        "Если ссылки пока нет, отправь <code>-</code>.",
        reply_markup=back("menu:bingx"),
    )


@router.message(SetBingX.referral)
async def bingx_ref(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    ref = (message.text or "").strip()
    with SessionLocal() as db:
        exchange = db.query(Exchange).filter(Exchange.name == "bingx").first()
        if not exchange:
            exchange = Exchange(name="bingx")
            db.add(exchange)
        exchange.api_key = encrypt_secret(data["api_key"])
        exchange.api_secret = encrypt_secret(data["api_secret"])
        exchange.referral_link = None if ref == "-" else ref
        exchange.is_active = True
        db.commit()
    await state.clear()
    await message.answer("✅ Ок, BingX сохранил", reply_markup=back("menu:bingx"))


@router.callback_query(F.data == "menu:channels")
async def channels_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    with SessionLocal() as db:
        channels = db.query(PublishChannel).order_by(PublishChannel.id.asc()).all()
        lines = ["<b>Каналы публикации</b>", ""]
        buttons = []
        for item in channels:
            status = "🟢 Активен" if item.is_active else "⚪️ Отключен"
            lines.append(f"#{item.id} <code>{item.title}</code> {item.channel_id} ({status})")
            buttons.append([(f"Настроить #{item.id} {item.title}", f"channel:manage:{item.id}")])
            
    buttons.append([("➕ Добавить канал", "channel:add")])
    buttons.append([("⬅️ Назад", "menu:main")])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=kb(buttons),
    )
    await callback.answer()

@router.callback_query(F.data.startswith("channel:manage:"))
async def channel_manage_menu(callback: CallbackQuery) -> None:
    channel_id = int(callback.data.split(":")[2])
    with SessionLocal() as db:
        channel = db.get(PublishChannel, channel_id)
        if not channel:
            await callback.answer("Канал не найден")
            return
            
        status = "🟢 Активен" if channel.is_active else "⚪️ Отключен"
        text = f"<b>Канал #{channel.id}</b>\nНазвание: {channel.title}\nID: {channel.channel_id}\nСтатус: {status}"
        
        buttons = [
            [("🌟 Сделать основным", f"channel:action:active:{channel.id}")],
            [("⏸ Отключить", f"channel:action:disable:{channel.id}")],
            [("🗑 Удалить", f"channel:action:delete:{channel.id}")],
            [("⬅️ Назад", "menu:channels")]
        ]
        await callback.message.edit_text(text, reply_markup=kb(buttons))
    await callback.answer()

@router.callback_query(F.data.startswith("channel:action:"))
async def channel_action(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    action = parts[2]
    channel_id = int(parts[3])
    with SessionLocal() as db:
        channel = db.get(PublishChannel, channel_id)
        if not channel:
            await callback.answer("Канал не найден")
            return
            
        if action == "active":
            db.query(PublishChannel).update({PublishChannel.is_active: False})
            channel.is_active = True
            await callback.answer("Канал теперь основной")
        elif action == "disable":
            channel.is_active = False
            await callback.answer("Канал отключен")
        elif action == "delete":
            db.delete(channel)
            await callback.answer("Канал удален")
        db.commit()
        
    await channels_menu(callback, state)


@router.callback_query(F.data == "channel:add")
async def channel_title(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddChannel.title)
    await callback.message.edit_text(
        "Название канала.\n\n"
        "Например: <code>main signals</code>. Это имя только внутри админки.",
        reply_markup=back("menu:channels"),
    )
    await callback.answer()


@router.message(AddChannel.title)
async def channel_id_start(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(AddChannel.channel_id)
    await message.answer(
        "Введи channel_id или @username.\n\n"
        "Проще всего указать публичный username канала, например <code>@my_channel</code>.",
        reply_markup=back("menu:channels"),
    )


@router.message(AddChannel.channel_id)
async def channel_username_start(message: Message, state: FSMContext) -> None:
    await state.update_data(channel_id=(message.text or "").strip())
    await state.set_state(AddChannel.username)
    await message.answer(
        "Введи username без @ или <code>-</code>.\n\n"
        "Если в прошлом шаге уже указал <code>@username</code>, "
        "тут можно отправить <code>-</code>.",
        reply_markup=back("menu:channels"),
    )


@router.message(AddChannel.username)
async def channel_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    username = (message.text or "").strip()
    with SessionLocal() as db:
        db.add(
            PublishChannel(
                title=data["title"],
                channel_id=data["channel_id"],
                username=None if username == "-" else username,
            )
        )
        db.commit()
    await state.clear()
    await message.answer("✅ Ок, канал добавил", reply_markup=back("menu:channels"))
