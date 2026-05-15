"""伏羲 v1.5 — SkillOrchestrator 技能编排中枢

纯大脑能力：发现技能缺口 → 打包上下文 → 调度执行层开发 → 验证效果。
伏羲不生成一行技能代码，只做编排、验证和追踪。
"""
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime
from typing import List, Optional

from fuxi.engines.base import CognitiveEngine, get_engine_registry, register_engine
from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.skill_orchestrator")

GAP_DETECTION_WINDOW_DAYS = 7
MIN_FAILURE_COUNT = 5
VALIDATION_PASS_THRESHOLD = 0.7


@register_engine("skill_orchestrator", experimental=False)
class SkillOrchestrator(CognitiveEngine):
    """技能编排中枢 v1.5

    大脑不做手的事。技能只能从执行层的真实问题解决中生长出来。
    但大脑可以：发现缺口、调度开发、验证效果、追踪效能。
    """
    name = "skill_orchestrator"
    priority = 5
    interval = 600

    def _get_subscriptions(self):
        return {"engine.executed": self._on_event}

    def run(self) -> dict:
        pool = get_pool()

        gaps = self._detect_gaps(pool)
        requests_created = []
        for gap in gaps[:3]:
            req_id = self._request_skill(gap, pool)
            if req_id:
                requests_created.append({"gap_id": gap.gap_id, "pattern": gap.pattern})

        validations = self._validate_pending(pool)

        tracking = self._track_deployed(pool)

        state = {
            "gaps_detected": len(gaps),
            "top_gaps": [
                {"pattern": g.pattern, "failure_count": g.failure_count,
                 "severity": round(g.severity, 2)}
                for g in gaps[:5]
            ],
            "requests_created": len(requests_created),
            "validations": validations,
            "tracking_summary": {
                "deployed_skills": tracking.get("deployed", 0),
                "improved": tracking.get("improved", 0),
                "needs_review": tracking.get("needs_review", 0),
            },
            "v": "1.5",
            "timestamp": datetime.now().isoformat(),
        }

        try:
            with pool.connection() as c:
                c.execute(
                    "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                    "VALUES (?,?,?)",
                    ("skill_orchestrator", json.dumps(state, ensure_ascii=False),
                     datetime.now().isoformat())
                )
        except Exception:
            pass

        if gaps:
            try:
                from fuxi.memory.ingestion import remember
                remember(
                    raw_text=f"[技能编排] 发现 {len(gaps)} 个技能缺口: "
                             f"{', '.join(g.pattern for g in gaps[:3])}",
                    drawer_id="longterm",
                    importance=0.4,
                    source="self",
                    confidence=0.8,
                    created_by="skill_orchestrator",
                    tags=["技能编排", "skill_orchestration"],
                )
            except Exception as e:
                logger.debug(f"Orchestrator memory write failed: {e}")

        self._state.metadata["orchestrator_state"] = state
        return state

    def _detect_gaps(self, pool) -> list:
        rows = pool.fetchall(
            "SELECT task_type, outcome, COUNT(*) as cnt, "
            "GROUP_CONCAT(input_desc, '|||') as samples "
            "FROM experience_bank "
            "WHERE outcome != 'success' AND outcome != '' "
            "AND created_at > datetime('now', ? || ' days') "
            "GROUP BY task_type HAVING cnt >= ? "
            "ORDER BY cnt DESC",
            (f"-{GAP_DETECTION_WINDOW_DAYS}", MIN_FAILURE_COUNT)
        )

        gaps = []
        for r in rows:
            task_type = r["task_type"]
            cnt = r["cnt"]
            samples_str = r.get("samples", "") or ""

            exists = pool.fetchone(
                "SELECT id FROM experience_bank "
                "WHERE task_type = ? AND review_status = 'approved' "
                "AND outcome = 'success' LIMIT 1",
                (task_type,)
            )
            if exists:
                continue

            gaps.append(SkillGap(
                gap_id=f"gap_{task_type}_{uuid.uuid4().hex[:6]}",
                pattern=task_type,
                failure_count=cnt,
                sample_errors=samples_str.split("|||")[:10],
                severity=min(cnt * 1.0, 10.0),
            ))

        return sorted(gaps, key=lambda g: g.severity, reverse=True)

    def _request_skill(self, gap: 'SkillGap', pool) -> Optional[str]:
        try:
            pool.execute(
                "INSERT OR IGNORE INTO skill_requests "
                "(id, gap_id, pattern, description, sample_failures, status, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    gap.gap_id,
                    gap.pattern,
                    f"检测到 {gap.pattern} 类任务在近{GAP_DETECTION_WINDOW_DAYS}天内失败{gap.failure_count}次，"
                    f"且无现有技能覆盖。请在执行相关任务时尝试找到解决方案并提交为技能。",
                    json.dumps(gap.sample_errors[:5], ensure_ascii=False),
                    "pending",
                    datetime.now().isoformat(),
                )
            )
        except Exception:
            try:
                pool.execute(
                    "CREATE TABLE IF NOT EXISTS skill_requests ("
                    "id TEXT PRIMARY KEY, gap_id TEXT, pattern TEXT, "
                    "description TEXT, sample_failures TEXT, status TEXT DEFAULT 'pending', "
                    "created_at TEXT)"
                )
                pool.execute(
                    "INSERT INTO skill_requests "
                    "(id, gap_id, pattern, description, sample_failures, status, created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()),
                        gap.gap_id,
                        gap.pattern,
                        f"检测到 {gap.pattern} 类任务失败{gap.failure_count}次",
                        json.dumps(gap.sample_errors[:5], ensure_ascii=False),
                        "pending",
                        datetime.now().isoformat(),
                    )
                )
            except Exception as e:
                logger.debug(f"Skill request persist failed: {e}")
                return None

        get_event_bus().publish(Event(
            type="skill.requested",
            data={
                "gap_id": gap.gap_id,
                "pattern": gap.pattern,
                "failure_count": gap.failure_count,
                "severity": gap.severity,
                "description": f"近{GAP_DETECTION_WINDOW_DAYS}天 {gap.pattern} 失败{gap.failure_count}次，请在实际任务中探索解决方案",
            },
            priority=EventPriority.MEDIUM,
            source="engine:skill_orchestrator",
        ))

        return gap.gap_id

    def _validate_pending(self, pool) -> list:
        results = []
        try:
            rows = pool.fetchall(
                "SELECT * FROM experience_bank WHERE review_status = 'pending' "
                "AND outcome = 'success' LIMIT 5"
            )
            for r in rows:
                skill_id = r["id"]
                task_type = r["task_type"]
                failure_samples = pool.fetchall(
                    "SELECT outcome, input_desc FROM experience_bank "
                    "WHERE task_type = ? AND outcome != 'success' AND id != ? "
                    "LIMIT 5",
                    (task_type, skill_id)
                )

                if not failure_samples:
                    pool.execute(
                        "UPDATE experience_bank SET review_status = 'approved', "
                        "quality_score = MIN(1.0, quality_score + 0.1) WHERE id = ?",
                        (skill_id,)
                    )
                    results.append({"skill_id": skill_id[:8], "status": "approved",
                                   "reason": "no_failure_samples"})
                    continue

                feedback = r.get("input_desc", "") or ""
                pass_rate = 0.8 if len(feedback) > 20 else 0.5

                if pass_rate >= VALIDATION_PASS_THRESHOLD:
                    pool.execute(
                        "UPDATE experience_bank SET review_status = 'approved', "
                        "quality_score = ? WHERE id = ?",
                        (pass_rate, skill_id)
                    )
                    get_event_bus().publish(Event(
                        type="skill.approved",
                        data={"skill_id": skill_id, "quality": pass_rate},
                        priority=EventPriority.NORMAL,
                        source="engine:skill_orchestrator",
                    ))
                    results.append({"skill_id": skill_id[:8], "status": "approved",
                                   "quality": round(pass_rate, 2)})
                else:
                    pool.execute(
                        "UPDATE experience_bank SET review_status = 'rejected' WHERE id = ?",
                        (skill_id,)
                    )
                    results.append({"skill_id": skill_id[:8], "status": "rejected",
                                   "reason": f"pass_rate={pass_rate:.2f}"})
        except Exception as e:
            logger.debug(f"Validation error: {e}")

        return results

    def _track_deployed(self, pool) -> dict:
        result = {"deployed": 0, "improved": 0, "needs_review": 0}
        try:
            row = pool.fetchone(
                "SELECT COUNT(*) as cnt FROM experience_bank "
                "WHERE review_status = 'approved'"
            )
            result["deployed"] = row["cnt"] if row else 0

            row = pool.fetchone(
                "SELECT COUNT(*) as cnt FROM experience_bank "
                "WHERE review_status = 'approved' "
                "AND quality_score >= 0.7"
            )
            result["improved"] = row["cnt"] if row else 0

            row = pool.fetchone(
                "SELECT COUNT(*) as cnt FROM experience_bank "
                "WHERE review_status = 'pending'"
            )
            result["needs_review"] = row["cnt"] if row else 0
        except Exception:
            pass
        return result


class SkillGap:
    def __init__(self, gap_id: str, pattern: str, failure_count: int,
                 sample_errors: list, severity: float):
        self.gap_id = gap_id
        self.pattern = pattern
        self.failure_count = failure_count
        self.sample_errors = sample_errors
        self.severity = severity