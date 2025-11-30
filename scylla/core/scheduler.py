"""Task Scheduler Module

Manages and executes scheduled background tasks with configurable intervals,
error recovery, and concurrent execution support.
"""

# Standard library imports
import asyncio
from datetime import datetime, timedelta
from typing import Callable, List, Optional, Dict, Any

# Local imports
from scylla import logger, root_logger, c
from scylla.core.config import settings
from scylla.core.database import db
from scylla.core.redis_client import redis_client
from scylla.tasks import (
    crawl_task,
    validate_pending_task,
    validate_success_task,
    cleanup_task,
    update_country_task,
)


class Task:
    """Represents a scheduled task that executes periodically at specified intervals.

    Attributes:
        name: Human-readable task name for logging and identification
        func: Async callable to execute when the task runs
        interval: Time interval in seconds between executions
        last_run: Timestamp of the last successful execution
        next_run: Timestamp of the next scheduled execution
        is_running: Flag to prevent concurrent executions of the same task
        execution_count: Total number of successful executions
        failure_count: Total number of failed executions
    """

    def __init__(self, name: str, func: Callable, interval: int):
        self.name = name
        self.func = func
        self.interval = interval
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.is_running = False
        self.execution_count = 0
        self.failure_count = 0

    async def run(self) -> None:
        """Execute the task with concurrency protection and improved scheduling.

        Skips execution if the previous run is still in progress to prevent
        overlapping executions. Logs execution lifecycle and captures errors.

        Uses fixed-interval scheduling to prevent time drift accumulation.
        """
        colored_name = f"{c.BLUE}{self.name}{c.END}"
        if self.is_running:
            logger.warning(
                f"[{colored_name}] Previous execution still running, skipping"
            )
            return

        self.is_running = True
        start_time = datetime.now()
        execution_time = 0.0

        try:
            root_logger.debug(f"[{colored_name}] Execution started")
            await self.func()

            execution_time = (datetime.now() - start_time).total_seconds()
            self.last_run = start_time  # Use start time instead of end time
            self.execution_count += 1

            logger.info(
                f"[{colored_name}] {c.GREEN}✓{c.END} Completed in {execution_time:.2f}s "
                f"(total: {self.execution_count}, failures: {self.failure_count})"
            )

        except Exception as e:
            self.failure_count += 1
            execution_time = (datetime.now() - start_time).total_seconds()

            logger.error(
                f"[{colored_name}] {c.RED}✗{c.END} Failed after {execution_time:.2f}s: {e}",
                exc_info=True,
            )

        finally:
            self.is_running = False

            if self.next_run:
                self.next_run = self.next_run + timedelta(seconds=self.interval)
            else:
                self.next_run = start_time + timedelta(seconds=self.interval)

            await redis_client.update_task_info_batch(
                task_name=self.name,
                next_run=self.next_run,
                last_run=self.last_run,
                execution_count=self.execution_count,
                failure_count=self.failure_count,
                execution_time=execution_time,
            )

    def get_status(self) -> Dict[str, Any]:
        """Get current task status and statistics.

        Returns:
            Dictionary with task execution statistics
        """
        return {
            "name": self.name,
            "interval": self.interval,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "is_running": self.is_running,
            "execution_count": self.execution_count,
            "failure_count": self.failure_count,
        }


