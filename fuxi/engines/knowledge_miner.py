"""伏羲知识挖掘引擎 — 从记忆系统中筛选高价值内容，提炼后上传飞书知识库

架构：皮皮在瑾岚阁知识库下创建了「目录一」作为根目录，
伏羲自主判断创建子分类（系统事件、技术笔记、工作记录等），
并把记忆沉淀文档放到对应子分类下。

分类规则（自动推断，创建不存在的分类）：
  longterm + [wm_eviction/working_memory/auto] → 系统事件
  default + [python/coding]                   → 技术笔记
  default + [cooking/food]                   → 生活记录
  default + 其他                              → 工作记录

每次运行：
  1. 清理目标分类目录下的旧 wiki 页面（保留分类节点本身）
  2. 扫描 items 表 importance >= 0.7 的未归档记忆
  3. LLM 提炼要点
  4. 创建新 wiki 页面（已清理旧页，同类不会重复）
"""
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from fuxi.engines.base import CognitiveEngine, register_engine

logger = logging.getLogger("fuxi.engine.knowledge_miner")

_LARK_CLI = Path.home() / ".npm-global/bin/lark-cli"
_ROOT_NODE = os.environ.get("FUXI_FEISHU_WIKI_ROOT_NODE", "your_wiki_root_node_here")
_SPACE_ID = os.environ.get("FUXI_FEISHU_WIKI_SPACE_ID", "your_wiki_space_id_here")
_MIN_IMPORTANCE = 0.7
_MAX_ITEMS_PER_RUN = 10
_MAX_CHARS = 3000

# 分类规则：key → category_name
_CLASSIFY_RULES = {
    "longterm:wm_eviction": "系统事件",
    "longterm:working_memory": "系统事件",
    "longterm:auto": "系统事件",
    "default:python": "技术笔记",
    "default:coding": "技术笔记",
    "default:cooking": "生活记录",
    "default:food": "生活记录",
}


