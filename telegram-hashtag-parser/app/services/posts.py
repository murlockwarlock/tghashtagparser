from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.db.models import BlacklistedChannel, Post, Source
from app.utils.text import text_hash


def make_post_link(username: str | None, channel_id: int | None, message_id: int) -> str | None:
    if username:
        return f"https://t.me/{username.lstrip('@')}/{message_id}"
    if channel_id and str(channel_id).startswith("-100"):
        return f"https://t.me/c/{str(channel_id)[4:]}/{message_id}"
    return None


def save_post(
    db: Session,
    *,
    channel_id: int,
    channel_name: str | None,
    username: str | None,
    message_id: int,
    published_at: datetime | None,
    hashtag: str,
    text: str,
    status: str,
    reason: str | None = None,
    priority: str | None = None,
    label: str | None = None,
    account_id: int | None = None,
) -> tuple[Post | None, bool]:
    upsert_source(db, channel_id, channel_name, username)
    post = Post(
        channel_id=channel_id,
        channel_name=channel_name,
        username=username,
        message_id=message_id,
        post_link=make_post_link(username, channel_id, message_id),
        published_at=published_at,
        parsed_at=datetime.utcnow(),
        hashtag=hashtag,
        text=text,
        text_hash=text_hash(text),
        status=status,
        reason=reason,
        priority=priority,
        label=label,
        account_id=account_id,
    )
    db.add(post)
    try:
        db.flush()
        return post, True
    except IntegrityError:
        db.rollback()
        return None, False


def update_status(db: Session, post_id: int, status: str) -> bool:
    post = db.get(Post, post_id)
    if not post:
        return False
    post.status = status
    return True


def upsert_source(
    db: Session,
    channel_id: int,
    channel_name: str | None,
    username: str | None,
) -> Source:
    source = db.query(Source).filter(Source.channel_id == channel_id).first()
    if not source:
        source = Source(channel_id=channel_id)
        db.add(source)
    source.channel_name = channel_name
    source.username = username
    source.last_seen_at = datetime.utcnow()
    return source


def mark_not_signal(db: Session, post: Post) -> None:
    post.status = "rejected"
    post.label = "not_signal"


def mark_published(db: Session, post: Post) -> None:
    post.status = "published"
    post.label = "good_signal"


def mark_skipped(db: Session, post: Post) -> None:
    post.status = "skipped"
    post.label = "neutral"


def mark_bad_source(db: Session, post: Post) -> int:
    source = upsert_source(db, post.channel_id, post.channel_name, post.username)
    source.bad_source_score = (source.bad_source_score or 0) + 1
    source.is_blacklisted = True
    source.status = "blacklisted"
    source.blacklisted_at = datetime.utcnow()

    exists = db.query(BlacklistedChannel).filter_by(channel_id=post.channel_id).first()
    if not exists:
        db.add(
            BlacklistedChannel(
                channel_id=post.channel_id,
                channel_name=post.channel_name,
                username=post.username,
            )
        )

    filters = [Post.channel_id == post.channel_id]
    if post.channel_name:
        filters.append(Post.channel_name == post.channel_name)
    if post.username:
        filters.append(Post.username == post.username)

    return (
        db.query(Post)
        .filter(or_(*filters))
        .filter(Post.status == "candidate")
        .update(
            {
                Post.status: "rejected",
                Post.label: "bad_source",
            },
            synchronize_session=False,
        )
    )


def expire_old_candidates(db: Session, older_than_hours: int = 24) -> int:
    """Move candidate posts older than N hours to skipped/expired."""
    threshold = datetime.utcnow() - timedelta(hours=older_than_hours)
    count = (
        db.query(Post)
        .filter(Post.status == "candidate")
        .filter(Post.published_at < threshold)
        .update(
            {Post.status: "skipped", Post.label: "expired"},
            synchronize_session=False,
        )
    )
    db.commit()
    return count
