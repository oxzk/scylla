from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from ipaddress import ip_address


class ProxyProtocol(str, Enum):
    """代理协议枚举"""

    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"


class ProxyAnonymity(str, Enum):
    """代理匿名级别"""

    TRANSPARENT = "transparent"  # 透明代理
    ANONYMOUS = "anonymous"  # 匿名代理
    ELITE = "elite"  # 高匿代理


class ProxyStatus(str, Enum):
    """代理状态"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    CHECKING = "checking"


class ProxyData(BaseModel):
    """代理数据模型"""

    ip: str
    port: int = Field(ge=1, le=65535)
    protocol: ProxyProtocol
    country: Optional[str] = Field(None, max_length=2)
    anonymity: Optional[ProxyAnonymity] = None
    source: str
    speed: Optional[float] = None

    @field_validator("ip")
    def validate_ip(cls, v):
        try:
            return ip_address(v)  # 转换为 IPv4Address 或 IPv6Address
        except ValueError:
            raise ValueError("Invalid IP address")

    class Config:
        use_enum_values = True


class ProxyModel(ProxyData):
    """完整的代理模型（包含数据库字段）"""

    id: Optional[int] = None
    success_count: int = 0
    fail_count: int = 0
    last_checked: Optional[datetime] = None
    last_success: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    status: ProxyStatus = ProxyStatus.ACTIVE

    @property
    def success_rate(self) -> float:
        """成功率"""
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def url(self) -> str:
        """代理URL"""
        return f"{self.protocol}://{self.ip}:{self.port}"

    @property
    def quality_score(self) -> float:
        """质量评分 (0-100)"""
        from app.config import config

        # 成功率得分
        success_score = self.success_rate * 100

        # 速度得分 (速度越快分数越高，最快1秒=100分)
        if self.speed:
            speed_score = max(0, 100 - (self.speed * 10))
        else:
            speed_score = 0

        # 稳定性得分（基于最近成功时间）
        if self.last_success:
            hours_since_success = (
                datetime.now() - self.last_success
            ).total_seconds() / 3600
            stability_score = max(0, 100 - (hours_since_success * 5))
        else:
            stability_score = 0

        # 加权计算
        weights = config.get("proxy", {})
        w_success = weights.get("weight_success_rate", 0.4)
        w_speed = weights.get("weight_speed", 0.3)
        w_stability = weights.get("weight_stability", 0.3)

        return (
            success_score * w_success
            + speed_score * w_speed
            + stability_score * w_stability
        )

    def to_dict(self) -> dict:
        """转换为字典"""
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


# SQL 建表语句
CREATE_PROXY_TABLE = """
CREATE TABLE IF NOT EXISTS proxies (
    id SERIAL PRIMARY KEY,
    ip VARCHAR(45) NOT NULL,
    port INTEGER NOT NULL CHECK (port >= 1 AND port <= 65535),
    protocol VARCHAR(10) NOT NULL CHECK (protocol IN ('http', 'https', 'socks4', 'socks5')),
    country VARCHAR(2),
    anonymity VARCHAR(20) CHECK (anonymity IN ('transparent', 'anonymous', 'elite')),
    source VARCHAR(100) NOT NULL,
    speed FLOAT,
    success_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'checking')),
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
