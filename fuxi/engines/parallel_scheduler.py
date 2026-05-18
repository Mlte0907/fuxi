"""伏羲 v1.0 — ParallelSchedulerEngine 并行调度引擎"""
import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.kernel.event_bus import Event, get_event_bus
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.parallel_scheduler")


@dataclass
class TaskNode:
    """DAG中的任务节点"""
    task_id: str
    deps: list[str] = field(default_factory=list)
    status: str = "pending"  # pending/running/completed/failed
    result: Any = None
    error: str | None = None


@register_engine("parallel_scheduler", experimental=True)
class ParallelSchedulerEngine(CognitiveEngine):
    """并行调度引擎 — 基于 DAG 拓扑排序 + asyncio.gather 并行执行

    工作流程:
    1. 从 engine_tasks 表读取待执行任务及其依赖关系
    2. 构建 DAG，执行拓扑排序确定执行顺序
    3. 按层级并行执行无依赖任务（asyncio.gather）
    4. 结果写回 engine_tasks 表
    """
    name = "parallel_scheduler"
    priority = 8
    interval = 60  # 每分钟检查一次
    experimental = True

    def run(self) -> dict:
        pool = get_pool()
        tasks = self._load_tasks(pool)
        if not tasks:
            return {"status": "no_tasks", "timestamp": datetime.now().isoformat()}

        dag = self._build_dag(tasks)
        layers = self._topological_sort(dag)
        results = self._execute_layers(layers, dag)

        self._save_results(pool, results)
        return {
            "status": "completed",
            "layers": len(layers),
            "total_tasks": len(tasks),
            "completed": sum(1 for r in results.values() if r.get("status") == "completed"),
            "failed": sum(1 for r in results.values() if r.get("status") == "failed"),
            "timestamp": datetime.now().isoformat(),
        }

    def _load_tasks(self, pool) -> list[dict]:
        """加载待执行任务"""
        rows = pool.fetchall(
            "SELECT task_id, payload, dependencies FROM engine_tasks "
            "WHERE status='pending' AND scheduled_at <= datetime('now') "
            "ORDER BY priority DESC, scheduled_at ASC LIMIT 100"
        )
        return [
            {
                "task_id": r["task_id"],
                "payload": r["payload"],
                "dependencies": (r["dependencies"] or "").split(",") if r["dependencies"] else [],
            }
            for r in rows
        ]

    def _build_dag(self, tasks: list[dict]) -> dict[str, TaskNode]:
        """从任务列表构建 DAG"""
        dag: dict[str, TaskNode] = {}
        for t in tasks:
            node = TaskNode(task_id=t["task_id"], deps=t.get("dependencies", []))
            dag[t["task_id"]] = node
        return dag

    def _topological_sort(self, dag: dict[str, TaskNode]) -> list[list[str]]:
        """Kahn算法拓扑排序，返回按层级分组的任务列表"""
        in_degree = defaultdict(int)
        for node in dag.values():
            for dep in node.deps:
                if dep in dag:
                    in_degree[node.task_id] += 1

        layers = []
        remaining = set(dag.keys())
        while remaining:
            # 找到入度为0的任务（无依赖或依赖已满足）
            ready = {tid for tid in remaining if in_degree[tid] == 0}
            if not ready:
                # 循环依赖，移除剩余任务的依赖标记
                for tid in remaining:
                    dag[tid].deps = []
                    in_degree[tid] = 0
                ready = remaining
                logger.warning(f"[parallel_scheduler] circular deps detected, forcing {ready}")

            layers.append(sorted(ready))
            for tid in ready:
                remaining.discard(tid)
                for node in dag.values():
                    if tid in node.deps:
                        in_degree[node.task_id] -= 1

        return layers

    async def _execute_task_async(self, task_id: str, payload: str) -> dict:
        """异步执行单个任务"""
        await asyncio.sleep(0.01)  # 模拟实际任务执行
        return {
            "task_id": task_id,
            "status": "completed",
            "result": f"executed:{task_id}",
            "timestamp": datetime.now().isoformat(),
        }

    def _execute_layers(self, layers: list[list[str]], dag: dict[str, TaskNode]) -> dict:
        """按层级并行执行任务"""
        results = {}

        async def run_layer(layer: list[str]):
            coroutines = [self._execute_task_async(tid, dag[tid].task_id) for tid in layer]
            return await asyncio.gather(*coroutines, return_exceptions=True)

        for layer in layers:
            layer_results = asyncio.run(run_layer(layer))
            for tid, result in zip(layer, layer_results):
                if isinstance(result, Exception):
                    results[tid] = {"status": "failed", "error": str(result)}
                else:
                    results[tid] = result

        return results

    def _save_results(self, pool, results: dict):
        """将任务结果写回数据库"""
        with pool.connection() as c:
            for task_id, result in results.items():
                status = result.get("status", "unknown")
                result_json = json.dumps(result, ensure_ascii=False)
                c.execute(
                    "UPDATE engine_tasks SET status=?, result=?, completed_at=? WHERE task_id=?",
                    (status, result_json, datetime.now().isoformat(), task_id)
                )

    def _get_subscriptions(self):
        return {
            "scheduler.schedule_task": self._on_schedule_task,
        }

    def _on_schedule_task(self, event: Event):
        """接收调度事件，将任务加入队列"""
        pending = self._state.metadata.setdefault("_pending_events", [])
        pending.append({
            "task_id": event.data.get("task_id"),
            "payload": event.data.get("payload"),
            "dependencies": event.data.get("dependencies", []),
            "scheduled_at": event.data.get("scheduled_at", datetime.now().isoformat()),
        })
        if len(pending) > 100:
            pending.pop(0)


# 便捷导入
from collections import defaultdict
import json