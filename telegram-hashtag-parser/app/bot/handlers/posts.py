import html
import re
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import case, String
from sqlalchemy.orm import Session
from aiogram.exceptions import TelegramBadRequest

from app.bot.guards import admin_callback
from app.bot.keyboards import back, candidate_actions, kb, post_actions, post_queue_actions, preview_actions
from app.bot.render import post_status_display, post_text, telegram_spoiler_html
from app.bot.states import EditPost, EditMedia
from app.db.models import Post, PublishChannel, Keyword, Exchange
from app.db.session import SessionLocal
from app.services.posts import mark_bad_source, mark_not_signal, mark_published, mark_skipped, expire_old_candidates
from app.utils.pagination import paginate
from app.utils.text import clean_post_text

router = Router()

POST_FOLDERS = {
    "candidate": ("Кандидаты", ("candidate",), None),
    "archive": ("Архив (Все)", ("skipped", "rejected"), None),
    "not_signal": ("Архив (Не сигналы)", ("rejected",), "not_signal"),
    "bad_source": ("Архив (Плохие источники)", ("rejected",), "bad_source"),
    "expired": ("Архив (Устаревшие)", ("skipped",), "expired"),
    "published": ("Опубликованные", ("published",), None),
    "filtered": ("Отфильтровано", ("filtered_out",), None),
    "all": ("Все посты", None, None),
}
VISIBLE_POST_FOLDERS = ("candidate", "archive", "not_signal", "bad_source", "expired", "published", "filtered", "all")


def render_preview_text(db: Session, post: Post) -> str:
    lines = []
    
    hashtag_val = html.escape(post.hashtag or "")
    if hashtag_val:
        if hashtag_val.upper().endswith("USDT"):
            lines.append(f"{hashtag_val}\n")
        else:
            lines.append(f"{hashtag_val} / {hashtag_val}USDT\n")
    lines.append("Original signal:")
    
    soft_promo = [k.word for k in db.query(Keyword).filter(Keyword.kind == "soft_promo", Keyword.is_active.is_(True)).all()]
    cleaned = clean_post_text(post.text or "", soft_promo)
    lines.append(telegram_spoiler_html(cleaned, escaped=False))
    
    normal_name = post.channel_name.strip() if post.channel_name else ""
    source_display = html.escape(normal_name) if normal_name else "Telegram public signal"
    
    lines.append(f"\nSource: {source_display}")
    lines.append("Not financial advice.")
    return "\n".join(lines)


def folder_filter(query, folder: str, filters: dict | None = None):
    folder_def = POST_FOLDERS.get(folder, POST_FOLDERS["candidate"])
    statuses = folder_def[1]
    label = folder_def[2] if len(folder_def) > 2 else None
    
    if statuses is not None:
        query = query.filter(Post.status.in_(statuses))
    if label is not None:
        query = query.filter(Post.label == label)
    
    if filters:
        if filters.get("priority"):
            query = query.filter(Post.priority == filters["priority"])
        if filters.get("hashtag"):
            query = query.filter(Post.hashtag == filters["hashtag"])
        if filters.get("source"):
            src = filters["source"]
            query = query.filter(
                (Post.channel_name.ilike(f"%{src}%")) | 
                (Post.username.ilike(f"%{src}%")) | 
                (Post.channel_id.cast(String).ilike(f"%{src}%"))
            )
        if filters.get("hours"):
            from datetime import datetime, timedelta
            time_threshold = datetime.utcnow() - timedelta(hours=filters["hours"])
            query = query.filter(Post.published_at >= time_threshold)
            
    return query


def folder_title(folder: str) -> str:
    return POST_FOLDERS.get(folder, POST_FOLDERS["candidate"])[0]


def folder_count(db, folder: str, filters: dict | None = None) -> int:
    return folder_filter(db.query(Post), folder, filters).count()


def priority_order():
    return case(
        (Post.priority == "high", 1),
        (Post.priority == "medium", 2),
        (Post.priority == "low", 3),
        else_=4,
    )


def ordered_folder_query(db, folder: str, filters: dict | None = None):
    return folder_filter(db.query(Post), folder, filters).order_by(
        priority_order().asc(),
        Post.published_at.desc().nulls_last(),
        Post.id.desc(),
    )


