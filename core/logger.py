import logging
from datetime import datetime

def build_logger(root):
    folder = root / "logs"; folder.mkdir(exist_ok=True)
    log = logging.getLogger("shopee_autopost"); log.setLevel(logging.INFO)
    if not log.handlers:
        handler = logging.FileHandler(folder / f"{datetime.now():%Y-%m-%d}.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")); log.addHandler(handler)
    return log
