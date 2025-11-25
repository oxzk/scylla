"""Scylla CLI - Command-line interface for proxy pool tasks

Provides command-line access to run proxy validation tasks independently
from the main web server. Useful for manual testing and scheduled jobs.
"""

# Standard library imports
import asyncio
import logging

# Local imports
from scylla.core.database import db
from scylla.tasks import validate_task


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Suppress verbose logging from third-party libraries
logging.getLogger("aiohttp").setLevel(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)


async def main():
    """Main CLI entry point - executes validate_task."""
    logger.info("Starting Scylla CLI - Validate Task")

    try:
        # Initialize database connection
        logger.info("Connecting to database...")
        await db.connect()
        logger.info("✓ Database connected successfully")

        # Initialize proxy service with database
        from scylla.services.proxy_service import proxy_service

        proxy_service._initialize_db(db)

        # Execute validation task
        logger.info("Running validate_task...")
        await validate_task()
        logger.info("✓ Validate task completed successfully")

    except Exception as e:
        logger.error(f"✗ CLI execution failed: {e}", exc_info=True)
        raise
    finally:
        # Clean up database connection
        if db:
            await db.close()
            logger.debug("✓ Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
