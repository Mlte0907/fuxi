#!/usr/bin/env python3
"""引擎调度脚本 - 由 cron 定期调用确保引擎运行"""
import sys
import os

# 确保在 fuxi 目录
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) if os.path.dirname(__file__) else None
sys.path.insert(0, os.getcwd())

from fuxi.engines.base import get_engine_registry
from fuxi.store.connection import get_pool
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("fuxi.engine.runner")

def run_exp_engines():
    """运行实验性引擎"""
    registry = get_engine_registry()
    exp_engines = ['cognitive_loop', 'openclaw_memory', 'skill_evolution']

    # 检查各引擎状态
    for name in exp_engines:
        if name not in registry._engines:
            logger.warning(f"[{name}] 未注册")
            continue

        eng = registry._engines[name]

        # 检查上次运行时间
        pool = get_pool()
        row = pool.fetchone(
            f"SELECT state_json, updated_at FROM engine_states WHERE engine_name=?",
            (name,)
        )

        if row:
            state = json.loads(row['state_json'])
            last_run = state.get('last_run', 'N/A')
            logger.info(f"[{name}] last_run={last_run}")
        else:
            logger.info(f"[{name}] 从未运行，将执行")

        # 执行引擎
        try:
            result = eng._execute()
            logger.info(f"[{name}] 执行完成: {result.get('action', 'unknown')}")
        except Exception as e:
            logger.error(f"[{name}] 执行失败: {e}")

if __name__ == "__main__":
    run_exp_engines()
