"""Codex 适配器 - 生成 .codex/ 配置"""
import json
import logging
from pathlib import Path

from fuxi.config import config

logger = logging.getLogger("fuxi.compat.codex")


class CodexAdapter:
    """GitHub Copilot Codex 记忆适配器

    生成 Codex 所需配置：
    - .codex/config.toml - API 配置
    - .codex/agents/ - Agent 配置
    """

    def __init__(self, project_path: str = None):
        self.project_path = Path(project_path or config.current_project or ".")

    def write_configs(self) -> dict:
        """写入 Codex 配置文件"""
        results = {}

        # config.toml
        codex_dir = self.project_path / ".codex"
        codex_dir.mkdir(parents=True, exist_ok=True)

        config_toml = f"""[api]
endpoint = "http://localhost:19528"
api_key = os.environ.get("FUXI_API_KEY", "your_fuxi_api_key_here")

[memory]
default_drawer = "codex_view"
auto_store = true

[agents]
default_agent = "fuxi-codex"
"""
        config_file = codex_dir / "config.toml"
        config_file.write_text(config_toml, encoding="utf-8")
        results["config"] = str(config_file)

        # agents 目录
        agents_dir = codex_dir / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        agent_config = {
            "name": "fuxi-codex",
            "description": "伏羲记忆系统 Codex Agent",
            "api_endpoint": "http://localhost:19528/api/v2",
            "memory_drawer": "codex_view"
        }
        agent_file = agents_dir / "default.json"
        agent_file.write_text(json.dumps(agent_config, indent=2), encoding="utf-8")
        results["agents"] = str(agent_file)

        logger.info(f"Codex config generated: {results}")
        return results
