import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path

LOG_DIR = Path(os.getenv('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'minttune' / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / 'minttune.log'

def setup_logger():
    logger = logging.getLogger("minttune")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
