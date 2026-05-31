from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.guards import admin_callback, admin_message
from app.bot.keyboards import back, kb
from app.bot.states import AddTag, RemoveTag
from app.db.models import Hashtag
from app.db.session import SessionLocal
from app.services.tags import add_tag, list_tags, remove_tag

router = Router()


def button_rows(items: list[tuple[str, str]], per_row: int = 2) -> list[list[tuple[str, str]]]:
    return [items[index:index + per_row] for index in range(0, len(items), per_row)]


def tags_menu_text(db) -> str:
    tags = list_tags(db, active_only=True)
    if not tags:
        return "<b>Хэштеги</b>\n\nПока пусто"
    return f"<b>Хэштеги</b>\n\nАктивных: <code>{len(tags)}</code>"


def tags_menu_kb(db):
    tags = list_tags(db, active_only=True)
    disabled_count = db.query(Hashtag).filter(Hashtag.is_active.is_(False)).count()
    rows = button_rows(
        [(f"🔴 {tag.tag}", f"tag:disable:{tag.id}") for tag in tags]
    )
    rows.append([("Добавить", "tags:add"), ("Вручную", "tags:remove")])
    if disabled_count:
        rows.append([(f"Отключенные ({disabled_count})", "tags:disabled")])
    rows.append([("Назад", "menu:main")])
    return kb(rows)


def disabled_tags_menu_text(db) -> str:
    count = db.query(Hashtag).filter(Hashtag.is_active.is_(False)).count()
    if not count:
        return "<b>Отключенные хэштеги</b>\n\nПока пусто"
    return f"<b>Отключенные хэштеги</b>\n\nОтключено: <code>{count}</code>"


def disabled_tags_menu_kb(db):
    tags = db.query(Hashtag).filter(Hashtag.is_active.is_(False)).order_by(Hashtag.tag.asc()).all()
    rows = button_rows(
        [(f"🟢 {tag.tag}", f"tag:enable:{tag.id}") for tag in tags]
    )
    rows.append([("Назад", "menu:tags")])
    return kb(rows)


@router.callback_query(F.data == "menu:tags")
async def tags_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        await callback.message.edit_text(tags_menu_text(db), reply_markup=tags_menu_kb(db))
    await callback.answer()


@router.message(Command("list_tags"))
async def list_tags_cmd(message: Message) -> None:
    with SessionLocal() as db:
        if not await admin_message(message, db):
            return
        await message.answer(tags_menu_text(db), reply_markup=tags_menu_kb(db))


@router.callback_query(F.data == "tags:disabled")
async def disabled_tags_menu(callback: CallbackQuery) -> None:
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        await callback.message.edit_text(
            disabled_tags_menu_text(db),
            reply_markup=disabled_tags_menu_kb(db),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("tag:disable:"))
async def disable_tag(callback: CallbackQuery) -> None:
    tag_id = int(callback.data.rsplit(":", 1)[1])
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        tag = db.get(Hashtag, tag_id)
        if tag:
            tag.is_active = False
            db.commit()
        await callback.message.edit_text(tags_menu_text(db), reply_markup=tags_menu_kb(db))
    await callback.answer("Ок, убрал" if tag else "Не нашел", show_alert=True)


@router.callback_query(F.data.startswith("tag:enable:"))
async def enable_tag(callback: CallbackQuery) -> None:
    tag_id = int(callback.data.rsplit(":", 1)[1])
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        tag = db.get(Hashtag, tag_id)
        if tag:
            tag.is_active = True
            db.commit()
        await callback.message.edit_text(
            disabled_tags_menu_text(db),
            reply_markup=disabled_tags_menu_kb(db),
        )
    await callback.answer("Ок, включил" if tag else "Не нашел", show_alert=True)


@router.callback_query(F.data == "tags:add")
async def add_tag_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddTag.value)
    await callback.message.edit_text(
        "Введи хэштег, например <code>#BTC</code>",
        reply_markup=back("menu:tags"),
    )
    await callback.answer()


@router.message(Command("add_tag"))
async def add_tag_cmd(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат такой: <code>/add_tag #TOKEN</code>")
        return
    with SessionLocal() as db:
        if not await admin_message(message, db):
            return
        try:
            add_tag(db, parts[1])
            db.commit()
            text = "✅ Ок, добавил\n\n" + tags_menu_text(db)
            await message.answer(text, reply_markup=tags_menu_kb(db))
        except ValueError as exc:
            await message.answer(f"❌ {exc}", reply_markup=back("menu:tags"))


@router.message(AddTag.value)
async def add_tag_value(message: Message, state: FSMContext) -> None:
    if (message.text or "").startswith("/"):
        await state.clear()
        return
    with SessionLocal() as db:
        if not await admin_message(message, db):
            return
        try:
            add_tag(db, message.text or "")
            db.commit()
        except ValueError as exc:
            await message.answer(
                f"❌ {exc}\nВведи хэштег еще раз.",
                reply_markup=back("menu:tags"),
            )
            return
        text = "✅ Ок, добавил\n\n" + tags_menu_text(db)
        reply_markup = tags_menu_kb(db)
    await state.clear()
    await message.answer(text, reply_markup=reply_markup)


@router.callback_query(F.data == "tags:remove")
async def remove_tag_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(RemoveTag.value)
    await callback.message.edit_text(
        "Введи хэштег, который надо убрать.",
        reply_markup=back("menu:tags"),
    )
    await callback.answer()


@router.message(Command("remove_tag"))
async def remove_tag_cmd(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат такой: <code>/remove_tag #TOKEN</code>")
        return
    with SessionLocal() as db:
        if not await admin_message(message, db):
            return
        ok = remove_tag(db, parts[1])
        db.commit()
        prefix = "✅ Ок, убрал" if ok else "Не нашел"
        text = prefix + "\n\n" + tags_menu_text(db)
        reply_markup = tags_menu_kb(db)
    await message.answer(text, reply_markup=reply_markup)


@router.message(RemoveTag.value)
async def remove_tag_value(message: Message, state: FSMContext) -> None:
    if (message.text or "").startswith("/"):
        await state.clear()
        return
    with SessionLocal() as db:
        if not await admin_message(message, db):
            return
        ok = remove_tag(db, message.text or "")
        db.commit()
        prefix = "✅ Ок, убрал" if ok else "Не нашел"
        text = prefix + "\n\n" + tags_menu_text(db)
        reply_markup = tags_menu_kb(db)
    await state.clear()
    await message.answer(text, reply_markup=reply_markup)
