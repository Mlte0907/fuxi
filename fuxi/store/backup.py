"""伏羲 v1.0 — 自动备份"""
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path

from fuxi.config import config

logger = logging.getLogger("fuxi.store.backup")

# 备份冷却：距离上次成功备份的最短间隔（秒）
BACKUP_COOLDOWN_SEC = 600  # 10 分钟
_last_backup_ts: float = 0.0


def backup_db(force: bool = False) -> dict:
    """备份数据库到备份目录（带冷却保护）"""
    global _last_backup_ts

    import sqlite3
    src = config.db_path
    if not src.exists():
        logger.warning("DB not found, skip backup")
        return {"status": "skip", "reason": "db_not_found"}

    # 冷却检查 (force=True 可绕过)
    elapsed = time.time() - _last_backup_ts
    if not force and elapsed < BACKUP_COOLDOWN_SEC:
        logger.info(f"Backup cooldown ({BACKUP_COOLDOWN_SEC}s), last backup {elapsed:.0f}s ago, skip")
        return {"status": "skip", "reason": "cooldown"}

    config.backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = config.backup_dir / f"fuxi_backup_{ts}.db"

    try:
        # WAL checkpoint: 确保备份前所有数据已提交到主DB
        try:
            conn = sqlite3.connect(str(src), timeout=10)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
        except Exception as e:
            logger.warning(f"WAL checkpoint before backup failed: {e}")

        shutil.copy2(src, dst)
        size = dst.stat().st_size
        logger.info(f"Backup: {dst.name} ({size} bytes)")

        _last_backup_ts = time.time()

        # 清理旧备份
        _cleanup_old()

        return {"status": "ok", "file": str(dst), "size_bytes": size}
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return {"status": "error", "error": str(e)}


def restore_db(backup_file: str) -> dict:
    """从备份恢复数据库"""
    src = Path(backup_file)
    if not src.exists():
        return {"status": "error", "error": "backup_not_found"}

    try:
        # 先备份当前
        if config.db_path.exists():
            backup_db()

        # 校验备份文件完整性
        import sqlite3
        conn = sqlite3.connect(str(src))

        # 1. 基础完整性检查
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            conn.close()
            return {"status": "error", "error": f"Backup integrity check failed: {integrity}"}

        # 2. Schema 版本校验
        schema_version = None
        try:
            ver_row = conn.execute("SELECT version FROM schema_version ORDER BY rowid DESC LIMIT 1").fetchone()
            schema_version = ver_row[0] if ver_row else None
        except Exception:
            pass

        # 3. 必需表检查
        required_tables = ["items", "drawers", "edges", "schema_version"]
        for table in required_tables:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if not row:
                conn.close()
                return {"status": "error", "error": f"Missing required table: {table}"}

        # 4. 外键完整性检查
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            conn.close()
            return {"status": "error", "error": f"Foreign key violations: {len(fk_violations)} rows"}

        # 5. 数据统计
        cur = conn.execute("SELECT COUNT(*) FROM items")
        item_count = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(*) FROM drawers")
        drawer_count = cur.fetchone()[0]
        conn.close()

        # 恢复
        shutil.copy2(src, config.db_path)
        # 刷新连接池：关闭所有旧连接，下次获取时重新创建
        try:
            from fuxi.store.connection import _pool, get_pool
            if _pool is not None:
                while True:
                    try:
                        conn = _pool._pool.get_nowait()
                        conn.close()
                    except Exception:
                        break
                with _pool._lock:
                    _pool._created = 0
                logger.info("Connection pool invalidated after restore")
            else:
                # 池尚未初始化，强制初始化以绑定新 DB
                get_pool()
                logger.info("Connection pool initialized after restore")
        except Exception as e:
            logger.warning(f"Connection pool invalidate failed: {e}")
        logger.info(f"Restored from {src.name}: {item_count} items, {drawer_count} drawers, schema={schema_version}")

        return {
            "status": "ok",
            "items": item_count,
            "drawers": drawer_count,
            "schema_version": schema_version,
            "file": str(src)
        }
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        return {"status": "error", "error": str(e)}


def list_backups() -> list:
    config.backup_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(config.backup_dir.glob("fuxi_backup_*.db"), reverse=True)
    return [{
        "name": f.name,
        "size_bytes": f.stat().st_size,
        "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
    } for f in files]


def _cleanup_old():
    # 清理 .db 备份文件（保持数量上限）
    files = sorted(config.backup_dir.glob("fuxi_backup_*.db"))
    while len(files) > config.backup_max_count:
        old = files.pop(0)
        old.unlink()
        logger.debug(f"Removed old backup: {old.name}")
    # 清理遗留的非 .db 备份文件（legacy_workspace_backup_*.tar.gz 等），超过 24h 即删除
    for legacy in sorted(config.backup_dir.glob("legacy_*")):
        age_sec = time.time() - legacy.stat().st_mtime
        if age_sec > 86400:
            legacy.unlink()
            logger.info(f"Removed legacy backup: {legacy.name} (age={age_sec/3600:.1f}h)")
