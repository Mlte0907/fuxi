"""伏羲 Feature Flag 运行时开关系统 - 基于 CCB feature() 模式"""
import logging, threading
from typing import Optional

logger = logging.getLogger("fuxi.feature_flags")

DEFAULT_FEATURES = {
    "BUDDY": False, "TRANSCRIPT_CLASSIFIER": False, "SHOT_STATS": False,
    "PROMPT_CACHE_BREAK_DETECTION": False, "TOKEN_BUDGET": False,
    "AGENT_TRIGGERS": False, "ULTRATHINK": False, "EXTRACT_MEMORIES": True,
    "VERIFICATION_AGENT": False, "DAEMON": False, "INSTINCT_LEARNING": True,
    "HOOK_SYSTEM": True, "MULTI_MODEL_ROUTING": True, "SAFETY_SHIELD": True,
    "DREAM_CONSOLIDATION": True, "MEMORY_DECAY": True, "JINLANGE_INGESTION": True,
    "COGNITIVE_LOOP": True, "METACOGNITION": True,
}

class FeatureFlags:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            with threading.Lock():
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False): return
        self._flags = DEFAULT_FEATURES.copy()
        self._overrides = {}
        self._initialized = True

    def get(self, flag_name: str) -> bool:
        return self._overrides.get(flag_name, self._flags.get(flag_name, False))

    def set(self, flag_name: str, value: bool) -> None:
        self._overrides[flag_name] = value
        logger.info(f"FeatureFlag {flag_name} = {value}")

    def enable(self, flag_name: str) -> None: self.set(flag_name, True)
    def disable(self, flag_name: str) -> None: self.set(flag_name, False)
    def list_all(self) -> dict: return {f: self.get(f) for f in sorted(set(self._flags)|set(self._overrides))}
    def reset(self) -> None: self._overrides.clear()

_flags = FeatureFlags()

def feature(flag_name: str) -> bool: return _flags.get(flag_name)
def feature_enable(flag_name: str) -> None: _flags.enable(flag_name)
def feature_disable(flag_name: str) -> None: _flags.disable(flag_name)
def feature_list() -> dict: return _flags.list_all()
