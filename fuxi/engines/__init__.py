"""认知引擎 — 插件化注册"""
from fuxi.config import config

# Engine tier definitions (matching the optimization doc)
ENGINE_TIERS = {
    "essential": [
        "cognitive_loop", "decay", "perception", "soul", "metacognition", "safety"
    ],
    "standard": [
        "cognitive_loop", "decay", "perception", "soul", "metacognition", "safety",
        "dialogue", "jinlange_ingestion", "reasoning", "distill", "dream", "immune", "emotion",
        "event_logger"
    ],
    "advanced": [
        "cognitive_loop", "decay", "perception", "soul", "metacognition", "safety",
        "dialogue", "jinlange_ingestion", "reasoning", "distill", "dream", "immune", "emotion",
        "creative", "narrative", "proactive", "resonance", "prediction", "decision", "persona",
        "adaptive", "reconsolidation", "reflection", "nudge", "curiosity", "openclaw_memory",
        "skill_evolution", "feishu_kb", "emotion_orchestrator", "world_model",
        "skill_orchestrator", "arch_auditor", "knowledge_miner",
        "parallel_scheduler", "streaming_index", "lifecycle_manager", "multi_tenant",
        "export_migration", "multimodal_memory", "synthesis", "intent_prediction",
        "deep_emotion", "cognitive_bias", "meta_evolution"
    ],
    "all": None  # None means all engines
}

def get_enabled_engines() -> list[str] | None:
    """Get list of enabled engine names for current tier. None = all enabled."""
    tier = config.engine_tier
    if tier == "all":
        return None
    return ENGINE_TIERS.get(tier, ENGINE_TIERS["standard"])

from fuxi.engines.adaptive import AdaptiveEngine
from fuxi.engines.base import CognitiveEngine, get_engine_registry, register_engine
from fuxi.engines.cognitive_loop import CognitiveLoop
from fuxi.engines.creative import CreativeEngine
from fuxi.engines.curiosity import CuriosityEngine
from fuxi.engines.decision import DecisionEngine
from fuxi.engines.dialogue import DialogueEngine
from fuxi.engines.distill import DistillationTower
from fuxi.engines.dream import DreamConsolidation
from fuxi.engines.emotion import EmotionEngine
from fuxi.engines.emotion_orchestrator import EmotionOrchestrator
from fuxi.engines.immune import ImmuneEngine
from fuxi.engines.jinlange_ingestion import JinlangeIngestionEngine
from fuxi.engines.metacognition import MetacognitionEngine
from fuxi.engines.narrative import NarrativeEngine
from fuxi.engines.nudge import NudgeEngine
from fuxi.engines.perception import PerceptionEngine
from fuxi.engines.persona import PersonaEngine
from fuxi.engines.prediction import PredictionEngine
from fuxi.engines.proactive import ProactiveEngine
from fuxi.engines.world_model import PredictiveWorldModel
from fuxi.engines.skill_orchestrator import SkillOrchestrator
from fuxi.engines.arch_auditor import ArchAuditor
from fuxi.engines.reasoning import ReasoningEngine
from fuxi.engines.reconsolidation import ReconsolidationEngine
from fuxi.engines.reflection import ReflectionEngine
from fuxi.engines.resonance import ResonanceEngine
from fuxi.engines.safety import SafetyEngine
from fuxi.engines.openclaw_memory import OpenClawMemoryEngine
from fuxi.engines.skill_evolution import SkillEvolutionEngine
from fuxi.engines.decay import DecayEngine
from fuxi.engines.soul import SoulEngine
from fuxi.engines.feishu_im import FeishuIMEngine
from fuxi.engines.causal import CausalEngine
from fuxi.engines.feishu_kb import FeishuKnowledgeBaseEngine
from fuxi.engines.knowledge_miner import KnowledgeMiner
from fuxi.engines.event_logger import EventLoggerEngine
from fuxi.engines.parallel_scheduler import ParallelSchedulerEngine
from fuxi.engines.streaming_index import StreamingIndexEngine
from fuxi.engines.lifecycle_manager import LifecycleManagerEngine
from fuxi.engines.multi_tenant import MultiTenantEngine
from fuxi.engines.export_migration import ExportMigrationEngine
from fuxi.engines.multimodal_memory import MultimodalMemoryEngine
from fuxi.engines.synthesis import SynthesisEngine
from fuxi.engines.intent_prediction import IntentPredictionEngine
from fuxi.engines.deep_emotion import DeepEmotionEngine
from fuxi.engines.cognitive_bias import CognitiveBiasEngine
from fuxi.engines.meta_evolution import MetaEvolutionEngine

# Import this module to trigger register_engine() at startup
_ = OpenClawMemoryEngine
_ = SkillEvolutionEngine
_ = DecayEngine
_ = SoulEngine
_ = FeishuIMEngine
_ = CausalEngine
_ = FeishuKnowledgeBaseEngine
_ = EmotionOrchestrator
_ = PredictiveWorldModel
_ = SkillOrchestrator
_ = ArchAuditor
_ = KnowledgeMiner
_ = EventLoggerEngine
_ = ParallelSchedulerEngine
_ = StreamingIndexEngine
_ = LifecycleManagerEngine
_ = MultiTenantEngine
_ = ExportMigrationEngine
_ = MultimodalMemoryEngine
_ = SynthesisEngine
_ = IntentPredictionEngine
_ = DeepEmotionEngine
_ = CognitiveBiasEngine
_ = MetaEvolutionEngine
