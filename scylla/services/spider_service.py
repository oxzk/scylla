# Standard library imports
import asyncio
import inspect
import logging
from pathlib import Path
from typing import List, Optional
from importlib import import_module

# Local imports
from scylla import logger, c
from scylla.core.config import settings
from scylla.models import Proxy
from scylla.spiders.base import BaseSpider


class SpiderService:
    """Service for managing and executing proxy spiders"""

    def __init__(self):
        self._spiders: Optional[List[BaseSpider]] = None

    @property
    def spiders(self) -> List[BaseSpider]:
        """Lazy load spiders on first access"""
        if self._spiders is None:
            self._spiders = self._load_spiders()
        return self._spiders

    def _load_spiders(self) -> List[BaseSpider]:
        """Dynamically load all spider classes from the spiders directory"""
        spiders = []
        spiders_dir = Path(__file__).parent.parent / "spiders"

        if not spiders_dir.exists():
            logger.warning(f"Spiders directory not found: {spiders_dir}")
            return spiders

        for path in spiders_dir.glob("*.py"):
            if path.name.startswith("_"):
                continue

            module_name = f"scylla.spiders.{path.stem}"

            try:
                # Dynamically import module
                module = import_module(module_name)

                # Find all BaseSpider subclasses defined in this module
                for name, spider_class in inspect.getmembers(module, inspect.isclass):
                    # Only load spiders defined in this module (not imported ones)
                    if (
                        issubclass(spider_class, BaseSpider)
                        and spider_class is not BaseSpider
                        and spider_class.__module__ == module_name
                    ):
                        try:
                            spider_instance = spider_class()
                            if spider_instance.status:
                                spiders.append(spider_instance)
                                logger.debug(f"Loaded spider: {spider_instance.name}")
                        except Exception as e:
                            logger.error(
                                f"Failed to instantiate spider {spider_class.__name__}: {e}"
                            )

            except Exception as e:
                logger.error(f"Failed to load module {module_name}: {e}")
                continue

        logger.debug(f"Successfully loaded {len(spiders)} active spider(s)")
        return spiders

    def get_spider_by_name(self, spider_name: str) -> Optional[BaseSpider]:
        """Get a spider instance by name"""
        for spider in self.spiders:
            if spider.name == spider_name:
                return spider
        return None

    async def _run_with_semaphore(
        self, semaphore: asyncio.Semaphore, spider: BaseSpider
    ) -> Optional[List[Proxy]]:
        """Run a spider with semaphore control

        Args:
            semaphore: Semaphore for concurrency control
            spider: Spider instance to run

        Returns:
            List of fetched proxies, or None if failed
        """
        colored_name = f"{c.BLUE}{spider.name}{c.END}"
        async with semaphore:
            try:
                logger.info(f"{c.CYAN}[{spider.name}] Starting spider...{c.END}")
                proxies = await spider.run()

                if proxies:
                    logger.info(
                        f"{c.GREEN}[{spider.name}] ✓ Completed{c.END} - "
                        f"fetched {c.CYAN}{len(proxies)}{c.END} proxies"
                    )
                else:
                    logger.warning(
                        f"{c.YELLOW}[{spider.name}] ⚠ No proxies fetched{c.END}"
                    )
                return proxies
            except TimeoutError:
                logger.warning(
                    f"{c.YELLOW}[{spider.name}] ⏱ Timeout{c.END} - "
                    f"exceeded time limit"
                )
            except Exception as e:
                logger.error(
                    f"{c.RED}[{spider.name}] ✗ Failed{c.END} - {e}",
                    exc_info=True,
                )
            return None

    async def run_all(self) -> List[Optional[List[Proxy]]]:
        """Run all enabled spiders concurrently with semaphore control

        Returns:
            List of results from all spiders (each result is a list of proxies or None)
        """
        if not self.spiders:
            logger.warning(f"{c.YELLOW}No active spiders found{c.END}")
            return []

        logger.info(
            f"{c.CYAN}Starting spider crawl{c.END} - "
            f"running {c.CYAN}{len(self.spiders)}{c.END} spider(s) "
            f"with max {c.CYAN}{settings.max_concurrent_spiders}{c.END} concurrent"
        )

        semaphore = asyncio.Semaphore(settings.max_concurrent_spiders)

        return await asyncio.gather(
            *[self._run_with_semaphore(semaphore, spider) for spider in self.spiders],
            return_exceptions=True,
        )

    async def run_spider(self, spider_name: str) -> Optional[List[Proxy]]:
        """Run a specific spider by name

        Args:
            spider_name: Name of the spider to run

        Returns:
            List of fetched proxies, or None if spider not found or failed
        """
        spider = self.get_spider_by_name(spider_name)
        if spider is None:
            logger.warning(f"{c.YELLOW}Spider not found: {spider_name}{c.END}")
            return None

        logger.info(f"{c.CYAN}[{spider_name}] Starting spider...{c.END}")
        try:
            proxies = await spider.run()
            if proxies:
                logger.info(
                    f"{c.GREEN}[{spider_name}] ✓ Completed{c.END} - "
                    f"fetched {c.CYAN}{len(proxies)}{c.END} proxies"
                )
            else:
                logger.warning(f"{c.YELLOW}[{spider_name}] ⚠ No proxies fetched{c.END}")
            return proxies
        except TimeoutError:
            logger.warning(
                f"{c.YELLOW}[{spider_name}] ⏱ Timeout{c.END} - " f"exceeded time limit"
            )
        except Exception as e:
            logger.error(f"{c.RED}[{spider_name}] ✗ Failed{c.END} - {e}", exc_info=True)
        return None


spider_service = SpiderService()
