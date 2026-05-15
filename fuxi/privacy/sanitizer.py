"""伏羲 v1.0 — 记忆内容脱敏器

在记忆与外部服务交互前自动脱敏敏感内容。"""
import re
from typing import Dict, List, Tuple


class MemorySanitizer:
    """记忆内容脱敏器 — 在记忆与外部服务交互前自动脱敏"""

    # 顺序很重要：长/具体模式必须先匹配，避免被短模式截胡
    SENSITIVE_PATTERNS: Dict[str, Tuple[str, str]] = {
        "url_with_token": (
            r"https?://\S+[?&](token|key|secret|password|api_key|auth)=\S+",
            "[URL_WITH_CREDENTIAL]",
        ),
        "email": (r"[\w.-]+@[\w.-]+\.\w+", "[EMAIL]"),
        "ip_address": (r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "[IP]"),
        "id_card": (r"\d{17}[\dXx]", "[ID_CARD]"),
        "bank_card": (r"\d{16,19}", "[BANK_CARD]"),
        "phone": (r"1[3-9]\d{9}", "[PHONE]"),
    }

    custom_keywords: List[str] = []

    @classmethod
    def sanitize(cls, text: str, level: str = "standard") -> Tuple[str, dict]:
        """脱敏处理

        Args:
            text: 原始文本
            level: 脱敏级别 — minimal / standard / strict

        Returns:
            (脱敏后文本, {模式类型: 匹配数量})
        """
        sanitized = text
        redactions: dict = {}

        if level == "minimal":
            patterns = {"url_with_token": cls.SENSITIVE_PATTERNS["url_with_token"]}
        elif level == "strict":
            patterns = dict(cls.SENSITIVE_PATTERNS)
        else:
            patterns = {k: v for k, v in cls.SENSITIVE_PATTERNS.items()
                        if k != "ip_address"}

        for ptype, (pattern, replacement) in patterns.items():
            matches = re.findall(pattern, sanitized)
            if matches:
                sanitized = re.sub(pattern, replacement, sanitized)
                redactions[ptype] = len(matches)

        for keyword in cls.custom_keywords:
            if keyword in sanitized:
                sanitized = sanitized.replace(keyword, f"[REDACTED:{keyword[:2]}***]")
                redactions[f"keyword:{keyword[:2]}"] = 1

        return sanitized, redactions

    @classmethod
    def sanitize_for_embedding(cls, text: str) -> str:
        """为嵌入API调用脱敏 — 保留语义但移除敏感数据"""
        sanitized, _ = cls.sanitize(text, level="standard")
        return sanitized

    @classmethod
    def sanitize_for_export(cls, text: str) -> str:
        """为导出脱敏 — 严格级别"""
        sanitized, _ = cls.sanitize(text, level="strict")
        return sanitized

    @classmethod
    def add_custom_keyword(cls, keyword: str):
        """添加自定义敏感词"""
        if keyword not in cls.custom_keywords:
            cls.custom_keywords.append(keyword)
