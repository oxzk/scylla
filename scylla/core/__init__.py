"""Core Module

Provides core functionality including logging, database, configuration, and scheduling.
"""

from sanic.log import access_logger as logger
from sanic.log import error_logger
from sanic.log import logger as root_logger

VERSION = "1.0.0"

__all__ = ["logger", "error_logger", "root_logger", "VERSION"]
