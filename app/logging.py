"""
Logging configuration for Congress Trade Tracker using Loguru.
Provides structured logging with better defaults and automatic exception handling.
"""

import sys
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
