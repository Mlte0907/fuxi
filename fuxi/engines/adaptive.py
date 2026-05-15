"""伏羲 v1.0 — AdaptiveEngine 自适应学习引擎

根据用户行为模式自动调整记忆策略参数。"""
import json
import logging
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.adaptive")


@register_engine("adaptive", experimental=False)
class AdaptiveEngine(CognitiveEngine):
    """自适应学习引擎 — 根据用户行为模式自动调整记忆策略参数"""

    name = "adaptive"
    priority = 9
    interval = 1800  # 30分钟评估一次

    ADAPTATION_RULES = {
        "high_recall_low_creation": {
            "condition": lambda s: s["recall_frequency"] > 5 and s["creation_frequency"] < 1,
            "adjustments": {"decay_base": +0.01, "touch_boost_short": +0.05},
            "reason": "用户频繁回顾但少创建，增强记忆保持",
        },
        "high_search_refinement": {
            "condition": lambda s: s["search_refinement_rate"] > 0.3,
            "adjustments": {"vector_weight": -0.05, "fts_weight": +0.5, "similarity_threshold": -0.05},
            "reason": "用户频繁重搜，增强精确匹配能力",
        },
        "low_search_satisfaction": {
            "condition": lambda s: s["search_satisfaction"] < 0.3,
            "adjustments": {"similarity_threshold": -0.05, "vector_weight": +0.05, "decay_floor": -0.02},
            "reason": "搜索满意度低，扩大召回范围",
        },
        "longterm_heavy_user": {
            "condition": lambda s: s["longterm_access_ratio"] > 0.7,
            "adjustments": {"touch_boost_long": +0.02, "decay_floor": +0.02},
            "reason": "用户重度依赖长期记忆，加强长期记忆保护",
        },
        "shortterm_heavy_user": {
            "condition": lambda s: s["shortterm_access_ratio"] > 0.7,
            "adjustments": {"touch_boost_short": +0.05, "wm_capacity": +1},
            "reason": "用户重度使用短期记忆，扩大工作记忆容量",
        },
    }

    def run(self) -> dict:
        from fuxi.adaptive.params import clamp_params
        from fuxi.adaptive.signals import get_behavior_collector

        collector = get_behavior_collector()
        signals = collector.get_user_profile_signals()
        current = self._load_params()
        adjustments_made = []

        # BUG-007 fix: rollback protection when signals are unreliable
        # If all signals are zero (e.g. BehaviorCollector not yet working),
        # rollback to default params to prevent drift
        signal_values = list(signals.values())
        all_signals_zero = all(v == 0 for v in signal_values)
        if all_signals_zero and current.confidence < 0.5:
            # Rollback to safe defaults
            from fuxi.adaptive.params import AdaptiveParams, DEFAULT_PARAMS
            current = AdaptiveParams()
            logger.warning("AdaptiveEngine: all signals zero, rolling back to default params")
            self._save_params(current)
            self._apply_params(current)
            return {
                "signals": signals,
                "adjustments": [],
                "rollback": True,
                "reason": "all_signals_zero",
            }

        for rule_name, rule in self.ADAPTATION_RULES.items():
            if rule["condition"](signals):
                for param, delta in rule["adjustments"].items():
                    old_val = getattr(current, param)
                    new_val = old_val + delta
                    setattr(current, param, new_val)
                    adjustments_made.append({
                        "rule": rule_name, "param": param,
                        "old": old_val, "delta": delta,
                        "reason": rule["reason"],
                    })

        current = clamp_params(current)
        # BUG-007 fix: decay confidence when no adjustments made (signal lost relevance)
        if not adjustments_made:
            current.confidence = max(0.3, current.confidence - 0.02)
        else:
            current.confidence = min(1.0, current.confidence + 0.05)
        current.last_updated = datetime.now().isoformat()
        current.update_reason = "; ".join(a["reason"] for a in adjustments_made)

        self._save_params(current)
        self._apply_params(current)

        if adjustments_made:
            logger.info(f"Adaptive engine adjusted {len(adjustments_made)} params: {current.update_reason}")

        return {
            "signals": signals,
            "adjustments": adjustments_made,
            "current_params": {
                "decay_base": current.decay_base,
                "vector_weight": current.vector_weight,
                "fts_weight": current.fts_weight,
                "wm_capacity": current.wm_capacity,
                "confidence": current.confidence,
            },
        }

    def _load_params(self):
        from fuxi.adaptive.params import AdaptiveParams

        pool = get_pool()
        row = pool.fetchone(
            "SELECT state_json FROM engine_states WHERE engine_name='adaptive'"
        )
        if row:
            try:
                data = json.loads(row["state_json"])
                fields = {k: v for k, v in data.items()
                          if k in AdaptiveParams.__dataclass_fields__}
                # coerce wm_capacity to int
                if "wm_capacity" in fields:
                    fields["wm_capacity"] = int(fields["wm_capacity"])
                if "attention_replenish_rate" in fields:
                    fields["attention_replenish_rate"] = int(fields["attention_replenish_rate"])
                return AdaptiveParams(**fields)
            except Exception:
                pass
        return AdaptiveParams()

    def _save_params(self, params):
        pool = get_pool()
        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                "VALUES (?,?,?)",
                ("adaptive", json.dumps(params.__dict__, ensure_ascii=False),
                 datetime.now().isoformat())
            )

    def _apply_params(self, params):
        """将自适应参数应用到运行时配置"""
        from fuxi.config import config
        config.decay_base = params.decay_base
        config.touch_boost_short = params.touch_boost_short
        config.touch_boost_long = params.touch_boost_long
        config.decay_floor = params.decay_floor
        config.vector_weight_default = params.vector_weight
        config.fts_weight_default = params.fts_weight
        config.wm_capacity = params.wm_capacity
