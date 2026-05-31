import os
import pytest

os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("ADMIN_IDS", "123,9876543210123")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.db.models import Base
from app.db.session import engine

Base.metadata.create_all(engine)
