"""伏羲 v1.0 SQLite连接池（WAL模式）"""
import contextlib
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from queue import Empty, Queue

from fuxi.config import config

logger = logging.getLogger("fuxi.store.connection")

class ConnectionPool:
    def __init__(self):
        self._pool = Queue(maxsize=config.db_pool_max)
        self._lock = threading.Lock()
        self._created = 0
        self._stats = {"requests": 0, "misses": 0, "retries": 0}

    def _create(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(config.db_path), exist_ok=True)
        conn = sqlite3.connect(str(config.db_path), timeout=config.db_pool_timeout, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # 写入性能优化 pragma
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-8000")        # 8MB 缓存
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA wal_autocheckpoint=1000")
        conn.execute("PRAGMA mmap_size=33554432")       # 32MB 内存映射
        conn.execute("PRAGMA busy_timeout=5000")        # 5s 忙等待
        conn.execute("PRAGMA temp_store=MEMORY")         # 临时表存内存
        return conn

    def _get(self) -> sqlite3.Connection:
        self._stats["requests"] += 1
        try:
            return self._pool.get_nowait()
        except Empty:
            pass
        with self._lock:
            if self._created < config.db_pool_max:
                self._created += 1
                self._stats["misses"] += 1
                return self._create()
        try:
            return self._pool.get(timeout=config.db_pool_timeout)
        except Empty as e:
            raise TimeoutError("Connection pool exhausted") from e

    def _put(self, conn: sqlite3.Connection):
        try:
            self._pool.put_nowait(conn)
        except Exception:
            # Queue full — close the connection but don't decrement _created
            # since this connection was already counted and we're just
            # returning it to a full pool (another connection will be reused)
            with contextlib.suppress(Exception):
                conn.close()

    def _close_or_return(self, conn):
        if not conn:
            return
        try:
            self._put(conn)
        except Exception:
            with contextlib.suppress(Exception):
                conn.close()

    @contextmanager
    def connection(self):
        conn = None
        for attempt in range(config.self_heal_max_retries):
            try:
                conn = self._get()
                yield conn
                conn.commit()
                self._put(conn)
                return
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < config.self_heal_max_retries - 1:
                    self._stats["retries"] += 1
                    time.sleep(0.1 * (2 ** attempt))
                    self._close_or_return(conn)
                    conn = None
                    continue
                self._close_or_return(conn)
                raise
            except Exception:
                self._close_or_return(conn)
                raise

    def fetchall(self, sql: str, params=()):
        with self.connection() as c:
            return c.execute(sql, params).fetchall()

    def fetchone(self, sql: str, params=()):
        with self.connection() as c:
            return c.execute(sql, params).fetchone()

    def execute(self, sql: str, params=()):
        with self.connection() as c:
            return c.execute(sql, params)

    def batch_write(self, operations: list[tuple[str, tuple]]) -> int:
        """批量写入 — 单事务提交多条SQL，大幅减少写入锁竞争

        Args:
            operations: [(sql, params), ...]

        Returns:
            成功写入的操作数
        """
        count = 0
        with self.connection() as conn:
            for sql, params in operations:
                try:
                    conn.execute(sql, params)
                    count += 1
                except Exception as e:
                    logger.warning(f"Batch write failed for '{sql[:50]}': {e}")
        return count

    def checkpoint_wal(self):
        """手动触发 WAL checkpoint — 在低负载时合并 WAL 到主DB"""
        try:
            with self.connection() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                logger.debug("WAL checkpoint completed")
        except Exception as e:
            logger.warning(f"WAL checkpoint failed: {e}")

    @property
    def stats(self) -> dict:
        return dict(self._stats)


_pool = None

def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool()
    return _pool
