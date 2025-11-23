from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from ipaddress import ip_address as validate_ip_address


class ProxyAnonymity(str, Enum):
    """Proxy anonymity levels"""

    TRANSPARENT = "transparent"  # Transparent proxy
    ANONYMOUS = "anonymous"  # Anonymous proxy
    ELITE = "elite"  # Elite/High anonymity proxy


class ProxyStatus(int, Enum):
    """Proxy status codes"""

    SUCCESS = 1
    FAILED = 2
    PENDING = 0


class Proxy(BaseModel):
    """Unified proxy model for both spider output and database storage

    This model can be used in two ways:
    1. Spider output: Only basic fields (ip, port, protocol, etc.) are required
    2. Database storage: Additional fields (id, success_count, etc.) are populated

    All database-specific fields are optional to support both use cases.
    """

    # Required fields (for spider output)
    ip: str
    port: int = Field(ge=1, le=65535)
    protocol: str
    source: str

    # Optional basic fields
    country: Optional[str] = Field(None, max_length=2)
    anonymity: Optional[ProxyAnonymity] = None
    speed: Optional[float] = None

    # Optional database fields
    id: Optional[int] = None
    success_count: int = 0
    fail_count: int = 0
    last_checked: Optional[datetime] = None
    last_success: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    status: ProxyStatus = ProxyStatus.PENDING

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v):
        """Validate IP address format"""
        try:
            validate_ip_address(v)  # Validate but don't convert
            return str(v)  # Return as string for database compatibility
        except ValueError:
            raise ValueError("Invalid IP address")

    @field_validator("protocol", mode="before")
    @classmethod
    def normalize_protocol(cls, v):
        """Normalize protocol to lowercase"""
        return v.lower() if isinstance(v, str) else v

    @field_validator("port", mode="before")
    @classmethod
    def normalize_port(cls, v):
        """Normalize port to integer"""
        return int(v) if isinstance(v, str) else v

    @field_validator("country", mode="before")
    @classmethod
    def normalize_country(cls, v):
        """Normalize country code to uppercase ISO 3166-1 alpha-2"""
        if v is None:
            return v
        v = v.strip().upper()
        if len(v) != 2:
            raise ValueError(
                f"Country code {v} must be 2 characters (ISO 3166-1 alpha-2)"
            )
        return v

    @property
    def success_rate(self) -> float:
        """Calculate success rate as a percentage (0.0 to 1.0)"""
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def url(self) -> str:
        """Generate proxy URL in format: protocol://ip:port"""
        return f"{self.protocol}://{self.ip}:{self.port}"

    @property
    def quality_score(self) -> float:
        """Calculate overall proxy quality score (0-100)

        Combines success rate, speed, and stability into a weighted score.
        Higher scores indicate better quality proxies.
        """
        from scylla.core.config import settings

        # Success rate score (0-100)
        success_score = self.success_rate * 100

        # Speed score (faster = higher score, 1 second = 100 points)
        if self.speed:
            speed_score = max(0, 100 - (self.speed * 10))
        else:
            speed_score = 0

        # Stability score (based on time since last success)
        if self.last_success:
            hours_since_success = (
                datetime.now(timezone.utc) - self.last_success
            ).total_seconds() / 3600
            stability_score = max(0, 100 - (hours_since_success * 5))
        else:
            stability_score = 0

        # Weighted calculation
        w_success = settings.weight_success_rate
        w_speed = settings.weight_speed
        w_stability = settings.weight_stability

        return (
            success_score * w_success
            + speed_score * w_speed
            + stability_score * w_stability
        )

    def to_dict(self) -> dict:
        """Convert proxy model to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "ip": self.ip,
            "port": self.port,
            "protocol": self.protocol,
            "country": self.country,
            "anonymity": self.anonymity,
            "source": self.source,
            "speed": self.speed,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "success_rate": round(self.success_rate, 2),
            "quality_score": round(self.quality_score, 2),
            "url": self.url,
            "last_checked": (
                self.last_checked.isoformat() if self.last_checked else None
            ),
            "last_success": (
                self.last_success.isoformat() if self.last_success else None
            ),
            "status": self.status,
        }

    class Config:
        use_enum_values = True
        from_attributes = True

