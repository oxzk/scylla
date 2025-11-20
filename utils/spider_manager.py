import asyncio
import inspect
from pathlib import Path
from typing import List, Type, Optional
from functools import wraps, partial
from importlib import import_module
from spiders.base import BaseSpider
from core.config import config


class SpiderManager:
    """爬虫管理器"""

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
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseSpider) and obj is not BaseSpider:
                    spiders.append(obj)
        return spiders

    async def run_all(self):
        """并发运行所有爬虫"""
        logger.info(
            f"开始运行 {len(self.spiders)} 个爬虫，最大并发数: {config.max_concurrent_spiders}"
        )

        semaphore = asyncio.Semaphore(config.max_concurrent_spiders)

        async def run_with_semaphore(spider):
            async with semaphore:
                try:
                    logger.debug(
                        f"启动爬虫: {spider.name if hasattr(spider, 'name') else spider.__class__.__name__}"
                    )
                    return await spider.run()
                except Exception as e:
                    logger.error(
                        f"爬虫运行异常: {spider.__class__.__name__} - {e}",
                        exc_info=True,
                    )
                    raise

        results = await asyncio.gather(
            *[run_with_semaphore(spider) for spider in self.spiders],
            return_exceptions=True,
        )

        total = sum(r for r in results if isinstance(r, int))
        errors = [r for r in results if isinstance(r, Exception)]

        if errors:
            logger.warning(f"部分爬虫执行出错: {len(errors)}/{len(self.spiders)} 个")
            for idx, error in enumerate(errors, 1):
                logger.error(f"错误 {idx}: {type(error).__name__}: {error}")

        logger.info(f"所有爬虫运行完成，共保存 {total} 个有效代理")
        return total

    async def run_spider(self, spider_name: str):
        """运行指定爬虫"""
        for spider in self.spiders:
            if spider.name == spider_name:
                return await spider.run()
        return None

    def list_spiders(self) -> List[str]:
        """列出所有爬虫名称"""
        return [spider for spider in self.spiders]


# 全局爬虫管理器实例
spider_manager = SpiderManager()
