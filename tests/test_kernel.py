"""测试：微内核（WorkingMemory + EventBus + Attention）"""


class TestWorkingMemory:
    def test_push_and_get(self):
        from fuxi.kernel.working_memory import WMItem, WorkingMemory
        wm = WorkingMemory(capacity=5)
        item = WMItem(id="test1", content="Hello World", tokens=3)
        wm.push(item)
        assert wm.get("test1") is not None
        assert wm.get("test1").content == "Hello World"

    def test_capacity_eviction(self):
        from fuxi.kernel.working_memory import WMItem, WorkingMemory
        wm = WorkingMemory(capacity=3)
        for i in range(5):
            wm.push(WMItem(id=f"item_{i}", content=f"Content {i}", tokens=1))
        assert len(wm.slots) <= 3

    def test_emotional_protection(self):
        from fuxi.kernel.working_memory import WMItem, WorkingMemory
        wm = WorkingMemory(capacity=2)
        wm.push(WMItem(id="sad", content="Sad", tokens=1, emotional_valence=-0.8))
        wm.push(WMItem(id="happy", content="Happy", tokens=1, emotional_valence=0.9))
        wm.push(WMItem(id="neutral", content="Neutral", tokens=1))
        # 高情感项目受保护，不容易被驱逐
        assert wm.get("happy") is not None

    def test_focus(self):
        from fuxi.kernel.working_memory import WMItem, WorkingMemory
        wm = WorkingMemory(capacity=5)
        wm.push(WMItem(id="f1", content="Focus item", tokens=2))
        assert wm.focus is not None
        assert wm.focus.id == "f1"

    def test_decay_tick(self):
        from fuxi.kernel.working_memory import WMItem, WorkingMemory
        wm = WorkingMemory(capacity=5)
        # push 时 touch() 会 +0.1 激活，所以初始值设低一点
        wm.push(WMItem(id="decay_test", content="Will decay", tokens=1, activation=0.02))
        wm.decay_tick(dt=10.0)
        # push后: 0.02+0.1=0.12, decay后: 0.12*(1-0.02*10)=0.096 < 0.1 被移除
        assert wm.get("decay_test") is None

    def test_context_string(self):
        from fuxi.kernel.working_memory import WMItem, WorkingMemory
        wm = WorkingMemory(capacity=5)
        wm.push(WMItem(id="ctx1", content="记忆一", tokens=1))
        ctx = wm.context
        assert "记忆一" in ctx

    def test_clear(self):
        from fuxi.kernel.working_memory import WMItem, WorkingMemory
        wm = WorkingMemory(capacity=5)
        wm.push(WMItem(id="clr", content="Clear me", tokens=1))
        wm.clear()
        assert len(wm.slots) == 0

    def test_stats(self):
        from fuxi.kernel.working_memory import WMItem, WorkingMemory
        wm = WorkingMemory(capacity=5)
        wm.push(WMItem(id="stat1", content="Stats test", tokens=2))
        stats = wm.stats
        assert "capacity" in stats
        assert stats["slots_used"] == 1
        assert stats["total_tokens"] == 2

    def test_default_capacity_from_config(self):
        from fuxi.config import config
        from fuxi.kernel.working_memory import WorkingMemory
        wm = WorkingMemory()
        assert wm.capacity == config.wm_capacity


class TestEventBus:
    def test_subscribe_publish(self):
        from fuxi.kernel.event_bus import Event, EventBus
        bus = EventBus()
        results = []
        bus.subscribe("test_event", lambda e: results.append(e.data["msg"]))
        bus.publish(Event(type="test_event", data={"msg": "hello"}))
        assert results == ["hello"]

    def test_multiple_handlers(self):
        from fuxi.kernel.event_bus import Event, EventBus
        bus = EventBus()
        calls = []
        bus.subscribe("multi", lambda e: calls.append(1))
        bus.subscribe("multi", lambda e: calls.append(2))
        bus.publish(Event(type="multi"))
        assert len(calls) == 2

    def test_unsubscribe(self):
        from fuxi.kernel.event_bus import EventBus
        bus = EventBus()
        def handler(e): return None
        bus.subscribe("temp", handler)
        bus.unsubscribe("temp", handler)
        assert len(bus._sync_handlers.get("temp", [])) == 0

    def test_event_log(self):
        from fuxi.kernel.event_bus import Event, EventBus
        bus = EventBus()
        bus.clear()
        for i in range(3):
            bus.publish(Event(type=f"evt_{i}"))
        assert len(bus.recent_events) == 3

    def test_stats(self):
        from fuxi.kernel.event_bus import EventBus
        bus = EventBus()
        bus.clear()
        bus.subscribe("stats_event", lambda e: None)
        stats = bus.stats
        assert stats["total_subscribers"] >= 1
        assert "recent_events" in stats

    def test_singleton(self):
        from fuxi.kernel.event_bus import get_event_bus
        b1 = get_event_bus()
        b2 = get_event_bus()
        assert b1 is b2

    def test_clear(self):
        from fuxi.kernel.event_bus import Event, EventBus
        bus = EventBus()
        bus.subscribe("clear_test", lambda e: None)
        bus.publish(Event(type="clear_test"))
        bus.clear()
        assert len(bus.recent_events) == 0


class TestAttention:
    def test_default_strategy(self):
        from fuxi.kernel.attention import AttentionSystem
        attn = AttentionSystem()
        assert attn.active_strategy is not None

    def test_budget_allocate(self):
        from fuxi.kernel.attention import AttentionSystem
        attn = AttentionSystem()
        attn.allocate(10)
        assert attn.budget >= 0

    def test_evaluate(self):
        from fuxi.kernel.attention import AttentionSystem
        attn = AttentionSystem()
        strategy = attn.evaluate(emotional_valence=0.8, urgency=0.9, novelty=0.5)
        assert strategy is not None

    def test_switch(self):
        from fuxi.kernel.attention import AttentionStrategy, AttentionSystem
        attn = AttentionSystem()
        attn.switch(AttentionStrategy.FOCUS)
        assert attn.active_strategy == AttentionStrategy.FOCUS

    def test_stats(self):
        from fuxi.kernel.attention import AttentionSystem
        attn = AttentionSystem()
        stats = attn.stats
        assert "active_strategy" in stats
        assert "budget" in stats


class TestLifespan:
    def test_start_stop(self):
        from fuxi.kernel.lifespan import Lifespan
        ls = Lifespan()
        ls.start()
        assert ls._running is True
        ls.stop()
        assert ls._running is False

    def test_spawn_background(self):
        from fuxi.kernel.lifespan import Lifespan
        ls = Lifespan()
        ls.start()

        calls = []
        def worker():
            calls.append(1)

        ls.spawn_background(worker, name="test-worker", interval=3600)
        assert len(ls._bg_threads) == 1
        assert ls._bg_threads[0].name == "test-worker"
        ls.stop()

    def test_spawn_background_once(self):
        from fuxi.kernel.lifespan import Lifespan
        ls = Lifespan()
        ls.start()

        calls = []
        def worker():
            calls.append(1)

        ls.spawn_background(worker, name="once-worker", interval=0)
        ls.stop()

    def test_double_start_no_error(self):
        from fuxi.kernel.lifespan import Lifespan
        ls = Lifespan()
        ls.start()
        ls.start()  # should not crash
        ls.stop()

    def test_double_stop_no_error(self):
        from fuxi.kernel.lifespan import Lifespan
        ls = Lifespan()
        ls.stop()  # should not crash
        ls.stop()  # should not crash
