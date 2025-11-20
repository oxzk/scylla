import asyncio
from datetime import datetime
from typing import Callable, List
from core.config import settings
from services.spider_service import spider_service
from sanic.log import access_logger as logger


class Task:
    """定时任务"""

    def __init__(self, name: str, func: Callable, interval: int):
        self.name = name
        self.func = func
        self.interval = interval
        self.last_run = None
        self.is_running = False

    async def run(self):
        """执行任务"""
        if self.is_running:
            logger.info(f"[{self.name}] 上次任务仍在运行中，跳过本次执行")
            return

        self.is_running = True
        try:
            logger.info(f"[{self.name}] 开始执行")
            await self.func()
            self.last_run = datetime.now()
            logger.info(f"[{self.name}] 执行完成")
        except Exception as e:
            logger.error(f"[{self.name}] 执行失败: {e}")
        finally:
            self.is_running = False


class Scheduler:
    """任务调度器"""

    def __init__(self):
        self.tasks: List[Task] = []
        self.running = False

    def add_task(self, name: str, func: Callable, interval: int):
        """添加定时任务"""
        task = Task(name, func, interval)
        self.tasks.append(task)

    def _load_task(self):
        self.add_task(
            name="代理爬取", func=self.crawl_task, interval=settings.crawl_interval
        )
        # self.add_task(
        #     name="代理验证", func=self.validate_task, interval=settings.validate_interval
        # )
        # self.add_task(
        #     name="清理无效代理",
        #     func=self.cleanup_task,
        #     interval=settings.cleanup_interval,
        # )

    async def start(self):
        self._load_task()
        if not self.tasks:
            logger.error("没有任务需要执行")
            return

        self.running = True
        # 为每个任务创建独立的协程
        await asyncio.gather(*[self._run_task(task) for task in self.tasks])

    async def _run_task(self, task: Task):
        """运行单个任务的循环"""
        # 首次启动时立即执行一次
        await task.run()

        while self.running:
            logger.debug(f"[{task.name}] 等待 {task.interval} 秒后执行")
            await asyncio.sleep(task.interval)
            if self.running:
                await task.run()

    async def stop(self):
        """停止调度器"""
        self.running = False
        logger.info("调度器已停止")

    # 定时任务函数
    async def crawl_task(self):
        """爬取任务"""
        try:
            count = await spider_service.run_all()
            logger.info(f"爬取任务完成，获取 {count} 个代理")
        except Exception as e:
            logger.error(f"爬取任务失败: {e}", exc_info=True)

    async def validate_task(self):
        """验证任务"""
        logger.info("执行代理验证任务")
        try:
            proxies = await db.get_proxies_for_validation(limit=500)
            if proxies:
                valid_count = await validator.validate_batch(proxies)
                logger.info(f"验证任务完成，{valid_count} 个代理可用")
            else:
                logger.info("没有需要验证的代理")
        except Exception as e:
            logger.error(f"验证任务失败: {e}")

    async def cleanup_task(self):
        """清理任务"""
        logger.info("执行清理任务")
        try:
            result = await db.cleanup_invalid_proxies()
            logger.info(f"清理任务完成: {result}")
        except Exception as e:
            logger.error(f"清理任务失败: {e}")


# 全局调度器实例
scheduler = Scheduler()
