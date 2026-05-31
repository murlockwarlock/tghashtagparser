from sqlalchemy.orm import Session

from app.db.models import Setting


def get_setting(db: Session, key: str, default: str | None = None) -> str | None:
    item = db.query(Setting).filter(Setting.key == key).first()
    return item.value if item else default


def get_int(db: Session, key: str, default: int) -> int:
    try:
        return int(get_setting(db, key, str(default)) or default)
    except ValueError:
        return default


def set_setting(
    db: Session,
    key: str,
    value: str,
    value_type: str = "str",
    is_secret: bool = False,
) -> Setting:
    item = db.query(Setting).filter(Setting.key == key).first()
    if not item:
        item = Setting(key=key, value=value, value_type=value_type, is_secret=is_secret)
        db.add(item)
    else:
        item.value = value
        item.value_type = value_type
        item.is_secret = is_secret
    db.flush()
    return item
