from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database settings
    db_url: str = Field(default="postgresql://", description="Database connection URL")
    db_min_pool_size: int = Field(
        default=2, ge=1, description="Minimum database connection pool size"
    )
    db_max_pool_size: int = Field(
        default=10, ge=1, description="Maximum database connection pool size"
    )

    # Application settings
    app_host: str = Field(default="0.0.0.0", description="Application host")
    app_port: int = Field(default=8000, ge=1, le=65535, description="Application port")
    app_debug: bool = Field(default=False, description="Debug mode")
    app_secret: str = Field(default="", description="Application secret key")
    app_worker: int = Field(default=1, ge=1, le=20, description="Application workers")

    # Scheduler intervals (in seconds)
    crawl_interval: int = Field(
        default=3600, ge=1, description="Crawl interval in seconds"
    )
    validate_interval: int = Field(
        default=20, ge=1, description="Pending proxy validation interval in seconds"
    )
    validate_success_interval: int = Field(
        default=60, ge=1, description="Success proxy re-validation interval in seconds"
    )
    cleanup_interval: int = Field(
        default=1200, ge=1, description="Cleanup interval in seconds"
    )
    update_country_interval: int = Field(
        default=600, ge=1, description="Country update interval in seconds"
    )

    # Limits
    max_fail_count: int = Field(
        default=3, ge=1, description="Maximum failure count before removing proxy"
    )
    validate_batch_limit: int = Field(
        default=300,
        ge=1,
        description="Maximum number of proxies to validate in each batch",
    )
    max_concurrent_spiders: int = Field(
        default=5, ge=1, description="Maximum concurrent spider tasks"
    )
    max_concurrent_validators: int = Field(
        default=50, ge=1, description="Maximum concurrent validator tasks"
    )
    validator_timeout: int = Field(
        default=25, ge=1, description="Proxy validation timeout in seconds"
    )
    validator_test_url: str = Field(
        default="http://cp.cloudflare.com/generate_204",
        description="URL used for proxy validation",
    )

    # Logging format
    log_format: str = Field(
        default="\033[38;5;240m%(asctime)s\033[0m %(levelname)s: \033[1000D\033[26C\033[K %(message)s",
        description="Logging format string",
    )

    # Redis configuration
    redis_url: str = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )

    @model_validator(mode="after")
    def validate_pool_sizes(self) -> "Settings":
        """Validate that max pool size is greater than or equal to min pool size."""
        if self.db_max_pool_size < self.db_min_pool_size:
            raise ValueError(
                f"db_max_pool_size ({self.db_max_pool_size}) must be >= "
                f"db_min_pool_size ({self.db_min_pool_size})"
            )
        return self


settings = Settings()
