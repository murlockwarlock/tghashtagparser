from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(128), nullable=True)
    full_name = Column(String(255), nullable=True)
    role = Column(String(32), default="admin", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    value_type = Column(String(32), default="str", nullable=False)
    is_secret = Column(Boolean, default=False, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Proxy(Base):
    __tablename__ = "proxies"

    id = Column(Integer, primary_key=True)
    title = Column(String(128), nullable=False)
    proxy_type = Column(String(16), default="socks5", nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(255), nullable=True)
    password = Column(String(255), nullable=True)
    country = Column(String(64), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_checked_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    accounts = relationship("TelegramAccount", back_populates="proxy")


class TelegramAccount(Base):
    __tablename__ = "telegram_accounts"

    id = Column(Integer, primary_key=True)
    title = Column(String(128), unique=True, nullable=False)
    api_id = Column(Integer, nullable=False)
    api_hash = Column(String(255), nullable=False)
    phone = Column(String(64), nullable=False)
    session_string = Column(Text, nullable=False)
    proxy_id = Column(Integer, ForeignKey("proxies.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    status = Column(String(32), default="active", nullable=False)
    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    flood_wait_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    proxy = relationship("Proxy", back_populates="accounts")


class Hashtag(Base):
    __tablename__ = "hashtags"

    id = Column(Integer, primary_key=True)
    tag = Column(String(64), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Keyword(Base):
    __tablename__ = "keywords"

    id = Column(Integer, primary_key=True)
    word = Column(String(128), nullable=False)
    kind = Column(String(16), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("word", "kind", name="uq_keywords_word_kind"),)


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    channel_id = Column(BigInteger, unique=True, nullable=False, index=True)
    channel_name = Column(String(255), nullable=True)
    username = Column(String(128), nullable=True)
    status = Column(String(32), default="active", nullable=False)
    bad_source_score = Column(Integer, default=0, nullable=False)
    is_blacklisted = Column(Boolean, default=False, nullable=False)
    blacklisted_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True)
    channel_id = Column(BigInteger, nullable=False)
    channel_name = Column(String(255), nullable=True)
    username = Column(String(128), nullable=True)
    message_id = Column(BigInteger, nullable=False)
    post_link = Column(String(512), nullable=True)
    published_at = Column(DateTime, nullable=True)
    parsed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    hashtag = Column(String(64), nullable=False)
    text = Column(Text, nullable=False)
    text_hash = Column(String(64), nullable=False)
    status = Column(String(32), default="new", nullable=False)
    reason = Column(String(255), nullable=True)
    priority = Column(String(16), nullable=True)
    label = Column(String(32), nullable=True)
    media_id = Column(String(255), nullable=True)
    media_type = Column(String(32), nullable=True)
    account_id = Column(Integer, ForeignKey("telegram_accounts.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("channel_id", "message_id", name="uq_posts_channel_message"),
        UniqueConstraint("text_hash", name="uq_posts_text_hash"),
        Index("ix_posts_status", "status"),
        Index("ix_posts_hashtag", "hashtag"),
        Index("ix_posts_published_at", "published_at"),
    )


class SearchRun(Base):
    __tablename__ = "search_runs"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(32), default="running", nullable=False)
    account_id = Column(Integer, ForeignKey("telegram_accounts.id"), nullable=True)
    tags_count = Column(Integer, default=0, nullable=False)
    found_count = Column(Integer, default=0, nullable=False)
    saved_count = Column(Integer, default=0, nullable=False)
    candidate_count = Column(Integer, default=0, nullable=False)
    error = Column(Text, nullable=True)
    last_error = Column(Text, nullable=True)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    kind = Column(String(64), nullable=False, index=True)
    status = Column(String(32), default="pending", nullable=False, index=True)
    payload_json = Column(Text, nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    locked_at = Column(DateTime, nullable=True)
    locked_by = Column(String(128), nullable=True)
    run_after = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_by_admin_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AiProvider(Base):
    __tablename__ = "ai_providers"

    id = Column(Integer, primary_key=True)
    provider = Column(String(64), default="openai", nullable=False)
    api_key = Column(Text, nullable=True)
    selected_model = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Exchange(Base):
    __tablename__ = "exchanges"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), default="bingx", nullable=False)
    api_key = Column(Text, nullable=True)
    api_secret = Column(Text, nullable=True)
    referral_link = Column(String(512), nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PublishChannel(Base):
    __tablename__ = "publish_channels"

    id = Column(Integer, primary_key=True)
    title = Column(String(128), nullable=False)
    channel_id = Column(String(128), nullable=False)
    username = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class TradingPair(Base):
    __tablename__ = "trading_pairs"

    id = Column(Integer, primary_key=True)
    exchange = Column(String(64), default="bingx", nullable=False)
    symbol = Column(String(64), nullable=False)
    base_asset = Column(String(32), nullable=False)
    quote_asset = Column(String(32), default="USDT", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint("exchange", "symbol", name="uq_trading_pair_exchange_symbol"),
    )


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    symbol = Column(String(64), nullable=True)
    direction = Column(String(16), nullable=True)
    entry_min = Column(Float, nullable=True)
    entry_max = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profits_json = Column(Text, nullable=True)
    leverage = Column(String(64), nullable=True)
    confidence = Column(Float, nullable=True)
    ai_raw_json = Column(Text, nullable=True)
    status = Column(String(32), default="draft", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class BlacklistedChannel(Base):
    __tablename__ = "blacklisted_channels"

    id = Column(Integer, primary_key=True)
    channel_id = Column(BigInteger, unique=True, nullable=False, index=True)
    channel_name = Column(String(255), nullable=True)
    username = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
