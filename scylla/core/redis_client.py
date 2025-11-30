"""Redis Client Module

Provides Redis connection and operations for task scheduling.
"""

# Standard library imports
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

# Third-party imports
import redis.asyncio as redis

# Local imports
from scylla import logger
from scylla.core.config import settings


# Redis key prefix
KEY_TASK_STATS = "task:stats:{}"


class RedisClient:
    """Async Redis client for task scheduling.

    Attributes:
        client: Redis connection instance (None if not connected)
    """

    def __init__(self):
        """Initialize Redis client."""
        self.client: Optional[redis.Redis] = None

    @property
    def is_connected(self) -> bool:
        """Check if Redis client is connected."""
        return self.client is not None

    async def connect(self) -> None:
        """Connect to Redis server with connection pool configuration."""

        try:
            self.client = await redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=10,
                socket_keepalive=True,
                socket_connect_timeout=20,
                retry_on_timeout=True,
            )
            await self.client.ping()
            logger.debug("✓ Redis connected")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            self.client = None

    async def ensure_connected(self) -> bool:
        """Ensure Redis connection is available, reconnect if needed.

        Returns:
            True if connected, False otherwise
        """
        if self.client:
            try:
                await self.client.ping()
                return True
            except Exception:
                logger.warning("Redis connection lost, attempting to reconnect...")
                await self.close()

        await self.connect()
        return self.is_connected

    async def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            try:
                await self.client.close()
            except Exception as e:
                logger.debug(f"Error closing Redis: {e}")
            finally:
                self.client = None
                logger.debug("✓ Redis closed")

    async def get_task_stats(self, task_name: str) -> Optional[Dict[str, Any]]:
        """Get task statistics and schedule from Redis.

        Args:
            task_name: Name of the task

        Returns:
            Dictionary with task statistics and schedule or None if not found
        """
        if not await self.ensure_connected():
            return None

        try:
            stats_key = KEY_TASK_STATS.format(task_name)
            stats = await self.client.hgetall(stats_key)
            if stats:
                return {
                    "execution_count": int(stats.get("execution_count", 0)),
                    "failure_count": int(stats.get("failure_count", 0)),
                    "last_run": (
                        datetime.fromisoformat(stats["last_run"])
                        if stats.get("last_run")
                        else None
                    ),
                    "next_run": (
                        datetime.fromisoformat(stats["next_run"])
                        if stats.get("next_run")
                        else None
                    ),
                }
        except Exception as e:
            logger.debug(f"Failed to get task stats for {task_name}: {e}")

        return None

    async def update_task_info_batch(
        self,
        task_name: str,
        next_run: datetime,
        last_run: Optional[datetime],
        execution_count: int,
        failure_count: int,
        execution_time: float,
        ttl: int = 86400,
    ) -> None:
        """Batch update task information using pipeline.

        Args:
            task_name: Task name
            next_run: Next scheduled run time
            last_run: Last run time
            execution_count: Number of executions
            failure_count: Number of failures
            execution_time: Execution time in seconds
            ttl: TTL for all keys in seconds (default: 24 hours)
        """
        if not await self.ensure_connected():
            return

        try:
            # 使用 pipeline 减少网络往返
            stats = {
                "last_run": last_run.isoformat() if last_run else "",
                "next_run": next_run.isoformat(),
                "execution_count": str(execution_count),
                "failure_count": str(failure_count),
                "execution_time": f"{execution_time:.2f}",
            }
            stats_key = KEY_TASK_STATS.format(task_name)

            async with self.client.pipeline(transaction=False) as pipe:
                await pipe.hset(stats_key, mapping=stats)  # type: ignore
                await pipe.expire(stats_key, ttl)
                await pipe.execute()
        except Exception as e:
            logger.debug(f"Failed to update task info for {task_name}: {e}")

    async def health_check(self) -> Dict[str, Any]:
        """Check Redis connection health.

        Returns:
            Dictionary with health status information
        """
        if not self.client:
            return {"status": "disconnected", "connected": False}

        try:
            await self.client.ping()
            return {"status": "healthy", "connected": True}
        except Exception as e:
            return {"status": "error", "connected": False, "error": str(e)}


# Global Redis client instance
redis_client = RedisClient()
