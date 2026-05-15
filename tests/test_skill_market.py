"""测试 skill_market 子系统的技能发现、提交和集成功能"""
import pytest
import time
import uuid

from fuxi.skill_market.discovery import discover_skills, format_skills_for_prompt
from fuxi.skill_market.submission import (
    submit_skill,
    extract_skill_name,
    extract_keywords,
    estimate_quality,
    TASK_KEYWORDS,
)


class TestSkillDiscovery:
    """技能发现测试"""

    def test_discover_skills_empty(self):
        """空库应返回空列表"""
        skills = discover_skills(task_type="nonexistent", min_quality=0.9)
        assert isinstance(skills, list)
        assert len(skills) == 0

    def test_discover_skills_returns_list(self):
        """不传参数应返回列表"""
        skills = discover_skills()
        assert isinstance(skills, list)

    def test_format_skills_for_prompt_empty(self):
        """空技能列表返回空字符串（预期行为）"""
        result = format_skills_for_prompt([])
        assert result == ""

    def test_discover_with_keywords(self):
        """关键词搜索"""
        skills = discover_skills(
            task_type="debug",
            keywords=["bug", "fix"],
            min_quality=0.3,
            limit=3,
        )
        assert isinstance(skills, list)


class TestSkillSubmission:
    """技能提交测试"""

    def test_extract_skill_name_basic(self):
        """基本技能名提取"""
        name = extract_skill_name("debug", "修复一个崩溃问题", "")
        assert isinstance(name, str)
        assert len(name) > 0

    def test_extract_skill_name_from_outcome(self):
        """从outcome提取技能名"""
        name = extract_skill_name(
            "feature",
            "添加新功能",
            "成功: 实现了向量搜索加速模块",
        )
        assert isinstance(name, str)

    def test_extract_keywords_debug(self):
        """调试类型关键词"""
        kws = extract_keywords("debug", "修复了列表越界崩溃bug")
        assert "debug" in kws
        assert len(kws) <= 10

    def test_extract_keywords_feature(self):
        """功能类型关键词"""
        kws = extract_keywords("feature", "新增用户画像功能模块")
        assert "feature" in kws
        assert len(kws) <= 10

    def test_extract_keywords_unknown_type(self):
        """未知类型返回自身"""
        kws = extract_keywords("unknown_type", "test")
        assert "unknown_type" in kws

    def test_estimate_quality_success(self):
        """成功结果高分"""
        score = estimate_quality({"status": "ok", "data": {"result": 42}})
        assert score > 0.6

    def test_estimate_quality_error(self):
        """错误结果低分"""
        score = estimate_quality({"status": "error", "error": "something broke"})
        assert score < 0.7

    def test_estimate_quality_capped(self):
        """分数不超过0.95"""
        score = estimate_quality(
            {"status": "ok", "data": {"result": 42, "extra": "value"}}
        )
        assert score <= 0.95

    def test_submit_skill_returns_string(self):
        """提交技能返回ID字符串"""
        skill_id = submit_skill(
            task_type="test",
            description="test description",
            outcome="test outcome",
        )
        assert isinstance(skill_id, str)

    def test_submit_skill_with_agent(self):
        """带agent_id的提交"""
        skill_id = submit_skill(
            task_type="debug",
            description="fix bug test",
            outcome="bug fixed",
            agent_id="test_agent",
            auto_approve=False,
        )
        assert isinstance(skill_id, str)

    def test_task_keywords_complete(self):
        """任务关键词映射完整"""
        for task_type in ["debug", "refactor", "feature", "memory",
                           "deploy", "security", "monitor", "test"]:
            assert task_type in TASK_KEYWORDS, f"Missing task type: {task_type}"
            assert len(TASK_KEYWORDS[task_type]) > 0