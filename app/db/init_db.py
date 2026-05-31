from app.config import load_config
from app.db.models import Admin, AiProvider, Base, Exchange, Hashtag, Keyword, Setting
from app.db.models import Proxy, TelegramAccount, BlacklistedChannel
from app.db.session import SessionLocal, engine
from app.services.crypto import encrypt_secret
from app.services.tags import normalize_tag

DEFAULT_TAGS = [
    "#BTC",
    "#BTCUSDT",
    "#ETH",
    "#ETHUSDT",
    "#SOL",
    "#SOLUSDT",
    "#DOGE",
    "#DOGEUSDT",
    "#BNB",
    "#BNBUSDT",
]
DEFAULT_INCLUDE = {
    "direction": ["long", "short", "buy", "sell", "buying", "selling", "bullish", "bearish", "лонг", "шорт", "покупка", "продажа", "бай", "селл", "вверх", "вниз"],
    "entry": ["entry", "entries", "entry zone", "buy zone", "sell zone", "open", "open long", "open short", "limit", "limit order", "market entry", "current price", "cmp", "now", "вход", "точка входа", "зона входа", "войти", "заход", "лимитка", "по рынку", "текущая цена", "твх"],
    "target": ["target", "targets", "tp", "tp1", "tp2", "tp3", "take profit", "take-profit", "profit target", "цель", "цели", "таргет", "таргеты", "тейк", "тейки", "тейк профит", "тп", "тп1", "тп2", "тп3"],
    "stop_loss": ["sl", "stop", "stop loss", "stoploss", "stop-loss", "invalidated", "invalidation", "стоп"],
    "setup": ["leverage"],
    "include": ["signal"],
}
DEFAULT_EXCLUDE = {
    "hard_spam": ["airdrop", "axiom", "claim", "free money", "giveaway", "mint", "nft", "presale", "whitelist"],
    "soft_promo": ["bonus", "referral", "join", "vip", "register", "subscribe", "premium", "contact admin"],
    "result_report": ["hit tp", "tp hit", "all targets hit", "target reached", "targets reached", "position closed", "trade closed", "profit booked", "booked profit", "signal result", "trade result", "все цели", "цель достигнута", "цели достигнуты", "тейк достигнут", "тп достигнут", "забрали профит", "закрыли сделку", "сделка закрыта"],
    "exclude": ["casino"],
}
DEFAULT_SETTINGS = {
    "search_limit_per_tag": ("20", "int", "Global search limit per hashtag"),
    "search_pause_seconds": ("3", "int", "Pause between hashtag searches"),
    "search_recent_hours": ("6", "int", "Only keep global search posts newer than N hours"),
    "search_recent_days": ("3", "int", "Only keep global search posts newer than N days"),
    "search_auto_interval_minutes": ("60", "int", "Auto search interval in minutes"),
    "backup_hour": ("7", "int", "Daily database backup hour"),
    "backup_retention_days": ("7", "int", "Local backup archive retention"),
    "ai_enabled": ("false", "bool", "Enable AI analysis"),
    "bingx_sync_enabled": ("false", "bool", "Enable BingX symbols sync"),
}


def init_db() -> None:
    Base.metadata.create_all(engine)
    ensure_sqlite_columns()
    cfg = load_config()
    with SessionLocal() as db:
        for admin_id in cfg.admin_ids:
            if not db.query(Admin).filter(Admin.telegram_id == admin_id).first():
                db.add(Admin(telegram_id=admin_id, role="owner", is_active=True))
        normalize_existing_tags(db)
        for tag in DEFAULT_TAGS:
            normalized = normalize_tag(tag)
            if not db.query(Hashtag).filter(Hashtag.tag == normalized).first():
                db.add(Hashtag(tag=normalized, is_active=True))
        for kind, words in DEFAULT_INCLUDE.items():
            for word in words:
                exists = db.query(Keyword).filter(
                    Keyword.word == word,
                    Keyword.kind == kind,
                ).first()
                if not exists:
                    db.add(Keyword(word=word, kind=kind, is_active=True))
        for kind, words in DEFAULT_EXCLUDE.items():
            for word in words:
                exists = db.query(Keyword).filter(
                    Keyword.word == word,
                    Keyword.kind == kind,
                ).first()
                if not exists:
                    db.add(Keyword(word=word, kind=kind, is_active=True))
        for key, (value, value_type, description) in DEFAULT_SETTINGS.items():
            if not db.query(Setting).filter(Setting.key == key).first():
                db.add(
                    Setting(
                        key=key,
                        value=value,
                        value_type=value_type,
                        description=description,
                    )
                )
        if not db.query(AiProvider).filter(AiProvider.provider == "openai").first():
            db.add(AiProvider(provider="openai", selected_model="gpt-4.1-mini", is_active=False))
        if not db.query(Exchange).filter(Exchange.name == "bingx").first():
            db.add(Exchange(name="bingx", is_active=False))
        encrypt_existing_secrets(db)
        backfill_post_filter_meta(db)
        db.commit()


def ensure_sqlite_columns() -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    columns = {
        "telegram_accounts": {
            "last_error": "TEXT",
            "last_error_at": "DATETIME",
            "last_checked_at": "DATETIME",
            "flood_wait_until": "DATETIME",
        },
        "search_runs": {
            "last_error": "TEXT",
        },
        "proxies": {
            "last_checked_at": "DATETIME",
            "last_error": "TEXT",
        },
        "posts": {
            "reason": "VARCHAR(255)",
            "priority": "VARCHAR(16)",
            "label": "VARCHAR(32)",
            "media_id": "VARCHAR(255)",
            "media_type": "VARCHAR(32)",
        },
        "sources": {
            "bad_source_score": "INTEGER DEFAULT 0 NOT NULL",
            "is_blacklisted": "BOOLEAN DEFAULT 0 NOT NULL",
            "blacklisted_at": "DATETIME",
            "last_seen_at": "DATETIME",
        },
        "jobs": {},
    }
    with engine.begin() as connection:
        for table, expected_columns in columns.items():
            existing = {
                row[1]
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            for column, definition in expected_columns.items():
                if column not in existing:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                    )


def encrypt_existing_secrets(db) -> None:
    for account in db.query(TelegramAccount).all():
        account.api_hash = encrypt_secret(account.api_hash)
        account.session_string = encrypt_secret(account.session_string)
    for proxy in db.query(Proxy).all():
        proxy.password = encrypt_secret(proxy.password)
    for provider in db.query(AiProvider).all():
        provider.api_key = encrypt_secret(provider.api_key)
    for exchange in db.query(Exchange).all():
        exchange.api_key = encrypt_secret(exchange.api_key)
        exchange.api_secret = encrypt_secret(exchange.api_secret)


def normalize_existing_tags(db) -> None:
    for tag in db.query(Hashtag).all():
        try:
            normalized = normalize_tag(tag.tag)
        except ValueError:
            continue
        if tag.tag == normalized:
            continue
        existing = db.query(Hashtag).filter(Hashtag.tag == normalized).first()
        if existing:
            existing.is_active = existing.is_active or tag.is_active
            db.delete(tag)
        else:
            tag.tag = normalized


def backfill_post_filter_meta(db) -> None:
    from app.db.models import Post
    from app.services.filters import classify_text

    posts = (
        db.query(Post)
        .filter(Post.reason.is_(None))
        .filter(Post.status.in_(("candidate", "filtered_out")))
        .limit(5000)
        .all()
    )
    for post in posts:
        result = classify_text(db, post.text)
        post.reason = result.reason
        post.priority = result.priority
        post.label = result.label


if __name__ == "__main__":
    init_db()
