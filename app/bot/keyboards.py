from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows
        ]
    )


def main_menu() -> InlineKeyboardMarkup:
    return kb(
        [
            [("Хэштеги", "menu:tags"), ("Поиск", "search:run")],
            [("Посты", "menu:posts"), ("Фильтры", "menu:filters")],
            [("TG аккаунты", "menu:accounts"), ("Прокси", "menu:proxies")],
            [("Каналы", "menu:channels"), ("Настройки", "menu:settings")],
            [("Стата", "stats"), ("Статус", "status")],
            [("🚫 Черный список", "menu:blacklist")],
        ]
    )


def back(to: str = "menu:main") -> InlineKeyboardMarkup:
    return kb([[("Назад", to)]])


def pager(
    prefix: str,
    page: int,
    total_pages: int,
    back_to: str = "menu:main",
) -> InlineKeyboardMarkup:
    prev_page = page - 1 if page > 1 else total_pages
    next_page = page + 1 if page < total_pages else 1
    return kb(
        [
            [
                ("пред", f"{prefix}:{prev_page}"),
                (f"{page}/{total_pages}", "noop"),
                ("след", f"{prefix}:{next_page}"),
            ],
            [("Назад", back_to)],
        ]
    )


def post_actions(post_id: int, back_to: str = "posts:folder:candidate:page:1") -> InlineKeyboardMarkup:
    return kb(
        [
            [("✅ Publish", f"preview:pv:{post_id}")],
            [("⏭ Skip", f"post:{post_id}:skipped")],
            [("🗑 Not a signal", f"post:{post_id}:not_signal"), ("🚫 Bad source", f"post:{post_id}:ask_bad")],
            [("Назад", back_to)],
        ]
    )


def candidate_actions(post_id: int, page: int, total: int) -> InlineKeyboardMarkup:
    prev_page = page - 1 if page > 1 else total
    next_page = page + 1 if page < total else 1
    return kb(
        [
            [
                ("⬅️ пред", f"candidate_queue:page:{prev_page}"),
                (f"{page}/{total}", "noop"),
                ("след ➡️", f"candidate_queue:page:{next_page}"),
            ],
            [("✅ Publish", f"preview:cq:{post_id}:{page}")],
            [("⏭ Skip", f"candidate_queue:action:{post_id}:skipped:{page}")],
            [("🗑 Not a signal", f"candidate_queue:action:{post_id}:not_signal:{page}")],
            [("🚫 Bad source", f"candidate_queue:action:{post_id}:ask_bad:{page}")],
        ]
    )


def post_queue_actions(post_id: int, folder: str, page: int, total: int) -> InlineKeyboardMarkup:
    prev_page = page - 1 if page > 1 else total
    next_page = page + 1 if page < total else 1
    return kb(
        [
            [
                ("⬅️ пред", f"post_queue:page:{folder}:{prev_page}"),
                (f"{page}/{total}", "noop"),
                ("след ➡️", f"post_queue:page:{folder}:{next_page}"),
            ],
            [("✅ Publish", f"preview:pq:{post_id}:{folder}:{page}")],
            [("⏭ Skip", f"post_queue:action:{post_id}:skipped:{folder}:{page}")],
            [("🗑 Not a signal", f"post_queue:action:{post_id}:not_signal:{folder}:{page}")],
            [("🚫 Bad source", f"post_queue:action:{post_id}:ask_bad:{folder}:{page}")],
            [("Назад", f"posts:folder:{folder}:page:1")],
        ]
    )


def preview_actions(post_id: int, back_data: str, has_media: bool = False) -> InlineKeyboardMarkup:
    rows = []
    rows.append([("✏️ Редактировать текст", f"preview:edit_text:{post_id}:{back_data}")])
    if has_media:
        rows.append([("🗑 Удалить медиа", f"preview:remove_media:{post_id}:{back_data}")])
    else:
        rows.append([("🖼 Добавить медиа", f"preview:add_media:{post_id}:{back_data}")])
    rows.append([("✅ Confirm publish", f"confirm:{post_id}:{back_data}")])
    rows.append([("❌ Cancel", f"cancel:{post_id}:{back_data}")])
    return kb(rows)

def blacklist_actions(sources: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = []
    for s in sources:
        name = s.channel_name or s.username or str(s.channel_id)
        if len(name) > 20:
            name = name[:18] + ".."
        rows.append([(f"🔓 Разблокировать {name}", f"blacklist:ask:{s.id}:{page}")])
    
    if total_pages > 1:
        prev_page = page - 1 if page > 1 else total_pages
        next_page = page + 1 if page < total_pages else 1
        rows.append([
            ("⬅️ пред", f"blacklist:page:{prev_page}"),
            (f"{page}/{total_pages}", "noop"),
            ("след ➡️", f"blacklist:page:{next_page}")
        ])
    
    rows.append([("Назад", "menu:main")])
    return kb(rows)
