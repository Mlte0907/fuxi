"""共享测试fixtures"""
import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("FUXI_API_KEY", "test-key-2026")
os.environ.setdefault("FUXI_LOG_LEVEL", "ERROR")

# 确保 config 在测试时使用正确的 API key
from fuxi.config import config as _cfg

_cfg.api_key = "test-key-2026"


def _drain_pool(pool):
    """清空连接池中所有连接并重置计数器"""
    while not pool._pool.empty():
        try:
            c = pool._pool.get_nowait()
            c.close()
        except Exception:
            pass
    pool._created = 0


@pytest.fixture
def temp_db():
    """隔离的临时数据库 — 替换 setup_db/auth_db/eng_db/temp_db"""
    from fuxi.config import config
    from fuxi.store.connection import get_pool

    old = str(config.db_path)
    tmp = tempfile.mktemp(suffix=".db")
    config.db_path = Path(tmp)

    pool = get_pool()
    _drain_pool(pool)

    from fuxi.store.migrations import init_db
    init_db()

    yield

    config.db_path = Path(old)
    _drain_pool(pool)
    if os.path.exists(tmp):
        os.remove(tmp)


@pytest.fixture(autouse=True)
def reset_state():
    """每个测试前重置全局单例状态"""
    import fuxi.store.connection as conn_mod
    conn_mod._pool = None
    yield
    conn_mod._pool = None


@pytest.fixture
def client(temp_db):
    """FastAPI TestClient with isolated temp DB"""
    from fastapi.testclient import TestClient

    from fuxi.api.server import create_app
    app = create_app()
    return TestClient(app)


def auth_headers():
    return {"X-API-Key": "test-key-2026"}
