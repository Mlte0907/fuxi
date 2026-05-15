"""API集成测试 — 覆盖路由层（之前0%覆盖率）"""
from conftest import auth_headers

# ── Health (no auth) ──

class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "ok"

    def test_health_deep(self, client):
        r = client.get("/health/deep")
        assert r.status_code == 200
        status = r.json()["data"]["status"]
        assert status in ("ok", "degraded")  # degraded if embedding api not available
        assert "database" in r.json()["data"]["checks"]


# ── Memories CRUD ──

class TestMemories:
    def test_create_and_get(self, client):
        data = {"text": "API集成测试记忆", "importance": 0.8, "tags": ["test"]}
        r = client.post("/api/v2/memories", json=data, headers=auth_headers())
        assert r.status_code == 200
        item_id = r.json()["data"]["id"]
        assert item_id

        r2 = client.get(f"/api/v2/memories/{item_id}", headers=auth_headers())
        assert r2.status_code == 200
        assert r2.json()["data"]["raw_text"] == "API集成测试记忆"

    def test_list_memories(self, client):
        r = client.get("/api/v2/memories?limit=5", headers=auth_headers())
        assert r.status_code == 200
        items = r.json()["data"]
        assert isinstance(items, list)

    def test_delete_memory(self, client):
        data = {"text": "待删除记忆", "importance": 0.3, "tags": ["test"]}
        r = client.post("/api/v2/memories", json=data, headers=auth_headers())
        item_id = r.json()["data"]["id"]

        r2 = client.delete(f"/api/v2/memories/{item_id}", headers=auth_headers())
        assert r2.status_code == 200
        assert r2.json()["data"]["status"] == "deleted"

    def test_auth_required(self, client):
        r = client.get("/api/v2/memories")
        assert r.status_code == 401

    def test_invalid_empty_text(self, client):
        data = {"text": "  ", "importance": 0.5}
        r = client.post("/api/v2/memories", json=data, headers=auth_headers())
        assert r.status_code in (400, 422)


# ── Search ──

class TestSearch:
    def test_search_basic(self, client):
        client.post("/api/v2/memories", json={
            "text": "搜索测试：瑾岚阁Agent体系设计", "importance": 0.7, "tags": ["search-test"]
        }, headers=auth_headers())

        r = client.get("/api/v2/memories/search?q=瑾岚阁Agent&limit=5", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "results" in data
        assert data["total"] >= 1

    def test_search_no_results(self, client):
        r = client.get("/api/v2/memories/search?q=xyznonexistent123&limit=5", headers=auth_headers())
        assert r.status_code == 200
        assert r.json()["data"]["total"] == 0


# ── Context ──

class TestContext:
    def test_context_basic(self, client):
        client.post("/api/v2/memories", json={
            "text": "上下文测试记忆A：用户偏好配色方案为暗色系", "importance": 0.6, "tags": ["ctx-test"]
        }, headers=auth_headers())

        r = client.get("/api/v2/memories/context?budget=10", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert isinstance(data, (list, dict))  # returns list or {items: [...]}


# ── Engines ──

class TestEngines:
    def test_list_engines(self, client):
        r = client.get("/api/v2/engines", headers=auth_headers())
        assert r.status_code == 200
        engines = r.json()["data"]
        assert len(engines) >= 34

    def test_get_engine(self, client):
        r = client.get("/api/v2/engines/soul", headers=auth_headers())
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "soul"

    def test_run_engine(self, client):
        r = client.post("/api/v2/engines/emotion/run", headers=auth_headers())
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "ok"

    def test_engine_not_found(self, client):
        r = client.get("/api/v2/engines/nonexistent", headers=auth_headers())
        assert r.status_code == 404


# ── System ──

class TestSystem:
    def test_system_info(self, client):
        r = client.get("/api/v2/system/info", headers=auth_headers())
        assert r.status_code == 200
        assert r.json()["data"]["version"] == "1.0.0"

    def test_system_config(self, client):
        r = client.get("/api/v2/system/config", headers=auth_headers())
        assert r.status_code == 200
        assert "api_key" in r.json()["data"]  # masked value: "xxx***"


# ── Agents ──

class TestAgents:
    def test_list_agents(self, client):
        r = client.get("/api/v2/agents", headers=auth_headers())
        assert r.status_code == 200

    def test_get_agent(self, client):
        # register agent in unified_acl to ensure 200 path is covered
        from fuxi.store.connection import get_pool
        pool = get_pool()
        pool.execute(
            "INSERT OR REPLACE INTO unified_acl (agent_id, permissions, agent_domains, role) VALUES (?,?,?,?)",
            ("test-agent", '[]', '[]', "viewer")
        )
        r = client.get("/api/v2/agents/test-agent", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["agent_id"] == "test-agent"
        assert "permissions" in data
        assert "agent_domains" in data

    def test_get_agent_not_found(self, client):
        r = client.get("/api/v2/agents/nonexistent", headers=auth_headers())
        assert r.status_code == 404

    def test_set_agent_view_no_items(self, client):
        r = client.put("/api/v2/agents/test-agent/view", json={"item_ids": []},
                       headers=auth_headers())
        assert r.status_code == 400
        assert "item_id" in r.json()["detail"].lower()


# ── Admin ──

class TestAdmin:
    def test_admin_stats(self, client):
        r = client.get("/api/v2/admin/stats", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert isinstance(data, (list, dict))  # returns list or {items: [...]}

    def test_admin_backups_list(self, client):
        r = client.get("/api/v2/admin/backups", headers=auth_headers())
        assert r.status_code == 200
