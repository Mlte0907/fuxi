"""伏羲 v1.0 — CognitiveLoop 认知循环"""
import logging
import time
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, get_engine_registry, register_engine
from fuxi.kernel.attention import AttentionStrategy, get_attention_system
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.loop")


@register_engine("cognitive_loop", experimental=False)
class CognitiveLoop(CognitiveEngine):
    """认知循环 — 按优先级调度所有引擎执行，受注意力系统调控"""
    name = "cognitive_loop"
    priority = 1  # 最低优先级（自身调度器）
    interval = 180
    experimental = False

    def run(self) -> dict:
        pool = get_pool()
        now = time.time()
        results = {}
        attention = get_attention_system()

        # 工作记忆衰减
        from fuxi.kernel.working_memory import get_working_memory
        wm = get_working_memory()
        wm.decay_tick(dt=10.0)

        # 注意力预算恢复（每循环 +20，允许调度多个引擎）
        attention.replenish(20)

        # ── 意图驱动: 读取 WM 焦点决定注意力策略 ──
        wm_focus = [s for s in wm.slots if s.activation > 0.3]
        max_urgency = max((s.urgency for s in wm_focus), default=0.0)
        has_reflection = any("reflection" in s.source for s in wm_focus)

        # 如果 WM 中有高紧迫度项，切换到 FOCUS 模式
        if max_urgency > 0.6 and attention.active_strategy != AttentionStrategy.FOCUS:
            old, _ = attention.switch(AttentionStrategy.FOCUS, "wm_urgency_high")
            logger.debug(f"Intent-driven: {old.value} -> FOCUS (urgency={max_urgency:.2f})")
        # 如果有 reflection 问题，切换到 EXPLORE 模式
        elif has_reflection and attention.active_strategy != AttentionStrategy.EXPLORE:
            old, _ = attention.switch(AttentionStrategy.EXPLORE, "wm_has_reflection")
            logger.debug(f"Intent-driven: {old.value} -> EXPLORE (reflection questions)")

        # 从最近记忆评估注意力策略（作为基础判断，意图驱动优先）
        if attention.active_strategy not in (AttentionStrategy.FOCUS, AttentionStrategy.EXPLORE):
            try:
                row = pool.fetchone(
                    "SELECT AVG(emotion_valence) AS avg_v, COUNT(*) AS cnt "
                    "FROM items WHERE archived=0 AND created_at > datetime('now','-1 hour')"
                )
                if row and row["cnt"] > 5:
                    avg_valence = abs(float(row["avg_v"])) if row["avg_v"] else 0.0
                    novel_row = pool.fetchone(
                        "SELECT COUNT(*) AS cnt FROM items WHERE archived=0 "
                        "AND created_at > datetime('now','-1 hour') AND EXISTS (SELECT 1 FROM json_each(tags) WHERE value = 'new')"
                    )
                    novelty = (novel_row["cnt"] / row["cnt"]) if row["cnt"] > 0 else 0.0
                    new_strategy = attention.evaluate(
                        emotional_valence=avg_valence,
                        urgency=max_urgency,
                        novelty=novelty,
                    )
                    if new_strategy != attention.active_strategy:
                        old, _ = attention.switch(new_strategy, f"emotional={avg_valence:.2f} novelty={novelty:.2f}")
                        logger.debug(f"Attention strategy: {old.value} -> {new_strategy.value}")
            except Exception:
                pass

        # ── 引擎调度 ──
        from fuxi.engines import get_enabled_engines
        enabled = get_enabled_engines()
        all_engines = sorted(
            get_engine_registry().engines.items(),
            key=lambda x: x[1].priority, reverse=True
        )
        min_priority = 7 if attention.active_strategy == AttentionStrategy.FOCUS else 0

        for name, engine in all_engines:
            if name == "cognitive_loop":
                continue
            # 实验性引擎：interval > 0 表示已配置，可参与调度（不受enabled限制）
            # 实验性引擎如果未启动，自动启动（防止数据库恢复后一直停止）
            if engine.experimental:
                if engine.interval == 0:
                    continue  # interval=0 表示禁用
                if not engine._state.running:
                    engine.start()  # 自动启动未运行的实验性引擎
            else:
                # 非实验性引擎受enabled限制
                if enabled is not None and name not in enabled:
                    continue
            if engine.priority < min_priority:
                continue
                if engine.interval == 0:
                    continue  # interval=0 表示禁用
                if not engine._state.running:
                    engine.start()  # 自动启动未运行的实验性引擎

            last_run = engine._state.last_run
            if (last_run == 0 or (now - last_run) >= engine.interval) and engine._state.running and attention.allocate(3):
                    try:
                        engine._execute()
                        results[name] = {"status": "ok", "time_ms": round((time.time() - now) * 1000)}
                    except Exception as e:
                        results[name] = {"status": "error", "error": str(e)}

        state = {
            "running": self._state.running,
            "last_run": self._state.last_run,
            "run_count": self._state.run_count,
            "engines_triggered": len(results),
            "results": results,
            "attention": attention.stats,
            "working_memory": wm.stats,
            "wm_focus": [{"id": s.id, "urgency": s.urgency, "activation": round(s.activation, 2)} for s in wm_focus[:3]],
            "timestamp": datetime.now().isoformat(),
        }

        # 注意：不要在这里保存 engine_states，_execute() 会在 run() 返回后更新
        # run_count 和 last_run 由 _execute() 管理
        self._state.metadata["last_loop"] = state
        return state
