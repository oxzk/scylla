"""API Routes Module

Provides RESTful API endpoints for proxy management, validation, and statistics.
"""

# Third-party imports
from sanic import Blueprint, response
from sanic.request import Request
from scylla import logger, __version__ as VERSION

# Local imports
from scylla.services.proxy_service import proxy_service

api_bp = Blueprint("api", url_prefix="/api")


@api_bp.get("/robot.txt", name="robot_file")
async def robot_file(request):
    return response.empty()


@api_bp.route("/")
async def index(request: Request):
    """API index page with documentation links.

    Returns:
        JSON response with API information and endpoint documentation
    """
    return response.json(
        {
            "name": request.app.name,
            "version": VERSION,
            "message": f"{request.app.name} Proxy Pool API - Supports HTTP/HTTPS/SOCKS4/SOCKS5",
            "documentation": {
                "proxies": {
                    "list": "GET /api/proxies?protocol=http&country=US&limit=10",
                },
                "stats": "GET /api/stats",
                "health": "GET /api/health",
            },
        }
    )


@api_bp.route("/proxies", methods=["GET"])
async def get_proxies(request: Request):
    """Get available proxies with optional filtering.

    Query Parameters:
        - protocol: Filter by protocol (http/https/socks4/socks5)
        - country: Filter by country code (ISO 3166-1 alpha-2, e.g., US, CN)
        - anonymity: Filter by anonymity level (transparent/anonymous/elite)
        - limit: Maximum number of proxies to return (default: 10, max: 100)

    Returns:
        JSON response with list of proxies
    """
    try:
        protocol = request.args.get("protocol")
        country = request.args.get("country")
        anonymity = request.args.get("anonymity")
        limit = min(int(request.args.get("limit", 10)), 20)

        # Get proxies from service (filtering done at database level)
        proxies = []
        async for proxy in proxy_service.get_active_proxies(
            protocol=protocol, country=country, anonymity=anonymity, limit=limit
        ):
            proxies.append(proxy.to_dict())

        return response.json({"success": True, "count": len(proxies), "data": proxies})

    except ValueError as e:
        return response.json(
            {"success": False, "error": f"Invalid parameter: {str(e)}"}, status=400
        )
    except Exception as e:
        logger.error(f"Error in get_proxies: {e}", exc_info=True)
        return response.json({"success": False, "error": str(e)}, status=500)


@api_bp.route("/stats", methods=["GET"])
async def get_stats(request: Request):
    """Get proxy pool statistics.

    Returns:
        JSON response with statistics including:
        - total: Total number of proxies
        - active: Number of active proxies
        - inactive: Number of inactive proxies
        - checking: Number of proxies being checked
        - protocols: Number of unique protocols
        - countries: Number of unique countries
        - avg_speed: Average response speed
        - anonymity: Breakdown by anonymity level (transparent, anonymous, elite)
    """
    try:
        stats = await proxy_service.get_stats()
        return response.json({"success": True, "data": stats})

    except Exception as e:
        logger.error(f"Error in get_stats: {e}", exc_info=True)
        return response.json({"success": False, "error": str(e)}, status=500)


@api_bp.route("/health", methods=["GET"])
async def health_check(request: Request):
    """Health check endpoint.

    Returns:
        JSON response with service health status
    """
    try:
        # Check database connection
        stats = await proxy_service.get_stats()

        return response.json(
            {
                "success": True,
                "status": "healthy",
                "database": "connected",
                "proxy_count": stats.get("total", 0),
            }
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return response.json(
            {"success": False, "status": "unhealthy", "error": str(e)}, status=503
        )


@api_bp.route("/test", methods=["POST"])
async def test_proxy(request: Request):
    import time
    from curl_cffi import AsyncSession

    try:
        # Parse form data
        proxy_url = request.form.get("proxy")
        if not proxy_url:
            raise ValueError("Missing 'proxy' parameter in form data")

        test_url = request.form.get("test_url", "https://ipinfo.io/")
        timeout_seconds = int(request.form.get("timeout", 20))

        # Test the proxy
        start_time = time.time()
        test_result = {
            "proxy": proxy_url,
            "test_url": test_url,
            "working": False,
            "speed": None,
            "headers": None,
            "error": None,
        }

        async with AsyncSession() as session:
            resp = await session.request(
                method="GET",
                url=test_url,
                proxy=proxy_url,
                timeout=timeout_seconds,
                verify=False,
                headers={"user-agent": "curl/7.88.1"},
            )

            response_time = time.time() - start_time
            test_result["speed"] = round(response_time, 2)
            test_result["working"] = resp.ok
            test_result["headers"] = dict(resp.headers)
            test_result["data"] = resp.json()

    except Exception as e:
        test_result["error"] = str(e)

    return response.json({"success": True, "data": test_result})