class Scheduler:
    """Manages and executes multiple scheduled tasks concurrently.

    The scheduler runs each task in its own coroutine, allowing independent
    execution cycles. Tasks are executed immediately on startup, then repeat
    at their configured intervals.

    Attributes:
        tasks: List of registered Task instances
        running: Flag indicating if scheduler is active
    """

    def __init__(self):
        self.tasks: List[Task] = []
        self.running = False

    def add_task(self, name: str, func: Callable, interval: int) -> Task:
        """Register a new scheduled task.

        Args:
            name: Display name for the task (used in logs)
            func: Async function to execute
            interval: Execution interval in seconds

        Returns:
            The created Task instance
        """
        task = Task(name, func, interval)
        self.tasks.append(task)
        return task

    async def _initialize_tasks(self) -> None:
        lock_key = "scheduler:task_initialization"
        if await redis_client.client.set(lock_key, 1, ex=300, nx=True):
            self.add_task(
                name="Proxy Crawl",
                func=crawl_task,
                interval=settings.crawl_interval,
            )

            self.add_task(
                name="Proxy Cleanup",
                func=cleanup_task,
                interval=settings.cleanup_interval,
            )

            self.add_task(
                name="Country Update",
                func=update_country_task,
                interval=settings.update_country_interval,
            )

            self.add_task(
                name="Success Proxy Validation",
                func=validate_success_task,
                interval=settings.validate_success_interval,
            )

        # Each worker gets its own pending validation task
        self.add_task(
            name="Pending Proxy Validation",
            func=validate_pending_task,
            interval=settings.validate_interval,
        )

    async def initialize(self) -> None:
        """Initialize scheduler resources (database, Redis, tasks).

        This should be called during application startup (before_server_start)
        to set up all necessary resources before the server starts accepting requests.
        """
        # Initialize database connection

        await db.connect()

        # Connect to Redis (needed for distributed lock)
        await redis_client.connect()

        # Initialize tasks with distributed lock
        await self._initialize_tasks()

        if not self.tasks:
            return

        # Load task state from Redis
        for task in self.tasks:
            # Restore task statistics and schedule
            stats = await redis_client.get_task_stats(task.name)
            if stats:
                task.next_run = stats.get("next_run")
                task.execution_count = stats["execution_count"]
                task.failure_count = stats["failure_count"]
                task.last_run = stats["last_run"]
                logger.debug(
                    f"Restored state for {task.name}: "
                    f"next_run={task.next_run.isoformat() if task.next_run else 'None'}, "
                    f"executions={stats['execution_count']}, "
                    f"failures={stats['failure_count']}"
                )

        logger.debug(
            f"{c.GREEN}Scheduler initialized{c.END} with {len(self.tasks)} task(s)"
        )

    async def start(self) -> None:
        """Start executing scheduled tasks.

        This should be called after initialize() to begin task execution.
        Typically called during after_server_start.
        """
        if not self.tasks:
            logger.warning("No tasks scheduled for execution.")
            return

        self.running = True
        logger.info(f"{c.GREEN}Scheduler started{c.END}")

        # Create independent coroutine for each task to allow parallel execution
        await asyncio.gather(*[self._run_task(task) for task in self.tasks])

    async def _run_task(self, task: Task) -> None:
        """Execute the task loop for a single scheduled task.

        Flow:
        1. Check if next_run exists (from Redis or previous execution)
        2. If next_run is in the future -> wait until that time
        3. Execute the task (which sets the next next_run)
        4. Repeat

        Args:
            task: Task instance to execute
        """
        try:
            while self.running:
                # Calculate wait time if next_run is scheduled
                if task.next_run:
                    now = datetime.now()
                    wait_seconds = (task.next_run - now).total_seconds()

                    if wait_seconds > 0:
                        next_time = task.next_run.strftime("%H:%M:%S")
                        logger.info(
                            f"{c.BLUE}[{task.name}]{c.END} Next execution at "
                            f"{c.CYAN}{next_time}{c.END} "
                            f"(in {c.YELLOW}{wait_seconds:.0f}s{c.END})"
                        )

                        await asyncio.sleep(wait_seconds)

                # Execute the task (sets next_run for next iteration)
                await task.run()

        except asyncio.CancelledError:
            logger.info(f"{c.BLUE}[{task.name}]{c.END} Task cancelled gracefully")
            raise
        except Exception as e:
            logger.error(
                f"{c.RED}[{task.name}]{c.END} Task loop crashed: {e}", exc_info=True
            )
            # Don't re-raise to prevent one task from crashing the entire scheduler

    async def stop(self) -> None:
        self.running = False

        await db.close()

        await redis_client.close()

        logger.info(f"{c.GREEN}✓{c.END} Scheduler stopped")

    def get_tasks_status(self):
        """Get status of all registered tasks.

        Yields:
            Task status dictionaries
        """
        for task in self.tasks:
            yield task.get_status()


# Global scheduler instance
scheduler = Scheduler()
