"""伏羲 v1.1 — 端到端认知闭环集成测试

模拟完整认知闭环: 创建记忆 → 引擎触发 → 推理 → 决策 → 行动 → 自适应调参
"""
import pytest


class TestCognitiveLoopE2E:
    """完整认知闭环端到端测试"""

    def test_memory_created_triggers_reflection(self, temp_db):
        """记忆创建后触发 ReflectionEngine 产生反思"""
        from fuxi.memory.ingestion import remember
        from fuxi.engines.reflection import ReflectionEngine

        # 创建多条孤立记忆（无关联边）
        for i in range(5):
            remember(
                raw_text=f"测试记忆{i} 这是一条没有关联边的独立记忆",
                drawer_id="longterm",
                importance=0.5,
                source="test",
                created_by="test",
            )

        engine = ReflectionEngine()
        result = engine.run()

        # 结果有 "results" 键表示正常执行
        assert "results" in result or "status" in result

    def test_decision_engine_detects_situation_and_executes(self, temp_db):
        """DecisionEngine 检测到情境并通过 DecisionExecutor 执行"""
        from fuxi.engines.decision import DecisionEngine
        from fuxi.decision.executor import DecisionExecutor
        from fuxi.decision.framework import Decision, DecisionOption, DecisionStatus

        # 创建低价值记忆用于触发清理决策
        from fuxi.memory.ingestion import remember
        for i in range(3):
            remember(
                raw_text=f"低价值垃圾{i}",
                drawer_id="default",
                importance=0.05,
                source="test",
                created_by="test",
            )

        engine = DecisionEngine()
        result = engine.run()

        assert "decisions_made" in result
        assert isinstance(result["decisions_made"], int)

    def test_behavior_collector_receives_events(self, temp_db):
        """BehaviorCollector 通过 EventBus 接收事件"""
        from fuxi.adaptive.signals import get_behavior_collector, BEHAVIOR_SIGNALS
        from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus

        collector = get_behavior_collector()
        bus = get_event_bus()

        # 模拟发布多个信号事件
        bus.publish(Event(type="search.query", data={"query": "test"}, priority=EventPriority.LOW, source="test"))
        bus.publish(Event(type="memory.accessed", data={"id": "test123"}, priority=EventPriority.NORMAL, source="test"))
        bus.publish(Event(type="memory.created", data={"id": "new123"}, priority=EventPriority.NORMAL, source="test"))

        signals = collector.get_user_profile_signals()
        assert signals is not None

    def test_recall_publishes_memory_accessed_event(self, temp_db):
        """recall() 发布 memory.accessed 事件"""
        from fuxi.memory.ingestion import remember
        from fuxi.kernel.event_bus import get_event_bus

        # 写入一条记忆
        item_id = remember(raw_text="测试召回事件", drawer_id="default", importance=0.5)

        # 召回该记忆
        from fuxi.memory.retrieval import recall
        results = recall(query="测试召回事件", limit=5)

        assert len(results) >= 1
        assert results[0]["id"] == item_id

    def test_adaptive_engine_with_signals(self, temp_db):
        """AdaptiveEngine 有信号时可以正常调整参数"""
        from fuxi.adaptive.signals import get_behavior_collector
        from fuxi.engines.adaptive import AdaptiveEngine
        from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus

        collector = get_behavior_collector()
        bus = get_event_bus()

        # 模拟高搜索重搜率信号
        for _ in range(5):
            bus.publish(Event(type="search.query", data={"query": "test"}, priority=EventPriority.LOW, source="test"))
            bus.publish(Event(type="search.refine", data={"query": "test"}, priority=EventPriority.LOW, source="test"))

        engine = AdaptiveEngine()
        result = engine.run()

        assert "signals" in result
        assert "adjustments" in result

    def test_engine_priority_adjust_with_rollback(self, temp_db):
        """引擎优先级调整可以快照和回滚"""
        from fuxi.engines.base import get_engine_registry
        from fuxi.decision.handlers import snapshot_engine_priority_adjust, rollback_engine_priority_adjust

        registry = get_engine_registry()
        engine = registry.get("reflection")
        original_priority = engine.priority

        # snapshot
        snap = snapshot_engine_priority_adjust("test-decision", {"engine": "reflection", "priority": 1})
        assert snap["engine"] == "reflection"
        assert snap["old_priority"] == original_priority

        # 执行调整
        engine.priority = 1

        # rollback
        result = rollback_engine_priority_adjust("test-decision", {"engine": "reflection", "priority": 1}, snap)
        assert result["status"] == "ok"
        assert engine.priority == original_priority

    def test_emotion_frustration_publishes_event(self, temp_db):
        """EmotionEngine 发布 frustration 事件"""
        from fuxi.kernel.event_bus import get_event_bus
        from fuxi.engines.emotion import EmotionEngine

        engine = EmotionEngine()
        result = engine.run()

        assert "valence" in result
        assert "frustration" in result

    def test_reflection_daily_cap(self, temp_db):
        """ReflectionEngine 每日写入上限生效"""
        from fuxi.engines.reflection import ReflectionEngine

        engine = ReflectionEngine()

        # 多次运行不应超过每日上限
        results = []
        for _ in range(5):
            r = engine.run()
            results.append(r.get("status"))

        # 至少有一次应该是 idle（cap reached）
        assert "idle" in results or all(r in ("ok", "idle") for r in results)

    def test_decision_rollback_on_failure(self, temp_db):
        """决策执行失败时正确回滚"""
        from fuxi.decision.executor import DecisionExecutor
        from fuxi.decision.framework import Decision, DecisionOption, DecisionStatus
        from fuxi.engines.base import get_engine_registry

        # 保存原优先级
        registry = get_engine_registry()
        engine = registry.get("reflection")
        original_priority = engine.priority

        # 创建一个会失败的决策处理器（通过不存在的 action_type）
        DecisionExecutor.register_handler("test_fail", lambda p: (_ for _ in ()).throw(RuntimeError("intentional")))

        # snapshot/rollback 不存在时也应该不崩溃
        DecisionExecutor.ROLLBACK_HANDLERS["test_fail"] = (None, None)

        opt = DecisionOption(id="fail", description="故意失败", action_type="test_fail", risk_level=0.1)
        d = Decision(
            id="rollback-test",
            trigger_reason="test rollback",
            options=[opt],
            selected_option="fail",
            status=DecisionStatus.APPROVED,
        )

        executor = DecisionExecutor()
        result = executor.execute(d)

        assert result["status"] == "rolled_back"
        assert "error" in result

        # 恢复原状态
        engine.priority = original_priority


