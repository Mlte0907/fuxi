"""伏羲飞书知识库引擎 — 基于 lark-cli 实现知识搜索与索引"""
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from fuxi.engines.base import CognitiveEngine, register_engine

logger = logging.getLogger("fuxi.engines.feishu_kb")

_LARK_CLI_BIN = str(Path.home() / ".npm-global/bin/lark-cli")


def _run_lark(args: list, timeout: int = 30) -> dict:
    env = os.environ.copy()
    env["PATH"] = str(Path.home() / ".npm-global/bin") + ":" + env.get("PATH", "")
    try:
        result = subprocess.run(
            [_LARK_CLI_BIN] + args,
            capture_output=True, text=True, timeout=timeout, env=env
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()[:200]}
        output = result.stdout.strip()
        try:
            return {"ok": True, "data": __import__("json").loads(output)}
        except Exception:
            return {"ok": False, "error": f"parse failed: {output[:100]}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _strip_md(text: str) -> str:
    text = re.sub(r'\n#{1,6}\s+', '\n', text)
    text = re.sub(r'\*\*|__', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', '', text)
    return text.strip()


@register_engine("feishu_kb", experimental=True)
class FeishuKnowledgeBaseEngine(CognitiveEngine):
    """飞书知识库引擎 — 搜索、索引、检索飞书文档内容"""

    name = "feishu_kb"
    experimental = True
    interval = 0

    def __init__(self):
        super().__init__()
        self._index: list[dict] = []
        self._doc_texts: dict[str, str] = {}

    def health_check(self) -> dict:
        alive = os.path.exists(_LARK_CLI_BIN)
        return {
            "name": self.name,
            "binary_exists": alive,
            "indexed_docs": len(self._index),
            "binary_path": _LARK_CLI_BIN,
        }

    def search_remote(self, query: str, limit: int = 10) -> list[dict]:
        """直接搜索飞书文档（不索引）"""
        result = _run_lark(["docs", "+search", "--query", query, "--page-size", str(limit), "--as", "user"])
        if not result.get("ok"):
            logger.error(f"[feishu_kb] search failed: {result.get('error')}")
            return []
        docs = []
        for r in result.get("data", {}).get("results", []):
            meta = r.get("result_meta", {})
            docs.append({
                "title": r.get("title_highlighted", "").replace("<h>", "").replace("</h>", ""),
                "doc_id": meta.get("token", ""),
                "doc_url": meta.get("url", ""),
                "owner": meta.get("owner_name", ""),
                "snippet": r.get("snippet", ""),
            })
        return docs

    def fetch_and_index(self, doc_id: str) -> dict:
        """拉取并索引文档内容到本地知识库"""
        result = _run_lark(["docs", "+fetch", "--doc", doc_id, "--format", "json"])
        if not result.get("ok"):
            return result

        content = result.get("data", {}).get("content", {})
        blocks = content if isinstance(content, list) else content.get("blocks", [])

        text_parts = []
        for block in blocks:
            block_type = block.get("block_type", 0)
            text_val = block.get("text", "")
            if isinstance(text_val, list):
                text_val = "".join(t.get("text", "") for t in text_val)
            if text_val:
                text_parts.append(str(text_val))

        combined = "\n".join(text_parts)
        plain = _strip_md(combined)

        if doc_id not in self._doc_texts:
            self._index.append({"doc_id": doc_id, "text": plain, "len": len(plain)})
            self._doc_texts[doc_id] = plain
        else:
            for item in self._index:
                if item["doc_id"] == doc_id:
                    item["text"] = plain
                    item["len"] = len(plain)
                    break
            self._doc_texts[doc_id] = plain

        logger.info(f"[feishu_kb] indexed doc {doc_id}, chars={len(plain)}")
        return {"ok": True, "doc_id": doc_id, "chars": len(plain), "preview": plain[:200]}

    def query_local(self, query: str, top_k: int = 5) -> list[dict]:
        """在已索引的文档中检索（纯本地）"""
        q_lower = query.lower()
        scored = []
        for item in self._index:
            text = item["text"].lower()
            score = 0.0
            for word in q_lower.split():
                if word in text:
                    score += 1.0 / (len(text) / max(len(word), 1))
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, item in scored[:top_k]:
            results.append({
                "doc_id": item["doc_id"],
                "score": round(score, 4),
                "text": item["text"][:300] + "..." if len(item["text"]) > 300 else item["text"],
            })
        return results

    def search_and_retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """两步搜索：先查飞书，再从已索引的文档中取最相关的块"""
        remote = self.search_remote(query, limit=10)
        doc_ids = [d["doc_id"] for d in remote if d.get("doc_id")]
        for did in doc_ids:
            if did not in self._doc_texts:
                self.fetch_and_index(did)
        local = self.query_local(query, top_k=top_k)
        for r in local:
            r["doc_url"] = next((d["doc_url"] for d in remote if d["doc_id"] == r["doc_id"]), "")
            r["title"] = next((d["title"] for d in remote if d["doc_id"] == r["doc_id"]), r["doc_id"])
        return local

    def clear_index(self):
        """清空本地索引"""
        self._index.clear()
        self._doc_texts.clear()
        logger.info("[feishu_kb] index cleared")

    def run(self) -> dict:
        return {"ok": True, "indexed_docs": len(self._index), "indexed_chars": sum(i["len"] for i in self._index)}


_engine: "FeishuKnowledgeBaseEngine | None" = None


def get_kb_engine() -> "FeishuKnowledgeBaseEngine":
    global _engine
    if _engine is None:
        _engine = FeishuKnowledgeBaseEngine()
    return _engine