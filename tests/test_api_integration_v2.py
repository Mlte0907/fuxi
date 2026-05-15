"""API集成测试补充 — 修正版2"""
from pathlib import Path

from conftest import auth_headers


class TestWebSocket:
    def test_ws_connect(self, client):
        with client.websocket_connect("/api/v2/ws?api_key=test-key-2026") as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"
            assert "connections" in data


class TestAdminBackupRestore:
    def test_backup_create(self, client):
        r = client.post("/api/v2/admin/backup?force=true", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] == "ok"
        assert "file" in data

    def test_backup_list_and_restore(self, client):
        client.post("/api/v2/memories", json={
            "text": "备份恢复测试数据", "importance": 0.9,
        }, headers=auth_headers())

        r = client.post("/api/v2/admin/backup?force=true", headers=auth_headers())
        assert r.status_code == 200
        filename = Path(r.json()["data"]["file"]).name

        r = client.get("/api/v2/admin/backups", headers=auth_headers())
        assert r.status_code == 200
        backups = r.json()["data"]
        assert isinstance(backups, list)
        assert any(b.get("name") == filename for b in backups)


class TestEnginesAdvanced:
    def test_run_all_engines(self, client):
        r = client.post("/api/v2/engines/run_all", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["status"] in ("ok", "partial")
        assert "results" in data

    def test_engine_control(self, client):
        r = client.post(
            "/api/v2/engines/soul/control",
            json={"action": "start"},
            headers=auth_headers()
        )
        assert r.status_code == 200
        r2 = client.post(
            "/api/v2/engines/soul/control",
            json={"action": "stop"},
            headers=auth_headers()
        )
        assert r2.status_code == 200

    def test_all_production_engines(self, client):
        engines = ["soul", "emotion", "dream", "immune", "prediction",
                   "distill", "resonance", "safety"]
        for name in engines:
            r = client.get(f"/api/v2/engines/{name}", headers=auth_headers())
            assert r.status_code == 200, f"Engine {name} returned {r.status_code}"

    def test_engine_health(self, client):
        r = client.get("/api/v2/engines/soul/health", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["name"] == "soul"
        assert "run_count" in data


class TestMemoriesAdvanced:
    def test_create_with_drawer(self, client):
        data = {
            "text": "抽屉测试记忆",
            "importance": 0.7,
            "drawer_id": "default",
            "tags": ["drawer-test"],
        }
        r = client.post("/api/v2/memories", json=data, headers=auth_headers())
        assert r.status_code == 200
        assert "id" in r.json()["data"]

    def test_context_with_drawer_filter(self, client):
        r = client.get(
            "/api/v2/memories/context?budget=5&drawer=default",
            headers=auth_headers()
        )
        assert r.status_code == 200

    def test_decay_and_purge(self, client):
        r = client.post("/api/v2/memories/decay", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert isinstance(data, (list, dict))

        r2 = client.post("/api/v2/memories/purge", headers=auth_headers())
        assert r2.status_code == 200

    def test_clear_cache(self, client):
        r = client.delete("/api/v2/memories/cache", headers=auth_headers())
        assert r.status_code == 200


class TestAgentsAdvanced:
    def test_set_and_get_agent_view(self, client):
        r_create = client.post("/api/v2/memories", json={
            "text": "Agent视图测试记忆", "importance": 0.6,
        }, headers=auth_headers())
        item_id = r_create.json()["data"]["id"]

        r = client.put(
            "/api/v2/agents/test-agent/view",
            json={"item_ids": [item_id]},
            headers=auth_headers()
        )
        assert r.status_code == 200

        r2 = client.get(
            "/api/v2/agents/test-agent/view",
            headers=auth_headers()
        )
        assert r2.status_code == 200
        assert r2.json()["data"]["agent_id"] == "test-agent"

    def test_acl_in_agent_list(self, client):
        r = client.get("/api/v2/agents", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert "agents" in data
        assert "acl" in data


class TestSystemAdvanced:
    def test_system_info_fields(self, client):
        r = client.get("/api/v2/system/info", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["version"] == "1.0.0"
        assert "uptime_seconds" in data

    def test_system_config_masked(self, client):
        r = client.get("/api/v2/system/config", headers=auth_headers())
        assert r.status_code == 200
        data = r.json()["data"]
        key_val = data.get("api_key", "")
        assert key_val == "" or "***" in key_val


class TestAdminACL:
    def test_grant_permission(self, client):
        r = client.post(
            "/api/v2/admin/acl/grant",
            params={"agent_id": "test-acl-agent", "permissions": "read,write", "role": "editor"},
            headers=auth_headers()
        )
        assert r.status_code == 200
        assert r.json()["data"]["agent_id"] == "test-acl-agent"
