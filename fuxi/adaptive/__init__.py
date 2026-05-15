"""伏羲 v1.0 — 自适应学习模块

根据用户行为模式自动调整记忆策略参数。
"""

from fuxi.adaptive.feedback import AdaptiveFeedbackLoop
from fuxi.adaptive.params import PARAM_BOUNDS, AdaptiveParams, clamp_params
from fuxi.adaptive.signals import BehaviorCollector

__all__ = [
    "BehaviorCollector",
    "AdaptiveParams",
    "PARAM_BOUNDS",
    "clamp_params",
    "AdaptiveFeedbackLoop",
]
