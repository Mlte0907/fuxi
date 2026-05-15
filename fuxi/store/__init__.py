"""存储层 — 唯一数据入口"""
from fuxi.config import config
from fuxi.store.connection import ConnectionPool, get_pool
from fuxi.store.migrations import get_schema_version, init_db
from fuxi.store.pg_connection import get_pg_pool, export_sqlite_to_pg, PG_SCHEMA

# ── 统一数据入口 ──
# config.db_pg_enabled = True 时使用 PostgreSQL，否则使用 SQLite
_pool_mode = None  # "sqlite" | "pg"


def get_active_pool():
    """返回当前激活的连接池（SQLite 或 PostgreSQL）"""
    global _pool_mode
    if config.db_pg_enabled:
        if _pool_mode != "pg":
            _pool_mode = "pg"
            logger.info("Switching to PostgreSQL pool")
        return get_pg_pool()
    else:
        if _pool_mode != "sqlite":
            _pool_mode = "sqlite"
            logger.info("Using SQLite pool")
        return get_pool()


import logging
logger = logging.getLogger("fuxi.store")