def candidate_query(db):
    return ordered_folder_query(db, "candidate")


async def render_post_queue(
    callback: CallbackQuery,
    folder: str,
    page_num: int,
    answer: bool = True,
    toast: str | None = None,
    edit: bool = True,
    filters: dict | None = None,
) -> None:
    if folder not in POST_FOLDERS:
        folder = "candidate"
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        total = ordered_folder_query(db, folder, filters).count()
        title = folder_title(folder)
        if total == 0:
            if edit:
                try:
                    await callback.message.edit_text(
                        f"<b>{title}</b>\n\nПока пусто",
                        reply_markup=back("menu:posts"),
                    )
                except TelegramBadRequest as exc:
                    if "message is not modified" not in str(exc).lower() and "message to edit not found" not in str(exc).lower():
                        raise
            else:
                await callback.message.answer(
                    f"<b>{title}</b>\n\nПока пусто",
                    reply_markup=back("menu:posts"),
                )
            if answer:
                await callback.answer(toast)
            return
        page = max(1, min(page_num, total))
        post = ordered_folder_query(db, folder, filters).offset(page - 1).limit(1).first()
        if edit:
            try:
                await callback.message.edit_text(
                    post_text(post),
                    reply_markup=post_queue_actions(post.id, folder, page, total),
                )
            except TelegramBadRequest as exc:
                if "message is not modified" not in str(exc).lower() and "message to edit not found" not in str(exc).lower():
                    raise
        else:
            await callback.message.answer(
                post_text(post),
                reply_markup=post_queue_actions(post.id, folder, page, total),
            )
    if answer:
        await callback.answer(toast)


def legacy_candidate_query(db):
    priority_order = case(
        (Post.priority == "high", 1),
        (Post.priority == "medium", 2),
        (Post.priority == "low", 3),
        else_=4,
    )
    return db.query(Post).filter(Post.status == "candidate").order_by(priority_order.asc(), Post.id.desc())


async def render_candidate_queue(callback: CallbackQuery, page_num: int, answer: bool = True, filters: dict | None = None) -> None:
    await render_post_queue(callback, "candidate", page_num, answer, filters=filters)


