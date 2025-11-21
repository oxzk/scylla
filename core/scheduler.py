import asyncio
from datetime import datetime
from typing import Callable, List, Optional
from core.config import settings
from services.spider_service import spider_service
from services.proxy_service import proxy_service
from sanic import Sanic
from sanic.log import access_logger as logger
from sanic.log import logger as root_logger
from sanic.logging.color import Colors as c


class Task:
    """Represents a scheduled task that executes periodically at specified intervals.

    Attributes:
        name: Human-readable task name for logging and identification
        func: Async callable to execute when the task runs
        interval: Time interval in seconds between executions
        last_run: Timestamp of the last successful execution
        is_running: Flag to prevent concurrent executions of the same task
    """

    def __init__(self, name: str, func: Callable, interval: int):
        self.name = name
        self.func = func
        self.interval = interval
        self.last_run: Optional[datetime] = None
        self.is_running = False

    async def run(self):
        """Execute the task with concurrency protection.

        Skips execution if the previous run is still in progress to prevent
        overlapping executions. Logs execution lifecycle and captures errors.
        """
        colored_name = f"{c.BLUE}{self.name}{c.END}"
        if self.is_running:
            root_logger.debug(
                f"[{colored_name}] Previous task still running, skipping this execution"
            )
            return

        self.is_running = True
        try:
            root_logger.debug(f"[{colored_name}] Task execution started")
            await self.func()
            self.last_run = datetime.now()
            root_logger.debug(f"[{colored_name}] Task execution completed successfully")
        except Exception as e:
            logger.error(f"[{colored_name}] Task execution failed: {e}", exc_info=True)
        finally:
            self.is_running = False


class Scheduler:
    """Manages and executes multiple scheduled tasks concurrently.

    The scheduler runs each task in its own coroutine, allowing independent
    execution cycles. Tasks are executed immediately on startup, then repeat
    at their configured intervals.
    """

    def __init__(self):
        self.tasks: List[Task] = []
        self.running = False
        self.app: Optional[Sanic] = None

    def add_task(self, name: str, func: Callable, interval: int):
        """Register a new scheduled task.

        Args:
            name: Display name for the task (used in logs)
            func: Async function to execute
            interval: Execution interval in seconds
        """
        task = Task(name, func, interval)
        self.tasks.append(task)

    def _load_task(self):
        """Load all configured scheduled tasks"""
        self.add_task(
            name="Proxy Crawl", func=self.crawl_task, interval=settings.crawl_interval
        )
        # Additional tasks can be added here:
        # self.add_task(
        #     name="Proxy Validation",
        #     func=self.validate_task,
        #     interval=settings.validate_interval
        # )
        # self.add_task(
        #     name="Cleanup Invalid Proxies",
        #     func=self.cleanup_task,
        #     interval=settings.cleanup_interval,
        # )

    async def start(self, app: Sanic):
        """Start the scheduler and begin executing tasks

        Args:
            app: Sanic application instance
        """
        self._load_task()
        if not self.tasks:
            logger.warning("No tasks scheduled for execution")
            return

        self.app = app
        self.running = True
        logger.info(f"Scheduler started with {len(self.tasks)} task(s)")

        # Initialize proxy service with database connection
        proxy_service.init_db(self.app.ctx.db)

        # Create independent coroutine for each task to allow parallel execution
        await asyncio.gather(*[self._run_task(task) for task in self.tasks])

    async def _run_task(self, task: Task):
        """Execute the task loop for a single scheduled task.

        Runs the task immediately on first call, then enters a loop that
        waits for the specified interval before each subsequent execution.

        Args:
            task: Task instance to execute
        """
        # Execute immediately on first startup, then wait for interval
        await task.run()

        while self.running:
            logger.info(
                f"[{task.name}] Waiting {task.interval} seconds before next execution"
            )
            await asyncio.sleep(task.interval)
            if self.running:
                await task.run()

    async def stop(self):
        """Stop the scheduler and all running tasks gracefully."""
        self.running = False
        root_logger.info("Scheduler stopped successfully")

    # Scheduled task implementations
    async def crawl_task(self):
        """Execute proxy crawling from all configured spider sources."""
        try:
            results = await spider_service.run_all()

            # Process and save proxies
            total_proxies = 0
            saved_proxies = 0
            failed_proxies = 0

            for proxies in results:
                if not isinstance(proxies, list):
                    continue

                total_proxies += len(proxies)
                for proxy in proxies:
                    try:
                        await proxy_service.add_proxy(proxy)
                        saved_proxies += 1
                    except Exception as e:
                        failed_proxies += 1
                        logger.debug(
                            f"Failed to save proxy {proxy.ip}:{proxy.port} - {e}"
                        )

            logger.info(
                f"Proxy crawl completed - "
                f"fetched {c.CYAN}{total_proxies}{c.END} proxies, "
                f"saved {c.GREEN}{saved_proxies}{c.END}, "
                f"failed {c.RED}{failed_proxies}{c.END}"
            )
        except Exception as e:
            logger.error(f"Proxy crawl task failed: {e}", exc_info=True)


scheduler = Scheduler()
