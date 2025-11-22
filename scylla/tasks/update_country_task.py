"""Update country task module

Periodically updates proxy country information using IP geolocation API.
"""

# Standard library imports
import asyncio
from datetime import datetime
from typing import List, Dict, Any

# Third-party imports
import aiohttp

# Local imports
from scylla import logger, c
from scylla.services.proxy_service import proxy_service

# Constants
BATCH_SIZE = 20
BATCH_DELAY = 1.5
API_URL = "http://ip-api.com/batch"
API_FIELDS = "status,message,countryCode,query"
REQUEST_TIMEOUT = 30


async def update_country_task():
    """Execute country update task for proxies without country information."""
    try:
        start_time = datetime.now()

        # Get proxies without country information
        proxies = await proxy_service.get_proxies_without_country(limit=200)
        if not proxies:
            logger.info(f"{c.YELLOW}No proxies need country update{c.END}")
            return

        logger.info(
            f"{c.CYAN}Starting country update for {len(proxies)} proxies{c.END}"
        )

        # Get unique IPs and fetch country data
        unique_ips = list(set(p["ip"] for p in proxies))
        country_data = await fetch_country_batch(unique_ips)

        # Build IP to country mapping
        ip_to_country = {
            data["query"]: data["countryCode"]
            for data in country_data
            if data.get("status") == "success"
            and data.get("countryCode")
            and len(data["countryCode"]) == 2
        }

        if not ip_to_country:
            logger.warning(f"{c.YELLOW}Failed to fetch country data{c.END}")
            return

        # Collect all updates for batch processing
        updates = [
            (proxy["id"], ip_to_country[proxy["ip"]])
            for proxy in proxies
            if proxy["ip"] in ip_to_country
        ]

        # Batch update
        if updates:
            updated = await proxy_service.batch_update_countries(updates)
            failed = len(proxies) - updated
        else:
            updated = failed = 0

        # Log results
        execution_time = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"{c.GREEN}Country update completed{c.END} - "
            f"updated: {c.GREEN}{updated}{c.END}, "
            f"failed: {c.RED}{failed}{c.END}, "
            f"total: {c.CYAN}{len(proxies)}{c.END}, "
            f"unique IPs: {c.BLUE}{len(unique_ips)}{c.END}, "
            f"time: {c.BLUE}{execution_time:.2f}s{c.END}"
        )

    except Exception as e:
        logger.error(f"Country update task failed: {e}", exc_info=True)


async def fetch_country_batch(ip_list: List[str]) -> List[Dict[str, Any]]:
    """Fetch country information for IPs using ip-api.com batch endpoint.

    Args:
        ip_list: List of IP addresses to lookup

    Returns:
        List of dictionaries with country information
    """
    if not ip_list:
        return []

    total_batches = (len(ip_list) + BATCH_SIZE - 1) // BATCH_SIZE
    logger.debug(
        f"Fetching country data for {len(ip_list)} unique IPs in {total_batches} batch(es)"
    )

    all_results = []
    for i in range(0, len(ip_list), BATCH_SIZE):
        batch = ip_list[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1

        result = await _fetch_single_batch(batch, batch_num, total_batches)
        if result:
            all_results.extend(result)

        # Delay between batches
        if i + BATCH_SIZE < len(ip_list):
            await asyncio.sleep(BATCH_DELAY)

    logger.debug(f"Fetched country data for {len(all_results)} IPs")
    return all_results


async def _fetch_single_batch(
    ip_batch: List[str], batch_num: int, total_batches: int
) -> List[Dict[str, Any]]:
    """Fetch country information for a single batch of IPs.

    Args:
        ip_batch: List of IP addresses
        batch_num: Current batch number
        total_batches: Total number of batches

    Returns:
        List of country information dictionaries
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL,
                json=ip_batch,
                params={"fields": API_FIELDS},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                if response.status == 200:
                    return await response.json()

                logger.error(
                    f"Batch {batch_num}/{total_batches}: "
                    f"Request failed with status {response.status}"
                )
                return []

    except aiohttp.ClientError as e:
        logger.error(f"Batch {batch_num}/{total_batches}: Network error - {e}")
        return []
    except Exception as e:
        logger.error(f"Batch {batch_num}/{total_batches}: Error - {e}", exc_info=True)
        return []
