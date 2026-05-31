import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.guards import admin_callback, admin_message
from app.bot.keyboards import back, main_menu, blacklist_actions, kb
from app.db.session import SessionLocal
from app.db.models import Source, BlacklistedChannel, Job
from app.services.health import health_full_text
from app.services.jobs import JOB_SEARCH, enqueue_job
from app.services.stats import stats_text, status_text

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("start"))
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    with SessionLocal() as db:
        if not await admin_message(message, db):
            return
    await message.answer("<b>Админка парсера</b>", reply_markup=main_menu())


@router.message(Command("status"))
async def status_cmd(message: Message) -> None:
    with SessionLocal() as db:
        if not await admin_message(message, db):
            return
        await message.answer(status_text(db), reply_markup=back())


@router.callback_query(F.data == "menu:main")
async def menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
    await callback.message.edit_text("<b>Админка парсера</b>", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.message(Command("stats"))
async def stats_cmd(message: Message) -> None:
    with SessionLocal() as db:
        if not await admin_message(message, db):
            return
        await message.answer(stats_text(db), reply_markup=back())


@router.callback_query(F.data == "stats")
async def stats_cb(callback: CallbackQuery) -> None:
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        await callback.message.edit_text(stats_text(db), reply_markup=back())
    await callback.answer()


@router.callback_query(F.data == "status")
async def status_cb(callback: CallbackQuery) -> None:
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        await callback.message.edit_text(status_text(db), reply_markup=back())
    await callback.answer()


@router.message(Command("health_full"))
async def health_full_cmd(message: Message) -> None:
    with SessionLocal() as db:
        if not await admin_message(message, db):
            return
    await message.answer(health_full_text(), reply_markup=back())


@router.callback_query(F.data == "search:run")
async def run_search(callback: CallbackQuery) -> None:
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        active_job = db.query(Job).filter(Job.kind == JOB_SEARCH, Job.status.in_(["pending", "running"])).first()
        if active_job:
            await callback.message.edit_text(
                f"Поиск уже запущен или в очереди. Job <code>#{active_job.id}</code> ({active_job.status})",
                reply_markup=back(),
            )
            await callback.answer()
            return
        job = enqueue_job(db, JOB_SEARCH, created_by_admin_id=callback.from_user.id)
        db.commit()
    await callback.message.edit_text(
        f"Ок, поставил поиск в очередь. Job <code>#{job.id}</code>",
        reply_markup=back(),
    )
    await callback.answer()
    logger.info("Search job %s queued by admin %s", job.id, callback.from_user.id)


@router.message(Command("run_search"))
async def run_search_cmd(message: Message) -> None:
    with SessionLocal() as db:
        if not await admin_message(message, db):
            return
        active_job = db.query(Job).filter(Job.kind == JOB_SEARCH, Job.status.in_(["pending", "running"])).first()
        if active_job:
            await message.answer(
                f"Поиск уже запущен или в очереди. Job <code>#{active_job.id}</code> ({active_job.status})",
                reply_markup=back(),
            )
            return
        job = enqueue_job(db, JOB_SEARCH, created_by_admin_id=message.from_user.id)
        db.commit()
    await message.answer(
        f"Ок, поставил поиск в очередь. Job <code>#{job.id}</code>",
        reply_markup=back(),
    )
    logger.info("Search job %s queued by admin %s", job.id, message.from_user.id)


import math
from aiogram.exceptions import TelegramBadRequest

async def render_blacklist(callback: CallbackQuery, page: int = 1) -> None:
    per_page = 10
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        total = db.query(Source).filter(Source.is_blacklisted.is_(True)).count()
        if total == 0:
            await callback.message.edit_text("Черный список пуст.", reply_markup=back("menu:main"))
            await callback.answer()
            return
        
        total_pages = max(1, math.ceil(total / per_page))
        page = max(1, min(page, total_pages))
        
        sources = db.query(Source).filter(Source.is_blacklisted.is_(True)).order_by(Source.updated_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
        
        try:
            await callback.message.edit_text(
                f"<b>Черный список</b>\nВсего источников: {total}",
                reply_markup=blacklist_actions(sources, page, total_pages)
            )
        except TelegramBadRequest:
            pass
        await callback.answer()

@router.callback_query(F.data == "menu:blacklist")
async def list_bad_sources_menu(callback: CallbackQuery) -> None:
    await render_blacklist(callback, 1)

@router.callback_query(F.data.startswith("blacklist:page:"))
async def blacklist_page(callback: CallbackQuery) -> None:
    page = int(callback.data.split(":")[2])
    await render_blacklist(callback, page)

@router.callback_query(F.data.startswith("blacklist:ask:"))
async def blacklist_ask(callback: CallbackQuery) -> None:
    _, _, source_id_raw, page_raw = callback.data.split(":")
    yes_data = f"blacklist:confirm:{source_id_raw}:{page_raw}"
    no_data = f"blacklist:page:{page_raw}"
    try:
        await callback.message.edit_reply_markup(reply_markup=kb([
            [("⚠️ Точно разблокировать?", "noop")],
            [("Да, разблокировать", yes_data)],
            [("Отмена", no_data)]
        ]))
    except TelegramBadRequest:
        pass
    await callback.answer()

@router.callback_query(F.data.startswith("blacklist:confirm:"))
async def blacklist_confirm(callback: CallbackQuery) -> None:
    _, _, source_id_raw, page_raw = callback.data.split(":")
    source_id = int(source_id_raw)
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        source = db.get(Source, source_id)
        if source and source.is_blacklisted:
            source.is_blacklisted = False
            blacklisted = db.query(BlacklistedChannel).filter_by(channel_id=source.channel_id).first()
            if blacklisted:
                db.delete(blacklisted)
            db.commit()
    await render_blacklist(callback, int(page_raw))

@router.message(Command("list_bad_sources"))
async def list_bad_sources_cmd(message: Message) -> None:
    with SessionLocal() as db:
        if not await admin_message(message, db):
            return
        sources = db.query(Source).filter(Source.is_blacklisted.is_(True)).order_by(Source.updated_at.desc()).limit(50).all()
        if not sources:
            await message.answer("Черный список пуст.", reply_markup=back())
            return
        
        lines = ["<b>Плохие источники (последние 50)</b>", ""]
        for s in sources:
            lines.append(f"#{s.id} <code>{s.channel_name or s.username or s.channel_id}</code>")
        lines.append("\nРазблокировать: <code>/unblock_source &lt;ID&gt;</code>")
        
        await message.answer("\n".join(lines), reply_markup=back())


@router.message(Command("unblock_source"))
async def unblock_source_cmd(message: Message) -> None:
    with SessionLocal() as db:
        if not await admin_message(message, db):
            return
        
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].isdigit():
            await message.answer("Укажите ID: <code>/unblock_source 123</code>")
            return
        
        source_id = int(parts[1])
        source = db.get(Source, source_id)
        if not source:
            await message.answer("Источник не найден.")
            return
        if not source.is_blacklisted:
            await message.answer("Этот источник не в черном списке.")
            return
        
        source.is_blacklisted = False
        source.status = "active"
        source.blacklisted_at = None
        
        blacklisted = db.query(BlacklistedChannel).filter_by(channel_id=source.channel_id).first()
        if blacklisted:
            db.delete(blacklisted)
            
        db.commit()
        await message.answer(f"✅ Источник <b>{source.channel_name or source.username or source.channel_id}</b> разблокирован.")
