"""伏羲 v1.0 数据库Schema — 增量迁移"""
import logging
import sqlite3
from typing import List, Optional

from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.store.migrations")

Migration = tuple[str, str, str, Optional[str]]  # (version, label, forward_sql, rollback_sql_or_None)

MIGRATIONS: List[Migration] = []

# ── v1: 基础Schema ──

MIGRATIONS.append(("v1", "Initial schema", """
CREATE TABLE IF NOT EXISTS worlds (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rooms (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, world_id TEXT NOT NULL,
    description TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (world_id) REFERENCES worlds(id)
);

CREATE TABLE IF NOT EXISTS drawers (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, room_id TEXT NOT NULL,
    description TEXT DEFAULT '', item_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (room_id) REFERENCES rooms(id)
);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY, raw_text TEXT NOT NULL, facts TEXT DEFAULT '',
    drawer_id TEXT NOT NULL DEFAULT 'default', importance REAL DEFAULT 0.5,
    decay_score REAL DEFAULT 1.0, decay_factor REAL DEFAULT 0.95,
    tags TEXT DEFAULT '[]', confidence REAL DEFAULT 1.0, source TEXT DEFAULT 'direct',
    embedding TEXT, version INTEGER DEFAULT 1,
    created_by TEXT DEFAULT 'system', collaborators TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    archived INTEGER DEFAULT 0, emotion_valence REAL DEFAULT 0.0,
    FOREIGN KEY (drawer_id) REFERENCES drawers(id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    raw_text, facts, tags
);

CREATE TABLE IF NOT EXISTS edges (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
    edge_type TEXT NOT NULL, weight REAL DEFAULT 0.5,
    metadata TEXT DEFAULT '{}', created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (source_id) REFERENCES items(id),
    FOREIGN KEY (target_id) REFERENCES items(id)
);

CREATE TABLE IF NOT EXISTS version_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT NOT NULL,
    raw_text TEXT, facts TEXT, version INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_views (
    agent_id TEXT NOT NULL, item_id TEXT NOT NULL,
    drawer_id TEXT DEFAULT '', perspective TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (agent_id, item_id),
    FOREIGN KEY (item_id) REFERENCES items(id)
);

CREATE TABLE IF NOT EXISTS shared_memories (
    id TEXT PRIMARY KEY, item_id TEXT NOT NULL, from_agent TEXT DEFAULT '',
    to_agent TEXT DEFAULT '', permission TEXT DEFAULT 'read',
    shared_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (item_id) REFERENCES items(id)
);

CREATE TABLE IF NOT EXISTS experience_bank (
    id TEXT PRIMARY KEY, task_type TEXT, input_desc TEXT DEFAULT '',
    input_vec TEXT, reasoning_summary TEXT DEFAULT '',
    conclusion TEXT DEFAULT '', outcome TEXT DEFAULT 'unknown',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
    event_data TEXT DEFAULT '{}', source TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS unified_acl (
    agent_id TEXT PRIMARY KEY, permissions TEXT DEFAULT '[]',
    agent_domains TEXT DEFAULT '[]', role TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS engine_states (
    engine_name TEXT PRIMARY KEY, state_json TEXT DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schema_version (
    version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_items_drawer ON items(drawer_id);
CREATE INDEX IF NOT EXISTS idx_items_created_by ON items(created_by);
CREATE INDEX IF NOT EXISTS idx_items_archived ON items(archived);
CREATE INDEX IF NOT EXISTS idx_items_created_at ON items(created_at);
CREATE INDEX IF NOT EXISTS idx_items_archived_decay_importance ON items(archived, decay_score DESC, importance DESC);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);
CREATE INDEX IF NOT EXISTS idx_experience_task ON experience_bank(task_type);
CREATE INDEX IF NOT EXISTS idx_unified_acl_agent ON unified_acl(agent_id);
CREATE INDEX IF NOT EXISTS idx_engine_states_name ON engine_states(engine_name);
CREATE INDEX IF NOT EXISTS idx_agent_views_agent ON agent_views(agent_id);
CREATE INDEX IF NOT EXISTS idx_agent_views_item ON agent_views(item_id);
""", None))

