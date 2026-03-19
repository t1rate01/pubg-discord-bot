import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
LOG_PATH = DATA_DIR / "app.log"


def setup_logging() -> None:
    DATA_DIR.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    if not root.handlers:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)

        file_handler = RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)