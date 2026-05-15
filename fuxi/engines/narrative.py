"""伏羲 v1.5 — NarrativeEngine 叙事生成 + 主题提取 + LLM叙事"""
import json
import logging
from datetime import datetime
from typing import Optional

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engine.narrative")


def _extract_themes(items: list[dict]) -> list[dict]:
    """从记忆片段中提取主题聚类"""
    themes = {}
    for item in items:
        text = item.get("raw_text", "")
        if not text:
            continue
        drawer = item.get("drawer_name", "default")
        key = drawer
        if key not in themes:
            themes[key] = {"drawer": drawer, "count": 0, "previews": []}
        themes[key]["count"] += 1
        preview = text[:100].replace("\n", " ")
        themes[key]["previews"].append(preview)

    return sorted(themes.values(), key=lambda t: t["count"], reverse=True)


def _generate_identity_statement(identity_items: list[dict]) -> Optional[str]:
    """从自省记忆生成连续身份叙事"""
    if not identity_items:
        return None
    timeline = []
    for item in sorted(identity_items, key=lambda i: i.get("created_at", "")):
        text = item.get("raw_text", "")[:80].replace("\n", " ")
        timeline.append(text)
    if not timeline:
        return None
    return " → ".join(timeline[-5:])


@register_engine("narrative", experimental=False)
class NarrativeEngine(CognitiveEngine):
    """叙事生成 — 将碎片化记忆串成连贯叙事 + 主题提取 + 身份连续性"""
    name = "narrative"
    priority = 3
    interval = 1800
    experimental = False

    def run(self) -> dict:
        pool = get_pool()

        timeline = pool.fetchall(
            "SELECT items.id, items.raw_text, SUBSTR(items.raw_text,1,120) AS preview, "
            "items.importance, items.created_at, items.tags, items.emotion_valence, "
            "drawers.name AS drawer_name "
            "FROM items JOIN drawers ON items.drawer_id = drawers.id "
            "WHERE items.archived=0 AND items.importance > 0.5 "
            "ORDER BY items.created_at DESC LIMIT 30"
        )

        if not timeline:
            return {"narratives": 0, "message": "Not enough material"}

        themes = _extract_themes(timeline)

        by_drawer: dict[str, list] = {}
        for item in timeline:
            d = item["drawer_name"]
            if d not in by_drawer:
                by_drawer[d] = []
            by_drawer[d].append(item["preview"])

        narratives = []
        for drawer, previews in by_drawer.items():
            if len(previews) >= 3:
                avg_importance = sum(
                    i["importance"] for i in timeline
                    if i.get("drawer_name") == drawer
                ) / max(len(previews), 1)
                narrative = f"In drawer '{drawer}' ({len(previews)} memories, avg importance {avg_importance:.2f}): {' → '.join(previews[:5])}"
                narratives.append({
                    "drawer": drawer,
                    "thread_length": len(previews),
                    "narrative": narrative[:500],
                    "avg_importance": round(avg_importance, 2),
                })

        # 主题统计
        theme_summaries = []
        for theme in themes:
            if theme["count"] >= 2:
                theme_summaries.append({
                    "drawer": theme["drawer"],
                    "memory_count": theme["count"],
                    "sample": theme["previews"][0][:80] if theme["previews"] else "",
                })

        # 身份连续性 — 从反思和自省中提取
        identity_items = pool.fetchall(
            "SELECT items.id, items.raw_text, items.created_at "
            "FROM items JOIN drawers ON items.drawer_id = drawers.id "
            "WHERE items.archived=0 AND items.importance > 0.6 "
            "AND (items.tags LIKE '%自省%' OR items.tags LIKE '%反思%'"
            "  OR items.tags LIKE '%身份%' OR items.tags LIKE '%soul%') "
            "ORDER BY items.created_at DESC LIMIT 10"
        )
        identity_statement = _generate_identity_statement(identity_items)

        state = {
            "narratives": len(narratives),
            "samples": narratives[:3],
            "themes": theme_summaries,
            "total_items_in_window": len(timeline),
            "identity_continuity": identity_statement,
            "timestamp": datetime.now().isoformat(),
        }

        # 如果有身份叙事，写入长期记忆
        if identity_statement and len(identity_statement) > 30:
            try:
                from fuxi.memory.ingestion import remember
                remember(
                    raw_text=f"[身份叙事] {identity_statement}",
                    drawer_id="longterm",
                    importance=0.7,
                    source="narrative",
                    created_by="narrative_engine",
                    tags=["身份叙事", "narrative", "identity"],
                )
                state["identity_written"] = True
            except Exception as e:
                logger.warning(f"Failed to write identity narrative: {e}")

        self._state.metadata["last_narrative"] = state
        return state