@router.callback_query(F.data == "menu:posts")
async def posts_menu(callback: CallbackQuery) -> None:
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        counts = {folder: folder_count(db, folder) for folder in VISIBLE_POST_FOLDERS}
    try:
        await callback.message.edit_text(
            "<b>Посты</b>\n\nВыберите папку:",
            reply_markup=kb(
                [
                    [(f"Кандидаты ({counts['candidate']})", "posts:nofilter:candidate:1")],
                    [(f"Архив (Все) ({counts['archive']})", "posts:nofilter:archive:1")],
                    [(f"Архив (Не сигналы) ({counts['not_signal']})", "posts:nofilter:not_signal:1")],
                    [(f"Архив (Плохие источники) ({counts['bad_source']})", "posts:nofilter:bad_source:1")],
                    [(f"Архив (Устаревшие) ({counts['expired']})", "posts:nofilter:expired:1")],
                    [(f"Опубликованные ({counts['published']})", "posts:nofilter:published:1")],
                    [(f"Отфильтровано ({counts['filtered']})", "posts:nofilter:filtered:1")],
                    [(f"Все ({counts['all']})", "posts:nofilter:all:1")],
                    [("🔍 Настроить фильтры", "posts:filters")],
                    [("🗑 Очистить старые (>24ч)", "posts:expire")],
                    [("Назад", "menu:main")],
                ]
            ),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
    await callback.answer()


@router.callback_query(F.data.startswith("posts:nofilter:"))
async def posts_nofilter(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, folder, page_raw = callback.data.split(":", 3)
    data = await state.get_data()
    filters = data.get("post_filters", {})
    filters["active"] = False
    await state.update_data(post_filters=filters)
    await render_posts_page(callback, folder, int(page_raw), filters=None)

@router.callback_query(F.data.startswith("posts:filterview:"))
async def posts_filterview(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, folder, page_raw = callback.data.split(":", 3)
    data = await state.get_data()
    filters = data.get("post_filters", {})
    filters["active"] = True
    await state.update_data(post_filters=filters)
    await render_posts_page(callback, folder, int(page_raw), filters=filters)

@router.callback_query(F.data.startswith("posts:folder:"))
async def posts_page(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, folder, _, page_raw = callback.data.split(":", 4)
    data = await state.get_data()
    filters = data.get("post_filters", {})
    active_filters = filters if filters.get("active") else None
    await render_posts_page(callback, folder, int(page_raw), filters=active_filters)


async def render_posts_page(callback: CallbackQuery, folder: str, page_num: int, filters: dict | None = None) -> None:
    if folder not in POST_FOLDERS:
        folder = "candidate"
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        posts = ordered_folder_query(db, folder, filters).limit(500).all()
        page = paginate(posts, page_num, per_page=10)
        title = folder_title(folder)
        lines = [f"<b>{title}</b>", ""]
        for post in page.items:
            lines.append(
                f"#{post.id} <code>{html.escape(post_status_display(post))}</code> "
                f"<code>{post.priority or '-'}</code> "
                f"<code>{html.escape(post.hashtag or '')}</code> "
                f"{html.escape(str(post.channel_name or post.username or post.channel_id))}"
            )
        buttons = []
        for index, post in enumerate(page.items, start=1):
            post_page = ((page.page - 1) * 10) + index
            buttons.append([(f"#{post.id}", f"post_queue:page:{folder}:{post_page}")])
        prev_page = page.page - 1 if page.page > 1 else page.total_pages
        next_page = page.page + 1 if page.page < page.total_pages else 1
        buttons.append(
            [
                ("пред", f"posts:folder:{folder}:page:{prev_page}"),
                (f"{page.page}/{page.total_pages}", "noop"),
                ("след", f"posts:folder:{folder}:page:{next_page}"),
            ]
        )
        buttons.append([("Назад", "menu:posts")])
        text = "\n".join(lines) if posts else f"<b>{title}</b>\n\nПока пусто"
        try:
            await callback.message.edit_text(text, reply_markup=kb(buttons))
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc):
                raise
    await callback.answer()


@router.callback_query(F.data.startswith("post:view:"))
async def post_view(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    post_id = int(parts[2])
    folder = parts[3] if len(parts) > 3 else "candidate"
    page = int(parts[4]) if len(parts) > 4 else 1
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        post = db.get(Post, post_id)
        if not post:
            await callback.answer("Пост не нашел", show_alert=True)
            return
        try:
            await callback.message.edit_text(
                post_text(post),
                reply_markup=post_actions(post.id, f"posts:folder:{folder}:page:{page}"),
            )
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc):
                raise
    await callback.answer()


@router.callback_query(F.data.startswith("post_queue:page:"))
async def post_queue_page(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, folder, page_raw = callback.data.split(":", 3)
    data = await state.get_data()
    filters = data.get("post_filters", {})
    active_filters = filters if filters.get("active") else None
    await render_post_queue(callback, folder, int(page_raw), filters=active_filters)


@router.callback_query(F.data.startswith("post_queue:action:"))
async def post_queue_action(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, post_id_raw, status, folder, page_raw = callback.data.split(":", 5)
    
    if status == "ask_bad":
        yes_data = f"post_queue:action:{post_id_raw}:bad_source:{folder}:{page_raw}"
        no_data = f"post_queue:page:{folder}:{page_raw}"
        try:
            await callback.message.edit_reply_markup(reply_markup=kb([
                [("⚠️ Точно заблокировать источник?", "noop")],
                [("Да, заблокировать", yes_data)],
                [("Отмена", no_data)]
            ]))
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    post_id = int(post_id_raw)
    page = int(page_raw)
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
    message = await apply_post_action(post_id, status)
    data = await state.get_data()
    filters = data.get("post_filters", {})
    active_filters = filters if filters.get("active") else None
    await render_post_queue(callback, folder, page, answer=True, toast=message, filters=active_filters)


@router.callback_query(F.data.startswith("candidate_queue:page:"))
async def candidate_queue_page(callback: CallbackQuery, state: FSMContext) -> None:
    page_num = int(callback.data.rsplit(":", 1)[1])
    data = await state.get_data()
    filters = data.get("post_filters", {})
    active_filters = filters if filters.get("active") else None
    await render_post_queue(callback, "candidate", page_num, filters=active_filters)


@router.callback_query(F.data.startswith("candidate_queue:action:"))
async def candidate_queue_action(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, post_id_raw, status, page_raw = callback.data.split(":", 4)
    
    if status == "ask_bad":
        yes_data = f"candidate_queue:action:{post_id_raw}:bad_source:{page_raw}"
        no_data = f"candidate_queue:page:{page_raw}"
        try:
            await callback.message.edit_reply_markup(reply_markup=kb([
                [("⚠️ Точно заблокировать источник?", "noop")],
                [("Да, заблокировать", yes_data)],
                [("Отмена", no_data)]
            ]))
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    post_id = int(post_id_raw)
    page = int(page_raw)
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
    message = await apply_post_action(post_id, status)
    data = await state.get_data()
    filters = data.get("post_filters", {})
    active_filters = filters if filters.get("active") else None
    await render_post_queue(callback, "candidate", page, answer=True, toast=message, filters=active_filters)


@router.callback_query(F.data.startswith("post:"))
async def post_status(callback: CallbackQuery) -> None:
    _, post_id_raw, status = callback.data.split(":", 2)
    
    if status == "ask_bad":
        yes_data = f"post:{post_id_raw}:bad_source"
        no_data = f"posts:folder:candidate:page:1"
        try:
            await callback.message.edit_reply_markup(reply_markup=kb([
                [("⚠️ Точно заблокировать источник?", "noop")],
                [("Да, заблокировать", yes_data)],
                [("Отмена", no_data)]
            ]))
        except TelegramBadRequest:
            pass
        await callback.answer()
        return

    post_id = int(post_id_raw)
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
    message = await apply_post_action(post_id, status)
    try:
        await callback.message.edit_text(
            message,
            reply_markup=back("posts:folder:candidate:page:1"),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
    await callback.answer(message)


# ===== PUBLISH PREVIEW / EDIT =====

async def send_preview(db: Session, message: Message, post: Post, back_data: str):
    text = render_preview_text(db, post)
    has_media = bool(post.media_id)
    markup = preview_actions(post.id, back_data, has_media)
    
    limit = 1024 if has_media else 4096
    
    if len(text) > limit:
        text = text[:limit - 100] + f"\n\n<b>⚠️ ТЕКСТ СЛИШКОМ ДЛИННЫЙ! Лимит {limit} симв., у вас {len(text)}. Укоротите перед публикацией!</b>"
        
    try:
        if has_media:
            if post.media_type == "photo":
                await message.answer_photo(post.media_id, caption=text, reply_markup=markup, parse_mode="HTML")
            elif post.media_type == "video":
                await message.answer_video(post.media_id, caption=text, reply_markup=markup, parse_mode="HTML")
            else:
                await message.answer_document(post.media_id, caption=text, reply_markup=markup, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        safe_text = html.escape(text)
        if len(safe_text) > limit:
            safe_text = safe_text[:limit - 100] + f"\n\n<b>⚠️ ТЕКСТ СЛИШКОМ ДЛИННЫЙ! Лимит {limit} симв. Укоротите!</b>"
        await message.answer(f"Ошибка HTML разметки или предпросмотра: {e}\n\n{safe_text}", reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("preview:pv:") | F.data.startswith("preview:cq:") | F.data.startswith("preview:pq:"))
async def preview_post_start(callback: CallbackQuery) -> None:
    parts = callback.data.split(":", 1)
    back_data = parts[1]
    post_id = int(back_data.split(":")[1])
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        post = db.get(Post, post_id)
        if not post:
            await callback.answer("Пост не нашел", show_alert=True)
            return
        
        try:
            await callback.message.delete()
        except Exception:
            pass
            
        await send_preview(db, callback.message, post, back_data)
    await callback.answer()


@router.callback_query(F.data.startswith("preview:edit_text:"))
async def preview_edit_text(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":", 3)
    post_id = int(parts[2])
    back_data = parts[3]
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        post = db.get(Post, post_id)
        if not post:
            await callback.answer("Пост не нашел", show_alert=True)
            return
            
        await state.update_data(post_id=post.id, back_data=back_data)
        await state.set_state(EditPost.value)
        
        # We escape to ensure <pre> renders as code
        safe_text = html.escape(post.text)
        try:
            await callback.message.answer(
                f"Скопируй текст ниже (нажми на него для копирования), измени его и отправь мне в ответ. Можно использовать HTML теги (&lt;b&gt;, &lt;i&gt;, &lt;a href=\"url\"&gt;):\n\n<code>{safe_text}</code>",
                reply_markup=back(f"preview:{back_data}"),
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            await callback.message.answer("Ошибка вывода текста для редактирования.", reply_markup=back(f"preview:{back_data}"))
    await callback.answer()


@router.callback_query(F.data.startswith("preview:add_media:"))
async def preview_add_media(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":", 3)
    post_id = int(parts[2])
    back_data = parts[3]
    
    await state.update_data(post_id=post_id, back_data=back_data)
    await state.set_state(EditMedia.value)
    
    await callback.message.answer(
        "Отправь мне фото, видео или документ для этого поста.",
        reply_markup=back(f"preview:{back_data}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("preview:remove_media:"))
async def preview_remove_media(callback: CallbackQuery) -> None:
    parts = callback.data.split(":", 3)
    post_id = int(parts[2])
    back_data = parts[3]
    
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        post = db.get(Post, post_id)
        if post:
            post.media_id = None
            post.media_type = None
            db.commit()
            
            try:
                await callback.message.delete()
            except Exception:
                pass
            await send_preview(db, callback.message, post, back_data)
    await callback.answer("Медиа удалено")


@router.message(EditPost.value)
async def edit_post_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    post_id = data.get("post_id")
    back_data = data.get("back_data")
    if not post_id:
        await state.clear()
        return

    with SessionLocal() as db:
        post = db.get(Post, post_id)
        if post:
            post.text = message.html_text or getattr(message, 'html_caption', None) or message.text or message.caption or ""
            db.commit()
            await send_preview(db, message, post, back_data)
        else:
            await message.answer("Пост не нашел.")
    await state.clear()


@router.message(EditMedia.value, F.photo | F.video | F.document)
async def edit_media_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    post_id = data.get("post_id")
    back_data = data.get("back_data")
    if not post_id:
        await state.clear()
        return

    with SessionLocal() as db:
        post = db.get(Post, post_id)
        if post:
            if message.photo:
                post.media_id = message.photo[-1].file_id
                post.media_type = "photo"
            elif message.video:
                post.media_id = message.video.file_id
                post.media_type = "video"
            elif message.document:
                post.media_id = message.document.file_id
                post.media_type = "document"
            db.commit()
            await send_preview(db, message, post, back_data)
        else:
            await message.answer("Пост не нашел.")
    await state.clear()


@router.callback_query(F.data.startswith("preview:"))
async def preview_post_fallback(callback: CallbackQuery) -> None:
    # Just in case for direct backs
    parts = callback.data.split(":", 1)
    if len(parts) > 1 and parts[1].startswith(("pv:", "cq:", "pq:")):
        await preview_post_start(callback)
    else:
        await callback.answer("Неверная кнопка")


@router.callback_query(F.data.startswith("cancel:"))
async def cancel_preview(callback: CallbackQuery) -> None:
    parts = callback.data.split(":", 2)
    back_data = parts[2]
    
    try:
        await callback.message.delete()
    except Exception:
        pass
        
    if back_data.startswith("pv:"):
        post_id = int(back_data.split(":")[1])
        with SessionLocal() as db:
            post = db.get(Post, post_id)
            if not post:
                await callback.answer("Пост не нашел", show_alert=True)
                return
            await callback.message.answer(
                post_text(post),
                reply_markup=post_actions(post.id, "posts:folder:candidate:page:1"),
            )
        await callback.answer()
    elif back_data.startswith("cq:"):
        _, post_id, page = back_data.split(":")
        await render_post_queue(callback, "candidate", int(page), edit=False)
    elif back_data.startswith("pq:"):
        _, post_id, folder, page = back_data.split(":")
        await render_post_queue(callback, folder, int(page), edit=False)
    else:
        await callback.answer("Непонятный возврат")


@router.callback_query(F.data.startswith("confirm:"))
async def confirm_publish(callback: CallbackQuery) -> None:
    parts = callback.data.split(":", 2)
    post_id = int(parts[1])
    back_data = parts[2]
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        post = db.get(Post, post_id)
        if not post:
            await callback.answer("Пост не нашел")
            return
            
        text = render_preview_text(db, post)
        has_media = bool(post.media_id)
        limit = 1024 if has_media else 4096
        
        # Check if the text is empty or too short
        soft_promo = [k.word for k in db.query(Keyword).filter(Keyword.kind == "soft_promo", Keyword.is_active.is_(True)).all()]
        cleaned_text = clean_post_text(post.text or "", soft_promo)
        plain_text = re.sub(r'<[^>]+>', '', cleaned_text).strip()
        if len(plain_text) < 10:
            await callback.answer("Текст пустой или слишком короткий! Публикация отменена.", show_alert=True)
            return
            
        if len(text) > limit:
            await callback.answer(f"Текст слишком длинный ({len(text)} > {limit})! Укоротите его.", show_alert=True)
            return
        
        publish_channel = db.query(PublishChannel).filter_by(is_active=True).first()
        if not publish_channel:
            await callback.answer("Не настроен активный Publish Channel в настройках!", show_alert=True)
            return
        
        exchange = db.query(Exchange).filter_by(name="bingx").first()
        pub_markup = None
        if exchange and exchange.referral_link:
            pub_markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Trade on BingX", url=exchange.referral_link)]
            ])
            
        try:
            if has_media:
                if post.media_type == "photo":
                    await callback.bot.send_photo(chat_id=publish_channel.channel_id, photo=post.media_id, caption=text, reply_markup=pub_markup, parse_mode="HTML")
                elif post.media_type == "video":
                    await callback.bot.send_video(chat_id=publish_channel.channel_id, video=post.media_id, caption=text, reply_markup=pub_markup, parse_mode="HTML")
                else:
                    await callback.bot.send_document(chat_id=publish_channel.channel_id, document=post.media_id, caption=text, reply_markup=pub_markup, parse_mode="HTML")
            else:
                await callback.bot.send_message(
                    chat_id=publish_channel.channel_id,
                    text=text,
                    reply_markup=pub_markup,
                    parse_mode="HTML"
                )
        except Exception as exc:
            await callback.answer(f"Ошибка отправки в канал (HTML?): {exc}", show_alert=True)
            return

    message = await apply_post_action(post_id, "published")
    
    try:
        await callback.message.delete()
    except Exception:
        pass
        
    if back_data.startswith("pv:"):
        await callback.message.answer(message, reply_markup=back("posts:folder:candidate:page:1"))
        await callback.answer(message)
    elif back_data.startswith("cq:"):
        _, _, page = back_data.split(":")
        await render_post_queue(callback, "candidate", int(page), answer=True, toast=message, edit=False)
    elif back_data.startswith("pq:"):
        _, _, folder, page = back_data.split(":")
        await render_post_queue(callback, folder, int(page), answer=True, toast=message, edit=False)
    else:
        await callback.answer(message)


async def apply_post_action(post_id: int, status: str) -> str:
    changed_count = 0
    with SessionLocal() as db:
        post = db.get(Post, post_id)
        if not post:
            return "Пост не нашел"
        if status == "bad_source" and post.channel_id:
            changed_count = mark_bad_source(db, post)
            ok = True
        elif status == "not_signal":
            mark_not_signal(db, post)
            ok = True
            changed_count = 1
        elif status == "published":
            mark_published(db, post)
            ok = True
            changed_count = 1
        elif status == "skipped":
            mark_skipped(db, post)
            ok = True
            changed_count = 1
        else:
            ok = False
        db.commit()
    if not ok:
        return "Статус не понял"
    messages = {
        "published": "Ок, отметил как опубликованный.",
        "skipped": "Ок, убрал в архив.",
        "not_signal": "Ок, отметил как не сигнал.",
        "bad_source": f"Ок, источник сразу заблокирован. Постов убрано: {changed_count}.",
    }
    return messages.get(status, "Ок, статус обновил.")

# ===== FILTERS UI =====

from app.bot.states import FilterHashtag, FilterSource

async def get_filters_menu_content(state: FSMContext) -> tuple[str, InlineKeyboardMarkup]:
    data = await state.get_data()
    filters = data.get("post_filters", {})
    
    priority_text = filters.get("priority") or "Любой"
    hashtag_text = filters.get("hashtag") or "Любой"
    source_text = filters.get("source") or "Любой"
    hours_text = f"Последние {filters['hours']}ч" if filters.get("hours") else "За все время"
    
    text = (
        "<b>Настройки фильтров</b>\n\n"
        f"Приоритет: <code>{priority_text}</code>\n"
        f"Хэштег: <code>{hashtag_text}</code>\n"
        f"Источник: <code>{source_text}</code>\n"
        f"Время: <code>{hours_text}</code>\n\n"
        "Выберите, что изменить:"
    )
    
    buttons = [
        [("⭐️ Приоритет", "posts:filter:priority")],
        [("#️⃣ Хэштег", "posts:filter:hashtag"), ("📢 Источник", "posts:filter:source")],
        [("⏱ Время", "posts:filter:time")],
        [("❌ Сбросить фильтры", "posts:filter:reset")],
        [("👁 Показать кандидатов", "posts:filterview:candidate:1")],
        [("👁 Показать все посты", "posts:filterview:all:1")],
        [("🔙 Назад к постам", "menu:posts")]
    ]
    return text, kb(buttons)

@router.callback_query(F.data == "posts:expire")
async def posts_expire(callback: CallbackQuery) -> None:
    with SessionLocal() as db:
        if not await admin_callback(callback, db):
            return
        count = expire_old_candidates(db, older_than_hours=24)
    await callback.answer(f"✅ Перемещено в архив: {count} постов", show_alert=True)


@router.callback_query(F.data == "posts:filters")
async def posts_filters_menu(callback: CallbackQuery, state: FSMContext) -> None:
    text, markup = await get_filters_menu_content(state)
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise
    await callback.answer()

@router.callback_query(F.data == "posts:filter:priority")
async def filter_toggle_priority(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    filters = data.get("post_filters", {})
    
    current = filters.get("priority")
    nxt = {"high": "medium", "medium": "low", "low": None, None: "high"}
    filters["priority"] = nxt[current]
    
    await state.update_data(post_filters=filters)
    await posts_filters_menu(callback, state)

@router.callback_query(F.data == "posts:filter:time")
async def filter_toggle_time(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    filters = data.get("post_filters", {})
    
    current = filters.get("hours")
    nxt = {None: 24, 24: 12, 12: 6, 6: 1, 1: None}
    filters["hours"] = nxt[current]
    
    await state.update_data(post_filters=filters)
    await posts_filters_menu(callback, state)

@router.callback_query(F.data == "posts:filter:reset")
async def filter_reset(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(post_filters={})
    await posts_filters_menu(callback, state)

@router.callback_query(F.data == "posts:filter:cancel_input")
async def filter_cancel_input(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await posts_filters_menu(callback, state)

@router.callback_query(F.data == "posts:filter:hashtag")
async def filter_ask_hashtag(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FilterHashtag.value)
    await callback.message.edit_text(
        "Отправь хэштег для фильтрации (например, #TON).",
        reply_markup=kb([[("Отмена", "posts:filter:cancel_input")]])
    )
    await callback.answer()

@router.callback_query(F.data == "posts:filter:source")
async def filter_ask_source(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FilterSource.value)
    await callback.message.edit_text(
        "Отправь название, username или ID канала для фильтрации.",
        reply_markup=kb([[("Отмена", "posts:filter:cancel_input")]])
    )
    await callback.answer()

@router.message(FilterHashtag.value)
async def filter_set_hashtag(message: Message, state: FSMContext) -> None:
    val = message.text.strip()
    if val.lower() != "/cancel":
        data = await state.get_data()
        filters = data.get("post_filters", {})
        filters["hashtag"] = val
        await state.update_data(post_filters=filters)
    
    await state.set_state(None)
    text, markup = await get_filters_menu_content(state)
    await message.answer(text, reply_markup=markup)

@router.message(FilterSource.value)
async def filter_set_source(message: Message, state: FSMContext) -> None:
    val = message.text.strip()
    if val.lower() != "/cancel":
        data = await state.get_data()
        filters = data.get("post_filters", {})
        filters["source"] = val
        await state.update_data(post_filters=filters)
    
    await state.set_state(None)
    text, markup = await get_filters_menu_content(state)
    await message.answer(text, reply_markup=markup)
