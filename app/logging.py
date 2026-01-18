"""
Logging configuration for Congress Trade Tracker using Loguru.
Provides structured logging with better defaults and automatic exception handling.
"""

import sys
from pathlib import Path
from typing import Any

from loguru import logger


def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    """
    Configure application logging using Loguru.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: If True, use JSON formatter; otherwise use human-readable format
    """
    # Remove default handler
    logger.remove()

    # Ensure logs directory exists
    logs_dir = Path("./logs")
    logs_dir.mkdir(exist_ok=True)

    # Configure format based on preference
    if json_format:
        # JSON format for production/parsing
        logger.add(
            sys.stdout,
            level=level.upper(),
            format="{message}",
            serialize=True,  # This makes Loguru output JSON
            backtrace=True,
            diagnose=True,
        )
    else:
        # Human-readable format for development
        logger.add(
            sys.stdout,
            level=level.upper(),
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level:8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
                "<level>{message}</level>"
            ),
            colorize=True,
            backtrace=True,
            diagnose=True,
        )

    # Add file handler - main application log with rotation
    logger.add(
        logs_dir / "app.log",
        level=level.upper(),
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level:8} | "
            "{name}:{function} | "
            "{message}"
        ),
        rotation="10 MB",  # Rotate when file reaches 10MB
        retention="30 days",  # Keep logs for 30 days
        compression="zip",  # Compress rotated logs
        backtrace=True,
        diagnose=True,
    )

    # Add daily operations log - specifically for reviewing daily runs
    logger.add(
        logs_dir / "daily_operations_{time:YYYY-MM-DD}.log",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:8} | {message}",
        rotation="00:00",  # New file each day at midnight
        retention="90 days",  # Keep daily logs for 90 days
        filter=lambda record: "daily_operation" in record["extra"]
            or "CLI" in record["extra"]
            or record["name"] == "app.run",
    )

    # Reduce noise from third-party libraries by filtering
    logger.disable("urllib3")
    logger.disable("requests")
    logger.disable("httpx")
    logger.disable("ib_insync")


def get_logger(name: str):
    """
    Get a logger instance for a module.

    Note: Loguru uses a single global logger, so this returns the same logger
    with the module name bound to it for context.
    """
    return logger.bind(name=name)


# Convenience function for adding structured context to logs (for backward compatibility)
def log_with_context(log: Any, level: str, message: str, **context: Any) -> None:
    """
    Log a message with additional context fields.

    Args:
        log: Logger instance (Loguru logger)
        level: Log level (debug, info, warning, error, critical)
        message: Log message
        **context: Additional key-value pairs to include in log
    """
    # Bind context to logger and log at the specified level
    bound_logger = log.bind(**context)
    log_func = getattr(bound_logger, level.lower())
    log_func(message)


# Re-export logger for convenience
__all__ = ["logger", "setup_logging", "get_logger", "log_with_context"]
