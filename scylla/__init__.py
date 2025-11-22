from sanic.log import access_logger as logger
from sanic.log import logger as root_logger
from sanic.logging.color import Colors as c

__version__ = "1.0.0"

CREATE_PROXY_TABLE = """
    CREATE TABLE IF NOT EXISTS proxies (
        id SERIAL PRIMARY KEY,
        ip VARCHAR(45) NOT NULL,
        port INTEGER NOT NULL,
        protocol VARCHAR(10) NOT NULL,
        country VARCHAR(2),
        anonymity VARCHAR(20),
        source VARCHAR(100) NOT NULL,
        speed FLOAT,
        success_count INTEGER DEFAULT 0,
        fail_count INTEGER DEFAULT 0,
        status INTEGER DEFAULT 0,
        last_checked TIMESTAMP,
        last_success TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(ip, port, protocol)
    );
    CREATE INDEX IF NOT EXISTS idx_proxies_country ON proxies(country);
    CREATE INDEX IF NOT EXISTS idx_proxies_protocol ON proxies(protocol);
    CREATE INDEX IF NOT EXISTS idx_proxies_status ON proxies(status);
    CREATE INDEX IF NOT EXISTS idx_proxies_fail_count ON proxies(fail_count);
    CREATE INDEX IF NOT EXISTS idx_proxies_last_success ON proxies(last_success);
    CREATE INDEX IF NOT EXISTS idx_proxies_quality ON proxies(success_count DESC, speed ASC);
"""
__all__ = ["__version__", "logger", "root_logger", "c", "CREATE_PROXY_TABLE"]
