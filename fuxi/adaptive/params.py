"""伏羲 v1.0 — 自适应参数定义"""
from dataclasses import dataclass


@dataclass
class AdaptiveParams:
    """可自适应调整的记忆策略参数"""

    # 衰减参数
    decay_base: float = 0.95              # 基础衰减率 (0.9-0.99)
    touch_boost_short: float = 1.35       # 短期增益 (1.1-1.5)
    touch_boost_long: float = 1.06        # 长期保护 (1.0-1.2)
    decay_floor: float = 0.15             # 衰减底限 (0.05-0.3)

    # 搜索参数
    vector_weight: float = 0.6            # 向量搜索权重 (0.3-0.8)
    fts_weight: float = 4.0               # FTS搜索权重 (1.0-8.0)
    similarity_threshold: float = 0.25    # 向量相似度阈值 (0.15-0.4)

    # 工作记忆参数
    wm_capacity: int = 7                  # 工作记忆槽位数 (5-10)
    wm_decay_rate: float = 0.02           # 工作记忆衰减率 (0.01-0.05)

    # 注意力参数
    attention_replenish_rate: int = 5      # 注意力恢复速率 (3-10)

    # 去重参数
    dedup_boost_importance: float = 0.05   # 重复记忆重要性增益 (0.01-0.1)
    dedup_boost_decay: float = 1.1         # 重复记忆衰减增益 (1.05-1.2)

    # 元数据
    last_updated: str = ""
    update_reason: str = ""
    confidence: float = 0.5               # 参数置信度 (0-1)


# 参数调整范围约束
PARAM_BOUNDS = {
    "decay_base": (0.9, 0.99),
    "touch_boost_short": (1.1, 1.5),
    "touch_boost_long": (1.0, 1.2),
    "decay_floor": (0.05, 0.3),
    "vector_weight": (0.3, 0.8),
    "fts_weight": (1.0, 8.0),
    "similarity_threshold": (0.15, 0.4),
    "wm_capacity": (5, 10),
    "wm_decay_rate": (0.01, 0.05),
    "attention_replenish_rate": (3, 10),
    "dedup_boost_importance": (0.01, 0.1),
    "dedup_boost_decay": (1.05, 1.2),
}


def clamp_params(params: AdaptiveParams) -> AdaptiveParams:
    """将参数约束到合法范围内"""
    for attr, (lo, hi) in PARAM_BOUNDS.items():
        val = getattr(params, attr)
        setattr(params, attr, max(lo, min(hi, val)))
    return params
