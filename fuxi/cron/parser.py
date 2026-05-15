"""伏羲 v1.0 — NL-to-Cron 解析器"""
import re
from typing import Optional

# 中文时间表达式 → cron 映射规则库
_TIME_RULES = [
    # 每天固定时间
    (r"每天早上?(\d{1,2})点", lambda m: f"0 {int(m.group(1))} * * *"),
    (r"每天晚上?(\d{1,2})点", lambda m: f"0 {int(m.group(1))} * * *"),
    (r"每天上午(\d{1,2})点", lambda m: f"0 {int(m.group(1))} * * *"),
    (r"每天下午(\d{1,2})点", lambda m: f"0 {int(m.group(1)) + 12} * * *"),
    (r"每天中午(\d{1,2})点", lambda m: f"0 {int(m.group(1))} * * *"),
    (r"每天(\d{1,2}):(\d{2})", lambda m: f"{int(m.group(2))} {int(m.group(1))} * * *"),
    (r"每天半夜(\d{1,2})点", lambda m: f"0 {int(m.group(1))} * * *"),

    # 工作日/周末
    (r"每个?工作日早?上?(\d{1,2})点", lambda m: f"0 {int(m.group(1))} * * 1-5"),
    (r"每个?周末早?上?(\d{1,2})点", lambda m: f"0 {int(m.group(1))} * * 0,6"),

    # 每小时
    (r"每小时(?:的)?第?(\d{1,2})分", lambda m: f"{int(m.group(1))} * * * *"),
    (r"每小时(?:执行)?一次", lambda m: "0 * * * *"),

    # 每隔N分钟/小时
    (r"每隔?(\d+)分钟", lambda m: f"*/{int(m.group(1))} * * * *"),
    (r"每隔?(\d+)小?时", lambda m: f"0 */{int(m.group(1))} * * *"),

    # 每周固定
    (r"每周一早上?(\d{1,2})点", lambda m: f"0 {int(m.group(1))} * * 1"),
    (r"每周二早上?(\d{1,2})点", lambda m: f"0 {int(m.group(1))} * * 2"),
    (r"每周三早上?(\d{1,2})点", lambda m: f"0 {int(m.group(1))} * * 3"),
    (r"每周四早上?(\d{1,2})点", lambda m: f"0 {int(m.group(1))} * * 4"),
    (r"每周五早上?(\d{1,2})点", lambda m: f"0 {int(m.group(1))} * * 5"),
    (r"每周六早上?(\d{1,2})点", lambda m: f"0 {int(m.group(1))} * * 6"),
    (r"每周日早上?(\d{1,2})点", lambda m: f"0 {int(m.group(1))} * * 0"),

    # 每月
    (r"每月(\d{1,2})号?早上?(\d{1,2})点", lambda m: f"0 {int(m.group(2))} {int(m.group(1))} * *"),
    (r"每月(?:初|1号)", lambda m: "0 9 1 * *"),

    # 英文常见
    (r"every\s+(\d+)\s*minutes?", lambda m: f"*/{int(m.group(1))} * * * *"),
    (r"every\s+(\d+)\s*hours?", lambda m: f"0 */{int(m.group(1))} * * *"),
    (r"every\s+day\s+at\s+(\d{1,2}):(\d{2})", lambda m: f"{int(m.group(2))} {int(m.group(1))} * * *"),
    (r"every\s+monday", lambda m: "0 9 * * 1"),
    (r"every\s+weekday", lambda m: "0 9 * * 1-5"),
    (r"every\s+hour", lambda m: "0 * * * *"),
]


def parse_nl_to_cron(text: str) -> Optional[str]:
    """将自然语言时间表达式转换为标准 5-field cron 表达式

    Returns None if no rule matches.
    """
    text = text.strip().lower()
    for pattern, converter in _TIME_RULES:
        m = re.match(pattern, text)
        if m:
            return converter(m)
    return None


def validate_cron(expr: str) -> bool:
    """验证 cron 表达式是否合法（5-field）"""
    parts = expr.strip().split()
    if len(parts) != 5:
        return False
    # 简单校验：每个字段都是数字、*、*/N 或逗号分隔值
    field_pattern = r'^(\*|(\d+(-\d+)?)|(\*/\d+)|(\d+(,\d+)*))$'
    return all(re.match(field_pattern, p) for p in parts)


def predict_next_run(cron_expr: str) -> Optional[str]:
    """计算下次执行时间（ISO格式）

    Raises ImportError if croniter is not installed.
    """
    try:
        from datetime import datetime

        from croniter import croniter
    except ImportError as e:
        raise ImportError(
            "croniter is required for cron prediction. "
            "Install it with: pip install croniter"
        ) from e
    it = croniter(cron_expr, datetime.now())
    return it.get_next(datetime).isoformat()
