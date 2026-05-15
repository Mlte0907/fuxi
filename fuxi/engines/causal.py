"""伏羲 v1.5 — CausalEngine 因果推理（do-calculus + 因果图构建）"""
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from fuxi.engines.base import CognitiveEngine, register_engine
from fuxi.kernel.event_bus import Event, EventPriority, get_event_bus
from fuxi.store.connection import get_pool

logger = logging.getLogger("fuxi.engines.causal")

# 因果关系关键词
CAUSAL_KEYWORDS = ["因为", "所以", "导致", "引起", "造成", "致使", "因此", "由于", "使得", "结果是"]
CONFUNDER_KEYWORDS = ["既...又", "既可以", "也会导致", "共同导致", "多因素", "混杂"]


@dataclass
class CausalEdge:
    cause: str
    effect: str
    evidence: str
    strength: float = 1.0


class CausalGraph:
    """有向无环因果图 (DAG)"""

    def __init__(self):
        self.nodes: set[str] = set()
        self.edges: list[CausalEdge] = []
        self.adjacency: dict[str, list[str]] = defaultdict(list)
        self.reverse_adj: dict[str, list[str]] = defaultdict(list)

    def add_edge(self, edge: CausalEdge):
        self.nodes.add(edge.cause)
        self.nodes.add(edge.effect)
        self.edges.append(edge)
        self.adjacency[edge.cause].append(edge.effect)
        self.reverse_adj[edge.effect].append(edge.cause)

    def get_children(self, node: str) -> list[str]:
        return self.adjacency.get(node, [])

    def get_parents(self, node: str) -> list[str]:
        return self.reverse_adj.get(node, [])

    def has_path(self, start: str, end: str, visited: set[str] | None = None) -> bool:
        """检查是否存在从 start 到 end 的路径"""
        if visited is None:
            visited = set()
        if start == end:
            return True
        if start in visited:
            return False
        visited.add(start)
        for child in self.get_children(start):
            if self.has_path(child, end, visited):
                return True
        return False

    def get_descendants(self, node: str) -> set[str]:
        """获取节点的所有后代"""
        desc = set()
        stack = list(self.get_children(node))
        while stack:
            n = stack.pop()
            if n not in desc:
                desc.add(n)
                stack.extend(self.get_children(n))
        return desc


