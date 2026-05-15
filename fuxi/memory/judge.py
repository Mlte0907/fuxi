"""伏羲 v1.0 — MemoryJudge LLM 记忆价值判断

Agent 任务完成后，调用 LLM 判断产出是否值得写入长期记忆。
分类决策：A=写 longterm / B=写普通抽屉 / C=标记待复盘 """
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger("fuxi.memory.judge")


class JudgmentVerdict(str, Enum):
    A = "A"    # 写入 longterm — 高价值，未来会复用
    B = "B"    # 写入普通抽屉 — 有参考价值但非关键
    C = "C"    # 标记待复盘 — 不确定，需要后续评估


@dataclass
class JudgmentResult:
    verdict: JudgmentVerdict
    reasoning: str = ""
    confidence: float = 0.5
    suggested_tags: list = field(default_factory=list)
    suggested_importance: float = 0.5
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


JUDGMENT_PROMPT = """你是一个记忆价值评估助手。你的任务是判断一个任务产出是否值得存入长期记忆。

评估标准：
- 如果这个产出在未来遇到类似任务时很可能被复用，评 A
- 如果这个产出有参考价值但不是关键知识，评 B
- 如果这个产出是一次性的或价值不确定，评 C

请用以下 JSON 格式输出（只输出 JSON）：
{{"verdict": "A/B/C", "reasoning": "一句话理由", "confidence": 0.0-1.0, "tags": ["标签1", "标签2"], "importance": 0.0-1.0}}

---

任务类型：{task_type}
任务描述：{task_description}
产出摘要：{output_summary}
"""


class MemoryJudge:
    """记忆价值判断器 — LLM 驱动的 Nudge 决策

    由 Agent 任务完成后调用，判断产出是否值得进入长期记忆。
    """

    def __init__(self):
        self._history: list = []   # 最近判断历史

    def evaluate(
        self,
        task_type: str,
        task_description: str,
        output_summary: str,
        agent_id: str = "",
    ) -> JudgmentResult:
        """评估任务产出是否值得写入长期记忆"""
        prompt = JUDGMENT_PROMPT.format(
            task_type=task_type,
            task_description=task_description,
            output_summary=output_summary[:2000],
        )

        reply = self._call_llm(prompt)

        result = self._parse_reply(reply)

        # 记录判断历史
        self._history.append({
            "task_type": task_type,
            "agent_id": agent_id,
            "verdict": result.verdict.value,
            "confidence": result.confidence,
            "ts": result.timestamp,
        })
        if len(self._history) > 50:
            self._history = self._history[-50:]

        return result

    def _call_llm(self, prompt: str) -> Optional[str]:
        """调用 LLM 进行判断"""
        try:
            from fuxi.agent.integration import OpenClawAdapter
            adapter = OpenClawAdapter()
            response = adapter.call_agent(
                agent_id="persona",
                message=prompt,
            )
            if response and "reply" in response:
                return response["reply"].strip()
        except Exception as e:
            logger.debug(f"MemoryJudge LLM call failed: {e}")
        return None

    def _parse_reply(self, reply: Optional[str]) -> JudgmentResult:
        """解析 LLM 返回的判断 JSON"""
        if not reply:
            return self._fallback_judgment()

        # 尝试提取 JSON
        try:
            # 直接解析
            data = json.loads(reply)
        except json.JSONDecodeError:
            # 尝试从文本中提取 JSON 块
            import re
            m = re.search(r'\{[^{}]*"verdict"[^{}]*\}', reply)
            if m:
                try:
                    data = json.loads(m.group())
                except json.JSONDecodeError:
                    return self._fallback_judgment()
            else:
                return self._fallback_judgment()

        verdict_str = data.get("verdict", "B").upper()
        try:
            verdict = JudgmentVerdict(verdict_str)
        except ValueError:
            verdict = JudgmentVerdict.B

        return JudgmentResult(
            verdict=verdict,
            reasoning=data.get("reasoning", ""),
            confidence=float(data.get("confidence", 0.5)),
            suggested_tags=data.get("tags", []),
            suggested_importance=float(data.get("importance", 0.5)),
        )

    def _fallback_judgment(self) -> JudgmentResult:
        """LLM 不可用时的降级判断 — 默认 B（写入普通抽屉）"""
        return JudgmentResult(
            verdict=JudgmentVerdict.B,
            reasoning="LLM 不可用，默认写入普通抽屉",
            confidence=0.3,
        )

    def apply_verdict(
        self,
        result: JudgmentResult,
        raw_text: str,
        agent_id: str = "",
        drawer_override: Optional[str] = None,
    ) -> dict:
        """执行判断结果 — 将记忆写入对应抽屉"""
        from fuxi.memory.ingestion import remember

        if drawer_override:
            drawer = drawer_override
        elif result.verdict == JudgmentVerdict.A:
            drawer = "longterm"
        elif result.verdict == JudgmentVerdict.B:
            drawer = f"{agent_id}_view" if agent_id else "default"
        else:
            drawer = "default"

        tags = result.suggested_tags + ["judged", result.verdict.value]
        importance = result.suggested_importance

        if result.verdict == JudgmentVerdict.C:
            tags.append("待复盘")
            importance = max(0.3, importance)

        try:
            item_id = remember(
                raw_text=raw_text,
                drawer_id=drawer,
                importance=importance,
                source=f"agent:{agent_id}" if agent_id else "judge",
                confidence=result.confidence,
                created_by=agent_id or "memory_judge",
                tags=tags,
            )
            return {
                "status": "ok",
                "item_id": item_id,
                "drawer": drawer,
                "verdict": result.verdict.value,
            }
        except Exception as e:
            logger.error(f"MemoryJudge apply_verdict failed: {e}")
            return {"status": "error", "error": str(e)}

    @property
    def history(self) -> list:
        return list(self._history)


# ── 全局单例 ──
_judge: Optional[MemoryJudge] = None


def get_memory_judge() -> MemoryJudge:
    global _judge
    if _judge is None:
        _judge = MemoryJudge()
    return _judge
