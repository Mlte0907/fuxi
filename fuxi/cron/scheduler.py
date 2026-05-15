"""伏羲 v1.0 — Cron 调度器"""
import json
import logging
import threading
from datetime import datetime
from typing import List, Optional

from fuxi.agent.integration import OpenClawAdapter
from fuxi.cron.parser import parse_nl_to_cron, predict_next_run, validate_cron
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.cron.scheduler")


class CronScheduler:
    """轻量级 Cron 调度器 — 每分钟检查一次待执行任务"""

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stopped = threading.Event()

    def list_tasks(self, enabled_only: bool = True) -> List[dict]:
        pool = get_pool()
        clause = "WHERE enabled = 1" if enabled_only else ""
        rows = pool.fetchall(f"SELECT * FROM scheduled_tasks {clause} ORDER BY next_run")
        return [dict(r) for r in rows]

    def add_task(self, task_id: str, name: str, cron_expression: str,
                 agent_id: str = "", instruction: str = "",
                 description: str = "") -> str:
        pool = get_pool()
        if not validate_cron(cron_expression):
            raise ValueError(f"Invalid cron expression: {cron_expression}")
        next_run = predict_next_run(cron_expression)
        now = datetime.now().isoformat()
        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO scheduled_tasks "
                "(task_id, name, description, cron_expression, agent_id, instruction, next_run, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (task_id, name, description, cron_expression, agent_id, instruction, next_run, now)
            )
        logger.info(f"Cron task added: {task_id} ({cron_expression})")
        return task_id

    def add_from_nl(self, task_id: str, name: str, nl_schedule: str,
                    agent_id: str = "", instruction: str = "",
                    description: str = "") -> Optional[str]:
        cron_expr = parse_nl_to_cron(nl_schedule)
        if not cron_expr:
            raise ValueError(f"Cannot parse schedule: {nl_schedule}")
        return self.add_task(task_id, name, cron_expr, agent_id, instruction, description)

    def update_task(self, task_id: str, **kwargs) -> bool:
        pool = get_pool()
        allowed = {"name", "description", "cron_expression", "agent_id",
                    "instruction", "enabled"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if not updates:
            return False
        if "cron_expression" in updates:
            updates["next_run"] = predict_next_run(updates["cron_expression"])
        updates["updated_at"] = datetime.now().isoformat()
        sets = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [task_id]
        with pool.connection() as c:
            cur = c.execute(f"UPDATE scheduled_tasks SET {sets} WHERE task_id=?", values)
        return cur.rowcount > 0

    def delete_task(self, task_id: str) -> bool:
        pool = get_pool()
        with pool.connection() as c:
            cur = c.execute("DELETE FROM scheduled_tasks WHERE task_id=?", (task_id,))
        return cur.rowcount > 0

    def tick(self) -> List[dict]:
        """检查并执行到期的任务，返回已执行的任务列表"""
        pool = get_pool()
        now = datetime.now().isoformat()
        due = pool.fetchall(
            "SELECT * FROM scheduled_tasks WHERE enabled = 1 AND next_run <= ?",
            (now,)
        )
        fired = []
        for task in due:
            task_dict = dict(task)
            try:
                # 更新执行时间和下次运行时间
                next_run = predict_next_run(task_dict["cron_expression"])
                with pool.connection() as c:
                    c.execute(
                        "UPDATE scheduled_tasks SET last_run=?, next_run=?, updated_at=? WHERE task_id=?",
                        (now, next_run, now, task_dict["task_id"])
                    )
                # 写入事件日志
                with pool.connection() as c:
                    c.execute(
                        "INSERT INTO event_log (event_type, source, event_data, created_at) VALUES (?,?,?,?)",
                        ("cron_trigger", "scheduler",
                         json.dumps({"task_id": task_dict["task_id"],
                                     "agent_id": task_dict["agent_id"],
                                     "instruction": task_dict["instruction"]},
                                    ensure_ascii=False),
                         now)
                    )
                fired.append(task_dict)
                logger.info(f"Cron fired: {task_dict['task_id']} (next: {next_run})")

                # 通知 Agent 执行任务
                if task_dict.get("agent_id") and task_dict.get("instruction"):
                    try:
                        OpenClawAdapter().call_agent(
                            agent_id=task_dict["agent_id"],
                            message=task_dict["instruction"],
                        )
                    except Exception as e:
                        logger.warning(f"Cron agent call [{task_dict['agent_id']}] failed: {e}")
            except Exception as e:
                logger.error(f"Cron task {task_dict['task_id']} failed: {e}")
        return fired

    def start_background(self, interval: float = 60.0):
        """后台线程：定期检查待执行任务"""
        if self._thread and self._thread.is_alive():
            return
        self._stopped.clear()
        self._thread = threading.Thread(target=self._run_loop, args=(interval,),
                                        daemon=True, name="cron-scheduler")
        self._thread.start()
        logger.info(f"Cron scheduler started (interval={interval}s)")

    def _run_loop(self, interval: float):
        while not self._stopped.wait(timeout=interval):
            try:
                self.tick()
            except Exception as e:
                logger.error(f"Cron scheduler error: {e}")

    def stop(self):
        self._stopped.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Cron scheduler stopped")


_scheduler: CronScheduler | None = None


def get_cron_scheduler() -> CronScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = CronScheduler()
    return _scheduler
