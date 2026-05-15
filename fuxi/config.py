"""伏羲 v1.0 统一配置"""
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_env_file = Path.home() / ".openclaw" / "keys" / "fuxi.env"
if _env_file.exists():
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                os.environ.setdefault(k, v)


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FUXI_", extra="ignore")

    # 路径
    base_dir: Path = Path(os.path.expanduser("~/.openclaw/fuxi_v1"))
    db_path: Path = Path(".")
    backup_dir: Path = Path(".")

    # 服务
    host: str = "0.0.0.0"
    port: int = 19528
    api_key: str = ""

    # 记忆
    default_context_budget: int = 1000

    # 数据库
    db_pool_max: int = 10
    db_pool_timeout: int = 5

    # PostgreSQL + pgvector（v1.5: 升级为生产级存储）
    db_pg_enabled: bool = False  # True 时切换到 PostgreSQL
    db_pg_host: str = "localhost"
    db_pg_port: int = 5432
    db_pg_user: str = "fuxi"
    db_pg_password: str = ""
    db_pg_database: str = "fuxi"

    # 嵌入
    embed_cache_max: int = 32
    embed_dim: int = 1024
    embed_api_url: str = "https://api.siliconflow.cn/v1/embeddings"
    embed_api_model: str = "BAAI/bge-large-zh-v1.5"
    embed_fail_threshold: int = 3

    # 检索
    recall_cache_max: int = 16
    vector_weight_default: float = 0.6
    fts_weight_default: float = 4.0
    similarity_threshold: float = 0.5  # 向量搜索结果的最低余弦相似度

    # 衰减
    decay_base: float = 0.95
    night_decay_factor: float = 0.5
    touch_boost_short: float = 1.35
    touch_boost_long: float = 1.06
    decay_floor: float = 0.15

    # 工作记忆
    wm_capacity: int = 7
    wm_capacity_adaptive: bool = True  # v1.1: 根据系统负载自适应调整容量

    # 反思引擎
    reflection_daily_cap: int = 20  # 每日反思记忆上限

    # 梦境
    dream_interval: int = 1800

    confidence_sources: dict = Field(default_factory=lambda: {"direct": 1.0, "inferred": 0.6, "hearsay": 0.3})

    # 图
    edge_types: list = Field(default_factory=lambda: ["causes", "contradicts", "refines", "depends_on", "related_to",
                        "temporal", "enables", "hinders", "supersedes"])

    # 自愈
    self_heal_max_retries: int = 3

    # 备份
    backup_max_count: int = 7

    # API密钥（外部服务）
    siliconflow_key: str = ""
    openclaw_gateway: str = "http://127.0.0.1:18789"
    openclaw_llm_model: str = "minimax/MiniMax-M2.7"

    # QQbot 推送目标 OpenID（用于 PersonaEngine 主动推送）
    qq_openid: str = ""

    # 飞书（通过 FUXI_FEISHU_APP_SECRET 环境变量注入，不要硬编码）
    feishu_app_secret: str = ""

    # CORS
    cors_origins: list = Field(default_factory=lambda: ["http://localhost:19528", "http://127.0.0.1:19528",
                          "http://localhost:19527", "http://127.0.0.1:19527"])

    # 日志
    log_level: str = "INFO"
    log_format: str = "json"

    # 引擎分层 (essential=7引擎, standard=14引擎, advanced=全部25引擎, all=全部)
    engine_tier: str = "standard"

    def model_post_init(self, _context):
        if "db_path" not in self.model_fields_set:
            self.db_path = self.base_dir / "fuxi.db"
        if "backup_dir" not in self.model_fields_set:
            self.backup_dir = self.base_dir / "backups"

    @classmethod
    def reload(cls) -> "Config":
        """热更新配置 — 重新加载 env 文件并重建 Config"""
        import importlib

        import fuxi.config as mod
        importlib.reload(mod)
        return mod.config


config = Config()

