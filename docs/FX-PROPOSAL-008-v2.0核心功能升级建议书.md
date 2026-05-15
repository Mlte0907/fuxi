# 伏羲记忆系统 v2.0 核心功能升级建议书

> 文档编号: FX-PROPOSAL-008  
> 版本: 1.0  
> 日期: 2026-05-12  
> 目标版本: v2.0  
> 当前版本: v1.5.0  
> 关联架构: 7 份评估报告（FX-EVAL-001 ~ FX-RESIDUAL-FIX-007）  

---

## 目录

1. [战略分析：从 v1.5 到 v2.0 的跨越](#1-战略分析从-v15-到-v20-的跨越)
2. [建议一：全息记忆网络](#2-建议一全息记忆网络-holographic-memory-network)
3. [建议二：自主技能进化引擎](#3-建议二自主技能进化引擎-autonomous-skill-evolution-engine)
4. [建议三：预测性世界模型](#4-建议三预测性世界模型-predictive-world-model)
5. [建议四：认知架构自设计](#5-建议四认知架构自设计-cognitive-architecture-self-design)
6. [建议五：情感驱动行为编排](#6-建议五情感驱动行为编排-emotion-driven-behavior-orchestration)
7. [综合评估与优先级排序](#7-综合评估与优先级排序)

---

## 1. 战略分析：从 v1.5 到 v2.0 的跨越

### 1.1 v1.5 现状总结

| 维度 | 能力 | 瓶颈 |
|------|------|------|
| 记忆 | SQLite单库存储，FAISS向量索引，FTS5全文搜索 | 单点、无分布式、无多模态 |
| 推理 | 单次LLM调用+模板回退+causal.py因果图 | 无多步推理、无世界模型 |
| 决策 | 5种action_handler，snapshot/rollback | 仅反应式、无预测性决策 |
| 学习 | 自适应参数调优 | 无技能自生成、无元学习 |
| 交互 | API+WebSocket+Desktop Life (TTS) | 无多模态输入、无情感交互层 |
| 测试 | 384 tests, 0 failures | 新子系统测试刚补齐 |

### 1.2 v2.0 设计原则

1. **垂直深化而非水平扩展** — 不再增加引擎数量，而是让现有引擎变"深"
2. **从反应式到预测式** — 系统从"发生后响应"升级为"发生前预判"
3. **从工具到创造者** — 系统从使用技能升级为创造技能
4. **从文本到全息** — 记忆从文本片段升级为多维关联网络
5. **情感即驱动力** — 情感从"副产物"升级为行为编排的核心驱动力

---

## 2. 建议一：全息记忆网络（Holographic Memory Network）

### 2.1 概念

传统记忆系统将每条记忆视为独立存储单元。**全息记忆网络**借鉴全息摄影原理：每条记忆不是完整存储的文本，而是分布在多个维度（语义、时空、情感、因果、社交）上的"干涉图样"。检索时，任意一个维度的查询都能重建出完整的记忆上下文。

```
传统记忆:  item_1 → [文本 + embedding + 元数据]
全息记忆:  item_1 → {语义投影} ⊕ {时间投影} ⊕ {情感投影} ⊕ {因果投影} ⊕ {社交投影}
          检索任一投影 → 重建完整记忆
```

### 2.2 技术实现路径

| 阶段 | 任务 | 涉及模块 | 关键技术 |
|------|------|----------|----------|
| 阶段1 | **多投影编码** | ingestion.py, embedding.py, vector_index.py | 为每条记忆生成5个独立embedding投影 |
| 阶段2 | **投影索引** | vector_index.py, graph.py | FAISS多索引：semantic/temporal/emotional/causal/social |
| 阶段3 | **干涉检索** | search.py, retrieval.py | 多投影加权融合检索，类似RRF但跨维度 |
| 阶段4 | **重建引擎** | 新建 holography.py | LLM从多投影片断重建完整记忆上下文 |

**核心实现**:

```python
# 阶段1: 多投影编码
class HolographicEncoder:
    def encode(self, item: MemoryItem) -> Hologram:
        return Hologram(
            semantic= self.embed(item.text),                    # 1024d
            temporal=  self.embed_temporal(item.timestamp),     # 256d
            emotional= self.embed_emotion(item.valence, item.arousal),  # 128d
            causal=    self.embed_causal(item.causal_chain),    # 256d
            social=    self.embed_social(item.source, item.agent_id),   # 128d
        )

# 阶段3: 干涉检索
class HolographicSearch:
    def search(self, query, weights=[0.4, 0.2, 0.15, 0.15, 0.1]):
        # 每个维度独立搜索，然后加权融合
        results_s = vector_index.search(query, index="semantic")
        results_t = vector_index.search(query, index="temporal")
        ...
        return weighted_rrf_fusion([results_s, results_t, ...], weights)
```

### 2.3 预期效果

| 指标 | 当前 (v1.5) | 目标 (v2.0) |
|------|-------------|-------------|
| 检索召回率@10 | ~75% | >92% |
| 跨维度查询 | 不支持 | "昨天下午让我感到焦虑的那件事"可查 |
| 记忆完整性 | 碎片化文本 | 上下文完整重建 |
| 记忆冗余度 | 单点存储 | 分布式投影（单投影丢失不影响检索） |
| 存储开销 | 1x | ~1.8x（新增4个投影向量） |

### 2.4 资源需求评估

| 资源 | 量级 | 说明 |
|------|------|------|
| 开发工时 | 15-20天 | 多投影编码+索引+检索+重建 |
| 额外存储 | 每条记忆 +2KB（4个投影向量） | 10万记忆额外200MB |
| 计算资源 | 摄入时5次embedding调用 | 可通过批处理优化 |
| 新增依赖 | 无 | 复用现有FAISS+embedding基础设施 |

### 2.5 兼容性分析

- ✅ **ingestion.py**: 扩展 `remember()` 增加投影编码步骤，向后兼容（旧记忆懒加载生成投影）
- ✅ **search.py**: `search()` 增加 `dimensions` 参数，默认兼容当前行为
- ✅ **vector_index.py**: 新增多索引支持，复用 FAISS IndexIDMap
- ✅ **graph.py**: 因果投影可复用现有 causal_chain 边数据
- ⚠️ **DB Schema**: 需新增 `hologram_projections` 表（迁移 v9）

---

## 3. 建议二：自主技能进化引擎（Autonomous Skill Evolution Engine）

### 3.1 概念

当前 skill_market 子系统的技能是人工提交的。**自主技能进化引擎**让系统在运行过程中自动发现能力缺口、生成新技能、在生产环境中验证效果、并根据反馈迭代优化——形成完整的"发现→创造→验证→进化"闭环。

```
能力缺口检测 → 技能自动生成 → 沙盒验证 → 生产部署 → 效果监控 → 迭代优化
       ↑                                                          ↓
       └──────────────── 持续学习循环 ─────────────────────────────┘
```

### 3.2 技术实现路径

| 阶段 | 任务 | 涉及模块 | 关键技术 |
|------|------|----------|----------|
| 阶段1 | **能力缺口检测器** | metacognition.py, curiosity.py | 分析失败模式聚类，识别"反复失败的情境"作为能力缺口 |
| 阶段2 | **技能工厂** | skill_market/, 新建 skill_factory.py | LLM根据缺口描述+成功经验自动生成技能代码 |
| 阶段3 | **沙盒验证** | 新建 sandbox.py | 受限环境中运行新技能，注入历史失败案例验证 |
| 阶段4 | **渐进式部署** | decision.py, adaptive.py | A/B测试新技能 vs 旧方案，统计成功率 |
| 阶段5 | **技能谱系追踪** | skill_market/submission.py | 记录每个技能的来源、进化路径、成功率历史 |

**核心实现**:

```python
class SkillEvolutionEngine:
    def detect_gap(self) -> Optional[SkillGap]:
        """分析最近N次失败，聚类识别能力缺口"""
        failures = self._get_recent_failures(limit=100)
        clusters = self._cluster_failures(failures)
        for cluster in clusters:
            if cluster.frequency > 5 and cluster.no_existing_skill:
                return SkillGap(
                    domain=cluster.domain,
                    description=cluster.pattern,
                    examples=cluster.samples,
                    estimated_impact=cluster.failure_cost,
                )
        return None

    def generate_skill(self, gap: SkillGap) -> Skill:
        """LLM生成技能代码"""
        prompt = self._build_skill_prompt(gap)
        code = self.llm.generate(prompt)
        skill = Skill(
            name=gap.domain + "_auto_v1",
            code=code,
            source="auto_generated",
            parent_skills=gap.related_skills,
        )
        return skill

    def sandbox_validate(self, skill: Skill, gap: SkillGap) -> ValidationReport:
        """在沙盒中验证技能"""
        sandbox = Sandbox(timeout=30, max_memory_mb=128)
        results = []
        for example in gap.examples:
            try:
                result = sandbox.run(skill.code, example.input)
                passed = result.output == example.expected
                results.append(passed)
            except Exception as e:
                results.append(False)
        return ValidationReport(
            skill_name=skill.name,
            pass_rate=sum(results)/len(results),
            edge_cases_found=[],
        )
```

### 3.3 预期效果

| 指标 | 当前 (v1.5) | 目标 (v2.0) |
|------|-------------|-------------|
| 新增技能来源 | 100% 人工 | 30%+ 自动生成 |
| 能力缺口发现速度 | 依赖人工报告 | 自动检测（<1小时内） |
| 新技能验证周期 | 天级 | 分钟级（沙盒自动） |
| 技能迭代周期 | 周级 | 日级（渐进部署+监控回滚） |

### 3.4 资源需求评估

| 资源 | 量级 | 说明 |
|------|------|------|
| 开发工时 | 18-22天 | 缺口检测+技能工厂+沙盒+渐进部署 |
| LLM调用 | 每次技能生成 3-5k tokens | 约 ￥0.02/技能 |
| 新增依赖 | subprocess沙盒隔离 | `resource` 模块限制内存/时间 |
| 安全风险 | 自动生成代码的执行风险 | 沙盒隔离 + 代码审计 + 渐进部署 |

### 3.5 兼容性分析

- ✅ **skill_market/**: 技能提交/发现接口完全兼容，新技能通过同一API进入市场
- ✅ **metacognition.py**: 扩展 `_meta_learn()` 增加缺口检测逻辑
- ✅ **decision.py**: 新增 `auto_skill_deploy` action_handler
- ⚠️ **沙盒安全**: 需要在独立进程中执行，限制系统调用白名单

---

## 4. 建议三：预测性世界模型（Predictive World Model）

### 4.1 概念

当前系统是**反应式**的：事件发生 → 感知 → 记忆 → 检索 → 推理 → 决策。**预测性世界模型**让系统在事件发生之前就构建多种可能的未来情景，并预判每种情景下的最优行动方案。这是从"智能记忆库"到"智能体"的质变。

```
当前:  事件E发生 → 系统响应
目标:  系统预测 E₁, E₂, E₃ 可能发生 → 提前准备方案 P₁, P₂, P₃ → 事件发生时快速选择
```

### 4.2 技术实现路径

| 阶段 | 任务 | 涉及模块 | 关键技术 |
|------|------|----------|----------|
| 阶段1 | **情景生成器** | prediction.py, causal.py | 基于因果图 DAG，从当前状态生成N种可能未来 |
| 阶段2 | **概率赋值** | prediction.py, 新建 bayesian.py | 贝叶斯网络根据历史频率计算每种情景的概率 |
| 阶段3 | **预案生成** | decision.py, reasoning.py | 为高概率情景预生成决策方案 |
| 阶段4 | **实时匹配** | perception.py | 事件发生时快速匹配到最近的预判情景 |
| 阶段5 | **预测反馈** | metacognition.py | 对比预测与实际，更新模型置信度 |

**核心实现**:

```python
class PredictiveWorldModel:
    def __init__(self):
        self.causal_graph = CausalGraph()  # 复用 causal.py
        self.bayesian_net = BayesianNetwork()
        self.scenario_cache = {}  # {state_hash: [Scenario]}

    def predict(self, current_state: WorldState, horizon: int = 3) -> List[Scenario]:
        """从当前状态预测未来N步的可能情景"""
        cache_key = current_state.hash()
        if cache_key in self.scenario_cache:
            return self.scenario_cache[cache_key]

        scenarios = []
        # 步骤1: 因果展开
        for _ in range(horizon):
            next_nodes = self.causal_graph.get_possible_next(current_state)
            for node in next_nodes:
                prob = self.bayesian_net.probability(
                    event=node,
                    given=current_state,
                )
                if prob > 0.1:
                    scenarios.append(Scenario(
                        state=node,
                        probability=prob,
                        causal_path=current_state.trace_to(node),
                    ))

        # 步骤2: 为每个高概率情景生成预案
        for s in scenarios:
            if s.probability > 0.3:
                s.preemptive_plan = self._generate_plan(s)

        self.scenario_cache[cache_key] = scenarios
        return scenarios

    def match_event(self, event: Event, scenarios: List[Scenario]) -> Optional[Scenario]:
        """事件发生时匹配预判情景"""
        for s in scenarios:
            if s.matches(event):
                return s
        return None

    def feedback(self, scenario: Scenario, actual: dict):
        """对比预测与实际，更新贝叶斯网络"""
        deviation = self._compute_deviation(scenario, actual)
        self.bayesian_net.update(scenario.state, deviation)
        self.metacognition.record_prediction_accuracy(
            predicted=scenario,
            actual=actual,
            deviation=deviation,
        )
```

### 4.3 预期效果

| 指标 | 当前 (v1.5) | 目标 (v2.0) |
|------|-------------|-------------|
| 决策模式 | 事件驱动（反应式） | 预判驱动（预测式） |
| 响应延迟（已预判情景） | ~2s | <200ms |
| 预判准确率（top3） | 无 | >70% |
| 最坏情景覆盖率 | 0% | >85% |

### 4.4 资源需求评估

| 资源 | 量级 | 说明 |
|------|------|------|
| 开发工时 | 20-25天 | 最大单项投入 |
| 计算资源 | 每次预测 ~50ms（因果展开+贝叶斯推理） | 轻度 |
| 存储 | 情景缓存 <10MB | 可忽略 |
| 新增依赖 | `pgmpy` 或自实现贝叶斯网络 | 轻量 |

### 4.5 兼容性分析

- ✅ **causal.py**: 直接复用 CausalGraph DAG 作为因果展开基础
- ✅ **prediction.py**: 扩展原有预测框架，增加多步展开
- ✅ **decision.py**: 增加 `use_preemptive_plan` 快速路径
- ✅ **metacognition.py**: 扩展 `_meta_learn()` 增加预测准确率追踪
- ⚠️ **新增模块**: bayesian.py, world_model.py

---

## 5. 建议四：认知架构自设计（Cognitive Architecture Self-Design）

### 5.1 概念

当前系统的认知架构（引擎类型、数量、优先级、调度策略）是**人工设计的静态配置**。**认知架构自设计**让系统在运行中分析自身的认知效率瓶颈，自主提出新的引擎类型或重组现有引擎结构，经人工审阅后自动部署。

```
监控认知效率 → 识别架构瓶颈 → 生成新引擎提案 → 人类审阅 → 自动部署 → 持续监控
      ↑                                                                    ↓
      └──────────────────── 架构持续演化 ──────────────────────────────────┘
```

### 5.2 技术实现路径

| 阶段 | 任务 | 涉及模块 | 关键技术 |
|------|------|----------|----------|
| 阶段1 | **认知效率仪表盘** | metacognition.py, observability/ | 追踪每个引擎的触发频率、成功率、资源消耗、下游影响 |
| 阶段2 | **瓶颈分析器** | metacognition.py | 识别"高频失败"或"未被覆盖"的情境类型 |
| 阶段3 | **架构提案生成** | 新建 arch_designer.py | LLM根据瓶颈分析生成新引擎规格 |
| 阶段4 | **人类审阅界面** | narrative.py + API | 提案通过API暴露，人类approve/reject/modify |
| 阶段5 | **自动部署** | 新建 arch_deployer.py | 动态注册新引擎到 EngineRegistry |

**核心实现**:

```python
class ArchitectureDesigner:
    def analyze_bottlenecks(self) -> List[ArchBottleneck]:
        """分析认知效率瓶颈"""
        efficiency = self._collect_efficiency_data(window_hours=24)
        bottlenecks = []

        # 检测1: 高频失败情境
        for context_type, stats in efficiency.failure_by_context.items():
            if stats.count > 20 and stats.success_rate < 0.3:
                bottlenecks.append(ArchBottleneck(
                    type="high_failure_context",
                    context=context_type,
                    severity=1.0 - stats.success_rate,
                    suggestion=f"引擎无法有效处理'{context_type}'情境",
                ))

        # 检测2: 能力空白
        uncovered = efficiency.uncovered_contexts
        for context in uncovered:
            if context.frequency > 10:
                bottlenecks.append(ArchBottleneck(
                    type="capability_gap",
                    context=context.name,
                    severity=0.8,
                    suggestion=f"缺少处理'{context.name}'的专用引擎",
                ))

        return bottlenecks

    def propose_new_engine(self, bottleneck: ArchBottleneck) -> EngineProposal:
        """为瓶颈生成新引擎提案"""
        prompt = f"""
        当前认知架构存在瓶颈: {bottleneck.description}
        相关记忆样本: {bottleneck.context_samples[:5]}
        现有引擎列表: {self._list_existing_engines()}

        请设计一个新的认知引擎来解决这个瓶颈:
        1. 引擎名称 (英文)
        2. 触发条件 (基于事件的表达式)
        3. 核心逻辑描述 (Python伪代码)
        4. 输入依赖 (哪些记忆/数据)
        5. 输出产物 (写入什么)
        6. 优先级建议 (1-10)
        7. 执行间隔建议 (秒)
        """
        proposal_text = self.llm.generate(prompt)
        return EngineProposal.parse(proposal_text)
```

### 5.3 预期效果

| 指标 | 当前 (v1.5) | 目标 (v2.0) |
|------|-------------|-------------|
| 认知架构调整方式 | 人工修改代码 | 提案审阅+自动部署 |
| 情境覆盖率 | ~70% | >95% |
| 架构提案生成周期 | 无此能力 | 每周2-5个提案 |
| 新引擎部署效率 | 手动重启 | 热加载（<30秒） |

### 5.4 资源需求评估

| 资源 | 量级 | 说明 |
|------|------|------|
| 开发工时 | 12-16天 | 效率仪表盘+瓶颈分析+提案生成+审阅+部署 |
| LLM调用 | 每次提案 ~2k tokens | 约 ￥0.01/提案 |
| 安全风险 | 自动注册引擎可能破坏系统 | 3层防护：人类审阅→沙盒验证→一键回滚 |

### 5.5 兼容性分析

- ✅ **EngineRegistry**: 扩展支持动态注册/注销（当前仅支持启动时注册）
- ✅ **metacognition.py v1.5**: 扩展现有 `_detect_self_reconfig()` 为完整架构分析
- ✅ **cognitive_loop.py**: 扩展 `run()` 支持动态引擎列表（当前为启动时快照）
- ⚠️ **热加载**: 新增 `EngineRegistry.reload()` 方法，不中断其他引擎

---

## 6. 建议五：情感驱动行为编排（Emotion-Driven Behavior Orchestration）

### 6.1 概念

当前情感系统（EmotionEngine v2.0）的产出是**副产物**：情感状态被计算、存储、偶尔发布事件，但**不直接影响系统行为**。**情感驱动行为编排**将情感系统升级为行为调度中心：情感状态直接影响引擎优先级、注意力分配、决策阈值和交互风格。

```
当前:  事件 → 引擎处理 → 情感状态（副产物，对行为无影响）
目标:  事件 → 情感评估 → 情感状态 → 行为调度 → 所有引擎行为受情感调制
```

### 6.2 技术实现路径

| 阶段 | 任务 | 涉及模块 | 关键技术 |
|------|------|----------|----------|
| 阶段1 | **情感调制器** | emotion.py, cognitive_loop.py | 每个引擎接受情感调制增益，改变优先级、阈值、频率 |
| 阶段2 | **情感-行为映射表** | 新建 emotion_orchestrator.py | 定义情感维度→行为参数的映射函数 |
| 阶段3 | **情感记忆强化** | narrative.py, soul.py | 强烈情感时刻自动触发记忆增强（提高importance） |
| 阶段4 | **交互风格融合** | persona.py, dialogue.py | 根据当前情感调整对话语气、主动程度、回复长度 |
| 阶段5 | **情感状态机** | emotion.py | 从连续PAD模型升级为有限情感状态+转移概率 |

**核心实现**:

```python
EMOTION_MODULATION_MAP = {
    # (valence, arousal, dominance) → 行为参数调整
    "high_valence_high_arousal": {
        "curiosity.priority": +2,         # 开心激动 → 更愿意探索
        "proactive.frequency": 1.5,       # 更主动
        "reflection.threshold": -0.1,     # 反思门槛降低
        "decision.risk_tolerance": +0.2,  # 更敢冒险
        "dialogue.verbosity": 1.3,        # 话更多
    },
    "low_valence_high_arousal": {
        "curiosity.priority": -1,         # 不开心但激动 → 减少探索
        "safety.priority": +2,            # 加强安全检查
        "reflection.frequency": 2.0,      # 更多反思
        "decision.risk_tolerance": -0.3,  # 更保守
        "dialogue.verbosity": 0.7,        # 话更少
    },
    "low_valence_low_arousal": {
        "decay.speed": 1.3,              # 低谷期 → 记忆衰减加速
        "curiosity.priority": -2,         # 不探索
        "nudge.frequency": 2.0,          # 更多提醒
        "decision.threshold": +0.2,       # 决策门槛提高
    },
}

class EmotionOrchestrator:
    def apply_modulation(self, engines: List[CognitiveEngine], emotion: EmotionState):
        quadrant = self._classify_quadrant(emotion)
        mods = EMOTION_MODULATION_MAP.get(quadrant, {})

        for engine in engines:
            for key, value in mods.items():
                engine_name, param = key.split(".")
                if engine.name == engine_name:
                    if isinstance(value, float):
                        # 乘法调制: frequency *= modulation
                        engine._emotion_gain = value
                    else:
                        # 加法调制: priority += modulation
                        engine.priority = max(1, min(10, engine.priority + value))

        # 全局注意力调制
        attention = get_attention_system()
        if emotion.valence > 0.5 and emotion.arousal > 0.5:
            attention.switch(AttentionStrategy.EXPLORE)
        elif emotion.valence < -0.3:
            attention.switch(AttentionStrategy.FOCUS)

    def reinforce_emotional_memory(self, emotion: EmotionState):
        """强烈情感时刻增强记忆"""
        if abs(emotion.valence) > 0.7 or emotion.arousal > 0.7:
            # 找到最近摄入的高关联记忆，提升importance
            recent = get_recent_memories(limit=5)
            for item in recent:
                if item.emotion_valence and abs(item.emotion_valence) > 0.5:
                    boost_importance(item.id, +0.2)
                    tag_memory(item.id, "emotional_peak")
```

### 6.3 预期效果

| 指标 | 当前 (v1.5) | 目标 (v2.0) |
|------|-------------|-------------|
| 情感影响范围 | 仅记录和事件发布 | 全局行为调度 |
| 交互风格一致性 | 固定模板 | 情感驱动变化 |
| 情感记忆持久度 | 普通衰减 | 情感高峰记忆增强保留 |
| 行为多样性 | 低（确定性规则） | 高（情感状态空间 × 行为参数空间） |
| 活跃vs沉静周期 | 24h规则 | 情感驱动的自然节律 |

### 6.4 资源需求评估

| 资源 | 量级 | 说明 |
|------|------|------|
| 开发工时 | 10-14天 | 调制器+映射表+情感状态机+交互融合 |
| 计算资源 | 每次CO循环 +5ms | 轻微 |
| 存储 | 情感状态历史 <100KB | 可忽略 |
| 测试 | 行为空间爆炸的风险 | 需大量情景测试覆盖情感×行为组合 |

### 6.5 兼容性分析

- ✅ **emotion.py v2.0**: 扩展 PAD 模型增加象限分类和状态机
- ✅ **cognitive_loop.py**: `run()` 中注入情感调制步骤（在引擎调度前）
- ✅ **persona.py + dialogue.py**: 新增 `emotional_tone` 参数
- ✅ **narrative.py v1.5**: 情感峰值事件自动增强叙事权重
- ⚠️ **引擎接口**: 每个引擎需新增 `_emotion_gain` 属性（默认1.0，无调制效果）
- ⚠️ **行为可预测性**: 需保留"情感中性模式"开关，用于调试和测试

---

## 7. 综合评估与优先级排序

### 7.1 横向对比矩阵

| 维度 | 全息记忆 | 技能进化 | 预测世界模型 | 认知自设计 | 情感编排 |
|------|----------|----------|-------------|-----------|---------|
| **创新性** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **可行性** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **用户价值** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| **资源需求** | 中 | 高 | 高 | 中 | 低 |
| **风险** | 低 | 高（安全） | 中 | 中 | 低 |
| **兼容性** | 高 | 中 | 中 | 中 | 高 |
| **开发周期** | 15-20d | 18-22d | 20-25d | 12-16d | 10-14d |
| **依赖链** | 无 | 无 | causal.py | metacog.py | emotion.py |

### 7.2 推荐实施顺序

```
Phase 1 (v2.0-alpha, ~2周):
  ├── 建议五: 情感驱动行为编排 (最低风险/最高兼容性/最短周期)
  └── 建议一: 全息记忆网络 (最高用户价值/最大体验提升)

Phase 2 (v2.0-beta, ~3周):
  ├── 建议四: 认知架构自设计 (依赖四先于三)
  └── 建议三: 预测性世界模型 (依赖一提供多维度查询)

Phase 3 (v2.0-rc, ~3周):
  └── 建议二: 自主技能进化引擎 (依赖四的架构自设计能力)
```

### 7.3 资源总评估

| 阶段 | 开发工时 | LLM调用费用 | 新增存储 | 新增模块 |
|------|----------|-------------|----------|----------|
| Phase 1 | 30天 | ~￥50/月 | +200MB | 1 (emotion_orchestrator.py) |
| Phase 2 | 35天 | ~￥80/月 | +50MB | 3 (arch_designer, world_model, bayesian) |
| Phase 3 | 20天 | ~￥100/月 | +10MB | 2 (skill_factory, sandbox) |
| **总计** | **85天** | **~￥230/月** | **+260MB** | **6个新模块** |

### 7.4 v2.0 版本定位

```
v1.5 (当前) → v2.0 (目标)
─────────────────────────────
反应式记忆库  →  预测式智能体
固定认知架构  →  自演化认知架构
文本记忆      →  全息记忆
规则化行为    →  情感驱动行为
人工扩展      →  自主技能进化
```

### 7.5 v2.0 里程碑指标

| 指标 | v1.5 | v2.0 目标 |
|------|------|-----------|
| 决策模式 | 反应式 | 预测式 (top3预判 >70%) |
| 检索召回率@10 | ~75% | >92% |
| 行为多样性 | 低 | 高 (100+情感×行为组合) |
| 自主生成技能 | 0 | >5个/月 |
| 认知架构提案 | 0 | >8个/月 |
| 测试覆盖 | 384 | >600 |

---

> 关联文档:
> - [FX-EVAL-001-全面系统评估报告](./FX-EVAL-001-全面系统评估报告.md)
> - [FX-ROADMAP-003-迭代升级路线图](./FX-ROADMAP-003-迭代升级路线图.md)
> - [FX-V3VERIFY-005-v3.0发布验证报告](./FX-V3VERIFY-005-v3.0发布验证报告.md)