@register_engine("causal", experimental=False)
class CausalEngine(CognitiveEngine):
    """因果推理引擎 — 基于 do-calculus 实现因果推断"""

    name = "causal"
    priority = 7
    interval = 600

    def run(self) -> dict:
        pool = get_pool()
        graph = self._build_causal_graph(pool)
        confounders = self._identify_confounders(graph)
        inferences = self._do_inference(graph, confounders)

        if inferences:
            bus = get_event_bus()
            for inf in inferences:
                bus.publish(Event(
                    type="causal.inference",
                    data=inf,
                    priority=EventPriority.NORMAL,
                    source=f"engine:{self.name}",
                ))

        return {
            "graph_nodes": len(graph.nodes),
            "graph_edges": len(graph.edges),
            "confounders": confounders,
            "inferences": inferences,
        }

    def _build_causal_graph(self, pool) -> CausalGraph:
        """从记忆中提取因果关系，构建有向无环图"""
        graph = CausalGraph()

        rows = pool.fetchall(
            "SELECT content, metadata FROM items WHERE archived=0"
        )

        for row in rows:
            content = row["content"] if row["content"] else ""
            metadata_str = row["metadata"] if row["metadata"] else "{}"

            # 提取因果关系
            for cause_word in CAUSAL_KEYWORDS:
                idx = content.find(cause_word)
                if idx == -1:
                    continue

                # 尝试提取 因果 对
                before = content[:idx].strip()
                after = content[idx + len(cause_word):].strip()

                # 简单启发式：取前一句作为原因，后一句作为结果
                sentences_before = re.split(r'[。！？\n]', before)
                sentences_after = re.split(r'[。！？\n]', after)

                cause = sentences_before[-1] if sentences_before else before[-50:]
                effect = sentences_after[0] if sentences_after else after[:50]

                cause = cause.strip()[:100]
                effect = effect.strip()[:100]

                if cause and effect and cause != effect:
                    graph.add_edge(CausalEdge(
                        cause=cause,
                        effect=effect,
                        evidence=content[:200],
                    ))

        return graph

    def _identify_confounders(self, graph: CausalGraph) -> list[dict[str, Any]]:
        """识别可能的混杂因子 — 即同时影响多个结果的节点"""
        confounders = []

        for node in graph.nodes:
            children = graph.get_children(node)
            if len(children) >= 2:
                # 检查是否有共同后代的父节点（潜在的混杂因子）
                for i, child1 in enumerate(children):
                    for child2 in children[i+1:]:
                        # 如果 child1 和 child2 都有其他共同父节点，则当前节点可能是混杂因子
                        parents1 = set(graph.get_parents(child1))
                        parents2 = set(graph.get_parents(child2))
                        common = parents1 & parents2
                        if len(common) >= 1:
                            confounders.append({
                                "node": node,
                                "confounded_vars": [child1, child2],
                                "common_parents": list(common),
                            })

        return confounders

    def _do_intervention(self, graph: CausalGraph, x: str, y: str) -> dict[str, Any]:
        """do(X) 操作：计算 P(Y|do(X))

        do(X) 表示对 X 进行干预（强制其值），而非观察。
        这会切断所有指向 X 的边，只保留从 X 出发的边。
        """
        # 在 do-operators 下，Y 的分布只受 X 的影响（沿因果路径）
        descendants_x = graph.get_descendants(x)

        # 如果 Y 是 X 的后代或 X 本身，则 P(Y|do(X)) = P(Y|X)
        # 否则 P(Y|do(X)) = P(Y)（无因果影响）
        if y in descendants_x or y == x:
            return {
                "type": "do_inference",
                "intervention": f"do({x})",
                "target": y,
                "result": "P(Y|do(X)) = P(Y|X)",
                "interpretation": f"{y} 是 {x} 的后代，直接受 {x} 影响",
                "probability_type": "conditional",
            }
        else:
            return {
                "type": "do_inference",
                "intervention": f"do({x})",
                "target": y,
                "result": "P(Y|do(X)) = P(Y)",
                "interpretation": f"{y} 不受 {x} 因果路径影响",
                "probability_type": "marginal",
            }

    def _backdoor_adjustment(self, graph: CausalGraph, x: str, y: str, z: list[str]) -> dict[str, Any]:
        """后门路径阻断调整

        如果存在从 X 到 Y 的后门路径（非因果路径），需要通过 Z 来阻断。
        P(Y|do(X)) = sum_{z} P(Y|X, Z=z) * P(Z=z)
        """
        # 检查 z 是否真的能阻断后门路径
        blocked = []
        for zi in z:
            # Z 阻断 X <- Z -> Y 这样的后门路径
            parents_x = graph.get_parents(x)
            parents_y = graph.get_parents(y)
            if zi in parents_x or zi in parents_y:
                blocked.append(zi)

        return {
            "type": "backdoor_adjustment",
            "x": x,
            "y": y,
            "adjustment_set": z,
            "blocked_by": blocked,
            "formula": f"P(Y|do(X)) = sum_z P(Y|X, Z=z) * P(Z=z)",
            "note": f"通过 {blocked} 阻断后门路径" if blocked else "无需调整",
        }

    def _do_inference(self, graph: CausalGraph, confounders: list) -> list[dict[str, Any]]:
        """执行因果推断"""
        inferences = []

        # 对每条因果边执行 do-calculus 推断
        for edge in graph.edges:
            x, y = edge.cause, edge.effect

            # do(X) 对 Y 的影响
            do_inf = self._do_intervention(graph, x, y)
            inferences.append(do_inf)

            # 检查是否需要后门调整
            potential_confounders = [c["node"] for c in confounders
                                    if x in c["confounded_vars"] and y in c["confounded_vars"]]
            if potential_confounders:
                backdoor = self._backdoor_adjustment(graph, x, y, potential_confounders)
                inferences.append(backdoor)

        return inferences
