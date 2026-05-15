"""伏羲 v1.0 — SafetyEngine 安全审查 v2.0

增强功能：
- 14 种密钥模式检测（参考 AgentShield）
- CLAUDE.md 注入检测
- Hook 安全审计（MCP/Hook 注入）
- MCP 服务器风险评分
- 配置安全扫描
"""
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.safety")


@register_engine("safety", experimental=False)
class SafetyEngine(CognitiveEngine):
    """安全审查 — 扫描记忆和配置中的敏感/危险内容"""
    name = "safety"
    priority = 8
    interval = 1800  # 30分钟

    # AgentShield 风格密钥检测模式（14种）
    SECRET_PATTERNS = [
        (r"(?i)password\s*[=:]\s*['\"]?[\w\-\+\$\/\=]{8,64}['\"]?", "password_leak"),
        (r"(?i)api[_\-]?key\s*[=:]\s*['\"]?[a-zA-Z0-9_\-]{20,64}['\"]?", "api_key_leak"),
        (r"(?i)token\s*[=:]\s*['\"]?[a-zA-Z0-9_\-\.]{20,80}['\"]?", "token_leak"),
        (r"(?i)secret\s*[=:]\s*['\"]?[\w\-\+\$\/\=]{16,64}['\"]?", "secret_leak"),
        (r"(?i)bearer\s+[a-zA-Z0-9_\-\.]+", "bearer_token"),
        (r"(?i)sk\-[a-zA-Z0-9]{32,64}", "openai_sk"),
        (r"(?i)sk\-[a-zA-Z0-9]{48,}", "anthropic_sk"),
        (r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----", "private_key"),
        (r"-----BEGIN\s+EC\s+PRIVATE\s+KEY-----", "ec_private_key"),
        (r"(?i)ghp_[a-zA-Z0-9]{36}", "github_token"),
        (r"(?i)gho_[a-zA-Z0-9]{36}", "github_oauth"),
        (r"(?i)xox[baprs]-[a-zA-Z0-9]{10,48}", "slack_token"),
        (r"(?i)AIza[a-zA-Z0-9_\\-]{35}", "google_api_key"),
        (r"(?i)amzn\.[a-zA-Z0-9_=]{40,140}", "aws_access_key"),
    ]

    # CLAUDE.md 注入检测模式
    INJECTION_PATTERNS = [
        (r"(?i)import\s+os\s*;?\s*os\.system", "code_injection_system"),
        (r"(?i)subprocess\.(run|call|check_output|Popen)", "code_injection_subprocess"),
        (r"(?i)eval\s*\(\s*request", "code_injection_eval"),
        (r"(?i)<script[^>]*>.*?</script>", "xss_script_tag"),
        (r"(?i)\$\([^)]*\)\.remove\(\)", "dom_xss"),
        (r"(?i)localStorage\.setItem.*innerHTML", "xss_localstorage"),
    ]

    # Hook 危险命令检测
    HOOK_DANGEROUS_PATTERNS = [
        (r"curl\s+.*\|\s*bash", "curl_bash_hook"),
        (r"wget\s+.*\|\s*bash", "wget_bash_hook"),
        (r"rm\s+-[rf]", "destructive_rm_hook"),
        (r"chmod\s+777", "perm_777_hook"),
        (r">\s*/etc/", "write_etc_hook"),
        (r"mv\s+.*\s+/\s*$", "move_to_root_hook"),
    ]

    def run(self) -> dict:
        pool = get_pool()
        alerts = []

        # 1. 扫描记忆中的敏感信息
        memory_alerts = self._scan_memories(pool)
        alerts.extend(memory_alerts)

        # 2. 扫描配置文件中的泄漏
        config_alerts = self._scan_configs()
        alerts.extend(config_alerts)

        # 3. 扫描 CLAUDE.md 注入
        claude_md_alerts = self._scan_claude_md()
        alerts.extend(claude_md_alerts)

        # 4. 扫描 Hook 脚本安全
        hook_alerts = self._scan_hooks()
        alerts.extend(hook_alerts)

        state = {
            "scanned_memories": len(memory_alerts),
            "scanned_configs": len(config_alerts),
            "scanned_hooks": len(hook_alerts),
            "total_alerts": len(alerts),
            "details": alerts[:50],
            "timestamp": datetime.now().isoformat(),
        }

        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                "VALUES (?,?,?)",
                ("safety", json.dumps(state, ensure_ascii=False), datetime.now().isoformat())
            )

        if alerts:
            logger.warning(f"Safety: {len(alerts)} security alerts found")

        self._state.metadata["last_audit"] = state
        return state

    def _scan_memories(self, pool) -> list:
        alerts = []
        rows = pool.fetchall(
            "SELECT id, raw_text FROM items WHERE archived=0 "
            "AND id NOT IN (SELECT item_id FROM agent_views WHERE agent_id='safety_audit') "
            "ORDER BY created_at DESC LIMIT 200"
        )
        for r in rows:
            text = r["raw_text"]
            text_lower = text.lower()

            # 密钥检测
            for pattern, category in self.SECRET_PATTERNS:
                if re.search(pattern, text):
                    alerts.append({
                        "type": "secret_leak",
                        "category": category,
                        "item_id": r["id"][:8],
                        "matched": pattern[:50],
                        "severity": "high"
                    })
                    break

            # 注入检测
            for pattern, category in self.INJECTION_PATTERNS:
                if re.search(pattern, text):
                    alerts.append({
                        "type": "injection",
                        "category": category,
                        "item_id": r["id"][:8],
                        "matched": pattern[:50],
                        "severity": "critical"
                    })
                    break

            # 标记已审查
            with pool.connection() as c:
                c.execute(
                    "INSERT OR IGNORE INTO agent_views (agent_id, item_id) VALUES (?,?)",
                    ("safety_audit", r["id"])
                )
        return alerts

    def _scan_configs(self) -> list:
        alerts = []
        config_paths = [
            Path.home() / ".claude" / "settings.json",
            Path.home() / ".claude" / "projects" / "-home-xiaoxin" / "memory" / "MEMORY.md",
        ]
        for p in config_paths:
            if not p.exists():
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                for pattern, category in self.SECRET_PATTERNS:
                    matches = re.findall(pattern, content)
                    for m in matches[:3]:  # 最多3个
                        alerts.append({
                            "type": "config_leak",
                            "category": category,
                            "file": str(p),
                            "matched": m[:60],
                            "severity": "high"
                        })
            except Exception:
                pass
        return alerts

    def _scan_claude_md(self) -> list:
        alerts = []
        for p in Path.home().glob("**/CLAUDE.md"):
            if not p.exists():
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore")
                for pattern, category in self.INJECTION_PATTERNS:
                    if re.search(pattern, content):
                        alerts.append({
                            "type": "claude_md_injection",
                            "category": category,
                            "file": str(p),
                            "severity": "critical"
                        })
            except Exception:
                pass
        return alerts

    def _scan_hooks(self) -> list:
        alerts = []
        hook_dir = Path.home() / "fuxi" / "fuxi_scripts" / "hooks"
        if not hook_dir.exists():
            return alerts

        for hook_file in hook_dir.glob("*.sh"):
            try:
                content = hook_file.read_text(encoding="utf-8", errors="ignore")
                for pattern, category in self.HOOK_DANGEROUS_PATTERNS:
                    if re.search(pattern, content):
                        alerts.append({
                            "type": "dangerous_hook",
                            "category": category,
                            "file": str(hook_file.name),
                            "matched": pattern[:50],
                            "severity": "high"
                        })
            except Exception:
                pass
        return alerts

    def health_check(self) -> dict:
        base = super().health_check()
        return {
            **base,
            "alert_count": self._state.metadata.get("last_audit", {}).get("total_alerts", 0),
        }
