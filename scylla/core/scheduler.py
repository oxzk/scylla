"""Task Scheduler Module

Manages and executes scheduled background tasks with configurable intervals,
error recovery, and concurrent execution support.
"""

# Standard library imports
import asyncio
from datetime import datetime
from typing import Callable, List, Optional, Dict, Any

# Local imports
from scylla import logger, root_logger, c
from scylla.core.config import settings
from scylla.tasks import crawl_task, validate_task, cleanup_task, update_country_task


class Task:
    """Represents a scheduled task that executes periodically at specified intervals.

    Attributes:
        name: Human-readable task name for logging and identification
        func: Async callable to execute when the task runs
        interval: Time interval in seconds between executions
        last_run: Timestamp of the last successful execution
        is_running: Flag to prevent concurrent executions of the same task
        execution_count: Total number of successful executions
        failure_count: Total number of failed executions
    """

    def __init__(self, name: str, func: Callable, interval: int):
        self.name = name
        self.func = func
        self.interval = interval
        self.last_run: Optional[datetime] = None
        self.is_running = False
        self.execution_count = 0
        self.failure_count = 0

    async def run(self) -> bool:
        """Execute the task with concurrency protection.

        Skips execution if the previous run is still in progress to prevent
        overlapping executions. Logs execution lifecycle and captures errors.

        Returns:
            True if execution succeeded, False otherwise
        """
        colored_name = f"{c.BLUE}{self.name}{c.END}"
        if self.is_running:
            logger.warning(
                f"[{colored_name}] Previous execution still running, skipping"
            )
            return False

        self.is_running = True
        start_time = datetime.now()

        try:
            root_logger.debug(f"[{colored_name}] Execution started")
            await self.func()

            execution_time = (datetime.now() - start_time).total_seconds()
            self.last_run = datetime.now()
            self.execution_count += 1

            root_logger.debug(
                f"[{colored_name}] {c.GREEN}✓{c.END} Completed in {execution_time:.2f}s "
                f"(total: {self.execution_count}, failures: {self.failure_count})"
            )
            return True

        except Exception as e:
            self.failure_count += 1
            execution_time = (datetime.now() - start_time).total_seconds()

            logger.error(
                f"[{colored_name}] {c.RED}✗{c.END} Failed after {execution_time:.2f}s: {e}",
                exc_info=True,
            )
            return False

        finally:
            self.is_running = False

    def get_status(self) -> Dict[str, Any]:
        """Get current task status and statistics.

        Returns:
            Dictionary with task execution statistics
        """
        return {
            "name": self.name,
            "interval": self.interval,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "is_running": self.is_running,
            "execution_count": self.execution_count,
            "failure_count": self.failure_count,
            "success_rate": (
                round(
                    self.execution_count
                    / (self.execution_count + self.failure_count)
                    * 100,
                    2,
                )
                if (self.execution_count + self.failure_count) > 0
                else 0.0
            ),
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

    def _initialize_tasks(self, app) -> None:
        with app.shared_ctx.lock:
            if app.shared_ctx.queue.empty():
                app.shared_ctx.queue.put(app.m.pid)
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
                    name="Country Update", func=update_country_task, interval=3600
                )

        self.add_task(
            name="Proxy Validation",
            func=validate_task,
            interval=settings.validate_interval,
        )

    async def start(self) -> None:
        """Start the scheduler and begin executing tasks."""
        if not self.tasks:
            logger.warning("No tasks scheduled for execution")
            return

        self.running = True
        logger.info(f"{c.GREEN}Scheduler started{c.END} with {len(self.tasks)} task(s)")

        # Create independent coroutine for each task to allow parallel execution
        await asyncio.gather(*[self._run_task(task) for task in self.tasks])

    async def _run_task(self, task: Task) -> None:
        """Execute the task loop for a single scheduled task.

        Runs the task immediately on first call, then enters a loop that
        waits for the specified interval before each subsequent execution.

        Args:
            task: Task instance to execute
        """
        # Execute immediately on first startup
        await task.run()

        while self.running:
            logger.info(
                f"{c.BLUE}[{task.name}] Next execution in {task.interval}s{c.END}"
            )
            await asyncio.sleep(task.interval)

            if self.running:
                await task.run()

    async def stop(self) -> None:
        """Stop the scheduler and all running tasks gracefully."""
        self.running = False
        root_logger.debug(f"{c.YELLOW}Scheduler stopped{c.END}")

    def get_tasks_status(self):
        """Get status of all registered tasks.

        Yields:
            Task status dictionaries
        """
        for task in self.tasks:
            yield task.get_status()


# Global scheduler instance
scheduler = Scheduler()
