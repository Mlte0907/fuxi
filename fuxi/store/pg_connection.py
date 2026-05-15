"""伏羲 v1.5 PostgreSQL + pgvector 连接池

提供与 SQLite 连接池接口兼容的 PostgreSQL 连接池，
支持 pgvector 向量列和 HNSW 索引。
"""
import contextlib
import logging
import threading
import uuid
from queue import Empty, Queue

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2.extras import RealDictCursor

from fuxi.config import config

logger = logging.getLogger("fuxi.store.pg_connection")

# ── PostgreSQL 连接池 ──

_pg_pool: "PostgreSQLPool | None" = None


class PostgreSQLPool:
    """PostgreSQL 连接池，接口与 ConnectionPool 兼容"""

    def __init__(self):
        self._pool = pg_pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=config.db_pool_max,
            host=config.db_pg_host,
            port=config.db_pg_port,
            user=config.db_pg_user,
            password=config.db_pg_password,
            database=config.db_pg_database,
            cursor_factory=RealDictCursor,
        )
        self._lock = threading.Lock()
        self._stats = {"requests": 0, "misses": 0}

    def fetchall(self, sql: str, params=()):
        """查询所有结果（自动释放连接）"""
        with self._get() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    def fetchone(self, sql: str, params=()):
        """查询单条（自动释放连接）"""
        with self._get() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchone()

    def execute(self, sql: str, params=()):
        """执行单条 SQL（自动提交+释放）"""
        with self._get() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                conn.commit()

    @contextlib.contextmanager
    def connection(self):
        """获取连接上下文（自动提交+释放）"""
        conn = self._get()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    def _get(self):
        self._stats["requests"] += 1
        try:
            return self._pool.getconn()
        except Exception as e:
            self._stats["misses"] += 1
            raise TimeoutError(f"PG pool exhausted: {e}") from e

    def _put(self, conn):
        try:
            self._pool.putconn(conn)
        except Exception:
            pass

    def checkpoint_wal(self):
        """手动触发 Checkpoint"""
        try:
            with self._get() as conn:
                with conn.cursor() as cur:
                    cur.execute("CHECKPOINT;")
        except Exception as e:
            logger.warning(f"WAL checkpoint failed: {e}")

    @property
    def stats(self) -> dict:
        return dict(self._stats)


def get_pg_pool() -> PostgreSQLPool:
    global _pg_pool
    if _pg_pool is None:
        _pg_pool = PostgreSQLPool()
    return _pg_pool


# ── SQLite → PostgreSQL 数据迁移 ──

def export_sqlite_to_pg(sqlite_pool, pg_pool: PostgreSQLPool):
    """将 SQLite 数据导出到 PostgreSQL（一次性迁移）"""
    logger.info("Starting SQLite → PostgreSQL migration...")

    tables = ["items", "edges", "engine_states", "event_log",
              "schema_version", "experience_bank"]

    for table in tables:
        rows = sqlite_pool.fetchall(f"SELECT * FROM {table}")
        logger.info(f"Migrating table '{table}': {len(rows)} rows")
        for row in rows:
            cols = list(row.keys())
            placeholders = ", ".join(["%s"] * len(cols))
            values = tuple(row[c] for c in cols)
            try:
                with pg_pool.connection() as pg_conn:
                    with pg_conn.cursor() as cur:
                        cur.execute(
                            f"INSERT INTO {table} ({', '.join(cols)}) "
                            f"VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                            values,
                        )
            except Exception as e:
                logger.warning(f"Failed to migrate row in {table}: {e}")

    logger.info("SQLite → PostgreSQL migration completed")


# ── PostgreSQL Schema（用于初始化） ──

PG_SCHEMA = """
-- items 表（记忆）
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    raw_text TEXT NOT NULL DEFAULT '',
    facts TEXT DEFAULT '',
    importance REAL NOT NULL DEFAULT 0.5,
    decay_score REAL NOT NULL DEFAULT 1.0,
    emotion_valence REAL DEFAULT 0.0,
    drawer_id TEXT NOT NULL DEFAULT 'default',
    archived INTEGER NOT NULL DEFAULT 0,
    source TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    accessed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    embedding vector(1024),
    access_count INTEGER NOT NULL DEFAULT 0,
    tags TEXT DEFAULT ''
);

-- 向量索引（HNSW）
CREATE INDEX IF NOT EXISTS items_embedding_hnsw
    ON items USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

-- edges 表（图谱关系）
CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation TEXT NOT NULL DEFAULT 'related_to',
    weight REAL NOT NULL DEFAULT 1.0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT DEFAULT '',
    UNIQUE(source_id, target_id, relation)
);

CREATE INDEX IF NOT EXISTS edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS edges_target ON edges(target_id);

-- engine_states 表
CREATE TABLE IF NOT EXISTS engine_states (
    id SERIAL PRIMARY KEY,
    engine_name TEXT UNIQUE NOT NULL,
    state_json TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- event_log 表
CREATE TABLE IF NOT EXISTS event_log (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    source TEXT DEFAULT '',
    event_data TEXT DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS event_log_type_time ON event_log(event_type, created_at);

-- schema_version 表
CREATE TABLE IF NOT EXISTS schema_version (
    id SERIAL PRIMARY KEY,
    version TEXT UNIQUE NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- experience_bank 表
CREATE TABLE IF NOT EXISTS experience_bank (
    id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    input_desc TEXT NOT NULL,
    reasoning_summary TEXT DEFAULT '',
    conclusion TEXT NOT NULL,
    outcome TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""
