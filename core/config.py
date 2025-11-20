import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class Settings:

    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "user"
    db_password: str = "password"
    db_name: str = "proxy_db"
    min_pool_size: int = 5
    max_pool_size: int = 20

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True

    crawl_interval: int = 3600
    validate_interval: int = 1800
    cleanup_interval: int = 7200

    weight_success_rate: float = 0.4
    weight_speed: float = 0.3
    weight_stability: float = 0.3

    max_fail_count: int = 3
    max_concurrent_spiders: int = 5
    max_concurrent_validators: int = 50

    proxy_test_url: str = "http://httpbin.org/ip"
    proxy_test_timeout: int = 15

    def __init__(self):
        config_path = Path(__file__).parent.parent / "config.toml"
        if config_path.exists():
            toml_config = tomllib.load(config_path.open("rb"))
            for key, value in toml_config.items():
                setattr(self, key, value)

        self._override_from_env()

    def _override_from_env(self):
        """从环境变量覆盖配置"""
        env_mappings = {
            "DB_HOST": "db_host",
            "DB_PORT": "db_port",
            "DB_NAME": "db_name",
            "DB_USER": "db_user",
            "DB_PASSWORD": "db_password",
            "API_HOST": "app_host",
            "API_PORT": "app_port",
            "DEBUG": "app_debug",
        }

        for env_key, key in env_mappings.items():
            value = os.getenv(env_key)
            if value is not None:
                setattr(self, key, value)


settings = Settings()
