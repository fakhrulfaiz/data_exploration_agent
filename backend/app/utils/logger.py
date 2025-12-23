import logging
import os
from logging.handlers import TimedRotatingFileHandler
from typing import Optional

from app.core.config import settings


class LoggerManager:
    """Reusable logger manager with shared configuration and handlers."""

    _configured = False
    _level = logging.INFO
    _handlers: list[logging.Handler] = []

    @classmethod
    def configure(cls, level: Optional[str] = None, logs_dir: Optional[str] = None) -> None:
        """
        Configure root logging once with console + rotating file handlers.

        Args:
            level: Override log level (e.g., "DEBUG"). Defaults to settings.log_level.
            logs_dir: Override logs directory. Defaults to settings.logs_dir.
        """
        if cls._configured:
            return

        log_level_str = (level or settings.log_level).upper()
        cls._level = getattr(logging, log_level_str, logging.INFO)

        log_directory = logs_dir or settings.logs_dir
        os.makedirs(log_directory, exist_ok=True)

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        console_handler = logging.StreamHandler()
        console_handler.setLevel(cls._level)
        console_handler.setFormatter(formatter)

        file_path = os.path.join(log_directory, "app.log")
        file_handler = TimedRotatingFileHandler(
            file_path,
            when="midnight",
            backupCount=settings.log_retention_days,
            encoding="utf-8",
        )
        file_handler.setLevel(cls._level)
        file_handler.setFormatter(formatter)

        cls._handlers = [console_handler, file_handler]

        root_logger = logging.getLogger()
        root_logger.setLevel(cls._level)
        for handler in cls._handlers:
            root_logger.addHandler(handler)

        cls._configured = True

    @classmethod
    def get_logger(cls, name: str, level: Optional[str] = None) -> logging.Logger:
        """Return a configured logger instance."""
        if not cls._configured:
            cls.configure(level=level)

        logger = logging.getLogger(name)
        if level:
            logger.setLevel(getattr(logging, level.upper(), cls._level))
        return logger


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """Convenience wrapper to fetch a configured logger."""
    return LoggerManager.get_logger(name, level)







