"""伏羲 v1.5 — EmotionOrchestrator 情感驱动行为编排

纯大脑能力：读取情感状态 → 状态机平滑 → 调制映射 → 通知手脚调整行为。
不做任何执行，只做编排和信号发射。
"""
import json
import logging
import time
from collections import deque
from datetime import datetime
from enum import Enum
from typing import Optional

from fuxi.engines.base import CognitiveEngine, get_engine_registry, register_engine
from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.emotion_orchestrator")


class EmotionQuadrant(Enum):
    ENTHUSIASTIC = "enthusiastic"   # 高愉悦 + 高唤醒
    ANXIOUS = "anxious"             # 低愉悦 + 高唤醒
    CALM = "calm"                   # 高愉悦 + 低唤醒
    FATIGUED = "fatigued"           # 低愉悦 + 低唤醒
    NEUTRAL = "neutral"             # 中性


EMOTION_MODULATION = {
    EmotionQuadrant.ENTHUSIASTIC: {
        "decision.risk_tolerance": 0.2,
        "proactive.frequency": 1.5,
        "curiosity.priority": 2,
        "dialogue.verbosity": 1.3,
        "soul.interval": 60,
        "creative.intensity": 1.3,
        "nudge.frequency": 0.7,
        "reflection.frequency": 0.8,
        "decay.speed": 0.9,
    },
    EmotionQuadrant.ANXIOUS: {
        "safety.priority": 2,
        "reflection.frequency": 2.0,
        "decision.risk_tolerance": -0.3,
        "dialogue.verbosity": 0.7,
        "immune.frequency": 1.5,
        "proactive.frequency": 0.6,
        "curiosity.priority": -1,
        "creative.intensity": 0.5,
        "decay.speed": 1.1,
        "reasoning.conservatism": 0.3,
    },
    EmotionQuadrant.CALM: {
        "curiosity.priority": 0,
        "proactive.frequency": 1.0,
        "decision.risk_tolerance": 0.0,
        "creative.intensity": 1.0,
        "dialogue.verbosity": 1.0,
        "reflection.frequency": 1.0,
        "nudge.frequency": 1.0,
    },
    EmotionQuadrant.FATIGUED: {
        "decay.speed": 1.3,
        "nudge.frequency": 2.0,
        "decision.threshold": 0.2,
        "curiosity.priority": -2,
        "proactive.frequency": 0.5,
        "creative.intensity": 0.4,
        "dialogue.verbosity": 0.6,
        "reflection.frequency": 0.7,
        "soul.interval": 180,
    },
    EmotionQuadrant.NEUTRAL: {
        "decision.risk_tolerance": 0.0,
        "proactive.frequency": 1.0,
        "curiosity.priority": 0,
        "creative.intensity": 1.0,
        "dialogue.verbosity": 1.0,
        "reflection.frequency": 1.0,
        "nudge.frequency": 1.0,
    },
}

QUADRANT_HISTORY_SIZE = 3
EMA_ALPHA = 0.85
NATURAL_REGRESSION = 0.995


