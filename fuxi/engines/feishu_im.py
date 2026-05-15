"""伏羲飞书 IM 引擎 — 集成 larkcc 作为子进程（v1.1 修复: 注册为 CognitiveEngine）"""
import logging
import os
import subprocess

from fuxi.config import config
from fuxi.engines.base import CognitiveEngine, register_engine

logger = logging.getLogger("fuxi.engines.feishu_im")

_LARKCC_BIN = "/home/xiaoxin/.npm-global/bin/larkcc"


@register_engine("feishu_im", experimental=False)
class FeishuIMEngine(CognitiveEngine):
    """飞书 IM 引擎 — 管理 larkcc 子进程生命周期"""
    name = "feishu_im"
    experimental = False
    interval = 0  # 不通过引擎调度启动，手动 start() 即可
    priority = 10

    def __init__(self):
        super().__init__()
        self._process: subprocess.Popen | None = None
        self._running = False

    def start(self):
        """启动 larkcc 子进程"""
        if self._running:
            logger.warning("[feishu_im] already running")
            return
        env = os.environ.copy()
        env["ANTHROPIC_BASE_URL"] = "http://localhost:19528/anthropic"
        env["FEISHU_APP_ID"] = os.environ.get("FEISHU_APP_ID", "your_feishu_app_id_here")
        env["FEISHU_APP_SECRET"] = getattr(config, "feishu_app_secret", "")
        if not os.path.exists(_LARKCC_BIN):
            logger.error(f"[feishu_im] larkcc not found at {_LARKCC_BIN}")
            return
        logger.info("[feishu_im] starting larkcc...")
        self._process = subprocess.Popen(
            [_LARKCC_BIN, "-p", "fuxi", "--daemon", "--continue"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        self._running = True
        self._state.running = True
        logger.info(f"[feishu_im] larkcc started PID={self._process.pid}")

    def stop(self):
        """停止 larkcc 子进程"""
        if not self._running:
            return
        logger.info("[feishu_im] stopping...")
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            except Exception as e:
                logger.error(f"[feishu_im] stop error: {e}")
            self._process = None
        self._running = False
        self._state.running = False

    def run(self) -> dict:
        """引擎调度入口（interval=0 实际不自动调度，保留接口兼容）"""
        return {"status": "ok", "running": self._running, "pid": self._process.pid if self._process else None}

    def health_check(self) -> dict:
        alive = self._process is not None and self._process.poll() is None
        base = super().health_check()
        base.update({"running": alive, "pid": self._process.pid if self._process else None})
        return base


_engine: "FeishuIMEngine | None" = None


def get_feishu_im_engine() -> "FeishuIMEngine":
    global _engine
    if _engine is None:
        _engine = FeishuIMEngine()
    return _engine
