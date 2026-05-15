"""测试：统一权限系统"""


class TestUnifiedACL:
    def test_grant_and_check(self, temp_db):
        from fuxi.auth.acl import Permission, get_acl
        acl = get_acl()
        acl.clear_cache()
        acl.grant("agent_1", ["read", "write"])
        assert acl.check("agent_1", Permission.READ) is True
        assert acl.check("agent_1", Permission.WRITE) is True
        assert acl.check("agent_1", Permission.DELETE) is False

    def test_unknown_agent(self, temp_db):
        from fuxi.auth.acl import Permission, get_acl
        acl = get_acl()
        acl.clear_cache()
        assert acl.check("nonexistent_agent", Permission.READ) is False

    def test_role_based_permissions(self, temp_db):
        from fuxi.auth.acl import Permission, get_acl
        acl = get_acl()
        acl.clear_cache()
        acl.grant("admin_agent", [], role="admin")
        assert acl.check("admin_agent", Permission.ADMIN) is True
        assert acl.check("admin_agent", Permission.ENGINE_CONTROL) is True

    def test_viewer_role(self, temp_db):
        from fuxi.auth.acl import Permission, get_acl
        acl = get_acl()
        acl.clear_cache()
        acl.grant("viewer_agent", [], role="viewer")
        assert acl.check("viewer_agent", Permission.READ) is True
        assert acl.check("viewer_agent", Permission.WRITE) is False

    def test_revoke(self, temp_db):
        from fuxi.auth.acl import Permission, get_acl
        acl = get_acl()
        acl.clear_cache()
        acl.grant("temp_agent", ["read"])
        assert acl.check("temp_agent", Permission.READ) is True
        acl.revoke("temp_agent")
        assert acl.check("temp_agent", Permission.READ) is False

    def test_list_agents(self, temp_db):
        from fuxi.auth.acl import get_acl
        acl = get_acl()
        acl.clear_cache()
        acl.grant("agent_a", ["read"], role="peep")
        acl.grant("agent_b", ["read", "write"], role="editor")
        agents = acl.list_agents()
        assert len(agents) >= 2
        ids = [a["agent_id"] for a in agents]
        assert "agent_a" in ids
        assert "agent_b" in ids

    def test_cache_clear(self, temp_db):
        from fuxi.auth.acl import Permission, get_acl
        acl = get_acl()
        acl.clear_cache()
        acl.grant("cache_test", ["read"])
        acl.check("cache_test", Permission.READ)  # populates cache
        acl.clear_cache()
        assert acl.check("cache_test", Permission.READ) is True  # still works

    def test_permission_enum(self):
        from fuxi.auth.acl import Permission
        assert Permission.READ == "read"
        assert Permission.ADMIN == "admin"
        assert len(list(Permission)) == 6

    def test_get_acl_singleton(self, temp_db):
        from fuxi.auth.acl import get_acl
        a1 = get_acl()
        a2 = get_acl()
        assert a1 is a2
