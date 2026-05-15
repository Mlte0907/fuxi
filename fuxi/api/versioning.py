"""伏羲 v1.0 — API版本化管理

提供版本协商、弃用通告、迁移路径等API生命周期管理能力。"""
from datetime import datetime, timezone
from typing import Dict, Optional


class ApiVersion:
    """API 版本定义"""

    def __init__(
        self,
        version: str,
        status: str = "current",  # current / deprecated / sunset
        sunset_date: Optional[str] = None,
        migration_guide: str = "",
    ):
        self.version = version
        self.status = status
        self.sunset_date = sunset_date
        self.migration_guide = migration_guide


# API 版本注册表
API_VERSIONS: Dict[str, ApiVersion] = {
    "v2": ApiVersion(
        version="v2",
        status="current",
        migration_guide="直接使用 /api/v2/ 前缀，无需迁移",
    ),
}

# 端点弃用映射：旧路径 → 新路径 + 弃用日期
DEPRECATED_PATHS: Dict[str, dict] = {
    # 示例:
    # "/api/v1/memories": {
    #     "replacement": "/api/v2/memories",
    #     "deprecated_since": "2026-01-01",
    #     "sunset_date": "2026-07-01",
    # },
}

# 当前活跃的 API 版本
CURRENT_VERSION = "v2"
SUPPORTED_VERSIONS = ["v2"]

# 版本化的响应标头
VERSION_HEADER = "X-API-Version"
DEPRECATION_HEADER = "Deprecation"
SUNSET_HEADER = "Sunset"
LINK_HEADER = "Link"


def get_version_info() -> dict:
    """返回 API 版本信息"""
    return {
        "current_version": CURRENT_VERSION,
        "supported_versions": SUPPORTED_VERSIONS,
        "versions": {
            ver: {
                "status": info.status,
                "sunset_date": info.sunset_date,
                "migration_guide": info.migration_guide,
            }
            for ver, info in API_VERSIONS.items()
        },
        "deprecated_endpoints": len(DEPRECATED_PATHS),
    }


def get_deprecation_headers(path: str) -> dict:
    """为弃用端点生成响应头"""
    headers = {}
    if path in DEPRECATED_PATHS:
        dep = DEPRECATED_PATHS[path]
        resp_date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        headers[DEPRECATION_HEADER] = resp_date
        if dep.get("sunset_date"):
            headers[SUNSET_HEADER] = dep["sunset_date"]
        if dep.get("replacement"):
            headers[LINK_HEADER] = f'<{dep["replacement"]}>; rel="successor-version"'
    return headers


def negotiate_version(accept_header: Optional[str]) -> str:
    """协商客户端请求的 API 版本

    Accept-Version 格式: "v2" 或 "v2;q=1.0, v3;q=0.8"
    返回最佳匹配版本或当前版本。
    """
    if not accept_header:
        return CURRENT_VERSION

    # 简单解析
    candidates = []
    for part in accept_header.split(","):
        part = part.strip()
        if ";" in part:
            ver_str, q_str = part.split(";", 1)
            try:
                q = float(q_str.strip().split("=")[1])
            except (IndexError, ValueError):
                q = 1.0
        else:
            ver_str = part
            q = 1.0
        candidates.append((ver_str.strip(), q))

    candidates.sort(key=lambda x: x[1], reverse=True)

    for ver, _ in candidates:
        if ver in SUPPORTED_VERSIONS:
            return ver

    return CURRENT_VERSION


def register_deprecated_path(path: str, replacement: str,
                             deprecated_since: str, sunset_date: str):
    """注册弃用路径"""
    DEPRECATED_PATHS[path] = {
        "replacement": replacement,
        "deprecated_since": deprecated_since,
        "sunset_date": sunset_date,
    }