def _run_lark(args: list, timeout: int = 30) -> dict:
    import os
    env = os.environ.copy()
    env["PATH"] = str(Path.home() / ".npm-global/bin") + ":" + env.get("PATH", "")
    try:
        result = subprocess.run(
            [_LARK_CLI] + args,
            capture_output=True, text=True, timeout=timeout, env=env
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()[:200]}
        output = result.stdout.strip()
        try:
            return {"ok": True, "data": json.loads(output)}
        except Exception:
            return {"ok": False, "error": f"parse failed: {output[:100]}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _extract_node_token(result: dict) -> Optional[str]:
    outer = result.get("data", {})
    if isinstance(outer, str):
        outer = json.loads(outer)
    inner = outer.get("data", {}) if isinstance(outer, dict) else {}
    if isinstance(inner, str):
        inner = json.loads(inner)
    if isinstance(inner, dict):
        return inner.get("node_token", "") or None
    return None


async def _call_llm(prompt: str, model: str = "deepseek/deepseek-v4-pro") -> str:
    import aiohttp

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.post(
                "http://localhost:19528/api/v2/bridge/claude",
                json={"message": prompt, "model": model},
                headers={"X-API-Key": "jinlange-fuxi-2026"},
            ) as resp:
                data = await resp.json()
                if data.get("code") != 0:
                    return ""
                return data.get("data", {}).get("reply", "")
    except Exception as e:
        logger.error(f"LLM call error: {e}")
        return ""


def _strip_md(text: str) -> str:
    text = re.sub(r'\n#{1,6}\s+', '\n', text)
    text = re.sub(r'\*\*|__', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', '', text)
    return text.strip()


def _parse_tags(tags_str: str) -> list[str]:
    try:
        return json.loads(tags_str or "[]")
    except Exception:
        return []


def _classify(item: dict) -> str:
    """根据 drawer + tags 推断分类名称"""
    drawer = item.get("drawer", "default") or "default"
    tags = _parse_tags(item.get("tags", ""))

    for tag in tags:
        key = f"{drawer}:{tag}"
        if key in _CLASSIFY_RULES:
            return _CLASSIFY_RULES[key]

    return "工作记录"


@register_engine("knowledge_miner", experimental=True)
class KnowledgeMiner(CognitiveEngine):
    """知识挖掘引擎 — 自主分类沉淀记忆到飞书知识库"""

    name = "knowledge_miner"
    experimental = True
    priority = 4     # 提高优先级
    interval = 1800  # 30分钟

    def __init__(self):
        super().__init__()
        self._last_run = 0.0
        self._last_count = 0
        # category_name → wiki node_token（预先填充分类节点）
        self._category_nodes: dict[str, str] = {
            "系统事件": "DCr1w344ei1f85kRKsZcujiznKh",
            "工作记录": "FSjswuN9ZiuVo6kgwLEckJoYnDc",
            "技术笔记": "Z0UqwR3lriEScUkwLeScWvCnn6c",
            "生活记录": "CqVYwklt3i4puhktJmscoiBzng6",
        }

    def health_check(self) -> dict:
        return {
            "name": self.name,
            "binary_exists": Path(_LARK_CLI).exists(),
            "last_run": self._last_run,
            "last_uploaded": self._last_count,
            "root": _ROOT_NODE,
            "categories": list(self._category_nodes.keys()),
        }

    def _list_children(self, parent_node: str) -> list[dict]:
        """列出父节点下的所有直接子节点（只到一级）"""
        result = _run_lark([
            "api", "GET",
            f"/open-apis/wiki/v2/spaces/{_SPACE_ID}/nodes",
            "--params", json.dumps({"parent_node_token": parent_node}),
            "--as", "user",
        ])
        if not result.get("ok"):
            return []
        # 解析嵌套：result["data"]["data"]["items"]（wiki nodes list API）
        d0 = result.get("data", {})
        if isinstance(d0, str):
            d0 = json.loads(d0)
        inner = d0.get("data", {}) if isinstance(d0, dict) else {}
        if isinstance(inner, str):
            inner = json.loads(inner)
        items = inner.get("items", []) if isinstance(inner, dict) else []
        return items

    def _delete_node(self, node_token: str) -> bool:
        """删除指定的 wiki 节点"""
        result = _run_lark([
            "api", "DELETE",
            f"/open-apis/wiki/v2/spaces/{_SPACE_ID}/nodes/{node_token}",
            "--params", json.dumps({"obj_type": "origin"}),
            "--as", "user",
        ])
        ok = result.get("ok", False)
        if not ok:
            logger.warning(f"[knowledge_miner] delete node {node_token}: {result.get('error')}")
        return ok

    def _cleanup_category_pages(self, category_node: str) -> int:
        """清理分类节点下的所有旧 wiki 页面（文档节点），保留子分类节点本身"""
        children = self._list_children(category_node)
        deleted = 0
        for child in children:
            node_type = child.get("node_type", "")
            node_token = child.get("node_token", "")
            title = child.get("title", "")
            # 只删除文档节点（origin 类型的 docx），不删除目录节点（origin 下有子节点的）
            if node_type == "origin" and node_token:
                obj_type = child.get("obj_type", "")
                if obj_type == "docx":
                    if self._delete_node(node_token):
                        deleted += 1
                        logger.info(f"[knowledge_miner] cleaned page: {title} ({node_token})")
        return deleted

    def _ensure_category(self, category: str) -> str:
        """确保子分类节点存在，不存在则在目录一下自动创建"""
        if category in self._category_nodes:
            return self._category_nodes[category]

        result = _run_lark([
            "wiki", "+node-create",
            "--parent-node-token", _ROOT_NODE,
            "--title", category,
            "--as", "user",
        ])
        token = _extract_node_token(result)
        if token:
            self._category_nodes[category] = token
            logger.info(f"[knowledge_miner] created category: {category} → {token}")
            return token

        logger.warning(f"[knowledge_miner] failed to create category '{category}': {result.get('error')}")
        return _ROOT_NODE  # fallback to root

    def _get_pending_items(self, pool) -> list[dict]:
        rows = pool.fetchall(
            f"""
            SELECT id, drawer_id, raw_text, importance, tags, created_at
            FROM items
            WHERE importance >= {_MIN_IMPORTANCE}
              AND archived = 0
            ORDER BY importance DESC, created_at DESC
            LIMIT {_MAX_ITEMS_PER_RUN}
            """
        )
        return [
            {
                "id": r[0],
                "drawer": r[1],
                "text": r[2] or "",
                "importance": r[3],
                "tags": r[4] or "",
                "created_at": r[5],
            }
            for r in rows
        ]

    async def _distill_one(self, item: dict) -> str:
        prompt = f"""你是一个知识提炼助手。请从以下记忆片段中提取核心要点，整理成一段简洁的条目（100-200字）。

要求：
- 提取关键事实、决定、发现或教训
- 用清晰的中文描述
- 不要啰嗦，直接给出结论

记忆内容：
{item['text'][:_MAX_CHARS]}

标签：{item['tags']}
重要性：{item['importance']}
"""
        result = await _call_llm(prompt)
        if not result:
            result = _strip_md(item["text"])[:200]
        return result.strip()

    async def run(self) -> dict:
        from fuxi.store.connection import get_pool

        if not Path(_LARK_CLI).exists():
            return {"ok": False, "error": "lark-cli not found"}

        # 从 wiki 同步分类节点状态（发现已创建的分类）
        live_children = self._list_children(_ROOT_NODE)
        for child in live_children:
            title = child.get("title", "")
            token = child.get("node_token", "")
            if title and token and child.get("has_child"):
                self._category_nodes[title] = token
        logger.info(f"[knowledge_miner] synced categories: {list(self._category_nodes.keys())}")

        pool = get_pool()
        items = self._get_pending_items(pool)
        if not items:
            logger.info("[knowledge_miner] no pending items")
            return {"ok": True, "uploaded": 0, "skipped": 0}

        logger.info(f"[knowledge_miner] found {len(items)} pending items")

        # 按分类分组
        groups: dict[str, list] = {}
        for item in items:
            cat = _classify(item)
            if cat not in groups:
                groups[cat] = []
            groups[cat].append(item)

        total_uploaded = 0
        total_cleaned = 0

        for category, group in groups.items():
            # 确保分类存在
            parent_node = self._ensure_category(category)

            # 清理旧页面（保留分类节点本身）
            cleaned = self._cleanup_category_pages(parent_node)
            total_cleaned += cleaned
            logger.info(f"[knowledge_miner] cleaned {cleaned} old pages in category '{category}'")

            sections = []
            for item in group:
                distilled = await self._distill_one(item)
                if distilled:
                    sections.append(f"## {item['created_at'][:10]} [{item['importance']}]\n\n{distilled}")

            if not sections:
                continue

            content_md = "# 伏羲记忆沉淀\n\n"
            content_md += f"分类：{category} | 条目数：{len(sections)}\n\n"
            content_md += "---\n\n"
            content_md += "\n\n---\n\n".join(sections)

            result = _run_lark([
                "docs", "+create",
                "--title", f"伏羲记忆沉淀 {time.strftime('%Y-%m-%d')}",
                "--markdown", content_md,
                "--wiki-node", parent_node,
                "--as", "user",
            ])

            uploaded_ids = []
            if result.get("ok"):
                inner = result.get("data", {})
                if isinstance(inner, str):
                    inner = json.loads(inner)
                doc_id = ""
                if isinstance(inner, dict):
                    doc_id = inner.get("document", {})
                    if isinstance(doc_id, dict):
                        doc_id = doc_id.get("document_id", "")
                    elif isinstance(doc_id, str):
                        doc_id = ""
                total_uploaded += len(sections)
                uploaded_ids = [item["id"] for item in group]
                logger.info(f"[knowledge_miner] uploaded: category={category} doc={doc_id} items={len(sections)}")
            else:
                logger.warning(f"[knowledge_miner] upload failed for {category}: {result.get('error')}")

            # 归档已上传的记忆，避免下次重复上传
            if uploaded_ids:
                placeholders = ",".join(["?"] * len(uploaded_ids))
                pool.execute(
                    f"UPDATE items SET archived = 1 WHERE id IN ({placeholders})",
                    uploaded_ids
                )

        self._last_run = time.time()
        self._last_count = total_uploaded
        return {"ok": True, "uploaded": total_uploaded, "cleaned": total_cleaned, "categories": len(groups)}
