"""伏羲 v1.0 — 决策执行器

执行已批准的决策并追踪结果，沉淀经验到经验库。
v1.3 新增: 决策回滚机制 — 执行前快照，失败时自动回滚。"""
import logging
import uuid
from datetime import datetime
from typing import Dict

from fuxi.decision.framework import Decision, DecisionOption, DecisionStatus

logger = logging.getLogger("fuxi.decision.executor")


class DecisionExecutor:
    """决策执行器 — 执行决策并追踪结果，支持回滚"""

    ACTION_HANDLERS: Dict[str, callable] = {}
    ROLLBACK_HANDLERS: Dict[str, tuple] = {}  # action_type -> (snapshot_fn, rollback_fn)

    @classmethod
    def register_handler(cls, action_type: str, handler):
        """注册决策处理器"""
        cls.ACTION_HANDLERS[action_type] = handler

    def execute(self, decision: Decision) -> dict:
        """执行已批准的决策，失败时自动回滚"""
        if decision.status != DecisionStatus.APPROVED:
            return {"status": "rejected", "reason": "Decision not approved"}

        selected = next(
            (o for o in decision.options if o.id == decision.selected_option), None
        )
        if not selected:
            return {"status": "error", "reason": "Selected option not found"}

        handler = self.ACTION_HANDLERS.get(selected.action_type)
        if not handler:
            return {
                "status": "error",
                "reason": f"No handler for {selected.action_type}",
            }

        decision.status = DecisionStatus.EXECUTING

        # v1.3: 执行前快照
        snapshot_fn, rollback_fn = self.ROLLBACK_HANDLERS.get(selected.action_type, (None, None))
        snapshot = None
        if snapshot_fn:
            try:
                snapshot = snapshot_fn(decision.id, selected.action_params)
            except Exception as e:
                logger.warning(f"Snapshot failed for {selected.action_type}: {e}")

        try:
            result = handler(selected.action_params)
            decision.status = DecisionStatus.COMPLETED
            decision.execution_result = result
            decision.completed_at = datetime.now().isoformat()
            self._record_experience(decision, selected, result, "success")
            return result
        except Exception as e:
            logger.warning(f"Decision execution failed ({selected.action_type}): {e}")
            # v1.3: 失败时回滚
            if rollback_fn and snapshot is not None:
                try:
                    rollback_result = rollback_fn(decision.id, selected.action_params, snapshot)
                    logger.info(f"Rollback succeeded: {rollback_result}")
                    result = {"status": "rolled_back", "error": str(e), "rollback": rollback_result}
                except Exception as rb_err:
                    logger.error(f"Rollback also failed: {rb_err}")
                    result = {"status": "rollback_failed", "error": str(e), "rollback_error": str(rb_err)}
            else:
                result = {"status": "rolled_back", "error": str(e)}

            decision.status = DecisionStatus.ROLLED_BACK
            decision.execution_result = result
            decision.completed_at = datetime.now().isoformat()
            self._record_experience(decision, selected, result, "rolled_back")
            return result

    def _record_experience(self, decision: Decision, option: DecisionOption,
                           result: dict, outcome: str):
        """将决策结果沉淀为经验，并自动提交技能到市场。"""
        from fuxi.store.connection import get_pool

        pool = get_pool()
        detail = f"结果: {outcome}, 详情: {str(result)[:200]}"

        with pool.connection() as c:
            c.execute(
                "INSERT INTO experience_bank (id, task_type, input_desc, "
                "reasoning_summary, conclusion, outcome, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), option.action_type,
                 decision.trigger_reason[:200],
                 f"选项: {option.description}, 风险: {option.risk_level:.2f}",
                 detail[:300], outcome, datetime.now().isoformat())
            )

        # 成功后自动提交技能到市场
        if outcome == "success":
            try:
                from fuxi.skill_market.submission import submit_skill
                submit_skill(
                    task_type=option.action_type,
                    description=decision.trigger_reason[:300],
                    reasoning=option.description[:300],
                    outcome=detail[:200],
                    result=result,
                    agent_id="decision_engine",
                    auto_approve=False,
                )
            except Exception:
                pass
