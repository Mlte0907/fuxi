"""OpenCode 适配器 - 生成 opencode.json + plugin"""
import json
import logging
from pathlib import Path

from fuxi.config import config

logger = logging.getLogger("fuxi.compat.opencode")


class OpenCodeAdapter:
    """OpenCode 记忆适配器

    生成 OpenCode 所需配置：
    - opencode.json - 主配置
    - .opencode/plugins/fuxi/ - 插件
    """

    def __init__(self, project_path: str = None):
        self.project_path = Path(project_path or config.current_project or ".")

    def write_configs(self) -> dict:
        """写入 OpenCode 配置文件"""
        results = {}

        # opencode.json
        config = {
            "version": "1.0",
            "plugins": [
                {
                    "name": "fuxi-memory",
                    "type": "memory",
                    "enabled": True,
                    "config": {
                        "api_endpoint": "http://localhost:19528",
                        "api_key": os.environ.get("FUXI_API_KEY", "your_fuxi_api_key_here"),
                        "default_drawer": "opencode_view"
                    }
                }
            ]
        }
        config_file = self.project_path / "opencode.json"
        config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
        results["config"] = str(config_file)

        # plugin 目录
        plugin_dir = self.project_path / ".opencode" / "plugins" / "fuxi"
        plugin_dir.mkdir(parents=True, exist_ok=True)

        plugin_manifest = {
            "name": "fuxi-memory",
            "version": "1.0.0",
            "description": "伏羲记忆系统 OpenCode 插件",
            "api_version": "v2",
            "endpoints": {
                "remember": "/api/v2/memories",
                "recall": "/api/v2/memory/recall",
                "search": "/api/v2/memory/search"
            }
        }
        manifest_file = plugin_dir / "manifest.json"
        manifest_file.write_text(json.dumps(plugin_manifest, indent=2), encoding="utf-8")
        results["plugin"] = str(manifest_file)

        logger.info(f"OpenCode config generated: {results}")
        return results