# ── v2: FTS5 触发器 + agent_views perspective ──

MIGRATIONS.append(("v2", "FTS5 triggers (insert/delete/update/archive)", """
CREATE TRIGGER IF NOT EXISTS items_fts_insert AFTER INSERT ON items WHEN new.archived = 0 BEGIN
    INSERT INTO items_fts (rowid, raw_text, facts, tags) VALUES (new.rowid, new.raw_text, new.facts, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS items_fts_delete AFTER DELETE ON items BEGIN
    DELETE FROM items_fts WHERE rowid = old.rowid;
END;
CREATE TRIGGER IF NOT EXISTS items_fts_update AFTER UPDATE OF raw_text, facts, tags ON items WHEN new.archived = 0 BEGIN
    UPDATE items_fts SET raw_text=new.raw_text, facts=new.facts, tags=new.tags WHERE rowid = new.rowid;
END;
CREATE TRIGGER IF NOT EXISTS items_fts_archive AFTER UPDATE OF archived ON items WHEN new.archived = 1 BEGIN
    DELETE FROM items_fts WHERE rowid = new.rowid;
END;
""", """
DROP TRIGGER IF EXISTS items_fts_insert;
DROP TRIGGER IF EXISTS items_fts_delete;
DROP TRIGGER IF EXISTS items_fts_update;
DROP TRIGGER IF EXISTS items_fts_archive;
"""))


MIGRATIONS.append(("v3", "Task tracking", """
CREATE TABLE IF NOT EXISTS task_tracking (
    task_id TEXT PRIMARY KEY,
    parent_id TEXT,
    title TEXT NOT NULL DEFAULT '',
    assignee TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','RUNNING','DONE','FAILED','BLOCKED')),
    progress REAL NOT NULL DEFAULT 0.0 CHECK(progress >= 0.0 AND progress <= 1.0),
    result_summary TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_task_parent ON task_tracking(parent_id);
CREATE INDEX IF NOT EXISTS idx_task_assignee ON task_tracking(assignee);
CREATE INDEX IF NOT EXISTS idx_task_status ON task_tracking(status);
""", """
DROP TABLE IF EXISTS task_tracking;
"""))

MIGRATIONS.append(("v4", "Tool registry", """
CREATE TABLE IF NOT EXISTS tool_registry (
    tool_id TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    backend TEXT NOT NULL DEFAULT 'local' CHECK(backend IN ('local','docker','api')),
    need_confirmation INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    config_json TEXT DEFAULT '{}',
    last_used TEXT,
    use_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO tool_registry (tool_id, tool_name, description, backend, need_confirmation) VALUES
    ('web_search', 'Web Search', 'Search the web for current information', 'api', 0),
    ('fuxi_memory_write', 'FuXi Memory Write', 'Write a memory into the FuXi system', 'local', 0),
    ('fuxi_memory_search', 'FuXi Memory Search', 'Search memories in the FuXi system', 'local', 0),
    ('code_execute', 'Code Execute', 'Execute code in a Docker sandbox', 'docker', 1);
""", """
DROP TABLE IF EXISTS tool_registry;
"""))

MIGRATIONS.append(("v5", "Cron scheduler + user profile", """
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    task_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    description TEXT DEFAULT '',
    cron_expression TEXT NOT NULL,
    agent_id TEXT NOT NULL DEFAULT '',
    instruction TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run TEXT,
    next_run TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_scheduled_enabled ON scheduled_tasks(enabled);
CREATE INDEX IF NOT EXISTS idx_scheduled_next ON scheduled_tasks(next_run);

CREATE TABLE IF NOT EXISTS user_profile (
    profile_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    preferences TEXT DEFAULT '{}',
    habits TEXT DEFAULT '[]',
    taboos TEXT DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO user_profile (profile_id, user_id, preferences) VALUES
    ('default', 'default', '{"reply_style":"concise","preferred_language":"zh","notification_time":"09:00"}');
""", """
DROP TABLE IF EXISTS scheduled_tasks;
DROP TABLE IF EXISTS user_profile;
"""))

