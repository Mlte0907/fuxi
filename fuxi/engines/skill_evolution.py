"""伏羲 v1.0 — 技能进化引擎（自进化技能中心核心）

观察 → 本能 → 聚类 → 技能 → 晋升 闭环

Skill Evolution Loop:
  observe()      记录任务执行中的成功模式/失败教训
  instinct()     生成原子级本能单元（confidence 0.3-0.9）
  cluster()      将本能聚类为技能雏形
  promote()      验证通过的技能晋升到技能中心
  retrieve()     任务时检索相关技能
"""
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.memory.ingestion import remember
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.skill_evolution")

SKILL_OBSERVATIONS_DIR = Path.home() / ".claude" / "observations"
CLAUDE_CODE_SKILLS_DIR = Path.home() / ".claude" / "skills"
OPENCLAW_SKILLS_DIR = Path.home() / ".openclaw" / "skills"
INSTINCT_THRESHOLD = 0.55  # 本能生成阈值
SKILL_THRESHOLD = 0.75     # 技能晋升阈值


@register_engine("skill_evolution", experimental=True)
class SkillEvolutionEngine(CognitiveEngine):
    """技能进化引擎 — 自进化技能中心的大脑"""

    name = "skill_evolution"
    experimental = True
    interval = 600  # 每10分钟检查一次
    priority = 7

    def _get_subscriptions(self):
        return {
            "task.completed": self._on_task_completed,
            "task.failed": self._on_task_failed,
            "skill.executed": self._on_skill_executed,
            "engine.executed": self._on_engine_executed,
        }

    def run(self) -> dict:
        """执行技能进化闭环"""
        ctx = self._gather_context()

        # 1. 观察：收集未处理的观察记录
        observations = self._collect_observations()
        obs_processed = len(observations)

        # 2. 本能生成：从观察中提取本能
        instincts_generated = 0
        for obs in observations:
            inst = self._generate_instinct(obs)
            if inst:
                instincts_generated += 1

        # 3. 聚类：更新技能聚类
        clusters_updated = self._update_clusters()

        # 4. 晋升检查：检查是否有技能可以晋升
        promoted = self._check_promotions()

        # 5. 发布进化事件
        self._publish_evolution_event(obs_processed, instincts_generated, clusters_updated, promoted)

        return {
            "action": "completed",
            "observations_processed": obs_processed,
            "instincts_generated": instincts_generated,
            "clusters_updated": clusters_updated,
            "skills_promoted": promoted,
            "timestamp": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # 观察收集
    # ------------------------------------------------------------------

    def _collect_observations(self) -> list:
        """从观察目录收集观察记录"""
        observations = []
        if not SKILL_OBSERVATIONS_DIR.exists():
            return observations

        for obs_file in sorted(SKILL_OBSERVATIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime):
            if obs_file.stat().st_mtime > time.time() - 300:  # 只处理5分钟内的
                try:
                    obs = json.loads(obs_file.read_text())
                    obs["_file"] = str(obs_file)
                    observations.append(obs)
                except Exception:
                    pass
        return observations

    def _on_task_completed(self, event):
        """任务完成时记录成功观察"""
        self._save_observation({
            "type": "success",
            "task": event.data.get("task", ""),
            "agent": event.data.get("agent", ""),
            "pattern": event.data.get("pattern", ""),
            "outcome": "completed",
            "ts": datetime.now().isoformat(),
        })

    def _on_task_failed(self, event):
        """任务失败时记录失败观察"""
        self._save_observation({
            "type": "failure",
            "task": event.data.get("task", ""),
            "agent": event.data.get("agent", ""),
            "error": event.data.get("error", ""),
            "outcome": "failed",
            "ts": datetime.now().isoformat(),
        })

    def _on_skill_executed(self, event):
        """技能执行时记录技能观察"""
        self._save_observation({
            "type": "skill_use",
            "skill": event.data.get("skill", ""),
            "agent": event.data.get("agent", ""),
            "effectiveness": event.data.get("effectiveness", 0.5),
            "ts": datetime.now().isoformat(),
        })

    def _on_engine_executed(self, event):
        """引擎执行时记录引擎观察"""
        if event.data.get("status") == "error":
            self._save_observation({
                "type": "engine_error",
                "engine": event.data.get("engine", ""),
                "error": event.data.get("error", ""),
                "ts": datetime.now().isoformat(),
            })

    def _save_observation(self, obs: dict):
        """保存观察记录"""
        SKILL_OBSERVATIONS_DIR.mkdir(parents=True, exist_ok=True)
        obs_id = str(uuid.uuid4())[:8]
        obs_file = SKILL_OBSERVATIONS_DIR / f"{obs_id}.json"
        obs_file.write_text(json.dumps(obs, ensure_ascii=False))
        logger.debug(f"Observation saved: {obs_id}")

    # ------------------------------------------------------------------
    # 本能生成
    # ------------------------------------------------------------------

    def _generate_instinct(self, obs: dict) -> Optional[dict]:
        """从观察中生成本能单元"""
        obs_type = obs.get("type", "")
        confidence = 0.5

        if obs_type == "success":
            # 成功模式 → 高置信度本能
            task = obs.get("task", "")
            pattern = obs.get("pattern", "")
            if task and pattern:
                confidence = 0.75
                instinct_text = f"任务「{task}」使用模式「{pattern}」成功"
            else:
                return None
        elif obs_type == "failure":
            # 失败教训 → 中等置信度本能
            task = obs.get("task", "")
            error = obs.get("error", "")
            if task:
                confidence = 0.55
                instinct_text = f"任务「{task}」失败，原因：{error[:50]}"
            else:
                return None
        elif obs_type == "skill_use":
            # 技能使用效果
            skill = obs.get("skill", "")
            eff = obs.get("effectiveness", 0.5)
            confidence = 0.4 + eff * 0.4
            if confidence >= INSTINCT_THRESHOLD:
                instinct_text = f"技能「{skill}」效果评分 {eff:.2f}"
            else:
                return None
        else:
            return None

        instinct = {
            "id": str(uuid.uuid4())[:12],
            "text": instinct_text,
            "confidence": round(confidence, 3),
            "source": obs_type,
            "task": obs.get("task", ""),
            "created_at": datetime.now().isoformat(),
            "cluster_id": None,
        }

        # 存入伏羲记忆（本能抽屉）
        try:
            remember(
                raw_text=instinct_text,
                drawer_id="instincts",
                importance=confidence * 0.7,
                tags=["instinct", obs_type],
                source="skill-evolution",
                created_by="skill-evolution-engine",
                confidence=confidence,
            )
            logger.info(f"Instinct generated: {instinct['id']} (confidence={confidence:.2f})")
        except Exception as e:
            logger.debug(f"Instinct memory write failed: {e}")

        return instinct

    # ------------------------------------------------------------------
    # 聚类
    # ------------------------------------------------------------------

    def _update_clusters(self) -> int:
        """更新本能聚类"""
        pool = get_pool()
        # 获取最近的本能
        instincts = pool.fetchall(
            "SELECT id, raw_text, created_by FROM items "
            "WHERE drawer_id='instincts' AND archived=0 "
            "ORDER BY created_at DESC LIMIT 50"
        )

        if not instincts:
            return 0

        # 简单聚类：按任务前缀聚类
        clusters = {}
        for inst in instincts:
            task = inst.get("raw_text", "")
            # 提取任务名作为聚类键
            if "任务「" in task:
                task_name = task.split("任务「")[1].split("」")[0] if "」" in task else task[:30]
                if task_name not in clusters:
                    clusters[task_name] = []
                clusters[task_name].append(inst["id"])

        return len(clusters)

    def _check_promotions(self) -> int:
        """检查技能是否可以晋升"""
        pool = get_pool()
        # 查找高置信度本能，尝试晋升为技能
        high_conf = pool.fetchall(
            "SELECT id, raw_text, confidence FROM items "
            "WHERE drawer_id='instincts' AND archived=0 "
            "AND importance > 0.6 "
            "ORDER BY importance DESC LIMIT 10"
        )

        promoted = 0
        for inst in high_conf:
            if inst.get("confidence", 0) >= SKILL_THRESHOLD:
                # 晋升为技能
                skill_name = self._instinct_to_skill_name(inst["raw_text"])
                self._promote_skill(skill_name, inst)
                promoted += 1

        return promoted

    def _instinct_to_skill_name(self, text: str) -> str:
        """从本能文本提取技能名称"""
        # 移除任务/模式/原因等前缀
        import re
        text = re.sub(r"任务「.*?」", "", text)
        text = re.sub(r"模式「.*?」", "", text)
        text = re.sub(r"原因：.*", "", text)
        text = re.sub(r"技能「", "", text)
        text = re.sub(r"」.*", "", text)
        text = text.strip()
        # 保留前30字符作为技能名
        return text[:30] if text else "anonymous_skill"

    def _promote_skill(self, name: str, instinct: dict):
        """晋升本能为技能 — 双向输出到 Claude Code 和 OpenClaw"""
        confidence = instinct.get("confidence", 0)
        source = instinct.get("raw_text", "")
        instinct_id = instinct["id"][:8]

        # 技能内容模板
        content = f"""---
name: {name}
description: 自动生成的技能，来源：{source}。置信度 {confidence:.2f}。
origin: fuxi-evolution
version: 1.0.0
---

# {name}

**来源本能**: {source}
**置信度**: {confidence:.2f}
**晋升时间**: {datetime.now().isoformat()}
**状态**: active
**来源系统**: fuxi-evolution

## 描述
自动生成的技能，来源于任务执行中的成功模式。

## 使用场景
- 适用于类似的重复性任务
- 可作为技能检索的候选

## 示例
（待补充）
"""

        # 输出到 Claude Code skills
        CLAUDE_CODE_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        skill_id = f"fuxi-evolution-{instinct['id']}"
        cc_skill_file = CLAUDE_CODE_SKILLS_DIR / f"{skill_id}.md"
        cc_skill_file.write_text(content)
        logger.info(f"Skill promoted to Claude Code: {name} (from instinct {instinct_id})")

        # 输出到 OpenClaw skills
        oc_skill_dir = OPENCLAW_SKILLS_DIR / f"fuxi-evolution-{skill_id}"
        oc_skill_dir.mkdir(parents=True, exist_ok=True)
        oc_skill_file = oc_skill_dir / "SKILL.md"
        oc_skill_file.write_text(content)
        logger.info(f"Skill promoted to OpenClaw: {name} (from instinct {instinct_id})")

    # ------------------------------------------------------------------
    # 上下文 & 发布
    # ------------------------------------------------------------------

    def _gather_context(self) -> dict:
        pool = get_pool()

        # 统计
        instinct_count = pool.fetchone(
            "SELECT COUNT(*) as c FROM items WHERE drawer_id='instincts' AND archived=0"
        )
        cc_skills = len(list(CLAUDE_CODE_SKILLS_DIR.glob("fuxi-evolution-*.md"))) if CLAUDE_CODE_SKILLS_DIR.exists() else 0
        oc_skills = len(list(OPENCLAW_SKILLS_DIR.glob("fuxi-evolution-*"))) if OPENCLAW_SKILLS_DIR.exists() else 0
        skill_count = cc_skills + oc_skills
        obs_count = len(list(SKILL_OBSERVATIONS_DIR.glob("*.json"))) if SKILL_OBSERVATIONS_DIR.exists() else 0

        return {
            "instinct_count": instinct_count["c"] if instinct_count else 0,
            "skill_count": skill_count,
            "observation_count": obs_count,
            "claude_code_skills_dir": str(CLAUDE_CODE_SKILLS_DIR),
            "openclaw_skills_dir": str(OPENCLAW_SKILLS_DIR),
        }

    def _publish_evolution_event(self, obs, instincts, clusters, promoted):
        from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
        get_event_bus().publish(Event(
            type="skill_evolution.cycle",
            data={
                "observations_processed": obs,
                "instincts_generated": instincts,
                "clusters_updated": clusters,
                "skills_promoted": promoted,
            },
            priority=EventPriority.LOW,
            source="engine:skill_evolution",
        ))