"""伏羲 v1.5 — 元认知进化引擎 (meta_evolution)
自主实验框架 / 引擎效能评分
"""
import logging
import time
from datetime import datetime
from typing import Optional

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.meta_evolution")


@register_engine("meta_evolution", experimental=True)
class MetaEvolutionEngine(CognitiveEngine):
    """元认知进化引擎 v1.5 — 自主实验框架、引擎效能评分"""
    name = "meta_evolution"
    priority = 4
    interval = 7200
    experimental = True

    def _get_subscriptions(self):
        return {"engine.executed": self._on_event, "experiment.trial": self._on_event}

    def run(self) -> dict:
        pool = get_pool()

        # 处理 pending 事件
        pending = self._pop_pending_events()

        # 1. 自主实验框架 — 设计并执行自我改进实验
        experiments = self._self_experiment(pool)

        # 2. 引擎效能评分 — 评估各引擎运行效能
        engine_scores = self._engine_effectiveness_scorer(pool)

        state = {
            "experiments": experiments,
            "engine_scores": engine_scores,
            "timestamp": datetime.now().isoformat(),
        }

        self._state.metadata["last_evolution"] = state
        return state

    def _self_experiment(self, pool) -> dict:
        """自主实验框架 — 设计并执行自我改进实验"""
        experiment = {
            "active": False,
            "hypothesis": None,
            "variables": [],
            "results": None,
            "status": "idle",
        }

        try:
            # 检查是否有正在进行的实验
            current = self._state.metadata.get("current_experiment")

            if not current:
                # 设计新实验：测试不同参数设置的效果
                # 示例：测试不同记忆重要性阈值对检索质量的影响
                experiment = {
                    "active": True,
                    "hypothesis": "提高高重要性记忆的权重可提升检索质量",
                    "variables": [
                        {"name": "importance_threshold", "values": [0.5, 0.6, 0.7]},
                        {"name": "decay_rate", "values": [0.05, 0.1, 0.15]},
                    ],
                    "control_group": "当前默认参数",
                    "experimental_groups": ["高阈值+快衰减", "低阈值+慢衰减", "中等阈值"],
                    "duration": "7 days",
                    "status": "proposed",
                }
                self._state.metadata["current_experiment"] = experiment
            else:
                # 更新实验状态
                experiment = current

                # 简单评估实验进展
                if experiment.get("status") == "proposed":
                    # 检查是否应该开始实验
                    experiment["status"] = "running"
                    experiment["start_time"] = datetime.now().isoformat()
                    self._state.metadata["current_experiment"] = experiment

        except Exception as e:
            logger.warning(f"[meta_evolution] self_experiment failed: {e}")

        return experiment

    def _engine_effectiveness_scorer(self, pool) -> list:
        """引擎效能评分 — 评估各引擎运行效能"""
        scores = []

        try:
            # 获取所有引擎的执行历史
            engine_executions = pool.fetchall("""
                SELECT engine_name, run_count, error_count, last_run
                FROM engine_states
                WHERE last_run IS NOT NULL
                ORDER BY last_run DESC
            """)

            for exec_row in engine_executions:
                name = exec_row["engine_name"]
                run_count = exec_row["run_count"] or 0
                error_count = exec_row["error_count"] or 0

                # 计算效能分数
                # 基础分数：成功执行次数
                base_score = run_count

                # 错误惩罚
                error_penalty = error_count * 0.5

                # 计算执行频率得分（最近有运行的引擎得分更高）
                recency_score = 1.0
                if exec_row["last_run"]:
                    try:
                        last = datetime.fromisoformat(exec_row["last_run"])
                        hours_ago = (datetime.now() - last).total_seconds() / 3600
                        recency_score = max(0, 1.0 - hours_ago / 24.0)
                    except Exception:
                        pass

                effectiveness = max(0, base_score - error_penalty + recency_score)

                scores.append({
                    "engine": name,
                    "run_count": run_count,
                    "error_count": error_count,
                    "effectiveness_score": round(effectiveness, 3),
                    "health": "healthy" if error_count == 0 else "degraded" if error_count < 5 else "critical",
                })
        except Exception as e:
            logger.warning(f"[meta_evolution] engine_effectiveness_scorer failed: {e}")

        # 按效能分数排序
        scores.sort(key=lambda x: x["effectiveness_score"], reverse=True)
        return scores[:10]  # 返回 top 10