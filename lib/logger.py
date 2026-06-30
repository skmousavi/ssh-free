#!/usr/bin/env python3

import logging
import logging.handlers
import sys

from lib.paths import LOG_DIR

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "ssh-free.log"

RESET = "\033[0m"

COLORS = {
    logging.DEBUG: "\033[36m",
    logging.INFO: "\033[32m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[41m",
}


class ColorFormatter(logging.Formatter):

    def format(self, record):
        color = COLORS.get(record.levelno, "")
        message = super().format(record)
        return f"{color}{message}{RESET}"


class Logger:

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.logger = logging.getLogger("ssh-free")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()

        console = logging.StreamHandler(sys.stdout)
        console.setLevel(logging.INFO)
        console.setFormatter(ColorFormatter("[%(levelname)s] %(message)s"))

        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(filename)s | %(message)s"
            )
        )

        self.logger.addHandler(console)
        self.logger.addHandler(file_handler)

    def set_level(self, level: str):
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
        }
        lvl = level_map.get(level.upper(), logging.INFO)
        for handler in self.logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(
                handler, logging.handlers.RotatingFileHandler
            ):
                handler.setLevel(lvl)

    def debug(self, msg):
        self.logger.debug(msg)

    def info(self, msg):
        self.logger.info(msg)

    def warning(self, msg):
        self.logger.warning(msg)

    def error(self, msg):
        self.logger.error(msg)

    def critical(self, msg):
        self.logger.critical(msg)


log = Logger()
