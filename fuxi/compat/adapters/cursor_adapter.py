"""Cursor 适配器 - 生成 .cursor/ 配置"""
import json
import logging
from pathlib import Path

from fuxi.config import config
from fuxi.memory.ingestion import remember

logger = logging.getLogger("fuxi.compat.cursor")


class CursorAdapter:
    """Cursor AI 记忆适配器

    生成 Cursor 所需配置：
    - .cursor/rules/ - 记忆规则
    - .cursor/agents/ - Agent 配置
    """

    def __init__(self, project_path: str = None):
        self.project_path = Path(project_path or config.current_project or ".")

    def generate_hooks_config(self) -> dict:
        """生成 hooks.json，桥接到伏羲记忆"""
        return {
            "onFileChange": [
                {
                    "pattern": "**/*.py",
                    "command": f"curl -s -X POST http://localhost:19528/api/v2/memories "
                             f"-H 'X-API-Key: jinlange-fuxi-2026' "
                             f"-H 'Content-Type: application/json' "
                             f"-d '{{\"text\":\"File changed: {{file}}\",\"drawer_id\":\"cursor_view\"}}'"
                }
            ],
            "preCommit": [
                {
                    "command": f"curl -s http://localhost:19528/api/v2/memory/recall?drawer=cursor_view&limit=3"
                }
            ]
        }

    def write_configs(self) -> dict:
        """写入 Cursor 配置文件到项目目录"""
        results = {}

        # rules 目录
        rules_dir = self.project_path / ".cursor" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)

        # 生成伏羲记忆规则
        fuxi_rule = """# 伏羲记忆系统集成

## 规则
- 重要决策后调用 remember() 存储到 drawer: cursor_view
- 使用 recall() 检索相关记忆
- 文件变更自动记录

## API
- remember(text, drawer_id="cursor_view")
- recall(query, drawer_id="cursor_view")
"""
        rule_file = rules_dir / "fuxi_memory.md"
        rule_file.write_text(fuxi_rule, encoding="utf-8")
        results["rules"] = str(rule_file)

        # agents 目录
        agents_dir = self.project_path / ".cursor" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        # 生成 agent 配置
        agent_config = {
            "name": "伏羲助理",
            "description": "接入伏羲记忆系统的 Cursor Agent",
            "memory_drawer": "cursor_view",
            "api_endpoint": "http://localhost:19528"
        }
        agent_file = agents_dir / "fuxi.json"
        agent_file.write_text(json.dumps(agent_config, indent=2), encoding="utf-8")
        results["agents"] = str(agent_file)

        logger.info(f"Cursor config generated: {results}")
        return results
