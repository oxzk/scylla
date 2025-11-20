from sanic import Blueprint, response
from sanic.request import Request
from core.database import db
from models import ProxyProtocol
from pydantic import ValidationError

api_bp = Blueprint("api", url_prefix="/api")


@api_bp.route("/proxies", methods=["GET"])
async def get_proxies(request: Request):
    """
    获取可用代理
    参数:
        - protocol: http/https/socks4/socks5
        - country: 国家代码 (US, CN等)
        - limit: 返回数量，默认10
    """
    try:
        protocol = request.args.get("protocol")
        country = request.args.get("country")
        limit = int(request.args.get("limit", 10))

        # 验证协议
        if protocol:
            try:
                ProxyProtocol(protocol.lower())
            except ValueError:
                return response.json(
                    {
                        "success": False,
                        "error": f"Invalid protocol. Must be one of: {[p.value for p in ProxyProtocol]}",
                    },
                    status=400,
                )

        # 限制最大返回数量
        limit = min(limit, 100)

        proxies = await db.get_available_proxies(
            protocol=protocol, country=country, limit=limit
        )

        result = [proxy.to_dict() for proxy in proxies]

        return response.json({"success": True, "count": len(result), "data": result})

    except ValueError as e:
        return response.json(
            {"success": False, "error": f"Invalid parameter: {str(e)}"}, status=400
        )
    except Exception as e:
        return response.json({"success": False, "error": str(e)}, status=500)


@api_bp.route("/proxies/random", methods=["GET"])
async def get_random_proxy(request: Request):
    """
    获取一个随机可用代理
    参数:
        - protocol: http/https/socks4/socks5
        - country: 国家代码
    """
    try:
        protocol = request.args.get("protocol")
        country = request.args.get("country")

        # 验证协议
        if protocol:
            try:
                ProxyProtocol(protocol.lower())
            except ValueError:
                return response.json(
                    {
                        "success": False,
                        "error": f"Invalid protocol. Must be one of: {[p.value for p in ProxyProtocol]}",
                    },
                    status=400,
                )

        proxies = await db.get_available_proxies(
            protocol=protocol, country=country, limit=1
        )

        if not proxies:
            return response.json(
                {"success": False, "error": "No available proxy found"}, status=404
            )

        proxy = proxies[0]
        return response.json({"success": True, "data": proxy.to_dict()})

    except Exception as e:
        return response.json({"success": False, "error": str(e)}, status=500)


@api_bp.route("/proxies/<proxy_id:int>", methods=["GET"])
async def get_proxy_detail(request: Request, proxy_id: int):
    """获取代理详情"""
    try:
        proxy = await db.get_proxy_by_id(proxy_id)

        if not proxy:
            return response.json(
                {"success": False, "error": "Proxy not found"}, status=404
            )

        return response.json({"success": True, "data": proxy.to_dict()})

    except Exception as e:
        return response.json({"success": False, "error": str(e)}, status=500)


@api_bp.route("/proxies/<proxy_id:int>/validate", methods=["POST"])
async def validate_proxy(request: Request, proxy_id: int):
    """手动验证单个代理"""
    try:
        proxy = await db.get_proxy_by_id(proxy_id)

        if not proxy:
            return response.json(
                {"success": False, "error": "Proxy not found"}, status=404
            )

        # 验证代理
        proxy_id, success, speed = await validator.validate_proxy(proxy)
        await db.update_proxy_validation(proxy_id, success, speed)

        return response.json(
            {
                "success": True,
                "data": {"proxy_id": proxy_id, "is_valid": success, "speed": speed},
            }
        )

    except Exception as e:
        return response.json({"success": False, "error": str(e)}, status=500)


@api_bp.route("/stats", methods=["GET"])
async def get_stats(request: Request):
    """获取统计信息"""
    try:
        stats = await db.get_stats()

        return response.json({"success": True, "data": stats})

    except Exception as e:
        return response.json({"success": False, "error": str(e)}, status=500)


@api_bp.route("/spiders", methods=["GET"])
async def list_spiders(request: Request):
    """列出所有爬虫"""
    try:
        spiders = spider_manager.list_spiders()

        return response.json({"success": True, "count": len(spiders), "data": spiders})

    except Exception as e:
        return response.json({"success": False, "error": str(e)}, status=500)


@api_bp.route("/spiders/<spider_name>/run", methods=["POST"])
async def run_spider(request: Request, spider_name: str):
    """手动运行指定爬虫"""
    try:
        count = await spider_manager.run_spider(spider_name)

        return response.json(
            {"success": True, "data": {"spider": spider_name, "proxies_saved": count}}
        )

    except Exception as e:
        return response.json({"success": False, "error": str(e)}, status=500)


@api_bp.route("/protocols", methods=["GET"])
async def list_protocols(request: Request):
    """列出支持的协议类型"""
    return response.json({"success": True, "data": [p.value for p in ProxyProtocol]})


@api_bp.route("/health", methods=["GET"])
async def health_check(request: Request):
    """健康检查"""
    try:
        # 检查数据库连接
        async with db.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

        return response.json(
            {"success": True, "status": "healthy", "database": "connected"}
        )
    except Exception as e:
        return response.json(
            {"success": False, "status": "unhealthy", "error": str(e)}, status=503
        )
