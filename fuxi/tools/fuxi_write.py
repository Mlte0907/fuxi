"""伏羲 v1.0 — fuxi_write SKILL 封装

为 Agent 提供标准化的记忆写入接口。
封装了 remember() 函数，增加了参数验证、标签标准化、去重检查。"""
import logging
from typing import List, Optional

logger = logging.getLogger("fuxi.tools.write")


class FuxiWriteSkill:
    """Agent 记忆写入技能 — 标准化记忆写入

    用法:
        skill = FuxiWriteSkill(agent_id="qinglong")
        item_id = skill.write(
            raw_text="用户完成了数据迁移",
            memory_type="task_complete",
            importance=0.8,
        )
    """

    def __init__(self, agent_id: str = "default"):
        self.agent_id = agent_id

    def write(
        self,
        raw_text: str,
        memory_type: str = "general",
        importance: float = 0.5,
        drawer_id: str = "default",
        confidence: float = 1.0,
        source: str = "skill",
        tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """写入一条记忆

        Args:
            raw_text: 记忆文本
            memory_type: 记忆类型 (general/task_complete/issue_found/decision/insight/audit)
            importance: 重要性 (0-1)
            drawer_id: 目标抽屉
            confidence: 置信度 (0-1)
            source: 数据来源
            tags: 自定义标签列表

        Returns:
            item_id 或 None（失败时）
        """
        from fuxi.memory.ingestion import remember

        # 标准化标签
        final_tags = self._build_tags(memory_type, tags or [])

        # 类型→抽屉映射
        type_drawer_map = {
            "task_complete": "longterm",
            "issue_found": "longterm",
            "decision": "longterm",
            "insight": "longterm",
            "audit": "longterm",
        }
        if memory_type in type_drawer_map and drawer_id == "default":
            drawer_id = type_drawer_map[memory_type]

        # 类型→重要性映射
        type_importance_map = {
            "task_complete": 0.8,
            "issue_found": 0.9,
            "decision": 0.85,
            "insight": 0.75,
            "audit": 0.7,
        }
        if memory_type in type_importance_map and importance == 0.5:
            importance = type_importance_map[memory_type]

        try:
            item_id = remember(
                raw_text=raw_text,
                drawer_id=drawer_id,
                importance=min(1.0, max(0.0, importance)),
                source=source,
                confidence=min(1.0, max(0.0, confidence)),
                created_by=self.agent_id,
                tags=final_tags,
            )
            logger.info(
                f"[{self.agent_id}] Wrote {memory_type} memory to {drawer_id}: {item_id}"
            )
            return item_id
        except Exception as e:
            logger.error(f"[{self.agent_id}] Write failed: {e}")
            return None

    def write_task_complete(
        self,
        task_name: str,
        summary: str,
        tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """快捷方法：写入任务完成记忆"""
        return self.write(
            raw_text=f"[任务完成] {task_name}\n{summary}",
            memory_type="task_complete",
            importance=0.8,
            tags=["task-complete"] + (tags or []),
        )

    def write_issue(
        self,
        issue_desc: str,
        severity: str = "medium",
    ) -> Optional[str]:
        """快捷方法：写入发现的问题"""
        return self.write(
            raw_text=f"[问题发现] ({severity}) {issue_desc}",
            memory_type="issue_found",
            importance=0.9,
            tags=["issue", severity],
        )

    def write_decision(
        self,
        decision_desc: str,
        options_considered: str = "",
    ) -> Optional[str]:
        """快捷方法：写入决策记录"""
        raw = f"[决策] {decision_desc}"
        if options_considered:
            raw += f"\n考虑方案: {options_considered}"
        return self.write(
            raw_text=raw,
            memory_type="decision",
            importance=0.85,
            tags=["decision"],
        )

    def _build_tags(
        self, memory_type: str, custom_tags: List[str]
    ) -> List[str]:
        """构建标准化标签列表"""
        base_tags = ["fuxi-skill", memory_type, f"agent:{self.agent_id}"]
        seen = set(base_tags)
        result = list(base_tags)
        for tag in custom_tags:
            if tag not in seen:
                result.append(tag)
                seen.add(tag)
        return result
