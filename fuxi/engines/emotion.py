"""伏羲 v2.0 — EmotionEngine 情感建模（情感惯性 + 自然衰减 + 多维交互）"""
import json
import logging
import time
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.emotion")

# v2.0: 情感关键词触发器
EMOTION_TRIGGERS = {
    "positive": ["成功", "完成", "突破", "进展", "好", "棒", "优秀", "喜欢", "开心", "高兴"],
    "negative": ["失败", "错误", "问题", "困难", "挫折", "糟糕", "讨厌", "生气", "失败"],
    "exciting": ["惊喜", "兴奋", "激动", "突破", "发现", "创新"],
    "calming": ["休息", "放松", "平静", "安宁", "舒缓", "平静下来"],
}

# v2.0: EMA 平滑因子（情感惯性系数）
VALENCE_EMA_ALPHA = 0.7  # 0-1, 越高越跟随当前计算值，越低越平滑

# v2.0: 情感关键词缓存（60秒 TTL）
_kw_cache: dict = {"pos": 0.0, "neg": 0.0, "ts": 0.0}
_KW_CACHE_TTL = 60.0


@register_engine("emotion", experimental=False)
class EmotionEngine(CognitiveEngine):
    """情感建模 v2.0 — 非线性情感系统（情感惯性 + 自然衰减 + 多维交互）"""
    name = "emotion"
    priority = 9
    interval = 120

    # 情感维度 — PAD 三维 + 认知扩展
    # PAD: Pleasure(愉悦)=valence, Arousal(唤醒)=arousal, Dominance(支配)=dominance
    DIMENSIONS = ["valence", "arousal", "dominance", "interest", "frustration"]

    def _get_subscriptions(self):
        return {"soul.health_changed": self._on_event}

    def _detect_emotion_keywords(self) -> tuple:
        """检测最近记忆中的情感关键词，返回 (positive_score, negative_score)，带 60s 缓存"""
        global _kw_cache
        now = time.time()
        if now - _kw_cache["ts"] < _KW_CACHE_TTL:
            return _kw_cache["pos"], _kw_cache["neg"]

        pool = get_pool()
        rows = pool.fetchall(
            "SELECT raw_text FROM items WHERE archived=0 "
            "ORDER BY created_at DESC LIMIT 50"
        )
        if not rows:
            _kw_cache = {"pos": 0.0, "neg": 0.0, "ts": now}
            return 0.0, 0.0

        text = " ".join(r["raw_text"] for r in rows)
        pos_score = sum(1 for kw in EMOTION_TRIGGERS["positive"] if kw in text) * 0.1
        neg_score = sum(1 for kw in EMOTION_TRIGGERS["negative"] if kw in text) * 0.1
        _kw_cache = {"pos": min(0.3, pos_score), "neg": min(0.3, neg_score), "ts": now}
        return _kw_cache["pos"], _kw_cache["neg"]

    def _calc_ema_valence(self, computed_valence: float, last_valence: float) -> float:
        """v2.0: EMA 平滑情感效价（情感惯性）"""
        if last_valence is None:
            return computed_valence
        # EMA: 新值 = alpha * 当前计算值 + (1-alpha) * 上次值
        return VALENCE_EMA_ALPHA * computed_valence + (1 - VALENCE_EMA_ALPHA) * last_valence

    def _apply_natural_decay(self, valence: float) -> float:
        """v2.0: 自然衰减 — 情感效价向中性点 0 回归"""
        # 每 tick 衰减 5%，向 0 回归
        decay_rate = 0.05
        return valence * (1 - decay_rate)

    def _apply_multi_dimensional_interactions(
        self, valence: float, arousal: float, frustration: float
    ) -> tuple:
        """v2.0: 多维交互 — valence 影响 arousal，frustration 抑制 interest"""
        # 高效价提升唤醒度
        arousal = min(1.0, arousal + valence * 0.15)
        # 低效价降低支配感
        dominance = max(0.0, 1.0 - abs(valence) * 0.3 - frustration * 0.2)
        return arousal, dominance

    def run(self) -> dict:
        pool = get_pool()

        # v2.0: 关键词情感检测
        pos_kw, neg_kw = self._detect_emotion_keywords()

        # 处理 pending 事件：健康度变化影响情感基调
        pending = self._pop_pending_events()
        health_shift = 0.0
        for evt in pending:
            if evt["type"] == "soul.health_changed":
                old = evt["data"].get("old_label", "")
                new = evt["data"].get("new_label", "")
                if new == "needs_attention":
                    health_shift = -0.15
                elif new == "healthy":
                    health_shift = 0.1

        # 计算全局情感倾向
        rows = pool.fetchall(
            "SELECT emotion_valence, importance FROM items "
            "WHERE archived=0 AND emotion_valence != 0 "
            "ORDER BY created_at DESC LIMIT 100"
        )

        if not rows:
            return self._neutral_state()

        valences = [r["emotion_valence"] for r in rows]
        avg_valence = sum(valences) / len(valences)

        # 加权情感（高重要性记忆权重更大）
        weighted = sum(r["emotion_valence"] * r["importance"] for r in rows)
        total_imp = sum(r["importance"] for r in rows)
        weighted_valence = weighted / total_imp if total_imp > 0 else avg_valence

        # 情感趋势
        first_half = valences[:len(valences)//2] if len(valences) > 1 else valences
        second_half = valences[len(valences)//2:]
        trend = sum(second_half)/len(second_half) - sum(first_half)/len(first_half) if first_half and second_half else 0

        # v2.0: 关键词情感修正
        keyword_valence = pos_kw - neg_kw

        # 原始计算效价
        raw_valence = max(-1.0, min(1.0, weighted_valence + health_shift + keyword_valence))

        # v2.0: EMA 平滑（情感惯性）
        last_state = self._state.metadata.get("last_state", {})
        last_valence = last_state.get("valence")
        ema_valence = self._calc_ema_valence(raw_valence, last_valence)

        # v2.0: 自然衰减
        ema_valence = self._apply_natural_decay(ema_valence)
        ema_valence = max(-1.0, min(1.0, ema_valence))

        # frustration 基于"目标受阻"维度独立计算
        frustration = self._calc_frustration(pool)

        # v2.0: 基础唤醒度计算
        base_arousal = abs(ema_valence) * 0.8 + 0.2

        # v2.0: 多维交互
        arousal, dominance = self._apply_multi_dimensional_interactions(
            ema_valence, base_arousal, frustration
        )

        # v2.0: frustration 抑制 interest
        interest = max(0.0, min(1.0, len(rows) / 50.0 - frustration * 0.3))

        state = {
            "valence": round(ema_valence, 4),
            "arousal": round(arousal, 4),
            "dominance": round(dominance, 4),
            "interest": round(interest, 4),
            "frustration": round(frustration, 4),
            "trend": round(trend, 4),
            "trend_label": "improving" if trend > 0.05 else "declining" if trend < -0.05 else "stable",
            "v": "2.0",
            "kw_signal": round(keyword_valence, 3),
            "timestamp": datetime.now().isoformat(),
        }

        # 持久化
        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                "VALUES (?,?,?)",
                ("emotion", json.dumps(state, ensure_ascii=False), datetime.now().isoformat())
            )

        # v2.0: 情感显著变化时主动写入记忆
        # 注意：取上次状态的 valence（在当前 state 覆盖之前）
        prev_state = self._state.metadata.get("last_state", {})
        last_valence = prev_state.get("valence", 0)
        if abs(ema_valence - last_valence) > 0.3 or trend > 0.2 or trend < -0.2:
            mood = "积极向上" if trend > 0.05 else "低落" if trend < -0.05 else "平稳"
            try:
                from fuxi.memory.ingestion import remember
                remember(
                    raw_text=f"[情感] 当前情绪{mood}，效价{ema_valence:.2f}，唤醒度{state['arousal']:.2f}，趋势{state['trend_label']}",
                    drawer_id="longterm",
                    importance=0.25,
                    source="self",
                    confidence=0.8,
                    created_by="emotion",
                    emotion_valence=ema_valence,
                    tags=["情感", "emotion"],
                )
            except Exception as e:
                logger.debug(f"Emotion memory failed: {e}")

        # 更新状态（放在记忆检查之后，以便下次使用）
        self._state.metadata["last_state"] = state

        # 推入工作记忆
        from fuxi.kernel.working_memory import WMItem, get_working_memory
        frustration_alert = f"受挫{frustration:.2f}" if frustration > 0.4 else ""
        get_working_memory().push(WMItem(
            id=f"emotion:{datetime.now().strftime('%H%M')}",
            content=f"情绪{state['trend_label']} 效价{ema_valence:.2f} 唤醒{state['arousal']:.2f} {frustration_alert}".strip(),
            source="engine:emotion",
            emotional_valence=ema_valence,
            urgency=0.5 if abs(ema_valence) > 0.5 or frustration > 0.4 else 0.1,
            tokens=15,
        ))

        # DEAD-003 fix: 发布 frustration 事件供其他引擎消费
        if frustration > 0.3:
            from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
            get_event_bus().publish(Event(
                type="emotion.frustration",
                data={"frustration": frustration, "valence": ema_valence},
                priority=EventPriority.NORMAL if frustration > 0.5 else EventPriority.LOW,
                source="engine:emotion",
            ))

        return state

    def _calc_frustration(self, pool) -> float:
        """基于目标受阻信号独立计算 frustration，而非效价反转

        受阻信号包括: event_log 中的错误事件、工作记忆淘汰频率、搜索重搜率。
        """
        score = 0.0

        # 信号1: event_log 中的错误/警告事件（最近1小时）
        try:
            row = pool.fetchone(
                "SELECT COUNT(*) AS cnt FROM event_log "
                "WHERE event_type IN ('error', 'warning', 'failure') "
                "AND created_at > datetime('now', '-1 hour')"
            )
            if row:
                score += min(0.35, row["cnt"] * 0.05)
        except Exception:
            pass

        # 信号2: 搜索重搜率（event_log 中 search.refine vs search.query）
        try:
            refines = pool.fetchone(
                "SELECT COUNT(*) AS cnt FROM event_log WHERE event_type='search.refine' "
                "AND created_at > datetime('now', '-1 hour')"
            )
            queries = pool.fetchone(
                "SELECT COUNT(*) AS cnt FROM event_log WHERE event_type='search.query' "
                "AND created_at > datetime('now', '-1 hour')"
            )
            if queries and queries["cnt"] > 0:
                refine_rate = refines["cnt"] / queries["cnt"]
                score += min(0.3, refine_rate * 0.5)
        except Exception:
            pass

        # 信号3: 工作记忆高风险淘汰
        try:
            from fuxi.kernel.working_memory import get_working_memory
            wm = get_working_memory()
            if wm.stats.get("evictions", 0) > 10:
                score += min(0.25, (wm.stats["evictions"] - 10) * 0.02)
            if wm.usage() > 0.9:
                score += 0.1
        except Exception:
            pass

        return min(1.0, score)

    def _neutral_state(self):
        return {
            "valence": 0.0, "arousal": 0.2, "dominance": 1.0,
            "interest": 0.0, "frustration": 0.5, "trend": 0.0,
            "trend_label": "neutral", "timestamp": datetime.now().isoformat()
        }
