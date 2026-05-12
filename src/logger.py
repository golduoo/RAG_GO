"""全局 logger 配置(loguru)。其他模块直接 ``from src.logger import logger``。"""

from __future__ import annotations

import sys

from loguru import logger

from src.config import settings

# 替换 loguru 默认 handler:控制台带颜色,级别从 settings.log_level 取
logger.remove()
logger.add(
    sys.stderr,
    level=settings.log_level,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
        "| <level>{level: <8}</level> "
        "| <cyan>{name}:{function}:{line}</cyan> "
        "- <level>{message}</level>"
    ),
)

__all__ = ["logger"]
