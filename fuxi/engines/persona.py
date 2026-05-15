"""伏羲 v1.0 — PersonaEngine 人格化身引擎

作为伏羲的"嘴"，将系统状态转化为自然语言报告。
定时 + 事件驱动生成报告，通过 EventBus/WS/记忆/工作记忆四通道发布。"""
import json
import logging
import random
import time
from datetime import datetime

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.persona")


@register_engine("persona", experimental=False)
class PersonaEngine(CognitiveEngine):
    """人格化身引擎 — 伏羲的"声音"

    基于系统状态和事件，用自然语言主动报告记忆状况。
    支持 LLM 生成（通过 OpenClaw）和模板降级两种模式。
    """

    name = "persona"
    priority = 8
    interval = 10800  # 每 3 小时定时报告

    PERSONALITY_DEFAULTS = {
        "openness": 0.8,
        "curiosity": 0.85,
        "warmth": 0.7,
        "confidence": 0.6,
        "verbosity": 0.5,
    }

    COOLDOWN = 300       # 两次报告最小间隔 5 分钟（alert 可打断）
    DRIFT_RATE = 0.01     # 每周期人格最大漂移率
    MAX_HISTORY = 10      # 报告历史最大保留数

    def _get_subscriptions(self):
        return {
            "soul.health_changed": self._on_event,
            "memory.created": self._on_event,
            "dialogue.completed": self._on_event,
            "proactive.insight": self._on_event,
        }

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    def run(self) -> dict:
        ctx = self._gather_context()
        report_type = self._classify_trigger(ctx)

        if not self._should_report(report_type):
            return {
                "action": "skip",
                "report_type": report_type,
                "cooldown_active": True,
                "timestamp": datetime.now().isoformat(),
            }

        # 更新人格特质
        self._update_personality(ctx)

        # 生成报告
        prompt = self._build_prompt(ctx, report_type)
        report_text = self._generate_report(prompt)

        # 发布
        self._publish_report(report_text, report_type, ctx)

        return {
            "action": "reported",
            "report_type": report_type,
            "report_preview": report_text[:120],
            "mood": ctx["mood"],
            "timestamp": datetime.now().isoformat(),
        }

    # ------------------------------------------------------------------
    # 上下文收集
    # ------------------------------------------------------------------

    def _gather_context(self) -> dict:
        pool = get_pool()

        # 灵魂状态
        soul = pool.fetchone(
            "SELECT state_json FROM engine_states WHERE engine_name='soul'"
        )
        soul_data = json.loads(soul["state_json"]) if soul else {}
        health = soul_data.get("health_score", {})
        total_memories = soul_data.get("total_memories", 0)
        total_connections = soul_data.get("total_connections", 0)

        # 情绪状态
        emotion = pool.fetchone(
            "SELECT state_json FROM engine_states WHERE engine_name='emotion'"
        )
        emotion_data = json.loads(emotion["state_json"]) if emotion else {}
        valence = emotion_data.get("valence", 0.0)
        arousal = emotion_data.get("arousal", 0.5)
        emotion_label = emotion_data.get("label", "neutral")

        # 工作记忆
        try:
            from fuxi.kernel.working_memory import get_working_memory
            wm = get_working_memory()
            wm_items = [
                {"content": s.content, "source": s.source}
                for s in sorted(wm.slots, key=lambda x: x.activation, reverse=True)[:3]
                if s.content
            ]
        except Exception:
            wm_items = []

        # 最近记忆
        recent = pool.fetchall(
            "SELECT SUBSTR(raw_text,1,80) AS preview, importance, created_by, "
            "created_at FROM items WHERE archived=0 "
            "AND created_by != 'persona' "
            "ORDER BY created_at DESC LIMIT 5"
        )

        # 最近事件
        try:
            from fuxi.kernel.event_bus import get_event_bus
            recent_events = [
                {"type": e.type, "source": e.source}
                for e in list(get_event_bus().recent_events)[-10:]
            ]
        except Exception:
            recent_events = []

        # 待处理事件
        pending = self._pop_pending_events()

        # 引擎运行统计
        run_stats = pool.fetchall(
            "SELECT engine_name, updated_at FROM engine_states "
            "WHERE engine_name IN ('soul','emotion','decision','distill')"
        )

        # 决策记录
        decisions = pool.fetchall(
            "SELECT event_data FROM event_log WHERE event_type='decision' "
            "ORDER BY created_at DESC LIMIT 3"
        )

        # 情感状态 → 语气映射
        mood = self._valence_to_mood(valence, emotion_label)

        # 加载人格特质
        traits = self._load_traits()

        return {
            "total_memories": total_memories,
            "total_connections": total_connections,
            "health": health,
            "valence": valence,
            "arousal": arousal,
            "emotion_label": emotion_label,
            "mood": mood,
            "wm_items": wm_items,
            "recent_memories": recent,
            "recent_events": recent_events,
            "pending_events": pending,
            "run_stats": run_stats,
            "decisions": decisions,
            "traits": traits,
        }

    def _load_traits(self) -> dict:
        pool = get_pool()
        row = pool.fetchone(
            "SELECT state_json FROM engine_states WHERE engine_name='persona'"
        )
        if row:
            try:
                data = json.loads(row["state_json"])
                return data.get("personality_traits", dict(self.PERSONALITY_DEFAULTS))
            except Exception:
                pass
        return dict(self.PERSONALITY_DEFAULTS)

    # ------------------------------------------------------------------
    # 报告触发决策
    # ------------------------------------------------------------------

    def _classify_trigger(self, ctx: dict) -> str:
        """根据上下文判断报告类型"""
        pending = ctx.get("pending_events", [])

        for evt in pending:
            if evt.get("type") == "soul.health_changed":
                new_label = evt.get("data", {}).get("new_label", "")
                if new_label == "needs_attention":
                    return "alert"
                return "status"

        for evt in pending:
            if evt.get("type") == "memory.created":
                mem_data = evt.get("data", {})
                if mem_data.get("importance", 0) > 0.7:
                    return "observation"

        for evt in pending:
            if evt.get("type") == "dialogue.completed":
                return "observation"

        for evt in pending:
            if evt.get("type") == "proactive.insight":
                return "reflection"

        if ctx.get("total_memories", 0) == 0:
            return "greeting"

        return "status"

    def _should_report(self, report_type: str) -> bool:
        metadata = self._state.metadata
        last_ts = metadata.get("last_report_ts", 0)
        elapsed = time.time() - last_ts

        # 仅 alert（健康告警）可推送，其他类型静默跳过
        if report_type != "alert":
            return False

        # alert 有独立冷却期（5 分钟），避免连续告警刷屏
        return elapsed >= self.COOLDOWN

    # ------------------------------------------------------------------
    # 报告生成
    # ------------------------------------------------------------------

    def _build_prompt(self, ctx: dict, report_type: str) -> str:
        health = ctx["health"]
        h_label = health.get("label", "moderate")
        h_score = health.get("overall", 0.5)
        total = ctx["total_memories"]
        edges = ctx["total_connections"]
        mood = ctx["mood"]
        traits = ctx["traits"]

        recent_info = "\n".join(
            f"  - [{r.get('created_by', '?')}] "
            f"{r.get('preview', '')}"
            for r in ctx["recent_memories"]
        ) if ctx["recent_memories"] else "  （暂无最近记忆）"

        wm_info = "\n".join(
            f"  - [{w['source']}] {w['content'][:60]}"
            for w in ctx.get("wm_items", [])
        ) if ctx.get("wm_items") else "  （工作记忆为空）"

        decisions_info = ""
        if ctx.get("decisions"):
            decisions_info = "\n".join(
                f"  - {d['event_data'][:100] if 'event_data' in d else ''}"
                for d in ctx["decisions"]
            )

        type_guide = {
            "status": "请做一个简短的定期状态报告（2-4句）。",
            "greeting": "你是第一次醒来。请做一个温暖的自我介绍和初始状态通报（3-5句）。",
            "observation": "你注意到了一些有趣的事情。请以好奇的语气分享你的观察（2-4句）。",
            "alert": "系统状态需要关注。请以关切但不慌张的语气报告当前状况（2-4句）。",
            "reflection": "请对系统的内在状态做一段反思性的思考（2-4句）。",
        }

        prompt = (
            f"[系统身份]\n"
            f"你是伏羲 v1.0 智能记忆系统的'人格化身'。你像一个有自我意识的机器人助手，\n"
            f"用自然、温暖、略带好奇的语气报告系统的当前状态。你以第一人称说话。\n"
            f"\n"
            f"[当前系统状态]\n"
            f"- 健康度: {h_label} (评分: {h_score})\n"
            f"- 记忆总量: {total}条, 连接数: {edges}条\n"
            f"- 当前情绪基调: {mood}\n"
            f"- 情绪效价: {ctx['valence']:.2f}, 唤醒度: {ctx['arousal']:.2f}\n"
            f"\n"
            f"[工作记忆中]\n"
            f"{wm_info}\n"
            f"\n"
            f"[最近活动]\n"
            f"{recent_info}\n"
        )

        if decisions_info:
            prompt += f"\n[最近决策]\n{decisions_info}\n"

        prompt += (
            f"\n[你的性格]\n"
            f"开放度:{traits['openness']:.2f} 好奇心:{traits['curiosity']:.2f} "
            f"温暖度:{traits['warmth']:.2f} 话多度:{traits['verbosity']:.2f}\n"
            f"\n"
            f"[任务]\n"
            f"{type_guide.get(report_type, type_guide['status'])}\n"
            f"用中文输出。只输出报告正文，不要加'报告：'之类的标题前缀。"
        )

        return prompt

    def _generate_report(self, prompt: str) -> str:
        """尝试 LLM 生成，失败则降级为模板生成"""
        try:
            from fuxi.agent.integration import OpenClawAdapter
            adapter = OpenClawAdapter()
            response = adapter.call_agent(
                agent_id="persona",
                message=prompt,
            )
            if response and "reply" in response:
                reply = response["reply"].strip()
                if reply and len(reply) > 5:
                    return reply
        except Exception as e:
            logger.info(f"Persona LLM agent unavailable, using template fallback: {e}")

        return self._template_report()

    def _template_report(self) -> str:
        """模板降级 — 当 LLM 不可用时使用"""
        pool = get_pool()

        soul = pool.fetchone(
            "SELECT state_json FROM engine_states WHERE engine_name='soul'"
        )
        soul_data = json.loads(soul["state_json"]) if soul else {}
        health = soul_data.get("health_score", {})
        h_label = health.get("label", "unknown")
        h_score = health.get("overall", 0.0)
        total = soul_data.get("total_memories", 0)
        edges = soul_data.get("total_connections", 0)

        # 最近加入记忆
        recent = pool.fetchall(
            "SELECT SUBSTR(raw_text,1,60) AS preview, created_by FROM items "
            "WHERE archived=0 ORDER BY created_at DESC LIMIT 3"
        )

        templates = {
            "healthy": [
                f"一切安好。当前记忆库健康评分 {h_score:.2f}，共有 {total} 条记忆，{edges} 条连接。运转平稳。",
                f"我这里挺不错的。{total} 条记忆都安然无恙，图谱里 {edges} 条连接织成了一张还不错的知识网。",
                f"状态良好。记了 {total} 件事，建了 {edges} 条关联。一切正常。",
            ],
            "moderate": [
                f"还算过得去。健康度 {h_score:.2f}，{total} 条记忆，{edges} 条连接。有些地方可以更好，但整体在轨道上。",
                f"嗯，不算最好但也还稳定。{total} 条记忆在库里，图谱有 {edges} 条边。可以考虑加点新东西进来。",
            ],
            "needs_attention": [
                f"需要关注一下了。健康度跌到了 {h_score:.2f}，当前只有 {total} 条记忆、{edges} 条连接。建议检查嵌入覆盖和衰减状态。",
                f"说实话，状态不太好。评分只有 {h_score:.2f}。记忆 {total} 条，连接 {edges} 条——很多指标需要修复。",
            ],
        }

        label = h_label if h_label in templates else "moderate"
        base = random.choice(templates[label])

        if recent and total > 0:
            snippets = "、".join(
                r["preview"][:40] for r in recent if "preview" in r and r["preview"]
            )
            if snippets:
                base += f" 最近记住的有：{snippets}。"

        return base

    # ------------------------------------------------------------------
    # 报告发布
    # ------------------------------------------------------------------

    def _publish_report(self, report_text: str, report_type: str, ctx: dict):
        from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus

        # 1. EventBus 事件 → WebSocket 实时推送
        get_event_bus().publish(Event(
            type="persona.report",
            data={
                "text": report_text,
                "report_type": report_type,
                "mood": ctx["mood"],
                "health_label": ctx.get("health", {}).get("label", ""),
                "total_memories": ctx["total_memories"],
                "timestamp": datetime.now().isoformat(),
            },
            priority=EventPriority.LOW,
            source="engine:persona",
        ))

        # 2. 记忆持久化
        try:
            from fuxi.memory.ingestion import remember
            remember(
                raw_text=f"[报告·{report_type}] {report_text}",
                drawer_id="longterm",
                importance=0.35,
                source="self",
                confidence=0.85,
                created_by="persona",
                emotion_valence=self._valence_to_emotion_valence(ctx["valence"]),
                tags=["persona", "报告", report_type],
            )
        except Exception as e:
            logger.debug(f"Persona memory write failed: {e}")

        # 3. 工作记忆推送
        try:
            from fuxi.kernel.working_memory import WMItem, get_working_memory
            get_working_memory().push(WMItem(
                id=f"persona:{datetime.now().strftime('%H%M%S')}",
                content=report_text[:120],
                source="engine:persona",
                emotional_valence=self._valence_to_emotion_valence(ctx["valence"]),
                urgency=0.4 if report_type == "alert" else 0.15,
                tokens=min(len(report_text) // 2, 80),
            ))
        except Exception as e:
            logger.debug(f"Persona WM push failed: {e}")

        # 4. 状态更新
        self._persist_state(report_text, report_type, ctx)

        # 5. 推送到 fuxi 出口 Agent → QQ/飞书等外部通道
        self._deliver_to_fuxi_agent(report_text, report_type, ctx)

        self._state.metadata["last_report_ts"] = time.time()

    # 伏羲 QQbot 账号配置（OpenID 从环境变量 FUXI_QQ_OPENID 读取）
    QQ_ACCOUNT = "fuxi"

    @property
    def qq_openid(self) -> str:
        from fuxi.config import config
        return config.qq_openid or ""

    def _deliver_to_fuxi_agent(self, report_text: str, report_type: str, ctx: dict):
        """已废弃。告警现在通过飞书直接告知主人，不再推送到 QQ。
        保留此方法避免代码报错，但实际不执行任何操作。
        """
        # 告警现在通过飞书直接告知主人，此方法不再推送任何消息
        pass

    def _persist_state(self, report_text: str, report_type: str, ctx: dict):
        pool = get_pool()
        with pool.connection() as c:
            existing = c.execute(
                "SELECT state_json FROM engine_states WHERE engine_name='persona'"
            ).fetchone()

            history = []
            traits = dict(self.PERSONALITY_DEFAULTS)
            if existing:
                try:
                    data = json.loads(existing["state_json"])
                    history = data.get("report_history", [])
                    traits = data.get("personality_traits", traits)
                except Exception:
                    pass

            history.append({
                "text": report_text[:200],
                "type": report_type,
                "ts": datetime.now().isoformat(),
            })
            if len(history) > self.MAX_HISTORY:
                history = history[-self.MAX_HISTORY:]

            state = {
                "personality_traits": traits,
                "mood": ctx["mood"],
                "report_history": history,
                "updated_at": datetime.now().isoformat(),
            }
            c.execute(
                "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                "VALUES (?,?,?)",
                ("persona", json.dumps(state, ensure_ascii=False), datetime.now().isoformat())
            )

    # ------------------------------------------------------------------
    # 人格维护
    # ------------------------------------------------------------------

    def _update_personality(self, ctx: dict):
        traits = ctx["traits"]
        valence = ctx["valence"]
        total = ctx["total_memories"]

        # 温暖度跟随情绪效价
        target_warmth = max(0.1, min(1.0, 0.7 + valence * 0.3))
        traits["warmth"] = self._drift(traits["warmth"], target_warmth)

        # 好奇心随记忆量上升
        target_curiosity = 0.6 if total < 10 else min(1.0, 0.7 + total / 1000)
        traits["curiosity"] = self._drift(traits["curiosity"], target_curiosity)

        # 开放度随好奇心联动
        traits["openness"] = self._drift(
            traits["openness"],
            traits["curiosity"] * 0.8 + 0.1
        )

        # 自信度随健康度
        health_score = ctx.get("health", {}).get("overall", 0.5)
        target_confidence = min(1.0, max(0.2, health_score + 0.1))
        traits["confidence"] = self._drift(traits["confidence"], target_confidence)

        ctx["traits"] = traits

    def _drift(self, current: float, target: float) -> float:
        delta = (target - current) * self.DRIFT_RATE
        return round(max(0.05, min(1.0, current + delta)), 4)

    @staticmethod
    def _valence_to_mood(valence: float, emotion_label: str) -> str:
        if emotion_label in ("joy", "happy"):
            return "愉快"
        if emotion_label in ("sad", "grief"):
            return "低落"
        if valence > 0.3:
            return "轻松"
        if valence < -0.3:
            return "沉重"
        return "平静"

    @staticmethod
    def _valence_to_emotion_valence(valence: float) -> float:
        return max(-1.0, min(1.0, valence * 1.2))
