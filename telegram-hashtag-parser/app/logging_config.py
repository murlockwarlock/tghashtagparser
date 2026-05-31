import logging
import logging.handlers
import os
import sys

from app.config import Config


def setup_logging(config: Config) -> None:
    os.makedirs(config.log_dir, exist_ok=True)
    log_path = os.path.join(config.log_dir, "app.log")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_path,
        when="D",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(stream_handler)
    root.addHandler(file_handler)

    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("hydrogram").setLevel(logging.WARNING)
