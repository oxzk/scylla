"""Proxy Service Module

Provides high-level proxy management operations including CRUD operations,
validation tracking, quality scoring, and cleanup tasks.
"""

# Standard library imports
from datetime import datetime, timedelta
from typing import AsyncGenerator, List, Optional, Tuple

# Local imports
from scylla import logger
from scylla.core.database import db
from scylla.models.proxy import Proxy, ProxyStatus


class ProxyService:
    """Service for managing proxy pool operations.

    This service uses the global database instance for all operations.
    Database connection is automatically managed and reconnected if needed.

    Example:
        >>> from services.proxy_service import proxy_service
        >>> proxies = await proxy_service.get_active_proxies(limit=10)
    """

    def _ensure_db(self):
        """Ensure database connection exists.

        Raises an error if database is not connected. Database should be
        initialized during application startup via scheduler.start().
        """
        if db.pool is None:
            raise RuntimeError(
                "Database not initialized. Ensure scheduler.start() was called."
            )

    def _row_to_proxy(self, row) -> Proxy:
        """Convert database row to Proxy model.

        Args:
            row: Database row record

        Returns:
            Proxy instance populated from row data
        """
        return Proxy(
            id=row["id"],
            ip=row["ip"],
            port=row["port"],
            protocol=row["protocol"],
            country=row["country"],
            anonymity=row["anonymity"],
            source=row["source"],
            speed=row["speed"],
            success_count=row.get("success_count", 0),
            fail_count=row.get("fail_count", 0),
            status=row.get("status", 0),
            last_checked=row.get("last_checked"),
            last_success=row.get("last_success"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    async def add_proxy(self, proxy: Proxy) -> Optional[int]:
        """Add a single proxy to the database.

        Args:
            proxy: Proxy instance to add

        Returns:
            Proxy ID if inserted, None if already exists (conflict)
        """
        self._ensure_db()

        query = """
        INSERT INTO proxies (ip, port, protocol, country, source, status)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (ip, port, protocol) DO NOTHING
        RETURNING id;
        """

        try:
            return await db.fetchval(
                query,
                proxy.ip,
                proxy.port,
                proxy.protocol,
                proxy.country,
                proxy.source,
                proxy.status,
            )
        except Exception as e:
            logger.error(f"Failed to add proxy {proxy.url}: {e}")
            return None

    async def add_batch(self, proxies: List[Proxy]) -> int:
        """Add multiple proxies to database using batch operation.

        Uses executemany for better performance compared to individual inserts.

        Args:
            proxies: List of Proxy instances to add

        Returns:
            Number of successfully added proxies
        """
        self._ensure_db()

        if not proxies:
            return 0

        query = """
        INSERT INTO proxies (ip, port, protocol, country, source, status)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (ip, port, protocol) DO NOTHING;
        """

        try:
            # Prepare batch data
            batch_data = [
                (p.ip, p.port, p.protocol, p.country, p.source, p.status)
                for p in proxies
            ]

            async with db.pool.acquire() as conn:
                await conn.executemany(query, batch_data)

            return len(proxies)

        except Exception as e:
            logger.error(f"Batch insert failed: {e}", exc_info=True)
            return 0

    async def record_validation_result(
        self,
        proxy_id: int,
        is_success: bool,
        response_time: Optional[float] = None,
        anonymity: Optional[str] = None,
    ) -> None:
        """Record proxy validation result with single optimized query.

        Args:
            proxy_id: ID of proxy to update
            is_success: Whether validation was successful
            response_time: Response time in seconds (if successful)
            anonymity: Anonymity level (transparent/anonymous/elite, if successful)
        """
        self._ensure_db()

        if response_time is not None:
            response_time = round(response_time, 2)

        target_status = int(ProxyStatus.SUCCESS if is_success else ProxyStatus.FAILED)
        query = """
            UPDATE proxies 
            SET 
                success_count = CASE WHEN $2 THEN success_count + 1 ELSE 0 END,
                fail_count = CASE WHEN $2 THEN GREATEST(fail_count - 1, 0) ELSE fail_count + 1 END,
                last_checked = NOW(),
                last_success = CASE WHEN $2 THEN NOW() ELSE last_success END,
                speed = CASE WHEN $2 THEN $3 ELSE speed END,
                anonymity = CASE WHEN $2 THEN $5 ELSE anonymity END,
                status = $4,
                updated_at = NOW()
            WHERE id = $1
        """
        await db.execute(
            query,
            proxy_id,
            is_success,
            response_time,
            target_status,
            anonymity,
        )

    async def record_failure(self, proxy_id: int):
        """Record a validation failure for a proxy.

        Args:
            proxy_id: ID of proxy to update
        """
        self._ensure_db()

        query = """
            UPDATE proxies 
            SET fail_count = fail_count + 1,
                last_checked = $1,
                updated_at = $1
            WHERE id = $2
        """
        await db.execute(query, datetime.now(), proxy_id)

    async def get_active_proxies(
        self,
        protocol: Optional[str] = None,
        country: Optional[str] = None,
        anonymity: Optional[str] = None,
        limit: int = 10,
    ) -> AsyncGenerator[Proxy, None]:
        """Get active proxies with optional filtering.

        Args:
            protocol: Filter by protocol (http/https/socks4/socks5)
            country: Filter by country code (ISO 3166-1 alpha-2)
            anonymity: Filter by anonymity level (transparent/anonymous/elite)
            limit: Maximum number of proxies to return

        Yields:
            Proxy instances matching the criteria
        """
        self._ensure_db()

        conditions = [f"status = {int(ProxyStatus.SUCCESS)}"]
        params = []
        param_index = 1

        if protocol:
            conditions.append(f"protocol = ${param_index}")
            params.append(protocol.lower())
            param_index += 1

        if country:
            conditions.append(f"country = ${param_index}")
            params.append(country.upper())
            param_index += 1

        if anonymity:
            conditions.append(f"anonymity = ${param_index}")
            params.append(anonymity.lower())
            param_index += 1

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT *
            FROM proxies
            WHERE {where_clause}
            ORDER BY 
                last_success DESC,
                success_count DESC
            LIMIT ${param_index}
        """
        params.append(limit)

        rows = await db.fetch(query, *params)
        for row in rows:
            yield self._row_to_proxy(row)

    async def get_proxies_needing_validation(
        self, limit: int = 500, max_fail_count: int = 3
    ) -> AsyncGenerator[Proxy, None]:
        """Get proxies that need validation (pending/failed status).

        Prioritizes proxies that haven't been checked recently.

        Args:
            limit: Maximum number of proxies to return
            max_fail_count: Maximum fail count threshold

        Yields:
            Proxy instances needing validation
        """
        self._ensure_db()

        query = f"""
            SELECT *
            FROM proxies
            WHERE fail_count < {max_fail_count}
                AND status IN ({ProxyStatus.PENDING.value}, {ProxyStatus.FAILED.value})
            ORDER BY last_checked ASC NULLS FIRST
            LIMIT $1
        """

        rows = await db.fetch(query, limit)
        for row in rows:
            yield self._row_to_proxy(row)

    async def get_successful_proxies_for_validation(
        self, limit: int = 200
    ) -> AsyncGenerator[Proxy, None]:
        """Get successful proxies that need re-validation.

        Prioritizes successful proxies that haven't been checked recently
        to ensure they are still working.

        Args:
            limit: Maximum number of proxies to return

        Yields:
            Proxy instances needing re-validation
        """
        self._ensure_db()

        query = f"""
            SELECT *
            FROM proxies
            WHERE status = {ProxyStatus.SUCCESS.value}
            ORDER BY last_checked ASC NULLS FIRST
            LIMIT $1
        """

        rows = await db.fetch(query, limit)
        for row in rows:
            yield self._row_to_proxy(row)

    async def cleanup_failed_proxies(self, max_failures: int = 3) -> int:
        """Clean up proxies that have exceeded failure threshold.

        Args:
            max_failures: Maximum number of failures before deletion

        Returns:
            Number of deleted proxies
        """
        self._ensure_db()

        query = f"""
            DELETE FROM proxies
            WHERE status = {ProxyStatus.FAILED.value} AND fail_count >= $1
        """
        result = await db.execute(query, max_failures)
        return int(result.split()[-1])

    async def cleanup_stale_proxies(self, days: int = 7) -> int:
        """Clean up stale proxies that haven't been successful recently.

        Args:
            days: Number of days since last success before deletion

        Returns:
            Number of deleted proxies
        """
        self._ensure_db()

        cutoff_date = datetime.now() - timedelta(days=days)
        query = """
            DELETE FROM proxies
            WHERE last_success < $1 OR (last_success IS NULL AND created_at < $1)
        """
        result = await db.execute(query, cutoff_date)
        return int(result.split()[-1])

    async def get_all_proxies_for_backup(self, batch_size: int = 1000):
        """Get all proxies for backup operations using batch processing.

        Retrieves proxy records in batches to avoid memory issues with large datasets.
        Uses cursor-based pagination for efficient streaming.

        Args:
            batch_size: Number of records to fetch per batch (default: 1000)

        Yields:
            Batches of database rows, each batch containing up to batch_size records
        """
        self._ensure_db()

        offset = 0
        while True:
            query = f"""
                SELECT * FROM proxies 
                ORDER BY id 
                LIMIT $1 OFFSET $2
            """
            rows = await db.fetch(query, batch_size, offset)

            if not rows:
                break

            yield rows

            # If we got fewer rows than batch_size, we've reached the end
            if len(rows) < batch_size:
                break

            offset += batch_size

    async def get_stats(self) -> dict:
        """Get proxy statistics.

        Returns:
            Dictionary with proxy counts and statistics including anonymity breakdown
        """
        self._ensure_db()

        query = f"""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = {ProxyStatus.SUCCESS.value}) as active,
                COUNT(*) FILTER (WHERE status = {ProxyStatus.FAILED.value}) as inactive,
                COUNT(*) FILTER (WHERE status = {ProxyStatus.PENDING.value}) as checking,
                COUNT(DISTINCT protocol) as protocols,
                COUNT(DISTINCT country) as countries,
                AVG(speed) FILTER (WHERE speed IS NOT NULL) as avg_speed,
                COUNT(*) FILTER (WHERE anonymity = 'transparent') as transparent,
                COUNT(*) FILTER (WHERE anonymity = 'anonymous') as anonymous,
                COUNT(*) FILTER (WHERE anonymity = 'elite') as elite
            FROM proxies
        """
        row = await db.fetchrow(query)

        return {
            "total": row["total"],
            "active": row["active"],
            "inactive": row["inactive"],
            "checking": row["checking"],
            "protocols": row["protocols"],
            "countries": row["countries"],
            "avg_speed": (
                round(float(row["avg_speed"]), 2) if row["avg_speed"] else None
            ),
            "anonymity": {
                "transparent": row["transparent"],
                "anonymous": row["anonymous"],
                "elite": row["elite"],
            },
        }

    async def get_proxies_without_country(self, limit: int = 100) -> List[dict]:
        """Get successful proxies that don't have country information.

        Only returns proxies with SUCCESS status to avoid updating country
        information for proxies that may be removed soon.

        Args:
            limit: Maximum number of proxies to return (default: 100)

        Returns:
            List of dictionaries with 'id' and 'ip' keys
        """
        self._ensure_db()

        query = f"""
            SELECT id, ip FROM proxies 
            WHERE (country IS NULL OR country = '')
                AND status = {int(ProxyStatus.SUCCESS)}
            LIMIT $1
        """
        rows = await db.fetch(query, limit)
        return [{"id": row["id"], "ip": row["ip"]} for row in rows]

    async def update_proxy_country(self, proxy_id: int, country_code: str) -> None:
        """Update the country code for a specific proxy.

        Args:
            proxy_id: ID of the proxy to update
            country_code: ISO 3166-1 alpha-2 country code (e.g., 'US', 'CN')
        """
        self._ensure_db()

        query = """
            UPDATE proxies 
            SET country = $1, updated_at = NOW()
            WHERE id = $2
        """
        await db.execute(query, country_code, proxy_id)

    async def batch_update_countries(self, updates: List[Tuple[int, str]]) -> int:
        """Batch update proxy country information.

        Args:
            updates: List of (proxy_id, country_code) tuples

        Returns:
            Number of updated records
        """
        if not updates:
            return 0

        self._ensure_db()

        ids = [u[0] for u in updates]
        countries = [u[1] for u in updates]

        query = """
            UPDATE proxies SET 
                country = data.country,
                updated_at = NOW()
            FROM (
                SELECT 
                    unnest($1::int[]) as id, 
                    unnest($2::text[]) as country
            ) as data
            WHERE proxies.id = data.id
        """

        result = await db.execute(query, ids, countries)
        return int(result.split()[-1]) if result else 0


proxy_service = ProxyService()