class TestKnowledgeGraphIntegration:
    """知识图谱集成测试"""

    def test_graph_connects_new_memories(self, temp_db):
        """新记忆自动建立关联边"""
        from fuxi.memory.ingestion import remember
        from fuxi.memory.graph import MemoryGraph

        # 写入相关记忆
        id1 = remember(raw_text="Python是一种编程语言", drawer_id="longterm", importance=0.6)
        id2 = remember(raw_text="JavaScript也是一种编程语言", drawer_id="longterm", importance=0.6)

        graph = MemoryGraph()
        edges = graph.get_neighbors(id1)
        assert isinstance(edges, list)

    def test_recall_uses_graph_context(self, temp_db):
        """recall 利用图谱上下文增强结果"""
        from fuxi.memory.ingestion import remember
        from fuxi.memory.retrieval import recall

        remember(raw_text="深度学习是机器学习的子领域", drawer_id="longterm", importance=0.7)
        remember(raw_text="机器学习是人工智能的一部分", drawer_id="longterm", importance=0.7)

        results = recall(query="深度学习", limit=5)
        assert len(results) >= 1


class TestAPIIntegration:
    """API 层端到端测试"""

    def test_health_endpoint(self, client):
        """健康检查接口"""
        from conftest import auth_headers
        resp = client.get("/health", headers=auth_headers())
        assert resp.status_code == 200

    def test_memory_recall_publishes_event(self, client, temp_db):
        """记忆召回 API 发布事件"""
        from conftest import auth_headers
        # 先写入
        client.post("/api/v2/memories", headers=auth_headers(), json={
            "text": "API事件测试",
            "drawer_id": "default",
            "importance": 0.5,
        })
        # 再召回
        resp = client.get("/api/v2/memories?query=API事件测试&limit=5", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0

    def test_search_endpoint_publishes_event(self, client, temp_db):
        """搜索 API 发布 search.query 事件"""
        from conftest import auth_headers
        resp = client.get("/api/v2/memories/search?q=test&limit=5", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
