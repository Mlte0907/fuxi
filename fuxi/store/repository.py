"""伏羲 v1.0 — 统一 Repository 模式（CRUD 基类）"""
import contextlib
import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.store.repository")


class Repository:
    """通用 Repository，基于表名提供 CRUD"""
    table: str = ""
    id_field: str = "id"
    json_fields: tuple = ()
    auto_timestamp: bool = True

    def __init__(self, table: Optional[str] = None):
        if table:
            self.table = table

    def create(self, **kwargs) -> str:
        if not self.table:
            raise ValueError("table not set")
        pool = get_pool()
        item_id = kwargs.pop("id", str(uuid.uuid4()))
        now = datetime.now().isoformat()

        if self.auto_timestamp:
            kwargs.setdefault("created_at", now)
            kwargs.setdefault("updated_at", now)

        kwargs[self.id_field] = item_id

        # 序列化 JSON 字段
        for f in self.json_fields:
            if f in kwargs and not isinstance(kwargs[f], str):
                kwargs[f] = json.dumps(kwargs[f], ensure_ascii=False)

        columns = ",".join(kwargs.keys())
        placeholders = ",".join("?" * len(kwargs))
        values = list(kwargs.values())

        with pool.connection() as c:
            c.execute(
                f"INSERT INTO {self.table} ({columns}) VALUES ({placeholders})",
                values
            )
        return item_id

    def get(self, item_id: str) -> Optional[dict]:
        pool = get_pool()
        row = pool.fetchone(
            f"SELECT * FROM {self.table} WHERE {self.id_field}=?", (item_id,)
        )
        if row:
            return self._deserialize(dict(row))
        return None

    def list(self, limit: int = 50, offset: int = 0,
             order_by: Optional[str] = None, **filters) -> List[dict]:
        pool = get_pool()
        clauses = []
        params = []
        for k, v in filters.items():
            clauses.append(f"{k}=?")
            params.append(v)
        where = " AND ".join(clauses) if clauses else "1=1"
        order = f"ORDER BY {order_by}" if order_by else ""
        rows = pool.fetchall(
            f"SELECT * FROM {self.table} WHERE {where} {order} LIMIT ? OFFSET ?",
            params + [limit, offset]
        )
        return [self._deserialize(dict(r)) for r in rows]

    def update(self, item_id: str, **kwargs) -> bool:
        pool = get_pool()
        if self.auto_timestamp:
            kwargs["updated_at"] = datetime.now().isoformat()

        for f in self.json_fields:
            if f in kwargs and not isinstance(kwargs[f], str):
                kwargs[f] = json.dumps(kwargs[f], ensure_ascii=False)

        sets = ",".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [item_id]

        with pool.connection() as c:
            cur = c.execute(
                f"UPDATE {self.table} SET {sets} WHERE {self.id_field}=?",
                values
            )
        return cur.rowcount > 0

    def delete(self, item_id: str, soft: bool = True) -> bool:
        pool = get_pool()
        if soft and self._has_column("archived"):
            with pool.connection() as c:
                cur = c.execute(
                    f"UPDATE {self.table} SET archived=1, updated_at=? WHERE {self.id_field}=?",
                    (datetime.now().isoformat(), item_id)
                )
        else:
            with pool.connection() as c:
                cur = c.execute(f"DELETE FROM {self.table} WHERE {self.id_field}=?", (item_id,))
        return cur.rowcount > 0

    def _has_column(self, col: str) -> bool:
        pool = get_pool()
        # Fetch all rows
        rows = pool.fetchall(f"PRAGMA table_info({self.table})")
        return any(r["name"] == col for r in rows)

    def count(self, **filters) -> int:
        pool = get_pool()
        clauses = []
        params = []
        for k, v in filters.items():
            clauses.append(f"{k}=?")
            params.append(v)
        where = " AND ".join(clauses) if clauses else "1=1"
        row = pool.fetchone(f"SELECT COUNT(*) AS cnt FROM {self.table} WHERE {where}", params)
        return row["cnt"] if row else 0

    def _deserialize(self, row: dict) -> dict:
        for f in self.json_fields:
            if f in row and isinstance(row[f], str):
                with contextlib.suppress(json.JSONDecodeError):
                    row[f] = json.loads(row[f])
        return row


class ItemRepository(Repository):
    table = "items"
    json_fields = ("tags", "collaborators")


class DrawerRepository(Repository):
    table = "drawers"


class EdgeRepository(Repository):
    table = "edges"
    json_fields = ("metadata",)


class AgentViewRepository(Repository):
    table = "agent_views"
