from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.guards import admin_callback
from app.bot.keyboards import back, kb
from app.bot.states import AddKeyword, RemoveKeyword
from sqlalchemy.orm import Session
from app.db.models import Keyword
from app.db.session import SessionLocal
from app.services.filters import add_keyword, list_keywords, remove_keyword

router = Router()

FILTER_FOLDERS = {
    "direction": "Direction",
    "entry": "Entry",
    "target": "Targets",
    "stop_loss": "Stop Loss",
    "setup": "Setup",
    "include": "Custom Include",
    "hard_spam": "Hard Spam",
    "result_report": "Result Report",
    "exclude": "Custom Exclude",
    "soft_promo": "Promo Words",
}

def button_rows(items: list[tuple[str, str]], per_row: int = 2) -> list[list[tuple[str, str]]]:
    return [items[index:index + per_row] for index in range(0, len(items), per_row)]

def main_filters_kb(db: Session):
    rows = []
    rows.append([("🟢 Обязательные (Include)", "noop")])
    for kind in ("direction", "entry", "target", "stop_loss", "setup", "include"):
        count = len(list_keywords(db, kind))
        rows.append([(f"{FILTER_FOLDERS[kind]} ({count})", f"filters:folder:{kind}")])
    
    rows.append([("🔴 Исключения (Exclude)", "noop")])
    for kind in ("hard_spam", "result_report", "exclude", "soft_promo"):
        count = len(list_keywords(db, kind))
        rows.append([(f"{FILTER_FOLDERS[kind]} ({count})", f"filters:folder:{kind}")])
        
    rows.append([("Назад", "menu:main")])
    return kb(rows)

def folder_kb(db: Session, kind: str):
    words = list_keywords(db, kind)
    rows = button_rows(
        [(f"🔴 {kw.word}", f"kw:remove_exact:{kw.id}") for kw in words if kw.is_active]
    )
    rows.append([("Добавить слово", f"kw:add:{kind}")])
    rows.append([("Назад", "menu:filters")])
    return kb(rows)

@router.callback_query(F.data == "menu:filters")
async def filters_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        await callback.message.edit_text(
            "<b>Настройки фильтров</b>\n\nВыберите категорию для редактирования:",
            reply_markup=main_filters_kb(db),
        )
    await callback.answer()

@router.callback_query(F.data.startswith("filters:folder:"))
async def filters_folder(callback: CallbackQuery, state: FSMContext) -> None:
    kind = callback.data.split(":")[2]
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        await callback.message.edit_text(
            f"<b>{FILTER_FOLDERS[kind]}</b>\n\nНажмите на слово, чтобы удалить его:",
            reply_markup=folder_kb(db, kind),
        )
    await callback.answer()

@router.callback_query(F.data.startswith("kw:remove_exact:"))
async def kw_remove_exact(callback: CallbackQuery) -> None:
    kw_id = int(callback.data.split(":")[2])
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        kw = db.get(Keyword, kw_id)
        if kw:
            kw.is_active = False
            kind = kw.kind
            db.commit()
            await callback.message.edit_text(
                f"<b>{FILTER_FOLDERS[kind]}</b>\n\nНажмите на слово, чтобы удалить его:",
                reply_markup=folder_kb(db, kind),
            )
        await callback.answer("Удалено" if kw else "Не нашел")

@router.callback_query(F.data.startswith("kw:add:"))
async def kw_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    kind = callback.data.split(":")[2]
    await state.update_data(kind=kind)
    await state.set_state(AddKeyword.value)
    await callback.message.edit_text(
        f"Введи новое слово или фразу для <b>{FILTER_FOLDERS[kind]}</b>:",
        reply_markup=back(f"filters:folder:{kind}")
    )
    await callback.answer()

@router.message(AddKeyword.value)
async def kw_add_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    kind = data.get("kind")
    if not kind:
        await state.clear()
        return

    with SessionLocal() as db:
        add_keyword(db, kind, message.text or "")
        db.commit()
        await message.answer(
            f"✅ Добавлено\n\n<b>{FILTER_FOLDERS[kind]}</b>",
            reply_markup=folder_kb(db, kind)
        )
    await state.clear()
