"""测试：存储层"""


class TestMigrations:
    def test_init_creates_tables(self, temp_db):
        import sqlite3

        from fuxi.config import config
        conn = sqlite3.connect(str(config.db_path))
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )]
        assert "items" in tables
        assert "drawers" in tables
        assert "edges" in tables
        assert "unified_acl" in tables
        assert "engine_states" in tables
        assert "agent_views" in tables
        conn.close()

    def test_default_data(self, temp_db):
        import sqlite3

        from fuxi.config import config
        conn = sqlite3.connect(str(config.db_path))
        conn.row_factory = sqlite3.Row
        c = conn.execute("SELECT id, name FROM drawers ORDER BY id")
        drawers = c.fetchall()
        assert len(drawers) == 2
        assert drawers[0]["id"] == "default"
        assert drawers[1]["id"] == "longterm"
        conn.close()


class TestConnectionPool:
    def test_pool_creation(self):
        from fuxi.config import config
        from fuxi.store.connection import get_pool
        pool = get_pool()
        assert pool is not None
        assert pool._pool.maxsize == config.db_pool_max

    def test_execute_query(self, temp_db):
        from fuxi.store.connection import get_pool
        pool = get_pool()
        row = pool.fetchone("SELECT 1 AS val")
        assert row["val"] == 1

    def test_connection_context(self, temp_db):
        from fuxi.store.connection import get_pool
        pool = get_pool()
        with pool.connection() as c:
            c.execute("SELECT 1")


class TestWriteQueue:
    def test_start_stop(self):
        from fuxi.store.write_queue import WriteQueue
        wq = WriteQueue()
        assert wq._thread is None
        wq.start()
        assert wq._thread is not None
        assert wq._thread.is_alive()
        wq.stop()
        assert wq._stopped.is_set()

    def test_enqueue_dequeue(self):
        from fuxi.store.write_queue import WriteQueue
        wq = WriteQueue()
        wq.start()
        wq.enqueue("SELECT 1", ())
        wq.stop()  # stop drains, no error

    def test_double_start_no_error(self):
        from fuxi.store.write_queue import WriteQueue
        wq = WriteQueue()
        wq.start()
        wq.start()  # should not crash
        wq.stop()

    def test_double_stop_no_error(self):
        from fuxi.store.write_queue import WriteQueue
        wq = WriteQueue()
        wq.stop()  # should not crash
        wq.stop()  # should not crash

    def test_singleton(self):
        from fuxi.store.write_queue import get_write_queue
        wq1 = get_write_queue()
        wq2 = get_write_queue()
        assert wq1 is wq2

    def test_stats(self):
        from fuxi.store.write_queue import WriteQueue
        wq = WriteQueue()
        stats = wq.stats
        assert "enqueued" in stats
        assert "flushed" in stats
        assert "failed" in stats
        assert "pending" in stats
