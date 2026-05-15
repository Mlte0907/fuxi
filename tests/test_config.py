"""测试：配置系统"""


class TestConfig:
    def test_defaults(self):
        from fuxi.config import Config
        c = Config()
        assert c.port == 19528
        assert c.host == "0.0.0.0"
        assert c.wm_capacity == 7
        assert c.embed_dim == 1024
        assert c.decay_base == 0.95

    def test_env_override(self, monkeypatch):
        from fuxi.config import config
        monkeypatch.setattr(config, 'port', 9999)
        monkeypatch.setattr(config, 'wm_capacity', 10)
        assert config.port == 9999
        assert config.wm_capacity == 10

    def test_edge_types(self):
        from fuxi.config import Config
        c = Config()
        assert "causes" in c.edge_types
        assert "related_to" in c.edge_types
        assert len(c.edge_types) == 9

    def test_confidence_sources(self):
        from fuxi.config import Config
        c = Config()
        assert c.confidence_sources["direct"] == 1.0
        assert c.confidence_sources["hearsay"] == 0.3
