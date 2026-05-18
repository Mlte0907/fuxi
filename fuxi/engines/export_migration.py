"""伏羲 v1.0 — ExportMigrationEngine 导出迁移引擎"""
import json
import logging
from datetime import datetime
from pathlib import Path

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.export_migration")


@register_engine("export_migration", experimental=True)
class ExportMigrationEngine(CognitiveEngine):
    """导出迁移引擎 — 支持 JSON / Markdown / Obsidian 格式导出

    支持导出格式:
    - JSON: 结构化完整导出，包含所有元数据
    - Markdown: 单文件或多文件 Markdown，适合静态博客
    - Obsidian: Markdown + YAML frontmatter，兼容 Obsidian vault
    """
    name = "export_migration"
    priority = 5
    interval = 3600  # 每小时检查一次导出队列
    experimental = True

    EXPORT_FORMATS = ["json", "markdown", "obsidian"]

    def run(self) -> dict:
        pool = get_pool()
        pending = self._load_pending_exports(pool)
        if not pending:
            return {"status": "idle", "timestamp": datetime.now().isoformat()}

        results = []
        for job in pending:
            result = self._process_export(job, pool)
            results.append(result)

        return {
            "status": "completed",
            "processed": len(results),
            "succeeded": sum(1 for r in results if r["status"] == "ok"),
            "failed": sum(1 for r in results if r["status"] == "error"),
            "details": results,
            "timestamp": datetime.now().isoformat(),
        }

    def _load_pending_exports(self, pool) -> list[dict]:
        rows = pool.fetchall(
            "SELECT job_id, format, filter_spec, output_path FROM export_jobs "
            "WHERE status='pending' ORDER BY created_at ASC LIMIT 20"
        )
        return [dict(r) for r in rows]

    def _process_export(self, job: dict, pool) -> dict:
        """处理单个导出任务"""
        job_id = job["job_id"]
        fmt = job["format"]
        output_path = job["output_path"]

        try:
            items = self._load_items(pool, job.get("filter_spec"))
            if fmt == "json":
                content = self._export_json(items)
            elif fmt == "markdown":
                content = self._export_markdown(items)
            elif fmt == "obsidian":
                content = self._export_obsidian(items)
            else:
                return {"job_id": job_id, "status": "error", "error": f"Unknown format: {fmt}"}

            self._write_output(output_path, content)
            self._mark_completed(pool, job_id)
            logger.info(f"[export_migration] exported {len(items)} items to {output_path}")
            return {"job_id": job_id, "status": "ok", "item_count": len(items), "path": output_path}

        except Exception as e:
            self._mark_failed(pool, job_id, str(e))
            logger.error(f"[export_migration] job {job_id} failed: {e}")
            return {"job_id": job_id, "status": "error", "error": str(e)}

    def _load_items(self, pool, filter_spec: str | None) -> list[dict]:
        """根据 filter_spec 加载条目"""
        sql = "SELECT id, content, metadata, importance, tags, created_at, updated_at FROM items WHERE archived=0"
        params = []
        if filter_spec:
            try:
                spec = json.loads(filter_spec)
                if "min_importance" in spec:
                    sql += " AND importance >= ?"
                    params.append(spec["min_importance"])
                if "tags" in spec:
                    tag_list = spec["tags"]
                    placeholders = ",".join("?" * len(tag_list))
                    sql += f" AND tags IN ({placeholders})"
                    params.extend(tag_list)
            except json.JSONDecodeError:
                pass

        sql += " ORDER BY created_at DESC LIMIT 5000"
        rows = pool.fetchall(sql, tuple(params))
        return [dict(r) for r in rows]

    def _export_json(self, items: list[dict]) -> str:
        """导出为 JSON 格式"""
        export = {
            "exported_at": datetime.now().isoformat(),
            "item_count": len(items),
            "items": items,
        }
        return json.dumps(export, ensure_ascii=False, indent=2)

    def _export_markdown(self, items: list[dict]) -> str:
        """导出为 Markdown 格式（单文件）"""
        lines = [
            f"# 伏羲记忆导出",
            f"",
            f"导出时间: {datetime.now().isoformat()}",
            f"条目数量: {len(items)}",
            f"",
        ]
        for i, item in enumerate(items, 1):
            lines.append(f"## {i}. {self._extract_title(item['content'])}")
            lines.append(f"")
            lines.append(f"**ID**: {item['id']}  **重要性**: {item.get('importance', 0)}")
            lines.append(f"")
            lines.append(self._content_to_markdown(item["content"]))
            lines.append("")
            lines.append(f"---")
            lines.append("")

        return "\n".join(lines)

    def _export_obsidian(self, items: list[dict]) -> str:
        """导出为 Obsidian 兼容格式（多文件）"""
        files = {}
        for item in items:
            title = self._extract_title(item["content"])
            frontmatter = {
                "id": item["id"],
                "created": item.get("created_at"),
                "updated": item.get("updated_at"),
                "importance": item.get("importance", 0),
                "tags": item.get("tags", []),
            }
            content = [
                "---",
                json.dumps(frontmatter, ensure_ascii=False),
                "---",
                "",
                f"# {title}",
                "",
                self._content_to_markdown(item["content"]),
            ]
            # 使用 ID 作为文件名避免冲突
            filename = f"{item['id']}_{title[:50].replace('/', '_').replace(' ', '_')}.md"
            files[filename] = "\n".join(content)

        # 返回打包的多文件内容
        return json.dumps(files, ensure_ascii=False)

    def _extract_title(self, content: str) -> str:
        """从内容中提取标题"""
        first_line = content.strip().split("\n")[0]
        return first_line[:80] if first_line else "untitled"

    def _content_to_markdown(self, content: str) -> str:
        """将内容转换为 Markdown"""
        lines = content.strip().split("\n")
        md_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                md_lines.append(stripped)
            elif stripped.startswith("## "):
                md_lines.append(stripped)
            else:
                md_lines.append(stripped if stripped else "")
        return "\n".join(md_lines)

    def _write_output(self, output_path: str, content: str):
        """写入输出文件"""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _mark_completed(self, pool, job_id: str):
        with pool.connection() as c:
            c.execute(
                "UPDATE export_jobs SET status='completed', completed_at=? WHERE job_id=?",
                (datetime.now().isoformat(), job_id)
            )

    def _mark_failed(self, pool, job_id: str, error: str):
        with pool.connection() as c:
            c.execute(
                "UPDATE export_jobs SET status='failed', error_message=?, completed_at=? WHERE job_id=?",
                (error, datetime.now().isoformat(), job_id)
            )

    def _ensure_tables(self):
        """确保导出任务表存在"""
        pool = get_pool()
        pool.execute(
            "CREATE TABLE IF NOT EXISTS export_jobs ("
            "job_id TEXT PRIMARY KEY, "
            "format TEXT, "
            "filter_spec TEXT, "
            "output_path TEXT, "
            "status TEXT DEFAULT 'pending', "
            "error_message TEXT, "
            "created_at TEXT, "
            "completed_at TEXT)"
        )

    def _get_subscriptions(self):
        return {
            "export.request": self._on_export_request,
        }

    def _on_export_request(self, event):
        self._state.metadata.setdefault("_pending_events", []).append(event.data)

    def queue_export(self, format: str, output_path: str, filter_spec: dict | None = None) -> dict:
        """将导出任务加入队列"""
        import uuid
        pool = get_pool()
        job_id = uuid.uuid4().hex
        now = datetime.now().isoformat()
        with pool.connection() as c:
            c.execute(
                "INSERT INTO export_jobs (job_id, format, filter_spec, output_path, status, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (job_id, format, json.dumps(filter_spec or {}), output_path, "pending", now)
            )
        return {"job_id": job_id, "status": "queued", "format": format}