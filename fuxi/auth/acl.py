"""伏羲 v1.0 — 统一 ACL（合并 ACL+RBAC+Domain）"""
import json
import logging
from enum import Enum
from pathlib import Path
from typing import List, Optional

import yaml

from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.acl")

_agents_yml = Path(__file__).parent.parent / "agent" / "agents.yml"
with open(_agents_yml) as f:
    _config = yaml.safe_load(f)
    ROLE_PERMISSIONS = {
        role: set(perms)
        for role, perms in _config["roles"].items()
    }


class Permission(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"
    ENGINE_CONTROL = "engine_control"
    AGENT_IMPERSONATE = "agent_impersonate"


class UnifiedACL:
    """三合一权限：ACL + RBAC + Agent Domains"""

    def __init__(self):
        self._cache: dict = {}
        self._domain_cache: dict = {}

    def check(self, agent_id: str, permission: Permission,
              resource_id: Optional[str] = None, drawer_id: Optional[str] = None) -> bool:
        """检查 agent 是否有权限"""
        # 先查缓存
        cache_key = f"{agent_id}:{permission}:{resource_id or '*'}:{drawer_id or '*'}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        pool = get_pool()
        row = pool.fetchone(
            "SELECT permissions, agent_domains FROM unified_acl WHERE agent_id = ?",
            (agent_id,)
        )

        if not row:
            result = False
        else:
            perms = set(json.loads(row["permissions"] or "[]"))
            domains = json.loads(row["agent_domains"] or "[]")

            # RBAC检查
            result = permission.value in perms

            # Domain检查（如果有资源/抽屉ID）
            if result and (resource_id or drawer_id):
                result = self._check_domain(domains, drawer_id, resource_id)

        self._cache[cache_key] = result
        return result

    def grant(self, agent_id: str, permissions: List[str],
              agent_domains: Optional[List[str]] = None, role: Optional[str] = None):
        """授权"""
        pool = get_pool()
        perms_json = json.dumps(permissions, ensure_ascii=False)

        if role:
            # 根据角色扩展权限
            role_perms = ROLE_PERMISSIONS.get(role, set())
            perms_json = json.dumps(list(role_perms | set(permissions)), ensure_ascii=False)

        domains_json = json.dumps(agent_domains or [], ensure_ascii=False)

        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO unified_acl (agent_id, permissions, agent_domains, role) "
                "VALUES (?,?,?,?)",
                (agent_id, perms_json, domains_json, role)
            )

        self._cache.clear()
        logger.info(f"ACL grant: {agent_id} role={role} perms={permissions}")

    def revoke(self, agent_id: str):
        pool = get_pool()
        with pool.connection() as c:
            c.execute("DELETE FROM unified_acl WHERE agent_id = ?", (agent_id,))
        self._cache.clear()

    def list_agents(self) -> List[dict]:
        pool = get_pool()
        rows = pool.fetchall("SELECT * FROM unified_acl")
        return [{
            "agent_id": r["agent_id"],
            "permissions": json.loads(r["permissions"]),
            "agent_domains": json.loads(r["agent_domains"]),
            "role": r["role"]
        } for r in rows]

    def _check_domain(self, domains: List[str], drawer_id: Optional[str] = None,
                      resource_id: Optional[str] = None) -> bool:
        """检查 domain 限制"""
        if not domains:
            return True  # 无限制
        cache_key = f"{tuple(sorted(domains))}:{drawer_id}:{resource_id}"
        if cache_key in self._domain_cache:
            return self._domain_cache[cache_key]
        result = bool((drawer_id and drawer_id in domains) or (resource_id and resource_id in domains))
        self._domain_cache[cache_key] = result
        return result

    def clear_cache(self):
        self._cache.clear()
        self._domain_cache.clear()


_acl_instance: Optional[UnifiedACL] = None


def get_acl() -> UnifiedACL:
    global _acl_instance
    if _acl_instance is None:
        _acl_instance = UnifiedACL()
    return _acl_instance
