import base64
import functools
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

PREFIX = "enc:"


def key_path() -> Path:
    raw = os.getenv("SECRET_KEY_PATH", "data/secret.key")
    return Path(raw)


def load_key() -> bytes:
    path = key_path()
    if path.exists():
        return path.read_bytes().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    path.write_bytes(key)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return key


@functools.lru_cache(maxsize=1)
def fernet() -> Fernet:
    return Fernet(load_key())


def encrypt_secret(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    if value.startswith(PREFIX):
        return value
    token = fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return f"{PREFIX}{token}"


def decrypt_secret(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    if not value.startswith(PREFIX):
        return value
    token = value.removeprefix(PREFIX)
    try:
        return fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return value


def mask_secret(value: str | None) -> str:
    raw = decrypt_secret(value)
    if not raw:
        return "не задан"
    if len(raw) <= 8:
        return "***"
    return f"{raw[:4]}...{raw[-4:]}"
