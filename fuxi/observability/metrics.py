"""伏羲 v1.0 — Prometheus 指标导出

提供标准的 Prometheus /metrics 端点和关键业务指标采集。"""
import contextlib
import logging
import time
from functools import wraps
from typing import Callable

logger = logging.getLogger("fuxi.observability.metrics")

# 延迟导入 prometheus_client，允许在未安装时优雅降级
_prom_available = False
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
    _prom_available = True
except ImportError:
    logger.debug("prometheus_client not installed, metrics disabled")


# ── 内存操作指标 ──
if _prom_available:
    MEMORY_CREATED = Counter(
        "fuxi_memory_created_total",
        "Total number of memories created",
        ["drawer_id"],
    )
    MEMORY_ACCESSED = Counter(
        "fuxi_memory_accessed_total",
        "Total number of memory accesses",
        ["drawer_id"],
    )
    MEMORY_DELETED = Counter(
        "fuxi_memory_deleted_total",
        "Total number of memories deleted",
    )
    MEMORY_SEARCHED = Counter(
        "fuxi_memory_search_total",
        "Total number of memory searches",
    )
    ACTIVE_MEMORIES = Gauge(
        "fuxi_active_memories",
        "Current number of active (non-archived) memories",
    )

    # ── 引擎指标 ──
    ENGINE_RUNS = Counter(
        "fuxi_engine_runs_total",
        "Total number of engine runs",
        ["engine_name", "status"],
    )
    ENGINE_RUN_DURATION = Histogram(
        "fuxi_engine_run_duration_seconds",
        "Engine run duration in seconds",
        ["engine_name"],
        buckets=[0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 30.0, 60.0],
    )
    ENGINE_ERRORS = Counter(
        "fuxi_engine_errors_total",
        "Total number of engine errors",
        ["engine_name"],
    )

    # ── API指标 ──
    API_REQUESTS = Counter(
        "fuxi_api_requests_total",
        "Total number of API requests",
        ["method", "path", "status_code"],
    )
    API_REQUEST_DURATION = Histogram(
        "fuxi_api_request_duration_seconds",
        "API request duration in seconds",
        ["method", "path"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0],
    )

    # ── 数据库指标 ──
    DB_POOL_ACTIVE = Gauge(
        "fuxi_db_pool_active",
        "Active database connections in pool",
    )
    DB_POOL_SIZE = Gauge(
        "fuxi_db_pool_size",
        "Maximum database connection pool size",
    )
else:
    # 空桩实现，避免代码中的 if/else 分支
    class _NoopMetric:
        def labels(self, **kw):
            return self

        def inc(self, *a, **kw):
            pass

        def dec(self, *a, **kw):
            pass

        def set(self, *a, **kw):
            pass

        def observe(self, *a, **kw):
            pass

    _noop = _NoopMetric()
    MEMORY_CREATED = MEMORY_ACCESSED = MEMORY_DELETED = MEMORY_SEARCHED = _noop
    ACTIVE_MEMORIES = _noop
    ENGINE_RUNS = ENGINE_RUN_DURATION = ENGINE_ERRORS = _noop
    API_REQUESTS = API_REQUEST_DURATION = _noop
    DB_POOL_ACTIVE = DB_POOL_SIZE = _noop


def track_engine_run(engine_name: str):
    """装饰器：追踪引擎运行"""

    def decorator(fn: Callable):
        @wraps(fn)
        def wrapper(*args, **kw):
            start = time.time()
            try:
                result = fn(*args, **kw)
                ENGINE_RUNS.labels(engine_name=engine_name, status="success").inc()
                return result
            except Exception:
                ENGINE_RUNS.labels(engine_name=engine_name, status="error").inc()
                ENGINE_ERRORS.labels(engine_name=engine_name).inc()
                raise
            finally:
                ENGINE_RUN_DURATION.labels(engine_name=engine_name).observe(
                    time.time() - start
                )

        return wrapper

    return decorator


def get_metrics_response() -> tuple:
    """获取 Prometheus metrics 端点响应内容"""
    if not _prom_available:
        _content = "# prometheus_client not installed\n"
        _type = "text/plain; charset=utf-8"
    else:
        _content = generate_latest(REGISTRY)
        _type = CONTENT_TYPE_LATEST
    return _content, _type


def update_memory_count(count: int):
    """更新活跃记忆数指标"""
    with contextlib.suppress(Exception):
        ACTIVE_MEMORIES.set(count)


def record_api_request(method: str, path: str, status_code: int, duration: float):
    """记录一次 API 请求"""
    try:
        API_REQUESTS.labels(method=method, path=path, status_code=str(status_code)).inc()
        API_REQUEST_DURATION.labels(method=method, path=path).observe(duration)
    except Exception:
        pass
