from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Post, SearchRun, TelegramAccount, Source


def status_text(db: Session) -> str:
    accounts = db.query(TelegramAccount).count()
    active_accounts = (
        db.query(TelegramAccount)
        .filter(TelegramAccount.is_active.is_(True))
        .count()
    )
    posts = db.query(Post).count()
    candidates = db.query(Post).filter(Post.status == "candidate").count()
    last_run = db.query(SearchRun).order_by(SearchRun.id.desc()).first()
    run_text = "еще не запускали"
    if last_run:
        tr_status = {"done": "успешно", "error": "ошибка", "rate_limited": "лимиты"}.get(last_run.status, last_run.status)
        run_text = (
            f"№{last_run.id} ({tr_status})\n"
            f"   Найдено: {last_run.found_count}\n"
            f"   Новых сохранено: {last_run.saved_count}\n"
            f"   Кандидатов: {last_run.candidate_count}"
        )
    return (
        f"<b>📊 Статус системы</b>\n\n"
        f"TG Аккаунты (активны): <code>{active_accounts} / {accounts}</code>\n"
        f"Всего постов в БД: <code>{posts}</code>\n"
        f"Ожидают проверки: <code>{candidates}</code>\n\n"
        f"<b>Последний поиск:</b>\n<code>{run_text}</code>"
    )


STATUS_TRANSLATIONS = {
    "candidate": "🔥 Кандидаты (ждут проверки)",
    "filtered_out": "🗑 Отфильтровано (спам автоматом)",
    "skipped": "⏩ Пропущено (вручную)",
    "rejected": "🗑 Отклонено (вручную)",
    "published": "✅ Опубликовано",
    "draft": "📝 Черновики",
    "failed": "❌ Ошибки",
    "rate_limited": "⏳ Лимиты (Rate Limit)",
}

def stats_text(db: Session) -> str:
    total_found = db.query(func.sum(SearchRun.found_count)).scalar() or 0
    total_saved = db.query(Post).count()
    duplicates = total_found - total_saved if total_found > total_saved else 0

    candidates = db.query(Post).filter(Post.status == "candidate").count()
    
    empty_message = db.query(Post).filter(Post.status == "filtered_out", Post.reason == "empty_message").count()
    blacklisted_source_auto = db.query(Post).filter(Post.status == "filtered_out", Post.reason == "blacklisted_source").count()
    filtered_out = db.query(Post).filter(Post.status == "filtered_out").filter(Post.reason.notin_(["empty_message", "blacklisted_source"])).count()
    published = db.query(Post).filter(Post.status.in_(["published", "ready_for_ai_preview"])).count()
    not_signal = db.query(Post).filter(Post.status == "rejected", Post.label == "not_signal").count()
    bad_source = db.query(Post).filter(Post.status == "rejected", Post.label == "bad_source").count()
    skipped = db.query(Post).filter(Post.status == "skipped").count()

    high_pri = db.query(Post).filter(Post.status == "candidate", Post.priority == "high").count()
    med_pri = db.query(Post).filter(Post.status == "candidate", Post.priority == "medium").count()
    low_pri = db.query(Post).filter(Post.status == "candidate", Post.priority == "low").count()

    top_tags = (
        db.query(Post.hashtag, func.count(Post.id))
        .filter(Post.status == "candidate")
        .group_by(Post.hashtag)
        .order_by(func.count(Post.id).desc())
        .limit(5)
        .all()
    )

    top_sources = (
        db.query(Post.channel_name, func.count(Post.id))
        .filter(Post.status == "candidate")
        .group_by(Post.channel_name)
        .order_by(func.count(Post.id).desc())
        .limit(5)
        .all()
    )

    bad_sources = (
        db.query(Source.channel_name, Source.bad_source_score)
        .filter(Source.bad_source_score > 0)
        .order_by(Source.bad_source_score.desc())
        .limit(5)
        .all()
    )

    lines = [
        "<b>📊 Детальная статистика</b>\n",
        f"🔍 <b>Глобальный поиск:</b>",
        f"├ Всего найдено: <code>{total_found}</code>",
        f"├ Дубликаты (отброшено): <code>{duplicates}</code>",
        f"└ Сохранено уникальных: <code>{total_saved}</code>\n",
        f"🎯 <b>Воронка обработки:</b>",
        f"├ Отфильтровано (пустые): <code>{empty_message}</code>",
        f"├ Отфильтровано (черный список): <code>{blacklisted_source_auto}</code>",
        f"├ Отфильтровано (спам): <code>{filtered_out}</code>",
        f"├ Не сигнал (руками): <code>{not_signal}</code>",
        f"├ Плохой источник (руками): <code>{bad_source}</code>",
        f"├ Пропущено (скип): <code>{skipped}</code>",
        f"├ Опубликовано: <code>{published}</code>",
        f"└ 🔥 <b>Кандидаты:</b> <code>{candidates}</code>\n",
        f"⭐ <b>Приоритет кандидатов:</b>",
        f"├ High: <code>{high_pri}</code>",
        f"├ Medium: <code>{med_pri}</code>",
        f"└ Low: <code>{low_pri}</code>\n"
    ]

    if top_tags:
        lines.append("🏷 <b>Топ хэштегов (по кандидатам):</b>")
        for tag, cnt in top_tags:
            lines.append(f"├ {tag}: <code>{cnt}</code>")
        lines.append("")

    if top_sources:
        lines.append("🏆 <b>Топ источников (лучшие сигналы):</b>")
        for src, cnt in top_sources:
            lines.append(f"├ {src or 'Без названия'}: <code>{cnt}</code>")
        lines.append("")

    if bad_sources:
        lines.append("🚫 <b>Топ спамеров (Bad Source Score):</b>")
        for src, score in bad_sources:
            lines.append(f"├ {src or 'Без названия'}: <code>{score}</code> балла(ов)")

    return "\n".join(lines)
