from sanic import Sanic
from sanic.log import access_logger as logger
from sanic.log import logger as root_logger
from sanic.response import json as json_response
from core.config import settings
from core.database import db
from core.scheduler import scheduler
from api.routes import api_bp
from sanic.log import LOGGING_CONFIG_DEFAULTS
from sanic.logging.color import Colors as c
from core import VERSION
from pathlib import Path
import logging


logging.getLogger("aiohttp").setLevel(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

log_config = LOGGING_CONFIG_DEFAULTS.copy()
log_config["formatters"]["access"]["class"] = "sanic.logging.formatter.AutoFormatter"
log_config["formatters"]["access"]["format"] = settings.log_format
log_config["formatters"]["access"]["datefmt"] = "%Y-%m-%d %H:%M:%S"

# 创建Sanic应用
app = Sanic("scylla", log_config=log_config)
app.config.APP_PATH = Path(__file__).parent
app.config["REAL_IP_HEADER"] = "X-Real-IP"
app.config["PROXIES_COUNT"] = 1
app.config["FORWARDED_SECRET"] = settings.app_secret

# 注册蓝图
app.blueprint(api_bp)


@app.before_server_start
async def setup_db(app: Sanic, loop):
    """初始化数据库"""
    root_logger.debug("正在连接数据库...")
    try:
        await db.connect()
        app.ctx.db = db
        root_logger.debug("数据库连接成功")
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")


@app.after_server_start
async def start_scheduler(app: Sanic, loop):
    """启动后启动调度器"""
    root_logger.debug("正在启动调度器...")
    try:
        app.add_task(scheduler.start(app))
        root_logger.debug("调度器启动成功")
    except Exception as e:
        logger.error(f"调度器启动失败: {e}")


@app.before_server_stop
async def server_stop(app: Sanic, loop):
    """停止前关闭资源"""
    root_logger.debug("正在关闭调度器...")
    await scheduler.stop()

    root_logger.debug("正在关闭数据库连接...")
    if app.ctx.db:
        await app.ctx.db.close()


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

    app.run(
        host=settings.app_host,
        port=settings.app_port,
        dev=settings.app_debug,
        fast=False,
    )
