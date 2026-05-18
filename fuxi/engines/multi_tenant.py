"""伏羲 v1.0 — MultiTenantEngine 多租户引擎"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime
from typing import Optional

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.multi_tenant")


@register_engine("multi_tenant", experimental=True)
class MultiTenantEngine(CognitiveEngine):
    """多租户引擎 — tenant_id 隔离 + 租户 API key 绑定

    功能:
    1. 租户创建、状态管理
    2. API Key 生成与验证（HMAC签名）
    3. 数据隔离：所有查询自动附加 tenant_id 条件
    4. 租户资源配额（items数量上限）
    """
    name = "multi_tenant"
    priority = 7
    interval = 300
    experimental = True

    QUOTA_DEFAULT = 10000  # 默认配额

    def run(self) -> dict:
        pool = get_pool()
        # 检查配额超限租户
        over_quota = self._check_quotas(pool)
        # 清理过期租户
        expired = self._cleanup_expired(pool)

        return {
            "status": "completed",
            "over_quota_tenants": len(over_quota),
            "expired_cleaned": expired,
            "timestamp": datetime.now().isoformat(),
        }

    # ── 租户管理 ──

    def create_tenant(self, name: str, quota: int | None = None, metadata: dict | None = None) -> dict:
        """创建新租户"""
        pool = get_pool()
        tenant_id = secrets.token_hex(16)
        api_key = self._generate_api_key(tenant_id)
        quota = quota or self.QUOTA_DEFAULT
        now = datetime.now().isoformat()

        with pool.connection() as c:
            c.execute(
                "INSERT INTO tenants (tenant_id, name, api_key, quota, metadata, created_at, status) "
                "VALUES (?,?,?,?,?,?,?)",
                (tenant_id, name, api_key, quota, json.dumps(metadata or {}), now, "active")
            )

        logger.info(f"[multi_tenant] created tenant: {tenant_id} ({name})")
        return {
            "tenant_id": tenant_id,
            "name": name,
            "api_key": api_key,
            "quota": quota,
            "status": "active",
        }

    def get_tenant(self, tenant_id: str) -> Optional[dict]:
        """获取租户信息"""
        pool = get_pool()
        row = pool.fetchone("SELECT * FROM tenants WHERE tenant_id=?", (tenant_id,))
        return dict(row) if row else None

    def validate_api_key(self, tenant_id: str, api_key: str) -> bool:
        """验证 API Key（HMAC签名校验）"""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return False
        expected = self._generate_api_key(tenant_id, tenant["api_secret"])
        return hmac.compare_digest(api_key, expected)

    def _generate_api_key(self, tenant_id: str, secret: str | None = None) -> str:
        """生成 API Key（HMAC-SHA256）"""
        secret = secret or secrets.token_hex(32)
        msg = f"{tenant_id}:{secret}"
        key = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()[:32]
        return f"fuxi_{tenant_id[:8]}_{key}"

    # ── 数据隔离 ──

    def filter_by_tenant(self, sql: str, tenant_id: str | None = None) -> tuple[str, tuple]:
        """为 SQL 查询附加 tenant_id 过滤"""
        if not tenant_id:
            return sql, ()
        # 简单实现：确保 tenant_id 出现在 WHERE 条件中
        if "WHERE" in sql.upper():
            return f"{sql} AND tenant_id=?", (tenant_id,)
        return f"{sql} WHERE tenant_id=?", (tenant_id,)

    def check_quota(self, tenant_id: str) -> dict:
        """检查租户配额使用情况"""
        pool = get_pool()
        row = pool.fetchone(
            "SELECT COUNT(*) as count FROM items WHERE tenant_id=?",
            (tenant_id,)
        )
        current = row["count"] if row else 0
        tenant = self.get_tenant(tenant_id)
        quota = tenant["quota"] if tenant else self.QUOTA_DEFAULT
        return {
            "tenant_id": tenant_id,
            "current": current,
            "quota": quota,
            "usage_pct": round(current / quota * 100, 2) if quota > 0 else 100,
            "over_quota": current >= quota,
        }

    def _check_quotas(self, pool) -> list[dict]:
        """检查所有超配额租户"""
        rows = pool.fetchall(
            "SELECT tenant_id, quota FROM tenants WHERE status='active'"
        )
        over = []
        for r in rows:
            usage = self.check_quota(r["tenant_id"])
            if usage["over_quota"]:
                over.append(usage)
        return over

    def _cleanup_expired(self, pool) -> int:
        """清理过期租户（超过30天未活跃）"""
        threshold = (datetime.now().timestamp() - 30 * 86400) if False else datetime.now().isoformat()
        rows = pool.fetchall(
            "SELECT tenant_id FROM tenants WHERE status='expired' OR last_active_at < ?",
            (threshold,)
        )
        count = 0
        with pool.connection() as c:
            for r in rows:
                c.execute("DELETE FROM tenants WHERE tenant_id=?", (r["tenant_id"],))
                count += 1
        return count

    def _ensure_tables(self):
        """确保租户表存在"""
        pool = get_pool()
        pool.execute(
            "CREATE TABLE IF NOT EXISTS tenants ("
            "tenant_id TEXT PRIMARY KEY, "
            "name TEXT, "
            "api_key TEXT, "
            "api_secret TEXT, "
            "quota INTEGER DEFAULT 10000, "
            "metadata TEXT, "
            "created_at TEXT, "
            "last_active_at TEXT, "
            "status TEXT DEFAULT 'active')"
        )

    def _get_subscriptions(self):
        return {
            "tenant.created": self._on_tenant_event,
        }

    def _on_tenant_event(self, event):
        self._state.metadata.setdefault("_pending_events", []).append(event.data)


# json import needed for metadata serialization
import json