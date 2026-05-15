"""伏羲 v1.0 — 上下文预算分析器

适配自 ECC context-budget 技能:
- Phase 1: Inventory — 扫描所有组件目录
- Phase 2: Classify — 分类到 Always/Sometimes/Rarely
- Phase 3: Detect Issues — 检测 bloated/heavy/redundant 问题
- Phase 4: Report — 生成token节省建议
"""
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("fuxi.observability.context_budget")

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"

COMPONENT_LIMITS = {
    "agent": {"max_lines": 200, "max_desc_words": 30},
    "skill": {"max_lines": 400},
    "rule": {"max_lines": 100},
    "mcp_tool": {"max_tokens_per_tool": 500, "max_tools_per_server": 20},
    "claude_md": {"max_total_lines": 300},
}

@dataclass
class ComponentInventory:
    """组件清单"""
    component_type: str
    name: str
    path: str
    lines: int = 0
    tokens: int = 0
    issues: list = None
    
    def __post_init__(self):
        self.issues = self.issues or []


class ContextBudgetAnalyzer:
    """上下文预算分析器"""
    
    def __init__(self):
        self.inventoryy = []
        self.total_tokens = 0
    
    def run_inventory(self) -> list:
        """Phase 1: 扫描所有组件目录"""
        components = []
        
        # 扫描Agents
        agents_dir = CLAUDE_DIR / "agents"
        if agents_dir.exists():
            for f in agents_dir.glob("*.md"):
                comp = self._analyze_file(f, "agent")
                components.append(comp)
        
        # 扫描Skills
        skills_dir = CLAUDE_DIR / "plugins" / "everything-claude-code@everything-claude-code" / "skills"
        if skills_dir.exists():
            for f in skills_dir.glob("*/SKILL.md"):
                comp = self._analyze_file(f, "skill")
                components.append(comp)
        
        # 扫描项目memory
        if PROJECTS_DIR.exists():
            for proj in PROJECTS_DIR.iterdir():
                memory_dir = proj / "memory"
                if memory_dir.exists():
                    for f in memory_dir.glob("*.md"):
                        comp = self._analyze_file(f, "memory")
                        comp.name = f"{proj.name}/{f.name}"
                        components.append(comp)
        
        self.inventoryy = components
        self.total_tokens = sum(c.tokens for c in components)
        return components
    
    def _analyze_file(self, path: Path, comp_type: str) -> ComponentInventory:
        """分析单个文件"""
        try:
            content = path.read_text()
            lines = len(content.split('\n'))
            tokens = int(lines * 1.3)  # 估算: words * 1.3
        except Exception:
            lines, tokens = 0, 0
        
        name = path.stem
        issues = []
        
        # 检测问题
        if comp_type == "agent":
            if lines > COMPONENT_LIMITS["agent"]["max_lines"]:
                issues.append(f"Heavy agent: {lines} lines (max {COMPONENT_LIMITS['agent']['max_lines']})")
        elif comp_type == "skill":
            if lines > COMPONENT_LIMITS["skill"]["max_lines"]:
                issues.append(f"Large skill: {lines} lines (max {COMPONENT_LIMITS['skill']['max_lines']})")
        
        return ComponentInventory(
            component_type=comp_type,
            name=name,
            path=str(path),
            lines=lines,
            tokens=tokens,
            issues=issues
        )
    
    def classify_components(self) -> dict:
        """Phase 2: 分类组件"""
        buckets = {
            "always_needed": [],
            "sometimes_needed": [],
            "rarely_needed": [],
        }
        
        for comp in self.inventoryy:
            if comp.issues:
                buckets["sometimes_needed"].append(comp)
            elif comp.component_type in ("memory", "claude_md"):
                buckets["always_needed"].append(comp)
            else:
                buckets["rarely_needed"].append(comp)
        
        return buckets
    
    def generate_report(self) -> str:
        """Phase 4: 生成报告"""
        lines = ["=" * 60, "Context Budget Report", "=" * 60, ""]
        
        # 按类型汇总
        by_type = {}
        for comp in self.inventoryy:
            t = comp.component_type
            if t not in by_type:
                by_type[t] = {"count": 0, "tokens": 0, "issues": 0}
            by_type[t]["count"] += 1
            by_type[t]["tokens"] += comp.tokens
            by_type[t]["issues"] += len(comp.issues)
        
        lines.append("Component Breakdown:")
        lines.append(f"{'Type':<15} {'Count':>8} {'Tokens':>10} {'Issues':>8}")
        lines.append("-" * 45)
        for t, data in sorted(by_type.items()):
            lines.append(f"{t:<15} {data['count']:>8} ~{data['tokens']:>8} {data['issues']:>8}")
        
        lines.append("")
        lines.append(f"Total estimated overhead: ~{self.total_tokens:,} tokens")
        
        # 问题列表
        issues_comp = [c for c in self.inventoryy if c.issues]
        if issues_comp:
            lines.append(f"\nWARNING: {len(issues_comp)} components with issues:")
            for comp in issues_comp[:5]:
                lines.append(f"  - {comp.name}: {', '.join(comp.issues)}")
        
        return "\n".join(lines)
