import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import LOG_DIR


def setup_logging() -> logging.Logger:
    Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("rag_app")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = RotatingFileHandler(
            filename=str(Path(LOG_DIR) / "app.log"),
            maxBytes=2_000_000,
            backupCount=5,
        )
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logging()