MIGRATIONS.append(("v6", "Model routing rules", """
CREATE TABLE IF NOT EXISTS model_routing (
    rule_id TEXT PRIMARY KEY,
    rule_name TEXT NOT NULL DEFAULT '',
    task_types TEXT NOT NULL DEFAULT '[]',
    agent_ids TEXT NOT NULL DEFAULT '[]',
    model_name TEXT NOT NULL DEFAULT 'minimax/MiniMax-M2.7',
    priority INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
-- 默认路由规则：全部使用 MiniMax（当前唯一可用模型）
INSERT OR IGNORE INTO model_routing (rule_id, rule_name, task_types, agent_ids, model_name, priority) VALUES
    ('default', 'Default Route', '["*"]', '["*"]', 'minimax/MiniMax-M2.7', 0),
    ('chat', 'Chat Route', '["chat","conversation","greeting","casual"]', '["pipi"]', 'minimax/MiniMax-M2.7', 10),
    ('research', 'Research Route', '["research","search","investigation","fact_check"]', '["zhuque"]', 'minimax/MiniMax-M2.7', 10),
    ('planning', 'Planning Route', '["planning","reasoning","analysis","coding","debugging"]', '["qinglong"]', 'minimax/MiniMax-M2.7', 10),
    ('summary', 'Summary Route', '["summary","summarization","report","documentation"]', '["xuanwu"]', 'minimax/MiniMax-M2.7', 10),
    ('audit', 'Audit Route', '["audit","compliance","security","review"]', '["yinsi"]', 'minimax/MiniMax-M2.7', 10);
""", """
DROP TABLE IF EXISTS model_routing;
"""))

MIGRATIONS.append(("v7", "Experience bank skill-gen fields", """
ALTER TABLE experience_bank ADD COLUMN agent_id TEXT DEFAULT '';
ALTER TABLE experience_bank ADD COLUMN skill_name TEXT DEFAULT '';
ALTER TABLE experience_bank ADD COLUMN trigger_keywords TEXT DEFAULT '[]';
ALTER TABLE experience_bank ADD COLUMN quality_score REAL DEFAULT 0.5;
ALTER TABLE experience_bank ADD COLUMN review_status TEXT DEFAULT 'pending';
ALTER TABLE experience_bank ADD COLUMN reviewed_by TEXT DEFAULT '';
ALTER TABLE experience_bank ADD COLUMN review_note TEXT DEFAULT '';
ALTER TABLE experience_bank ADD COLUMN skill_file_path TEXT DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_exp_review ON experience_bank(review_status);
CREATE INDEX IF NOT EXISTS idx_exp_agent ON experience_bank(agent_id);
""", None))

MIGRATIONS.append(("v8", "PostgreSQL + pgvector preparation", """
-- embedding 列已在 v1 中定义，此处仅添加 pg_migration_status 表
CREATE TABLE IF NOT EXISTS pg_migration_status (
    id INTEGER PRIMARY KEY,
    pg_host TEXT,
    pg_port INTEGER DEFAULT 5432,
    pg_database TEXT,
    pg_migrated_at TIMESTAMP,
    pg_row_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending'
);
""", None))


def _current_version(pool) -> Optional[str]:
    """读取当前已应用的版本。"""
    try:
        row = pool.fetchone("SELECT version FROM schema_version ORDER BY rowid DESC LIMIT 1")
        return row["version"] if row else None
    except Exception:
        # schema_version 表可能还不存在（数据库为空）
        return None


def _record_version(conn: sqlite3.Connection, version: str):
    conn.execute("INSERT OR IGNORE INTO schema_version (version) VALUES (?)", (version,))


