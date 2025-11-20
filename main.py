from sanic import Sanic
from sanic.log import access_logger as logger
from sanic.response import json as json_response
from core.config import settings
from core.database import db
from core.scheduler import scheduler
from api.routes import api_bp
from sanic.log import LOGGING_CONFIG_DEFAULTS
from core import VERSION
import logging
import os
from pathlib import Path


log_config = LOGGING_CONFIG_DEFAULTS.copy()
# log_config["formatters"]["access"]["class"] = "sanic.logging.formatter.AutoFormatter"
# log_config["formatters"]["access"]["format"] = "%(asctime)s[%(name)s][%(levelname)s]:%(message)s"
log_config["formatters"]["access"]["datefmt"] = "%Y-%m-%d %H:%M:%S"

# logging.basicConfig(
#     format="%(asctime)s[%(name)s][%(levelname)s]:%(message)s",
#     level=logging.INFO,
#     datefmt="%Y-%m-%d %H:%M:%S",
# )
# 创建Sanic应用
app = Sanic("scylla", log_config=log_config)
app.config.APP_PATH = Path(__file__).parent
app.config.update_config(
    {
        "REAL_IP_HEADER": "X-Real-IP",
        "PROXIES_COUNT": 1,
        "FORWARDED_SECRET": os.getenv("FORWARDED_SECRET", None),
    }
)
# 注册蓝图
app.blueprint(api_bp)


@app.before_server_start
async def setup_db(app, loop):
    """启动前初始化数据库"""
    logger.debug("正在连接数据库...")
    # try:
    #     await db.connect()
    #     logger.info("数据库连接成功")
    # except Exception as e:
    #     logger.error(f"数据库连接失败: {e}")
    #     raise


@app.after_server_start
async def start_scheduler(app: Sanic, loop):
    """启动后启动调度器"""
    logger.info("正在启动调度器...")
    logger.debug('11')

    # try:
    #     app.add_task(scheduler.start())
    #     logger.debug("调度器启动成功")
    # except Exception as e:
    #     logger.error(f"调度器启动失败: {e}")


@app.before_server_stop
async def close_db(app, loop):
    """停止前关闭资源"""
    logger.debug("正在关闭调度器...")
    # await scheduler.stop()

    # logger.info("正在关闭数据库连接...")
    # await db.close()
    # logger.info("资源清理完成")


@app.route("/")
async def index(request):
    """首页"""
    return json_response(
        {
            "name": app.name,
            "version": VERSION,
            "message": f"{app.name} API - 支持 HTTP/HTTPS/SOCKS4/SOCKS5",
            "documentation": {
                "proxies": {
                    "list": "GET /api/proxies?protocol=http&country=US&limit=10",
                    "random": "GET /api/proxies/random?protocol=socks5",
                    "detail": "GET /api/proxies/{id}",
                    "validate": "POST /api/proxies/{id}/validate",
                },
                "stats": "GET /api/stats",
                "spiders": {
                    "list": "GET /api/spiders",
                    "run": "POST /api/spiders/{name}/run",
                },
                "protocols": "GET /api/protocols",
                "health": "GET /api/health",
            },
        }
    )


@app.exception(Exception)
async def handle_exception(request, exception):
    """全局异常处理"""
    logger.error(f"未处理的异常: {exception}", exc_info=True)
    return json_response(
        {"success": False, "error": "Internal server error", "message": str(exception)},
        status=500,
    )


if __name__ == "__main__":
    # import asyncio
    # from services.spider_service import spider_service

    # asyncio.run(spider_service.run_all())
    app.run(
        host=settings.app_host,
        port=settings.app_port,
        dev=settings.app_debug,
        fast=False,
    )
