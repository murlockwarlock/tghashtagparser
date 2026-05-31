from aiogram.types import CallbackQuery, Message
from sqlalchemy.orm import Session

from app.db.models import Admin


def is_admin(db: Session, user_id: int) -> bool:
    return bool(
        db.query(Admin)
        .filter(Admin.telegram_id == user_id, Admin.is_active.is_(True))
        .first()
    )


async def admin_message(message: Message, db: Session) -> bool:
    if not message.from_user or not is_admin(db, message.from_user.id):
        await message.answer("⛔ Нет доступа")
        return False
    return True


async def admin_callback(callback: CallbackQuery, db: Session) -> bool:
    if not callback.from_user or not is_admin(db, callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return False
    return True