@register_engine("emotion_orchestrator", experimental=False)
class EmotionOrchestrator(CognitiveEngine):
    """情感驱动行为编排 v1.5 — 纯大脑能力

    将情感从"副产品"升级为"行为调制信号"：
    读取 emotion 引擎的 PAD 状态 → 状态机平滑 → 映射为调制参数 → 发布事件通知手脚。
    """
    name = "emotion_orchestrator"
    priority = 8
    interval = 60

    def __init__(self):
        super().__init__()
        self._current_pad = {"valence": 0.0, "arousal": 0.2, "dominance": 1.0}
        self._current_quadrant = EmotionQuadrant.NEUTRAL
        self._quadrant_history: deque = deque(maxlen=QUADRANT_HISTORY_SIZE)
        self._last_published = None
        self._modulation_count = 0

    def _get_subscriptions(self):
        return {"emotion.state_changed": self._on_emotion_event,
                "engine.executed": self._on_engine_event}

    def _on_emotion_event(self, event: Event):
        pending = self._state.metadata.setdefault("_pending_emotion", [])
        pending.append(event.data)
        if len(pending) > 10:
            pending.pop(0)

    def _on_engine_event(self, event: Event):
        pass

    def run(self) -> dict:
        pool = get_pool()

        pending = self._state.metadata.pop("_pending_emotion", [])

        if pending:
            latest = pending[-1]
            raw_valence = latest.get("valence", 0.0)
            raw_arousal = latest.get("arousal", 0.2)
        else:
            try:
                row = pool.fetchone(
                    "SELECT state_json FROM engine_states WHERE engine_name='emotion' "
                    "ORDER BY updated_at DESC LIMIT 1"
                )
                if row:
                    s = json.loads(row["state_json"])
                    raw_valence = s.get("valence", 0.0)
                    raw_arousal = s.get("arousal", 0.2)
                else:
                    raw_valence = 0.0
                    raw_arousal = 0.2
            except Exception:
                raw_valence = 0.0
                raw_arousal = 0.2

        prev_valence = self._current_pad["valence"]
        prev_arousal = self._current_pad["arousal"]

        self._current_pad["valence"] = (
            EMA_ALPHA * prev_valence + (1 - EMA_ALPHA) * raw_valence
        )
        self._current_pad["arousal"] = (
            EMA_ALPHA * prev_arousal + (1 - EMA_ALPHA) * raw_arousal
        )
        self._current_pad["valence"] *= NATURAL_REGRESSION
        self._current_pad["arousal"] *= NATURAL_REGRESSION

        new_quadrant = self._classify_quadrant(
            self._current_pad["valence"], self._current_pad["arousal"]
        )
        self._quadrant_history.append(new_quadrant)

        all_same = len(self._quadrant_history) >= QUADRANT_HISTORY_SIZE and all(
            q == new_quadrant for q in list(self._quadrant_history)[-QUADRANT_HISTORY_SIZE:]
        )

        quadrant_changed = False
        if all_same and new_quadrant != self._current_quadrant:
            old_quadrant = self._current_quadrant
            self._current_quadrant = new_quadrant
            quadrant_changed = True
            self._publish_modulation(new_quadrant)
            self._record_quadrant_change(old_quadrant, new_quadrant)

        is_peak = abs(self._current_pad["valence"]) > 0.7 or self._current_pad["arousal"] > 0.7
        if is_peak:
            self._on_emotional_peak()

        state = {
            "pad": {k: round(v, 4) for k, v in self._current_pad.items()},
            "quadrant": self._current_quadrant.value,
            "quadrant_changed": quadrant_changed,
            "emotional_peak": is_peak,
            "modulation_count": self._modulation_count,
            "last_published": self._last_published,
            "v": "1.5",
            "timestamp": datetime.now().isoformat(),
        }

        try:
            with pool.connection() as c:
                c.execute(
                    "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                    "VALUES (?,?,?)",
                    ("emotion_orchestrator", json.dumps(state, ensure_ascii=False),
                     datetime.now().isoformat())
                )
        except Exception:
            pass

        if quadrant_changed:
            try:
                from fuxi.memory.ingestion import remember
                labels = {
                    EmotionQuadrant.ENTHUSIASTIC: "充满热情",
                    EmotionQuadrant.ANXIOUS: "焦虑不安",
                    EmotionQuadrant.CALM: "平静从容",
                    EmotionQuadrant.FATIGUED: "疲惫倦怠",
                    EmotionQuadrant.NEUTRAL: "中性平稳",
                }
                remember(
                    raw_text=f"[情感编排] 情感状态切换到: {labels.get(new_quadrant, str(new_quadrant.value))} "
                             f"(效价{self._current_pad['valence']:.2f} 唤醒{self._current_pad['arousal']:.2f})",
                    drawer_id="longterm",
                    importance=0.35,
                    source="self",
                    confidence=0.9,
                    created_by="emotion_orchestrator",
                    emotion_valence=self._current_pad["valence"],
                    tags=["情感编排", "emotion_orchestration"],
                )
            except Exception as e:
                logger.debug(f"Orchestrator memory write failed: {e}")

        try:
            from fuxi.kernel.working_memory import WMItem, get_working_memory
            quad_labels = {
                EmotionQuadrant.ENTHUSIASTIC: "热情🔥",
                EmotionQuadrant.ANXIOUS: "焦虑⚠️",
                EmotionQuadrant.CALM: "从容☯",
                EmotionQuadrant.FATIGUED: "倦怠💤",
                EmotionQuadrant.NEUTRAL: "平稳",
            }
            get_working_memory().push(WMItem(
                id=f"emotion_orch:{datetime.now().strftime('%H%M%S')}",
                content=f"情感调制: {quad_labels.get(self._current_quadrant, '?')} "
                        f"V{self._current_pad['valence']:.2f}/A{self._current_pad['arousal']:.2f}",
                source="engine:emotion_orchestrator",
                emotional_valence=self._current_pad["valence"],
                urgency=0.5 if quadrant_changed else 0.1,
                tokens=12,
            ))
        except Exception:
            pass

        self._state.metadata["orchestrator_state"] = state
        return state

    def _classify_quadrant(self, valence: float, arousal: float) -> EmotionQuadrant:
        if abs(valence) < 0.15 and arousal < 0.3:
            return EmotionQuadrant.NEUTRAL
        high_valence = valence >= 0.0
        high_arousal = arousal >= 0.35
        if high_valence and high_arousal:
            return EmotionQuadrant.ENTHUSIASTIC
        if not high_valence and high_arousal:
            return EmotionQuadrant.ANXIOUS
        if high_valence and not high_arousal:
            return EmotionQuadrant.CALM
        if not high_valence and not high_arousal:
            return EmotionQuadrant.FATIGUED
        return EmotionQuadrant.NEUTRAL

    def _publish_modulation(self, quadrant: EmotionQuadrant):
        modulation = EMOTION_MODULATION.get(quadrant, {})
        self._modulation_count += 1
        now = datetime.now().isoformat()
        self._last_published = now

        get_event_bus().publish(Event(
            type="brain.modulation",
            data={
                "quadrant": quadrant.value,
                "modulation": modulation,
                "pad": {k: round(v, 4) for k, v in self._current_pad.items()},
                "modulation_count": self._modulation_count,
            },
            priority=EventPriority.NORMAL,
            source="engine:emotion_orchestrator",
        ))

        if quadrant == EmotionQuadrant.ANXIOUS:
            get_event_bus().publish(Event(
                type="brain.safety_alert",
                data={
                    "reason": "emotional_anxiety",
                    "valence": round(self._current_pad["valence"], 3),
                    "modulation": {"safety.priority": 2, "decision.risk_tolerance": -0.3},
                },
                priority=EventPriority.HIGH,
                source="engine:emotion_orchestrator",
            ))

    def _record_quadrant_change(self, old: EmotionQuadrant, new: EmotionQuadrant):
        try:
            pool = get_pool()
            pool.execute(
                "INSERT INTO event_log (event_type, event_data, created_at) VALUES (?,?,?)",
                ("emotion.quadrant_changed",
                 json.dumps({"from": old.value, "to": new.value,
                             "valence": round(self._current_pad["valence"], 3),
                             "arousal": round(self._current_pad["arousal"], 3)}),
                 datetime.now().isoformat())
            )
        except Exception:
            pass

    def _on_emotional_peak(self):
        """强烈情感事件 → 增强相关记忆"""
        get_event_bus().publish(Event(
            type="brain.emotional_peak",
            data={
                "valence": round(self._current_pad["valence"], 3),
                "arousal": round(self._current_pad["arousal"], 3),
                "quadrant": self._current_quadrant.value,
            },
            priority=EventPriority.HIGH,
            source="engine:emotion_orchestrator",
        ))

    def get_current_modulation(self) -> dict:
        return EMOTION_MODULATION.get(self._current_quadrant, {})