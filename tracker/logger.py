"""Logging configuration using loguru."""

import sys
from pathlib import Path

from loguru import logger

from tracker.config import settings

# Remove default handler
logger.remove()

# Console handler with colors
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level=settings.log_level,
    colorize=True,
)

# File handler with JSON format for parsing
log_path = Path("logs")
log_path.mkdir(exist_ok=True)

logger.add(
    log_path / "tracker_{time:YYYY-MM-DD}.log",
    rotation="00:00",  # New file each day
    retention="30 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} | {message}",
    level=settings.log_level,
    serialize=False,  # Keep human readable for now
)

# Separate file for errors
logger.add(
    log_path / "errors_{time:YYYY-MM-DD}.log",
    rotation="00:00",
    retention="90 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} | {message}",
    level="ERROR",
)
