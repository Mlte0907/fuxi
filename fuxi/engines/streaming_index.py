"""伏羲 v1.0 — StreamingIndexEngine 流式索引引擎"""
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.streaming_index")


@register_engine("streaming_index", experimental=True)
class StreamingIndexEngine(CognitiveEngine):
    """流式索引引擎 — 增量索引 + WAL 日志

    工作流程:
    1. 扫描 items 表中未索引的新记录
    2. 将增量写入 WAL（Write-Ahead Log）文件
    3. 后台合并 WAL 到主索引表
    4. 支持断点续传和故障恢复
    """
    name = "streaming_index"
    priority = 6
    interval = 30  # 每30秒增量索引
    experimental = True

    WAL_TABLE = "index_wal"
    INDEX_TABLE = "item_index"

    def run(self) -> dict:
        pool = get_pool()
        new_items = self._scan_new_items(pool)
        if not new_items:
            return {"status": "idle", "scanned": 0, "timestamp": datetime.now().isoformat()}

        wal_entries = self._write_wal(pool, new_items)
        merged = self._merge_wal(pool)

        return {
            "status": "completed",
            "scanned": len(new_items),
            "wal_entries": wal_entries,
            "merged": merged,
            "timestamp": datetime.now().isoformat(),
        }

    def _scan_new_items(self, pool) -> list[dict]:
        """扫描未索引的新记录"""
        last_indexed = self._state.metadata.get("last_indexed_id", 0)
        rows = pool.fetchall(
            f"SELECT id, content, metadata, created_at FROM items "
            f"WHERE id > ? AND archived=0 "
            f"ORDER BY id ASC LIMIT 500",
            (last_indexed,)
        )
        return rows

    def _write_wal(self, pool, items: list[dict]) -> int:
        """写入 WAL 日志"""
        self._ensure_wal_table(pool)
        entries = 0
        now = datetime.now().isoformat()
        with pool.connection() as c:
            for item in items:
                index_data = {
                    "item_id": item["id"],
                    "content": item["content"],
                    "metadata": item["metadata"],
                    "indexed_at": now,
                    "wal_status": "pending",
                }
                c.execute(
                    f"INSERT OR REPLACE INTO {self.WAL_TABLE} "
                    f"(item_id, index_data, wal_status, created_at) VALUES (?,?,?,?)",
                    (item["id"], json.dumps(index_data, ensure_ascii=False), "pending", now)
                )
                entries += 1

        # 更新游标
        if items:
            self._state.metadata["last_indexed_id"] = items[-1]["id"]

        logger.debug(f"[streaming_index] wrote {entries} WAL entries")
        return entries

    def _merge_wal(self, pool) -> int:
        """合并 WAL 到主索引表"""
        self._ensure_index_table(pool)
        merged = 0
        now = datetime.now().isoformat()

        pending = pool.fetchall(
            f"SELECT item_id, index_data FROM {self.WAL_TABLE} WHERE wal_status='pending' LIMIT 200"
        )
        if not pending:
            return 0

        with pool.connection() as c:
            for row in pending:
                index_data = json.loads(row["index_data"])
                c.execute(
                    f"INSERT OR REPLACE INTO {self.INDEX_TABLE} "
                    f"(item_id, content, metadata, indexed_at) VALUES (?,?,?,?)",
                    (
                        index_data["item_id"],
                        index_data["content"],
                        index_data["metadata"],
                        now,
                    )
                )
                c.execute(
                    f"UPDATE {self.WAL_TABLE} SET wal_status='merged' WHERE item_id=?",
                    (row["item_id"],)
                )
                merged += 1

        logger.debug(f"[streaming_index] merged {merged} entries to index")
        return merged

    def _ensure_wal_table(self, pool):
        """确保 WAL 表存在"""
        pool.execute(
            f"CREATE TABLE IF NOT EXISTS {self.WAL_TABLE} ("
            f"item_id INTEGER PRIMARY KEY, "
            f"index_data TEXT, "
            f"wal_status TEXT DEFAULT 'pending', "
            f"created_at TEXT)"
        )

    def _ensure_index_table(self, pool):
        """确保主索引表存在"""
        pool.execute(
            f"CREATE TABLE IF NOT EXISTS {self.INDEX_TABLE} ("
            f"item_id INTEGER PRIMARY KEY, "
            f"content TEXT, "
            f"metadata TEXT, "
            f"indexed_at TEXT)"
        )
        pool.execute(
            f"CREATE INDEX IF NOT EXISTS idx_index_item_id ON {self.INDEX_TABLE}(item_id)"
        )

    def _get_subscriptions(self):
        return {
            "items.created": self._on_event,
            "items.updated": self._on_event,
        }

    def recover(self) -> dict:
        """故障恢复：从 WAL 恢复未合并的条目"""
        pool = get_pool()
        pending = pool.fetchall(
            f"SELECT item_id, index_data FROM {self.WAL_TABLE} WHERE wal_status='pending'"
        )
        self._ensure_index_table(pool)
        merged = self._merge_wal(pool)
        return {
            "status": "recovered",
            "pending_before": len(pending),
            "merged": merged,
            "timestamp": datetime.now().isoformat(),
        }