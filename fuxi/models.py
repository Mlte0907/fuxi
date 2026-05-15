"""伏羲 v1.0 数据模型"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应格式"""
    code: int = 0
    data: Optional[T] = None
    meta: Optional[dict[str, Any]] = None

    @classmethod
    def ok(cls, data: Optional[T] = None, meta: Optional[dict[str, Any]] = None) -> "ApiResponse[T]":
        return cls(code=0, data=data, meta=meta)

    @classmethod
    def error(cls, code: int, detail: str) -> "ApiResponse[Any]":
        return cls(code=code, data=None, meta={"error": detail})


@dataclass
class Drawer:
    id: str
    name: str
    room_id: str
    description: str = ""
    item_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class MemoryItem:
    id: str
    raw_text: str
    facts: str = ""
    drawer_id: str = "default"
    importance: float = 0.5
    decay_score: float = 1.0
    tags: List[str] = field(default_factory=list)
    confidence: float = 1.0
    source: str = "direct"
    embedding: Optional[List[float]] = None
    version: int = 1
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    archived: bool = False
    collaborators: List[str] = field(default_factory=list)
    emotion_valence: float = 0.0

@dataclass
class Edge:
    id: str
    source_id: str
    target_id: str
    edge_type: str
    weight: float = 0.5
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class AgentView:
    id: str
    agent_id: str
    item_id: str
    perspective: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
