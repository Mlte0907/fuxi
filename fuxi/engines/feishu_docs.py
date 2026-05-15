"""伏羲飞书文档引擎 — 集成 lark-cli (官方 Feishu CLI) 实现云文档操作"""
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("fuxi.engines.feishu_docs")

_LARK_CLI_BIN = str(Path.home() / ".npm-global/bin/lark-cli")


class FeishuDocsEngine:
    """飞书云文档操作引擎 — 通过 lark-cli 调用官方 Feishu API"""

    name = "feishu_docs"
    experimental = False
    interval = 0  # 非周期引擎，按需调用

    def __init__(self):
        self._bin = _LARK_CLI_BIN

    def health_check(self) -> dict:
        """检查 lark-cli 是否可用"""
        alive = os.path.exists(self._bin)
        return {
            "name": self.name,
            "binary_exists": alive,
            "binary_path": self._bin,
        }

    def _run(self, args: list, timeout: int = 30) -> dict:
        """执行 lark-cli 命令并解析 JSON 输出"""
        env = os.environ.copy()
        env["PATH"] = str(Path.home() / ".npm-global/bin") + ":" + env.get("PATH", "")

        try:
            result = subprocess.run(
                [self._bin] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            if result.returncode != 0:
                return {"ok": False, "error": result.stderr.strip()[:200]}
            output = result.stdout.strip()
            try:
                return json.loads(output)
            except json.JSONDecodeError:
                return {"ok": False, "error": f"JSON parse failed: {output[:100]}"}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "command timeout"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def create_document(self, title: str, markdown: str = "") -> dict:
        """创建飞书文档

        Args:
            title: 文档标题
            markdown: Markdown 内容（可选）

        Returns:
            {"ok": true, "doc_id": "...", "doc_url": "...", "message": "..."}
        """
        args = ["docs", "+create", "--title", title]
        if markdown:
            args.extend(["--markdown", markdown])

        result = self._run(args)
        if result.get("ok"):
            logger.info(f"[feishu_docs] created doc: {result.get('data', {}).get('doc_id')}")
        else:
            logger.error(f"[feishu_docs] create failed: {result.get('error')}")
        return result

    def fetch_document(self, doc_id: str) -> dict:
        """获取文档内容"""
        result = self._run(["docs", "+fetch", "--doc", doc_id, "--format", "json"])
        return result

    def update_document(self, doc_id: str, markdown: str, mode: str = "overwrite") -> dict:
        """更新文档内容

        Args:
            doc_id: 文档 token
            markdown: Markdown 内容
            mode: 更新模式 (append/overwrite/replace_range/...)
        """
        args = ["docs", "+update", "--doc", doc_id, "--markdown", markdown, "--mode", mode]
        return self._run(args)

    def search_documents(self, query: str, limit: int = 10, as_user: str = "user") -> dict:
        """搜索文档

        Note: 搜索需要 user 身份，如果用 bot 身份会失败。可传入 as_user="user" 尝试。
        """
        args = ["docs", "+search", "--query", query, "--page-size", str(limit)]
        if as_user:
            args.extend(["--as", as_user])
        result = self._run(args)
        # 标准化返回结构，将 results 转为 docs 列表
        if result.get("ok") and "results" in result.get("data", {}):
            docs = []
            for r in result["data"]["results"]:
                meta = r.get("result_meta", {})
                docs.append({
                    "title": r.get("title_highlighted", "").replace("<h>", "").replace("</h>", ""),
                    "doc_url": meta.get("url", ""),
                    "doc_id": meta.get("token", ""),
                    "owner": meta.get("owner_name", ""),
                    "update_time": meta.get("update_time_iso", ""),
                })
            result["data"]["docs"] = docs
        return result

    def create_document_from_template(
        self,
        title: str,
        content_blocks: list[dict],
        folder_token: Optional[str] = None,
    ) -> dict:
        """从内容块创建文档（更细粒度控制）"""
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(content_blocks[0].get("content", "") if content_blocks else "")
            f.flush()
            temp_path = f.name

        try:
            args = ["docs", "+create", "--title", title, "--markdown", f"@{temp_path}"]
            if folder_token:
                args.extend(["--folder-token", folder_token])
            return self._run(args)
        finally:
            os.unlink(temp_path)

    def grant_permission(
        self, doc_id: str, user_id: str = "", permission: str = "full_access"
    ) -> dict:
        """给文档授权（需要用户 ID）"""
        # lark-cli docs 命令通过 API 实现，这里通过 drive 权限管理
        args = [
            "drive", "permission", "create", doc_id,
            "--type", "docx",
            "--perm", permission,
        ]
        if user_id:
            args.extend(["--user-id", user_id])
        return self._run(args)


_engine: "FeishuDocsEngine | None" = None


def get_feishu_docs_engine() -> "FeishuDocsEngine":
    global _engine
    if _engine is None:
        _engine = FeishuDocsEngine()
    return _engine