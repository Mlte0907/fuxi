"""Tests for ACP protocol — internal client, server connection, relay"""


class TestInternalACPClient:
    def test_register_unregister(self):
        from fuxi.acp.client import InternalACPClient
        client = InternalACPClient("test-client")
        assert client._registered is False
        client.register()
        assert client._registered is True
        from fuxi.acp.server import connections
        assert "test-client" in connections
        client.unregister()
        assert client._registered is False
        assert "test-client" not in connections

    def test_get_acp_client_singleton(self):
        from fuxi.acp.client import get_acp_client, InternalACPClient
        import fuxi.acp.client as client_mod
        client_mod._internal_client = None

        c1 = get_acp_client()
        c2 = get_acp_client()
        assert c1 is c2
        assert isinstance(c1, InternalACPClient)

    def test_double_register_no_error(self):
        from fuxi.acp.client import InternalACPClient
        client = InternalACPClient("test-double")
        client.register()
        client.register()  # should not crash
        client.unregister()

    def test_unregister_without_register(self):
        from fuxi.acp.client import InternalACPClient
        client = InternalACPClient("test-unreg")
        client.unregister()  # should not crash


class TestACPConnection:
    def test_send_with_none_websocket(self):
        """send() with None websocket should not crash"""
        import asyncio
        from fuxi.acp.server import ACPConnection

        async def run():
            conn = ACPConnection(None, "test-none")
            await conn.send("ping", {"seq": 1})
            return True

        assert asyncio.run(run())

    def test_connection_attributes(self):
        from datetime import datetime
        from fuxi.acp.server import ACPConnection

        conn = ACPConnection(None, "test-attr")
        assert conn.client_id == "test-attr"
        assert conn.session_id is None
        assert conn.authenticated is False
        assert conn.project_scope is None
        assert isinstance(conn.last_activity, datetime)

    def test_connection_session_init(self):
        from fuxi.acp.server import ACPConnection
        conn = ACPConnection(None, "test-sess")
        conn.session_id = "my-session"
        conn.project_scope = "my-project"
        conn.authenticated = True
        assert conn.session_id == "my-session"
        assert conn.project_scope == "my-project"
        assert conn.authenticated is True


class TestACPMessageHandling:
    def test_ping_pong(self):
        import asyncio
        from fuxi.acp.server import ACPConnection, handle_acp_message

        async def run():
            conn = ACPConnection(None, "test-ping")
            await handle_acp_message(conn, {"type": "ping", "data": {"seq": 42}})
            return True

        assert asyncio.run(run())

    def test_unknown_message_type(self):
        import asyncio
        from fuxi.acp.server import ACPConnection, handle_acp_message

        async def run():
            conn = ACPConnection(None, "test-unknown")
            await handle_acp_message(conn, {"type": "unknown_type", "data": {}})
            return True

        assert asyncio.run(run())

    def test_memory_query(self, temp_db):
        import asyncio
        from fuxi.acp.server import ACPConnection, handle_acp_message

        async def run():
            conn = ACPConnection(None, "test-memquery")
            conn.session_id = "test"
            conn.project_scope = "default"
            await handle_acp_message(conn, {
                "type": "memory.query",
                "data": {"query": "test", "limit": 3},
            })
            return True

        assert asyncio.run(run())

    def test_memory_store(self, temp_db):
        import asyncio
        from fuxi.acp.server import ACPConnection, handle_acp_message

        async def run():
            conn = ACPConnection(None, "test-memstore")
            conn.session_id = "test"
            conn.project_scope = "default"
            await handle_acp_message(conn, {
                "type": "memory.store",
                "data": {"text": "ACP store test memory", "drawer": "default"},
            })
            return True

        assert asyncio.run(run())

    def test_context_inject(self, temp_db):
        import asyncio
        from fuxi.acp.server import ACPConnection, handle_acp_message

        async def run():
            conn = ACPConnection(None, "test-ctx")
            conn.session_id = "test"
            conn.project_scope = "default"
            await handle_acp_message(conn, {
                "type": "context.inject",
                "data": {"context_type": "recent", "max_chars": 100},
            })
            return True

        assert asyncio.run(run())

    def test_skill_exec_not_found(self, temp_db):
        import asyncio
        from fuxi.acp.server import ACPConnection, handle_acp_message

        async def run():
            conn = ACPConnection(None, "test-skill")
            conn.session_id = "test"
            await handle_acp_message(conn, {
                "type": "skill.exec",
                "data": {"skill_name": "nonexistent_skill", "params": {}},
            })
            return True

        assert asyncio.run(run())


class TestACPRouter:
    def _headers(self):
        return {"X-API-Key": "test-key-2026"}

    def test_acp_status(self, client):
        resp = client.get("/acp/status", headers=self._headers())
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert data.get("enabled") is True

    def test_acp_clients(self, client):
        resp = client.get("/acp/clients", headers=self._headers())
        assert resp.status_code == 200
        data = resp.json().get("data", {})
        assert "clients" in data
        assert isinstance(data["count"], int)
