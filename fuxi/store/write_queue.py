"""伏羲 v1.0 — 异步写队列

将非关键写入（event_log、统计更新等）异步批量提交，
降低主线程SQLite写入竞争，提升整体吞吐量。"""
import logging
import queue
import threading
from typing import List, Tuple

from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.store.write_queue")


class WriteQueue:
    """异步写队列 — 将低优先级写入操作批量提交"""

    def __init__(self, flush_interval: float = 5.0, batch_size: int = 50):
        self._queue: queue.Queue = queue.Queue()
        self._flush_interval = flush_interval
        self._batch_size = batch_size
        self._thread: threading.Thread | None = None
        self._stopped = threading.Event()
        self._stats = {"enqueued": 0, "flushed": 0, "failed": 0}

    def enqueue(self, sql: str, params: tuple = ()):
        """入队一条写入操作"""
        self._queue.put((sql, params))
        self._stats["enqueued"] += 1

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stopped.clear()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="write-queue"
        )
        self._thread.start()
        logger.info("Write queue started")

    def stop(self):
        self._stopped.set()
        if self._thread:
            self._thread.join(timeout=10)
        # 清空剩余
        self._drain()
        logger.info("Write queue stopped")

    def _run(self):
        while not self._stopped.wait(timeout=self._flush_interval):
            self._drain()

    def _drain(self):
        batch: List[Tuple[str, tuple]] = []
        while len(batch) < self._batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break

        if not batch:
            return

        pool = get_pool()
        try:
            with pool.connection() as conn:
                for sql, params in batch:
                    conn.execute(sql, params)
            self._stats["flushed"] += len(batch)
        except Exception as e:
            logger.warning(f"Write queue flush failed: {e}")
            self._stats["failed"] += len(batch)

    @property
    def stats(self) -> dict:
        return {
            **self._stats,
            "pending": self._queue.qsize(),
        }


# 全局写队列（用于 event_log 等非关键写入）
_write_queue: WriteQueue | None = None
_wq_lock = threading.Lock()


def get_write_queue() -> WriteQueue:
    global _write_queue
    if _write_queue is None:
        with _wq_lock:
            if _write_queue is None:
                _write_queue = WriteQueue()
    return _write_queue
