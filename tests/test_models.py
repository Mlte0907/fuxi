"""测试：数据模型"""
from fuxi.models import AgentView, Drawer, Edge, MemoryItem


class TestModels:
    def test_drawer_creation(self):
        d = Drawer(id="test", name="测试", room_id="main")
        assert d.id == "test"
        assert d.item_count == 0

    def test_memory_item_creation(self):
        item = MemoryItem(
            id="m1", raw_text="测试记忆",
            drawer_id="default", importance=0.8
        )
        assert item.raw_text == "测试记忆"
        assert item.emotion_valence == 0.0
        assert item.archived == 0
        assert item.tags == []

    def test_edge_creation(self):
        e = Edge(id="e1", source_id="m1", target_id="m2", edge_type="related_to")
        assert e.weight == 0.5
        assert e.edge_type == "related_to"

    def test_agent_view(self):
        av = AgentView(id="av1", agent_id="peep", item_id="m1")
        assert av.perspective == ""
