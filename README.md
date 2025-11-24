# Scylla - 高性能代理池系统

<div align="center">

![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Status](https://img.shields.io/badge/status-active-success.svg)

一个基于 Python 的高性能代理池管理系统，支持 HTTP/HTTPS/SOCKS4/SOCKS5 代理协议，具有自动验证、匿名级别检测和质量评分功能。

[特性](#-特性) • [快速开始](#-快速开始) • [API 文档](#-api-文档) • [配置](#-配置) • [部署](#-部署)

</div>

---

## ✨ 特性

### 核心功能

-   🚀 **高性能架构** - 基于 Sanic 异步框架，支持高并发请求
-   🔄 **自动验证** - 定期验证代理可用性，自动移除失效代理
-   🎭 **匿名级别检测** - 自动检测代理匿名级别（透明/匿名/高匿）
-   📊 **智能评分** - 基于成功率、速度和稳定性的质量评分系统
-   🌐 **多协议支持** - HTTP、HTTPS、SOCKS4、SOCKS5 全协议支持

### 数据管理

-   🗄️ **PostgreSQL 存储** - 可靠的数据持久化和高效查询
-   🔍 **灵活筛选** - 支持按协议、国家、匿名级别等多维度筛选

### 开发友好

-   📡 **RESTful API** - 简单易用的 HTTP API 接口
-   🔧 **环境变量配置** - 通过 .env 文件轻松配置
-   📝 **详细日志** - 彩色日志输出，便于调试和监控
-   🐳 **Docker 支持** - 一键部署，开箱即用

---

## 📋 目录

-   [快速开始](#-快速开始)
-   [API 文档](#-api-文档)
-   [配置说明](#-配置)
-   [Docker 部署](#-docker-部署)
-   [开发指南](#-开发指南)
-   [架构设计](#-架构设计)
-   [许可证](#-许可证)

---

## 🚀 快速开始

### 前置要求

-   Python 3.11+
-   PostgreSQL 12+
-   pip 或 poetry

### 安装步骤

1. **克隆项目**

```bash
git clone https://github.com/yourusername/scylla.git
cd scylla
```

2. **安装依赖**

```bash
pip install -r requirements.txt
```

3. **配置环境变量**

```bash
cp .env.example .env
# 编辑 .env 文件，配置数据库连接等信息
```

54. **启动服务**

```bash
python main.py
```

服务将在 `http://localhost:8000` 启动

---

## 📡 API 文档

### 基础 URL

```
http://localhost:8000/api
```

### 主要端点

#### 1. 获取代理列表

```bash
GET /api/proxies?protocol=http&country=US&anonymity=elite&limit=10
```

**参数:**

-   `protocol` (可选): 协议类型 - `http`, `https`, `socks4`, `socks5`
-   `country` (可选): 国家代码 - ISO 3166-1 alpha-2 (如: `US`, `CN`)
-   `anonymity` (可选): 匿名级别 - `transparent`, `anonymous`, `elite`
-   `limit` (可选): 返回数量 - 默认 10，最大 100

**响应示例:**

```json
{
    "success": true,
    "count": 10,
    "data": [
        {
            "id": 1,
            "ip": "1.2.3.4",
            "port": 8080,
            "protocol": "http",
            "country": "US",
            "anonymity": "elite",
            "speed": 1.23,
            "success_rate": 0.85,
            "quality_score": 88.5,
            "url": "http://1.2.3.4:8080"
        }
    ]
}
```
---

## 🐳 Docker 部署

### 使用 Docker Compose（推荐）

1. **启动服务**

```bash
docker-compose up -d
```

2. **查看日志**

```bash
docker-compose logs -f scylla
```

3. **停止服务**

```bash
docker-compose down
```

### 使用 Docker

1. **构建镜像**

```bash
docker build -t scylla:latest .
```

2. **运行容器**

```bash
docker run -d \
  --name scylla \
  -p 8000:8000 \
  -e DB_URL=postgresql://user:password@host:5432/scylla \
  scylla:latest
```

---

## 📝 更新日志

### v1.0.0 (2025-11-22)

-   ✨ 初始版本发布
-   🎭 添加匿名级别检测功能
-   📊 实现智能质量评分系统
-   🔄 支持自动验证和清理
-   💾 添加数据库备份功能

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 🙏 致谢

-   [Sanic](https://sanic.dev/) - 高性能异步 Web 框架
-   [asyncpg](https://github.com/MagicStack/asyncpg) - 快速 PostgreSQL 驱动
-   [curl_cffi](https://github.com/yifeikong/curl_cffi) - 代理验证工具

---

<div align="center">

**[⬆ 回到顶部](#scylla---高性能代理池系统)**

Made with ❤️ by Scylla Team

</div>
