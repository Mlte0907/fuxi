"""伏羲 v1.5 — MetacognitionEngine 元认知（基础元学习框架）

系统级长期监测伏羲记忆系统运行状态和引擎情况。
"""
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta

from fuxi.engines.base import CognitiveEngine, get_engine_registry, register_engine
from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.metacognition")

META_LEARN_WINDOW = 100


@register_engine("metacognition", experimental=False)
class MetacognitionEngine(CognitiveEngine):
    """元认知 v1.5 — 元学习 + 自重构 + 策略自适应 + 系统级长期监测"""
    name = "metacognition"
    priority = 4
    interval = 300
    experimental = False

    def _get_subscriptions(self):
        return {"engine.executed": self._on_event, "decision.executed": self._on_event}

    # ── 系统级长期监测 ──
    def _monitor_system_health(self, pool) -> dict:
        """长期监测伏羲记忆系统和引擎运行状态"""
        now = time.time()
        health_report = {
            "timestamp": datetime.now().isoformat(),
            "engines": {},
            "memory": {},
            "event_log": {},
            "recommendations": [],
        }

        # 引擎健康检测
        engine_stats = {"total": 0, "running": 0, "stale": 0, "error": 0}
        for name, engine in get_engine_registry().engines.items():
            health = engine.health_check()
            engine_stats["total"] += 1
            if health.get("running"):
                engine_stats["running"] += 1
            if health.get("error_count", 0) > 0:
                engine_stats["error"] += 1
            if health.get("last_run", 0) > 0:
                idle = now - health["last_run"]
                if idle > engine.interval * 3:
                    engine_stats["stale"] += 1

        health_report["engines"] = engine_stats

        # 记忆系统健康检测
        try:
            mem_stats = pool.fetchone(
                "SELECT COUNT(*) as total, SUM(CASE WHEN archived=0 THEN 1 ELSE 0 END) as active FROM items"
            )
            drawer_stats = pool.fetchall(
                "SELECT drawer_id, COUNT(*) as cnt FROM items GROUP BY drawer_id"
            )
            recent_count = pool.fetchone(
                "SELECT COUNT(*) as cnt FROM items WHERE created_at > datetime('now', '-1 hour')"
            )
            health_report["memory"] = {
                "total": mem_stats["total"] if mem_stats else 0,
                "active": mem_stats["active"] if mem_stats else 0,
                "drawers": {r["drawer_id"]: r["cnt"] for r in drawer_stats} if drawer_stats else {},
                "last_hour_new": recent_count["cnt"] if recent_count else 0,
            }
        except Exception as e:
            health_report["memory"] = {"error": str(e)}

        # 事件日志活性检测
        try:
            event_stats = pool.fetchone(
                "SELECT COUNT(*) as cnt FROM event_log WHERE created_at > datetime('now', '-1 hour')"
            )
            health_report["event_log"] = {
                "last_hour_events": event_stats["cnt"] if event_stats else 0,
            }
        except Exception as e:
            health_report["event_log"] = {"error": str(e)}

        # 生成建议
        if engine_stats["stale"] > 3:
            health_report["recommendations"].append(
                f"引擎过期数量过多({engine_stats['stale']}), 检查调度器"
            )
        if engine_stats["error"] > 0:
            health_report["recommendations"].append(
                f"存在{engine_stats['error']}个引擎错误, 需要人工检查"
            )
        if health_report["memory"].get("last_hour_new", 0) == 0:
            health_report["recommendations"].append(
                "过去1小时无新记忆摄入, 检查采集引擎是否正常"
            )

        self._state.metadata["last_health_report"] = health_report
        return health_report

    def run(self) -> dict:
        pool = get_pool()

        # ── 系统级长期监测 ──
        system_health = self._monitor_system_health(pool)

        # v1.5: 元学习 — 分析引擎执行模式并自适应调整
        meta_learn = self._meta_learn(pool)

        # v1.5: 自重构 — 检测并重组低效引擎配置
        self_reconfig = self._detect_self_reconfig(pool)

        # 收集所有引擎状态
        engine_health = {}
        for name, engine in get_engine_registry().engines.items():
            engine_health[name] = engine.health_check()

        # 检测异常引擎并采取行动
        alerts = []
        actions_taken = []
        for name, health in engine_health.items():
            error_count = health.get("error_count", 0)
            if error_count > 5:
                alerts.append({
                    "engine": name,
                    "issue": "high_error_rate",
                    "error_count": error_count,
                })
                # 自动重启高错误率引擎
                eng = get_engine_registry().get(name)
                if eng and name != "cognitive_loop":
                    try:
                        eng.stop()
                        eng.start()
                        actions_taken.append({"engine": name, "action": "restart", "reason": f"error_count={error_count}"})
                        logger.warning(f"Metacognition: auto-restarted {name} (error_count={error_count})")
                    except Exception as e:
                        logger.warning(f"Metacognition restart of {name} failed: {e}")

            # 检查最后运行时间
            last_run = health.get("last_run", 0)
            if last_run > 0:
                idle = time.time() - health["last_run"]
                eng = get_engine_registry().get(name)
                if eng is not None and idle > eng.interval * 3:
                    alerts.append({
                        "engine": name,
                        "issue": "stale",
                        "idle_seconds": round(idle),
                    })
                    # 将过期引擎告警推入 WM
                    from fuxi.kernel.working_memory import WMItem, get_working_memory
                    get_working_memory().push(WMItem(
                        id=f"metacognition:stale:{name}:{datetime.now().strftime('%H%M%S')}",
                        content=f"[引擎过期] {name} 已{round(idle)}秒未运行(预期{eng.interval}s)",
                        source="engine:metacognition",
                        emotional_valence=-0.2,
                        urgency=0.7,
                        tokens=15,
                    ))

            # 检查 cognitive_loop 是否卡住（单点故障检测）
            if name == "cognitive_loop" and health.get("running"):
                idle = time.time() - last_run if last_run > 0 else 0
                if idle > 600:  # 超过10分钟未调度视为严重告警
                    alerts.append({
                        "engine": name,
                        "issue": "single_point_of_failure",
                        "idle_seconds": round(idle),
                        "severity": "CRITICAL",
                    })

        # 全局系统健康
        immune = get_engine_registry().get("immune")
        immune_issues = immune._state.metadata.get("last_patrol", {}).get("issues", []) if immune else []

        state = {
            "engines": engine_health,
            "alerts": alerts,
            "actions_taken": actions_taken,
            "immune_issues": immune_issues,
            "overall": "degraded" if alerts else "healthy",
            "meta_learn": meta_learn,
            "self_reconfig": self_reconfig,
            "system_health": system_health,
            "v": "3.0",
            "timestamp": datetime.now().isoformat(),
        }

        if alerts:
            logger.warning(f"Metacognition: {len(alerts)} alerts — {'; '.join(a['issue'] for a in alerts)}")

        # 发布行动事件
        if actions_taken:
            get_event_bus().publish(Event(
                type="metacognition.action_taken",
                data={"actions": actions_taken},
                priority=EventPriority.HIGH,
                source="engine:metacognition",
            ))

        # 将元认知报告写入 longterm 记忆
        if alerts or actions_taken:
            try:
                from fuxi.memory.ingestion import remember
                remember(
                    raw_text=f"[元认知] 系统检查: {state['overall']}, {len(alerts)}告警, {len(actions_taken)}行动已执行",
                    drawer_id="longterm",
                    importance=0.6,
                    source="self",
                    confidence=0.8,
                    created_by="metacognition",
                    tags=["元认知", "metacognition", "自检"],
                )
            except Exception as e:
                logger.debug(f"Metacognition memory write failed: {e}")

        self._state.metadata["last_meta"] = state
        return state

    # v1.5: 元学习 — 从历史决策中学习，优化引擎参数
    def _meta_learn(self, pool) -> dict:
        """分析过去 N 次决策执行结果，提取成功率模式"""
        rows = pool.fetchall(
            "SELECT task_type, outcome, COUNT(*) AS cnt FROM experience_bank "
            "WHERE created_at > datetime('now', '-7 days') "
            "GROUP BY task_type, outcome ORDER BY cnt DESC"
        )
        if not rows:
            return {"status": "no_data", "insights": []}

        # 统计每个 task_type 的成功率
        task_stats = defaultdict(lambda: {"success": 0, "failure": 0})
        for r in rows:
            task = r["task_type"]
            if r["outcome"] == "success":
                task_stats[task]["success"] += r["cnt"]
            else:
                task_stats[task]["failure"] += r["cnt"]

        insights = []
        for task, stats in task_stats.items():
            total = stats["success"] + stats["failure"]
            if total >= 5:
                rate = stats["success"] / total
                insights.append({
                    "task_type": task,
                    "success_rate": round(rate, 3),
                    "sample_size": total,
                    "recommendation": "increase_frequency" if rate > 0.8 else "decrease_frequency" if rate < 0.4 else "maintain",
                })

        return {"status": "ok", "insights": insights[:10]}

    # v1.5: 自重构 — 检测是否需要调整引擎优先级或参数
    def _detect_self_reconfig(self, pool) -> dict:
        """基于元学习洞察检测是否需要自重构"""
        # 检测低成功率引擎，降优先级
        low_perf = pool.fetchall(
            "SELECT task_type FROM experience_bank "
            "WHERE outcome != 'success' AND created_at > datetime('now', '-3 days') "
            "GROUP BY task_type HAVING COUNT(*) > 3"
        )
        if not low_perf:
            return {"status": "stable", "actions": []}

        # 映射 task_type 到引擎名
        engine_map = {
            "distillation": "distill",
            "memory_cleanup": "decay",
            "reflection": "reflection",
            "decision": "decision",
        }
        actions = []
        for r in low_perf:
            task = r["task_type"]
            engine_name = engine_map.get(task, task)
            actions.append({
                "engine": engine_name,
                "action": "reduce_priority",
                "reason": f"low_success_rate_in_{task}",
            })
        return {"status": "reconfig_needed", "actions": actions}
