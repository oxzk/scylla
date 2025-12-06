"""Scylla Proxy Pool - Main Application Entry Point

A high-performance proxy pool management system built with Sanic.
Supports HTTP/HTTPS/SOCKS4/SOCKS5 proxy protocols with automatic
validation, rotation, and quality scoring.
"""

# Standard library imports
import logging

# Third-party imports
from sanic import Sanic, Request
from sanic.response import json as json_response, HTTPResponse, empty
from sanic.log import LOGGING_CONFIG_DEFAULTS

# Local imports
from scylla import logger, root_logger, c, __version__ as VERSION
from scylla.core.config import settings
from scylla.core.scheduler import scheduler
from scylla.api.routes import api_bp


# Suppress verbose logging from third-party libraries
logging.getLogger("aiohttp").setLevel(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

# Configure Sanic logging
log_config = LOGGING_CONFIG_DEFAULTS.copy()
log_config["formatters"]["access"]["class"] = "sanic.logging.formatter.AutoFormatter"
log_config["formatters"]["access"]["format"] = settings.log_format
log_config["formatters"]["access"]["datefmt"] = "%H:%M:%S"

# Create Sanic application
app = Sanic("scylla", log_config=log_config)
app.config["REAL_IP_HEADER"] = "X-Real-IP"
app.config["PROXIES_COUNT"] = 1
app.config["FORWARDED_SECRET"] = settings.app_secret

# Register API blueprint
app.blueprint(api_bp)
app.static("/favicon.ico", "static/favicon.png")


@app.get("/robot.txt", name="robot_file")
async def robot_file(request: Request):
    return empty()


@app.get("/", name="index")
async def robot_file(request: Request):
    return empty()


@app.get("/version", name="version")
async def version(request: Request):
    return json_response({"version": VERSION})


@app.before_server_start
async def initialize_scheduler(app: Sanic, _loop) -> None:
    """Initialize scheduler resources before server starts.

    This hook runs before the server starts accepting connections.
    It initializes database, Redis, and sets up all scheduled tasks.

    Args:
        app: Sanic application instance
        loop: Event loop (unused, required by Sanic)
    """
    root_logger.debug(f"{c.CYAN}Initializing scheduler...{c.END}")
    try:
        await scheduler.initialize()
        root_logger.debug(f"{c.GREEN}✓{c.END} Scheduler initialized successfully")
    except Exception as e:
        logger.error(
            f"{c.RED}✗{c.END} Scheduler initialization failed: {e}", exc_info=True
        )
        raise


@app.after_server_start
async def start_scheduler(app: Sanic, _loop) -> None:
    """Start the task scheduler after server is ready.

    This hook runs after the server has started and is ready to accept
    connections. It begins executing the background scheduled tasks.

    Args:
        app: Sanic application instance
        loop: Event loop (unused, required by Sanic)
    """
    root_logger.debug(f"{c.CYAN}Starting scheduler execution...{c.END}")
    try:
        app.add_task(scheduler.start())
        root_logger.debug(f"{c.GREEN}✓{c.END} Scheduler execution started successfully")
    except Exception as e:
        logger.error(f"{c.RED}✗{c.END} Scheduler execution failed: {e}", exc_info=True)


@app.before_server_stop
async def server_stop(app: Sanic, _loop) -> None:
    """Gracefully shutdown resources before server stops.

    This hook runs before the server stops. It ensures all background
    tasks are stopped and database connections are properly closed.

    Args:
        app: Sanic application instance
        loop: Event loop (unused, required by Sanic)
    """
    await scheduler.stop()


@app.exception(Exception)
async def handle_exception(request: Request, exception: Exception) -> HTTPResponse:
    """Global exception handler for unhandled errors.

    Args:
        request: The request that caused the exception
        exception: The unhandled exception

    Returns:
        JSON error response with 500 status code
    """
    logger.error(f"Unhandled exception: {exception}", exc_info=True)
    return json_response(
        {
            "success": False,
            "error": "Internal server error",
            "message": str(exception),
        },
        status=500,
    )


if __name__ == "__main__":
    app.run(
        host=settings.app_host,
        port=settings.app_port,
        dev=settings.app_debug,
        workers=settings.app_worker,
    )
