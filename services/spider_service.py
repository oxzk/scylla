import asyncio
import inspect
import logging
from pathlib import Path
from typing import List, Optional
from importlib import import_module
from spiders.base import BaseSpider
from core.config import settings
from sanic.log import access_logger as logger


class SpiderService:

    def __init__(self):
        self.spiders: Optional[List[BaseSpider]] = None

    def _load_spiders(self) -> List[BaseSpider]:
        """动态加载所有爬虫类"""
        spiders = []
        spiders_dir = Path(__file__).parent.parent / "spiders"

        for path in spiders_dir.glob("**/*.py"):
            # 跳过 __init__.py 文件
            if path.name == "__init__.py":
                continue

            rel_path = path.relative_to(spiders_dir.parent)
            module_name = ".".join(rel_path.with_suffix("").parts)

            # 动态导入模块
            module = import_module(module_name)

            # 查找所有 BaseSpider 子类
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseSpider) and obj is not BaseSpider:
                    spiders.append(obj())
        return spiders

    async def run_all(self):
        """并发运行所有爬虫"""
        if not self.spiders:
            self.spiders = self._load_spiders()

        for spider in self.spiders:
            logger.info(f"启动爬虫: {spider.name}")
            await spider.run()

        # semaphore = asyncio.Semaphore(config.max_concurrent_spiders)

        # async def run_with_semaphore(spider):
        #     async with semaphore:
        #         try:
        #             logger.debug(f"启动爬虫: {spider.name}")
        #             return await spider.run()
        #         except Exception as e:
        #             logger.error(f"爬虫运行异常: {spider.name} - {e}", exc_info=True)

        # results = await asyncio.gather(
        #     *[run_with_semaphore(spider) for spider in self.spiders],
        #     return_exceptions=True,
        # )

        # total = sum(r for r in results if isinstance(r, int))
        # errors = [r for r in results if isinstance(r, Exception)]

        # if errors:
        #     logger.warning(f"部分爬虫执行出错: {len(errors)}/{len(self.spiders)} 个")
        #     for idx, error in enumerate(errors, 1):
        #         logger.error(f"错误 {idx}: {type(error).__name__}: {error}")

        # logger.info(f"所有爬虫运行完成，共保存 {total} 个有效代理")
        # return total

    async def run_spider(self, spider_name: str):
        """运行指定爬虫"""
        for spider in self.spiders:
            if spider.name == spider_name:
                return await spider.run()
        return None


spider_service = SpiderService()
