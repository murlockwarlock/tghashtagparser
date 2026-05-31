import re

from sqlalchemy.orm import Session

from app.db.models import Hashtag

TAG_RE = re.compile(r"^#[A-Za-z0-9_]{2,32}$")


def normalize_tag(tag: str) -> str:
    value = tag.strip()
    if not value.startswith("#"):
        value = f"#{value}"
    value = value.upper()
    if not TAG_RE.match(value):
        raise ValueError("Hashtag must look like #TOKEN")
    return value


def list_tags(db: Session, active_only: bool = False) -> list[Hashtag]:
    query = db.query(Hashtag)
    if active_only:
        query = query.filter(Hashtag.is_active.is_(True))
    return query.order_by(Hashtag.tag.asc()).all()


def add_tag(db: Session, tag: str) -> Hashtag:
    normalized = normalize_tag(tag)
    existing = db.query(Hashtag).filter(Hashtag.tag == normalized).first()
    if existing:
        existing.is_active = True
        return existing
    item = Hashtag(tag=normalized, is_active=True)
    db.add(item)
    db.flush()
    return item


def remove_tag(db: Session, tag: str) -> bool:
    normalized = normalize_tag(tag)
    legacy = tag.strip()
    if not legacy.startswith("#"):
        legacy = f"#{legacy}"
    item = db.query(Hashtag).filter(Hashtag.tag.in_((normalized, legacy))).first()
    if not item:
        return False
    item.is_active = False
    return True
