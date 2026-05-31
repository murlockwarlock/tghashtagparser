import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: set[int]
    database_url: str
    log_dir: str


def _parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        value = part.strip()
        if value:
            ids.add(int(value))
    return ids


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))
    database_url = os.getenv("DATABASE_URL", "sqlite:///data/app.db").strip()
    log_dir = os.getenv("LOG_DIR", "logs").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required")
    if not admin_ids:
        raise RuntimeError("ADMIN_IDS is required")
    return Config(
        bot_token=bot_token,
        admin_ids=admin_ids,
        database_url=database_url,
        log_dir=log_dir,
    )
