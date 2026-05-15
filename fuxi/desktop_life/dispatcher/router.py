"""任务分类与路由分发模块"""
import logging
import re
from enum import Enum
from typing import Literal

logger = logging.getLogger("fuxi.dispatcher")


class TaskType(Enum):
    CHAT = "chat"          # 闲聊/问答
    CODE = "code"          # 代码任务
    CREATION = "creation"  # 创作任务
    SCHEDULE = "schedule"  # 定时任务
    UNKNOWN = "unknown"


class TaskRouter:
    """任务路由器 — LLM判断 + 路由分发"""

    CODE_KEYWORDS = [
        "代码", "程序", "开发", "bug", "修复", "修改", "调试",
        "github", "git", "仓库", "项目", "适配", "优化", "学习方案",
        "写", "编译", "运行", "测试", "部署",
    ]

    CREATION_KEYWORDS = [
        "视频", "小说", "文案", "创作", "写作", "脚本", "故事",
        "制作", "生成", "画", "音乐", "配音",
    ]

    SCHEDULE_KEYWORDS = [
        "定时", " schedule", "cron", "每天", "每周", "几点",
    ]

    def classify(self, text: str) -> TaskType:
        """根据文本判断任务类型"""
        text_lower = text.lower()

        if any(kw in text_lower for kw in self.SCHEDULE_KEYWORDS):
            return TaskType.SCHEDULE

        if any(kw in text for kw in self.CREATION_KEYWORDS):
            return TaskType.CREATION

        if any(kw in text_lower for kw in self.CODE_KEYWORDS):
            return TaskType.CODE

        return TaskType.CHAT

    def route(self, text: str) -> tuple[TaskType, str]:
        """路由任务，返回类型和处理建议"""
        task_type = self.classify(text)

        routes = {
            TaskType.CHAT: ("fuxi_direct", "直接Fuxi对话"),
            TaskType.CODE: ("claude_code", "派发给Claude Code执行"),
            TaskType.CREATION: ("openclaw", "派发给OpenClaw Jinlange"),
            TaskType.SCHEDULE: ("cron_engine", "加入Cron调度"),
            TaskType.UNKNOWN: ("fuxi_direct", "默认Fuxi对话"),
        }

        handler, desc = routes.get(task_type, routes[TaskType.UNKNOWN])
        logger.info(f"任务分类: {task_type.value} -> {handler} ({desc})")
        return task_type, handler