def _execute_migration_idempotent(conn: sqlite3.Connection, forward_sql: str, version: str):
    """当 executescript 因 duplicate column 失败时，逐条重试跳过冲突列。"""
    statements = []
    buf = []
    for line in forward_sql.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";") and not stripped.upper().startswith("CREATE TRIGGER"):
            statements.append("\n".join(buf))
            buf = []
        elif stripped.upper().endswith("END;") or stripped == "END;":
            statements.append("\n".join(buf))
            buf = []
    if buf:
        statements.append("\n".join(buf))

    for stmt in statements:
        s = stmt.strip()
        if not s:
            continue
        try:
            conn.execute(s)
        except sqlite3.OperationalError as e:
            err = str(e).lower()
            if "duplicate column" in err:
                logger.info(f"  Skip (idempotent): column already exists")
            else:
                logger.warning(f"  Failed statement in {version}: {s[:80]} → {e}")
                raise


def run_migrations() -> str:
    """按序应用所有未执行的迁移。返回最终版本号。"""
    pool = get_pool()
    current = _current_version(pool)

    def _already_done(ver: str) -> bool:
        if current is None:
            # 新的空数据库：直接跳过到最新
            return False
        versions = [m[0] for m in MIGRATIONS]
        if current not in versions:
            # 旧数据库（schema_version 表不存在或无记录）但已有表结构
            # 检查 items 表是否存在来判断是否为已有数据的旧库
            row = pool.fetchone("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
            if row:
                logger.info(f"Detected pre-migration database, marking {MIGRATIONS[0][0]} as applied")
                with pool.connection() as c:
                    # 确保 schema_version 表存在
                    c.execute("CREATE TABLE IF NOT EXISTS schema_version (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))")
                    _record_version(c, MIGRATIONS[0][0])
                return True  # 已迁移过 v1
            return False  # 全新数据库
        idx_current = versions.index(current)
        idx_target = versions.index(ver)
        return idx_target <= idx_current

    with pool.connection() as conn:
        for version, label, forward_sql, _rollback in MIGRATIONS:
            if _already_done(version):
                continue
            logger.info(f"Applying migration {version}: {label}")
            try:
                conn.executescript(forward_sql)
            except sqlite3.OperationalError as e:
                errmsg = str(e).lower()
                if "duplicate column" in errmsg:
                    logger.info(f"  Delegating {version} to idempotent retry")
                    _execute_migration_idempotent(conn, forward_sql, version)
                else:
                    raise
            _record_version(conn, version)
            current = version

    # Post-migration: ensure agent_views has perspective column (idempotent)
    try:
        pool.execute("SELECT perspective FROM agent_views LIMIT 1")
    except sqlite3.OperationalError:
        with pool.connection() as conn:
            conn.execute("ALTER TABLE agent_views ADD COLUMN perspective TEXT DEFAULT ''")
            logger.info("Migrated: added perspective column to agent_views")

    return current or "none"


def init_db():
    """初始化数据库（幂等）。首次调用时自动运行所有待执行的迁移。"""
    run_migrations()
    _ensure_defaults()


def _ensure_defaults():
    pool = get_pool()
    pool.execute(
        "INSERT OR IGNORE INTO worlds (id, name, description) VALUES (?, ?, ?)",
        ("jinlange", "瑾岚阁", "瑾岚阁多Agent协作世界")
    )
    pool.execute(
        "INSERT OR IGNORE INTO rooms (id, name, world_id, description) VALUES (?, ?, ?, ?)",
        ("main", "主厅", "jinlange", "主工作区")
    )
    pool.execute(
        "INSERT OR IGNORE INTO drawers (id, name, room_id, description) VALUES (?, ?, ?, ?)",
        ("default", "默认", "main", "默认记忆抽屉")
    )
    pool.execute(
        "INSERT OR IGNORE INTO drawers (id, name, room_id, description) VALUES (?, ?, ?, ?)",
        ("longterm", "长期", "main", "长期记忆抽屉")
    )


def get_schema_version() -> str:
    """返回当前数据库的 schema 版本。"""
    try:
        pool = get_pool()
        row = pool.fetchone("SELECT version FROM schema_version ORDER BY rowid DESC LIMIT 1")
        return row["version"] if row else "none"
    except Exception:
        return "none"


def get_available_migrations() -> List[dict]:
    """列出所有已定义的迁移版本。"""
    return [
        {"version": v, "label": lbl, "has_rollback": r is not None}
        for v, lbl, _, r in MIGRATIONS
    ]


