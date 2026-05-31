from datetime import timedelta
import re

from app.db.models import Post
from app.utils.text import html_escape, trim
from app.utils.html_utils import fix_unclosed_html_tags


def post_status_display(post: Post) -> str:
    if post.label == "expired" and post.status == "skipped":
        return "expired"
    if post.status == "rejected" and post.label:
        return f"{post.status} / {post.label}"
    return post.status


def render_post_body(text: str, limit: int) -> str:
    trimmed = fix_unclosed_html_tags(trim(text or "", limit))
    return telegram_spoiler_html(trimmed, escaped=False)


def telegram_spoiler_html(text: str, escaped: bool = False) -> str:
    if escaped:
        return re.sub(r"&lt;(/?)spoiler&gt;", r"<\1tg-spoiler>", text, flags=re.IGNORECASE)
    return re.sub(r"<(/?)spoiler>", r"<\1tg-spoiler>", text, flags=re.IGNORECASE)


def post_text(post: Post) -> str:
    source = post.channel_name or post.username or post.channel_id
    link = f'\n<a href="{html_escape(post.post_link)}">Открыть пост</a>' if post.post_link else ""

    pub_date_str = str(post.published_at)
    if post.published_at:
        msk_date = post.published_at + timedelta(hours=3)
        pub_date_str = msk_date.strftime("%d.%m.%Y %H:%M МСК")

    status_display = post_status_display(post)
    
    header = (
        f"<b>Пост #{post.id}</b>\n"
        f"Статус: <code>{html_escape(status_display)}</code>\n"
        f"Причина: <code>{html_escape(post.reason or 'не указана')}</code>\n"
        f"Приоритет: <code>{html_escape(post.priority or 'нет')}</code>\n"
        f"Источник: <code>{html_escape(source)}</code>\n"
        f"Хэштег: <code>{html_escape(post.hashtag)}</code>\n"
        f"Дата: <code>{html_escape(pub_date_str)}</code>"
        f"{link}\n\n"
    )

    max_text_len = 4096 - len(header) - 100
    if max_text_len < 0:
        max_text_len = 0

    return header + render_post_body(post.text, max_text_len)
