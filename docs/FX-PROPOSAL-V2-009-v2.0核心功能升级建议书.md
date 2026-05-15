# 伏羲记忆系统 v2.0 核心功能升级建议书

> 文档编号: FX-PROPOSAL-V2-009  
> 版本: 2.0 (重写版)  
> 日期: 2026-05-12  
> 目标版本: v2.0  
> 当前版本: v1.5.0  
> 上一版: FX-PROPOSAL-008（已废弃 — 未正确理解 Brain-Limbs 架构）  

---

## 目录

1. [架构正位：大脑与手脚](#1-架构正位大脑与手脚)
2. [建议一：预测性世界模型](#2-建议一预测性世界模型-predictive-world-model)
3. [建议二：全息记忆网络](#3-建议二全息记忆网络-holographic-memory-network)
4. [建议三：情感驱动行为编排](#4-建议三情感驱动行为编排-emotion-driven-behavior-orchestration)
5. [建议四：技能编排中枢](#5-建议四技能编排中枢-skill-orchestration-hub)
6. [建议五：认知架构自审视](#6-建议五认知架构自审视-cognitive-architecture-self-audit)
7. [综合评估与实施路线](#7-综合评估与实施路线)

---

## 1. 架构正位：大脑与手脚

### 1.1 设计者的原始意图

> "伏羲是一个记忆中枢，一个大脑。OpenClaw 和 Claude Code 是它的手和脚。"

这句话定义了整个系统的根本分工：

```
                         ┌─────────────────────────────────┐
                         │         伏羲 (大脑中枢)            │
                         │                                 │
                         │  大脑专属能力:                     │
                         │  • 记忆 — 存储、编码、检索、遗忘     │
                         │  • 认知 — 推理、反思、预测、判断     │
                         │  • 情感 — 评估、调制、驱动          │
                         │  • 调度 — 发现需求、协调手脚、验证结果 │
                         │  • 进化 — 审视自身、重组结构         │
                         │                                 │
                         │  大脑不做的事:                     │
                         │  ✗ 不执行具体任务                  │
                         │  ✗ 不直接与外部世界交互             │
                         │  ✗ 不替代手脚创造技能               │
                         └──────────────┬──────────────────┘
                                        │
              ┌─────────────────────────┼─────────────────────────┐
              │                         │                         │
              ▼                         ▼                         ▼
     ┌──────────────┐          ┌──────────────┐          ┌──────────────┐
     │  OpenClaw    │          │  Claude Code │          │  更多平台    │
     │  Agent       │          │              │          │  ...         │
     └──────────────┘          └──────────────┘          └──────────────┘
     
     手和脚的职责:
     • 执行具体任务 (debug / refactor / deploy / ...)
     • 在解决问题中生成技能
     • 与外部世界交互 (QQ / 飞书 / 终端 / 浏览器)
     • 向大脑汇报结果、提交经验
```

### 1.2 由此推导的 v2.0 设计铁律

| 铁律 | 含义 |
|------|------|
| **大脑不伸手** | 任何需要"执行任务"的能力，不应由伏羲实现。伏羲只判断、预测、调度 |
| **手脚不思考** | 执行层不重复实现记忆、推理、情感。复杂判断回传大脑 |
| **技能生于执行** | 技能只能由执行层在解决实际问题中产生。伏羲负责发现缺口、协调开发、验证效果 |
| **模型调用归执行层** | 伏羲不直接调用大模型生成内容。如需 LLM 推理，走现有 OpenClawAdapter 通道 |

### 1.3 v2.0 提案筛选

基于以上铁律，对上一版建议书的修正：

| 原提案 | 判定 | 处理 |
|--------|------|------|
| 预测性世界模型 | ✅ 纯大脑能力 — 基于记忆构建未来情景 | **保留，升级为第一优先级** |
| 全息记忆网络 | ✅ 纯大脑能力 — 更好的记忆编码和检索 | **保留，列为第二优先级** |
| 情感驱动行为编排 | ✅ 纯大脑能力 — 情感调制认知过程 | **保留，列为第三优先级** |
| 自主技能进化 | ❌ 伏羲生成技能 = 大脑伸手做事 | **重写为"技能编排中枢"** |
| 认知架构自设计 | ✅ 大脑审视自身 — 但原定位过于宏大 | **缩小为"认知架构自审视"** |

---

## 2. 建议一：预测性世界模型（Predictive World Model）

### 2.1 为什么这是 v2.0 最核心的升级

当前伏羲是**反应式大脑**：

```
事件发生 → 感知 → 记忆 → 检索 → 推理 → 决策 → (通知手脚执行)
```

v2.0 的伏羲应该是**预测式大脑**：

```
大脑基于记忆库持续推演:
  "如果 X 发生，可能引发 Y，进而导致 Z"
  "根据过去 30 天的模式，明天大概率会出现 W 情境"
  "当前系统状态 + 情感趋势 → 2小时内可能需要手脚介入"
  
  → 提前生成预案
  → 事件发生时瞬间匹配，直接调度手脚
  → 不再等待事件发生后被动响应
```

**这是"大脑"最本质的能力升级：从记忆过去到预测未来。**

### 2.2 技术实现

#### 2.2.1 情景推演引擎

```python
class PredictiveWorldModel:
    """
    纯大脑能力 ── 基于因果图和记忆库，从当前状态推演可能的未来。
    不执行任何实际行动，只输出预测和预案。
    """

    def __init__(self):
        self.causal_graph = CausalGraph()   # 复用 causal.py v1.5
        self.scenario_cache = {}             # 缓存最近的预测结果
        self.prediction_history = []         # 用于准确率追踪

    def forecast(self, horizon: int = 3) -> List[Scenario]:
        """
        从当前世界状态出发，推演未来 N 步的可能情景。

        输入: 当前引擎状态、情感状态、最近 N 条关键事件、活跃的技能缺口
        输出: 按概率排序的情景列表，每个情景含:
          - 触发条件 (事件模式)
          - 发生概率
          - 因果路径 (从当前到该情景的因果链)
          - 建议预案 (如果概率 > 阈值)
          - 预估影响 (严重度 × 概率)
        """
        current_state = self._snapshot_current_state()
        scenarios = []

        for step in range(horizon):
            # 在因果图 DAG 上做步进展开
            possible_next = self.causal_graph.expand(current_state, depth=step+1)

            for node in possible_next:
                prob = self._estimate_probability(node, current_state)
                if prob > 0.05:  # 过滤极低概率情景
                    scenarios.append(Scenario(
                        trigger=self._describe_trigger(node),
                        probability=prob,
                        causal_path=self._trace_path(current_state, node),
                        severity=self._estimate_impact(node),
                    ))

        # 按预期影响排序 (概率 × 严重度)
        scenarios.sort(key=lambda s: s.probability * s.severity, reverse=True)

        # 缓存结果，供后续匹配使用
        self.scenario_cache[current_state.hash()] = scenarios
        return scenarios[:10]  # 只保留 top 10 情景


    def match(self, incoming_event: Event) -> Optional[Scenario]:
        """
        手脚报告了一个事件 → 大脑瞬间匹配到预判情景。
        如果命中，跳过整套推理流程，直接输出预案。
        这就是从"反应式"到"预测式"的关键跃迁。
        """
        for scenarios in self.scenario_cache.values():
            for s in scenarios:
                if s.matches(incoming_event):
                    logger.info(f"预判命中: {s.trigger} → 预案已就绪")
                    return s
        return None

    def learn_from_feedback(self, predicted: Scenario, actual: dict):
        """
        对比预测与实际，更新概率模型。
        预测对了 → 提高该路径的置信度。
        预测错了 → 降低，并分析偏差原因（为什么没预测到？缺什么记忆？）
        """
        deviation = self._compute_deviation(predicted, actual)
        self._update_bayesian_weights(predicted.causal_path, deviation)
        self.prediction_history.append({
            "ts": datetime.now().isoformat(),
            "predicted": predicted.trigger,
            "probability": predicted.probability,
            "actual": actual.get("outcome", "unknown"),
            "deviation": deviation,
        })
```

#### 2.2.2 数据来源（全部在现有架构中，无需新增采集）

| 输入 | 来源模块 | 说明 |
|------|----------|------|
| 因果图 DAG | causal.py v1.5 | 复用现有 do-calculus + counterfactual |
| 近期关键事件 | EventBus + memory retrieval | 高 importance 记忆的近期趋势 |
| 引擎状态快照 | EngineRegistry + engine_states | 哪些引擎最近频繁失败？ |
| 情感状态 | emotion.py v2.0 | PAD 三维当前值 + 趋势 |
| 活跃技能缺口 | experience_bank 查询 | 最近失败的 task_type 聚合 |
| 周期性模式 | memory search (时序查询) | "过去4周每周三下午发生了什么" |

#### 2.2.3 预案生成

高概率/高影响情景 → 生成预案。预案本身**不执行任何行动**，而是交给手脚：

```python
def _generate_plan(self, scenario: Scenario) -> Plan:
    """
    大脑为高概率情景准备预案。预案是"建议"不是"命令"。
    手脚收到预案后，自行判断是否采用。
    """
    return Plan(
        scenario_id=scenario.id,
        description=f"如果检测到 {scenario.trigger}，建议:",
        suggested_actions=[
            Action(
                target="openclaw",    # 指定由哪个手脚执行
                type="deploy_skill",  # 建议的执行类型
                skill_name=self._find_best_skill(scenario),
                fallback="manual_review",
            ),
        ],
        estimated_effect=f"预计降低 {scenario.severity} 影响",
    )
```

### 2.3 与现有模块的关系

```
                     prediction.py (已有 v1.0)
                           │
                    ┌──────┴──────┐
                    ▼             ▼
            causal.py v1.5   新建 world_model.py
            (因果图DAG)      (情景推演+概率估计+预案)
                    │             │
                    └──────┬──────┘
                           ▼
                    metacognition.py v1.5
                    (预测准确率追踪+偏差分析)
```

| 关键点 | 说明 |
|--------|------|
| **不新建引擎** | 复用并升级 prediction.py，从单步预测变为多步推演 |
| **零 LLM 成本** | 纯因果图展开 + 贝叶斯推理，全是确定性计算 |
| **成果直接喂给手脚** | 预案通过 EventBus 发布 `brain.forecast` 事件，执行层订阅 |

### 2.4 资源评估

| 资源 | 量级 |
|------|------|
| 开发工时 | 18-22天 |
| 新增 LLM 调用 | **0**（纯数学+因果图） |
| 新增存储 | <50MB（情景缓存 + 预测历史） |
| 新增模块 | 1（world_model.py，~400行） |
| 升级模块 | 1（prediction.py v1.0 → v2.0） |
| 新增测试 | ~20个 |

### 2.5 预期效果

| 指标 | v1.5 (反应式) | v2.0 (预测式) |
|------|--------------|--------------|
| 常见情景响应延迟 | ~2s (感知→检索→推理→决策) | <200ms (预案命中) |
| 突发事件覆盖 | 0% | 常见模式 >85% |
| 预判准确率 (top 3) | 无 | >70% |
| 学习周期 | 无 | 每次预测反馈都在改进概率模型 |

---

## 3. 建议二：全息记忆网络（Holographic Memory Network）

### 3.1 概念

当前记忆是**单维度存储**：一条记忆 → 一个文本 + 一个 embedding。

全息记忆是**多维度投影**：

```
传统记忆:  item_1 → [raw_text + embedding(1024d)]
全息记忆:  item_1 → {
              语义投影 (1024d): embedding(raw_text)
              时空投影 (256d):  embedding(时间戳 + 抽屉 + 序列位置)
              情感投影 (128d):  embedding(valence + arousal + dominance)
              因果投影 (256d):  embedding(causal_chain 摘要)
              来源投影 (128d):  embedding(agent_id + channel + session_id)
          }

          插值重建: 任一维度查询 → 找回完整记忆上下文
```

大脑不存储"完整画面"，而是存储多维的**干涉图样**。当你用一个维度（比如"上周三下午的事"）去查询，大脑通过多维投影交叉重建出完整记忆。

### 3.2 为什么是纯大脑能力

- **编码**是大脑的事：把输入信号分解为多维度特征
- **存储**是大脑的事：多索引向量库
- **检索**是大脑的事：跨维度加权融合搜索
- **重建**是大脑的事：从多个片断拼接完整记忆

整个过程手脚不参与。手脚只负责把原始数据交给大脑，大脑负责全部的记忆处理。

### 3.3 技术实现

#### 3.3.1 多投影编码

在 `ingestion.py` 的 `remember()` 流程中插入投影编码：

```python
# 由现有 _embed_for_ingestion() 扩展
def _encode_hologram(item: MemoryItem) -> Hologram:
    return Hologram(
        item_id=item.id,
        semantic=  embed_service.embed(item.raw_text),           # BGE 1024d
        temporal=  temporal_encoder.encode(item.created_at,
                                           item.drawer_id,
                                           item.sequence_position),  # 256d
        emotional= emotional_encoder.encode(item.valence,
                                            item.arousal,
                                            item.dominance),        # 128d
        causal=    causal_encoder.encode(item.causal_chain_summary),# 256d
        source=    source_encoder.encode(item.source,
                                         item.created_by,
                                         item.session_id),         # 128d
    )
```

#### 3.3.2 多索引向量库

扩展 `vector_index.py`，从单索引变为多索引：

```python
class HolographicVectorIndex:
    INDEX_NAMES = ["semantic", "temporal", "emotional", "causal", "source"]

    def __init__(self):
        self.indices = {
            name: FAISSIndex(dimension=DIMS[name])
            for name in self.INDEX_NAMES
        }

    def add(self, hologram: Hologram):
        for name in self.INDEX_NAMES:
            self.indices[name].add(hologram.item_id, hologram.projections[name])

    def search(self, query_projection: np.ndarray, index_name: str, top_k: int):
        return self.indices[index_name].search(query_projection, top_k)
```

#### 3.3.3 跨维度融合检索

扩展 `search.py`，增加多维度加权融合：

```python
def holographic_search(query: str, weights: dict = None) -> List[MemoryItem]:
    """
    将查询编码为多维度投影，每个维度独立搜索，加权融合结果。
    """
    if weights is None:
        weights = {
            "semantic": 0.40,   # 语义始终是主维度
            "temporal": 0.15,
            "emotional": 0.15,
            "causal": 0.20,
            "source": 0.10,
        }

    query_semantic = embed_service.embed(query)  # 主维度

    all_results = {}
    for dim, weight in weights.items():
        if weight > 0:
            query_vec = _encode_query_for_dimension(query, dim)
            results = vix.search(query_vec, index_name=dim, top_k=20)
            for item_id, score in results:
                all_results[item_id] = all_results.get(item_id, 0) + score * weight

    sorted_items = sorted(all_results.items(), key=lambda x: x[1], reverse=True)
    return [fetch_memory(item_id) for item_id, _ in sorted_items[:10]]
```

### 3.4 资源评估

| 资源 | 量级 |
|------|------|
| 开发工时 | 12-16天 |
| 新增 LLM 调用 | **0**（embedding API 约￥20/月新增） |
| 新增存储 | 每条记忆 +2KB（4个投影向量），10万条 +200MB |
| 新增模块 | 3（hologram.py, temporal_encoder.py, emotional_encoder.py） |
| 升级模块 | 3（ingestion.py, vector_index.py, search.py） |
| 新增测试 | ~25个 |

### 3.5 预期效果

| 指标 | v1.5 | v2.0 |
|------|------|------|
| 检索召回率@10 | ~75% | >90% |
| 跨维度查询 | 不支持（只能语义搜） | "昨天下午让我焦虑的那件事" ✅ |
| 单维度损坏恢复 | 0%（embedding丢失=记忆找不回） | 任一维度可独立检索 |
| 记忆关联密度 | 依赖显式 graph 边 | 跨维度隐式关联自动浮现 |

---

## 4. 建议三：情感驱动行为编排（Emotion-Driven Behavior Orchestration）

### 4.1 概念

当前情感系统的定位是"副产品"：情感被计算、记录、偶尔发事件，但**不对系统行为产生实质影响**。

在 Brain-Limbs 架构下，情感应该是大脑用来**调制手脚行为**的信号系统。就像人脑的杏仁核通过神经递质调节前额叶的决策阈值——伏羲的情感系统应该通过 EventBus 调制执行层的行为参数。

```
当前: 手脚做事 → 大脑记录情感（无反馈）
v2.0: 手脚做事 → 大脑评估情感 → 情感调制手脚的后续行为
      欣喜 → 手脚更主动、更敢冒险
      焦虑 → 手脚更谨慎、更多检查
      平静 → 手脚按默认模式运行
      倦怠 → 手脚减少主动操作、等待明确指令
```

### 4.2 情感→行为的调制映射

```python
EMOTION_MODULATION = {
    # (valence, arousal) 象限 → 对执行层的行为调制
    "enthusiastic": {   # 高愉悦 + 高唤醒
        "decision.risk_tolerance": 0.2,    # 更敢冒险
        "proactive.frequency": 1.5,        # 更主动
        "curiosity.priority": 2,           # 更愿探索
        "dialogue.verbosity": 1.3,         # 话更多
        "soul.interval": 60,               # 更频繁自省
    },
    "anxious": {        # 低愉悦 + 高唤醒
        "safety.priority": 2,              # 强安全检查
        "reflection.frequency": 2.0,       # 频繁反思
        "decision.risk_tolerance": -0.3,   # 保守
        "dialogue.verbosity": 0.7,         # 话少
        "immune.frequency": 1.5,           # 频繁自检
    },
    "calm": {           # 高愉悦 + 低唤醒
        "curiosity.priority": 0,           # 不主动探索
        "proactive.frequency": 1.0,        # 正常节奏
        "decision.risk_tolerance": 0.0,    # 默认
        "creativity.priority": 1,          # 适度创造
    },
    "fatigued": {       # 低愉悦 + 低唤醒
        "decay.speed": 1.3,               # 记忆衰减加速
        "nudge.frequency": 2.0,           # 更多提醒
        "decision.threshold": 0.2,        # 决策门槛提高
        "curiosity.priority": -2,         # 停止探索
        "proactive.frequency": 0.5,       # 减少主动操作
    },
}
```

### 4.3 情感状态机

从连续 PAD 值 → 离散情感状态 → 稳定转移（避免情感跳变）：

```python
class EmotionalStateMachine:
    """
    情感不是每120秒跳一次，而是有惯性的状态转移。
    当前状态 + 新事件的情感冲击 → 平滑转移到新状态。
    """

    def update(self, new_event_impact: EmotionImpact) -> EmotionState:
        # 1. 计算新事件对 PAD 的冲击
        pad_delta = self._compute_delta(new_event_impact)

        # 2. EMA 平滑（情感惯性）
        self.current_pad = (
            self.current_pad * 0.85 + pad_delta * 0.15
        )

        # 3. 自然回归（情感不持久，趋向中性）
        self.current_pad = self.current_pad * 0.995

        # 4. 离散化到象限
        new_quadrant = self._pad_to_quadrant(self.current_pad)

        # 5. 状态转移（需要连续3次在同一象限才切换，防止抖动）
        self.quadrant_history.append(new_quadrant)
        if len(self.quadrant_history) > 3:
            self.quadrant_history.pop(0)

        if all(q == new_quadrant for q in self.quadrant_history):
            if new_quadrant != self.current_quadrant:
                self.current_quadrant = new_quadrant
                self._publish_state_change()

        return self.current_state()
```

### 4.4 情感高峰记忆强化

```python
def _on_emotional_peak(self, memory: MemoryItem):
    """强烈情感事件 → 记忆 enhanced + 标签标记"""
    if abs(memory.emotion_valence) > 0.7 or memory.emotion_arousal > 0.7:
        # 提高该记忆的 importance，降低衰减速度
        boost_memory_importance(memory.id, +0.2)
        tag_memory(memory.id, "emotional_peak")
        # 触发叙事引擎记录这个"关键时刻"
        publish_event("memory.emotional_peak", memory)
```

### 4.5 资源评估

| 资源 | 量级 |
|------|------|
| 开发工时 | 8-12天 |
| 新增 LLM 调用 | **0**（纯数学+PAD模型） |
| 新增存储 | <100KB（情感历史+状态机） |
| 新增模块 | 1（emotion_orchestrator.py，~300行） |
| 新增测试 | ~15个 |

---

## 5. 建议四：技能编排中枢（Skill Orchestration Hub）

### 5.1 定位修正

> ❌ 原建议: 伏羲自主生成技能代码
> 
> ✅ 修正后: 伏羲发现技能缺口 → 打包上下文 → 调度执行层开发 → 验证效果

伏羲是大脑，不做手的事。技能只能从执行层的真实问题解决中生长出来。但大脑可以：
- 发现"我们需要什么技能"
- 调度正确的手脚去开发
- 验证手脚交回来的技能是否真的有效

### 5.2 编排流程

```
Step 1: 缺口发现 (伏羲)
  │ metacognition.py 分析最近 N 天的 failure 模式
  │ → 发现"SQLite 锁冲突"类失败出现了 15 次，无现有技能可处理
  │
Step 2: 需求打包 (伏羲)
  │ 收集: 15 次失败的错误信息、触发情境、相关记忆片段
  │ → 生成结构化技能需求文档
  │
Step 3: 派发请求 (伏羲 → 执行层)
  │ POST /api/skills/request
  │ { "gap": "sqlite_lock_conflict", "sample_failures": [...], ... }
  │
Step 4: 执行层开发 (OpenClaw / Claude Code + MiniMax)
  │ 收到需求 → 复现问题 → 找到解决方案 → 提取为技能
  │ → POST /api/skills/submit (走现有 submit_skill API)
  │
Step 5: 回归验证 (伏羲)
  │ 在新的 sandbox 中用历史 15 次失败案例验证技能
  │ ✅ 通过 → approve → 加入 skill_market
  │ ❌ 失败 → reject + 向执行层返回失败原因
  │
Step 6: 效果追踪 (伏羲)
  │ 技能部署后，监控同类 failure 是否下降
  │ → 下降 → 记录成功 → 提升技能质量评分
  │ → 未下降 → 标记技能为需改进 → 触发新一轮编排
```

### 5.3 核心实现

```python
class SkillOrchestrator:
    """技能编排中枢 — 纯大脑能力"""

    def detect_gaps(self, window_days: int = 7) -> List[SkillGap]:
        """分析近期失败模式，识别技能缺口"""
        failures = self._recent_failures(days=window_days)
        clustered = self._cluster_by_pattern(failures)

        gaps = []
        for pattern, cases in clustered.items():
            existing = self._find_existing_skill(pattern)
            if not existing and len(cases) >= 5:
                gaps.append(SkillGap(
                    pattern=pattern,
                    failure_count=len(cases),
                    sample_errors=cases[:10],
                    related_memories=self._find_related_memories(cases),
                    severity=sum(c.get("cost", 1) for c in cases),
                ))
        return sorted(gaps, key=lambda g: g.severity, reverse=True)

    def request_skill(self, gap: SkillGap) -> str:
        """打包技能需求，派发给执行层"""
        request = {
            "gap_id": str(uuid.uuid4()),
            "pattern": gap.pattern,
            "description": self._describe_gap(gap),
            "sample_failures": gap.sample_errors,
            "related_context": gap.related_memories,
            "suggested_approach": "请在实际任务中尝试复现并找到解决方案",
        }
        # 发布事件 → 执行层订阅后自主处理
        publish_event(Event(
            type="skill.requested",
            data=request,
            priority=EventPriority.MEDIUM,
        ))
        # 同时存入 DB 等待执行层拉取
        persist_skill_request(request)
        return request["gap_id"]

    def validate_skill(self, skill_id: str, gap_id: str) -> ValidationResult:
        """用历史失败案例验证新提交的技能"""
        gap = self._load_gap(gap_id)
        skill = self._load_skill(skill_id)

        results = []
        for failure in gap.sample_errors:
            passed = self._sandbox_test(skill, failure)
            results.append(passed)

        pass_rate = sum(results) / len(results)
        if pass_rate >= 0.7:
            approve_skill(skill_id, quality=pass_rate)
            return ValidationResult(status="approved", pass_rate=pass_rate)
        else:
            reject_skill(skill_id, reason=f"{len(results)-sum(results)}/{len(results)} cases failed")
            return ValidationResult(status="rejected", pass_rate=pass_rate)
```

### 5.4 与执行层的关系

| 伏羲(大脑) | 执行层(手脚) |
|-----------|-------------|
| 发现缺口 | — |
| 打包上下文 → | 收到需求 |
| — | 用 MiniMax 复现并解决 → |
| — | 提取技能 → 提交 |
| ← 收到技能 | — |
| 沙盒验证 | — |
| 效果追踪 | — |

**伏羲不生成一行技能代码。它只做编排。**

### 5.5 资源评估

| 资源 | 量级 |
|------|------|
| 开发工时 | 10-14天 |
| 新增 LLM 调用 | **0** |
| 新增存储 | <1MB（技能需求表 + 验证结果表） |
| 新增模块 | 1（skill_orchestrator.py，~350行） |
| 升级模块 | 2（metacognition.py, skill_market/submission.py） |

---

## 6. 建议五：认知架构自审视（Cognitive Architecture Self-Audit）

### 6.1 概念

当前认知架构（25个引擎的类型、优先级、调度策略）是**人工静态配置**。大脑应该有能力审视自己的思考模式，并提出改进建议。

但注意——这与"自设计"（自动部署新引擎）不同。**自审视是分析和提议；最终决定和执行仍由人类负责。**

```
监控认知效率 → 识别架构瓶颈 → 生成分析报告 → 人类审阅并决策
      ↑                                                    ↓
      └──────────── 持续监控架构健康度 ──────────────────────┘
```

### 6.2 分析维度

```python
class ArchitectureAuditor:
    """认知架构审计 — 分析大脑自身的工作效率"""

    def audit(self) -> AuditReport:
        return AuditReport(
            engine_efficiency=self._rank_engines_by_efficiency(),
            context_gaps=self._find_uncovered_contexts(),
            priority_conflicts=self._detect_priority_conflicts(),
            redundancy_alerts=self._detect_redundancy(),
            recommendations=self._generate_recommendations(),
        )

    def _rank_engines_by_efficiency(self) -> List[EngineRank]:
        """每个引擎的效率 = 有效产出 / 资源消耗"""
        rankings = []
        for engine in get_engine_registry().get_enabled():
            stats = self._collect_stats(engine.name)
            efficiency = (
                stats.useful_outputs /
                (stats.run_count * engine.interval + 1)
            )
            rankings.append(EngineRank(
                name=engine.name,
                efficiency=efficiency,
                run_count=stats.run_count,
                useful_outputs=stats.useful_outputs,
                failure_rate=stats.failure_rate,
            ))
        return sorted(rankings, key=lambda r: r.efficiency)

    def _find_uncovered_contexts(self) -> List[ContextGap]:
        """哪些情境反复出现但没有引擎专门处理它？"""
        # 分析 memory + event 中出现但引擎 run() 从未处理过的 context_type
        ...

    def _detect_redundancy(self) -> List[RedundancyAlert]:
        """两个引擎是否在做同样的事？"""
        # 对比引擎的 run() 输出相似度
        ...

    def _generate_recommendations(self) -> List[Recommendation]:
        """基于以上分析生成建议（文本，非自动执行）"""
        recommendations = []
        for rank in self.rankings:
            if rank.efficiency < 0.1 and rank.run_count > 50:
                recommendations.append(
                    f"引擎 [{rank.name}] 效率极低，建议降低优先级或暂停"
                )
        for gap in self.context_gaps:
            recommendations.append(
                f"情境 [{gap.context_type}] 出现 {gap.frequency} 次但无引擎覆盖"
            )
        return recommendations
```

### 6.3 输出形式

审计报告通过 API `/api/architecture/audit` 暴露，人类通过 Dashboard 查看。**不自动修改任何引擎配置。**

### 6.4 资源评估

| 资源 | 量级 |
|------|------|
| 开发工时 | 8-10天 |
| 新增 LLM 调用 | **0**（纯统计分析） |
| 新增模块 | 1（arch_auditor.py，~300行） |
| 新增测试 | ~10个 |

---

## 7. 综合评估与实施路线

### 7.1 五建议横向对比

| 维度 | 预测世界模型 | 全息记忆 | 情感编排 | 技能编排 | 认知自审 |
|------|:----------:|:-------:|:-------:|:-------:|:-------:|
| **变革性** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **可行性** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **工程量** | 18-22天 | 12-16天 | 8-12天 | 10-14天 | 8-10天 |
| **LLM成本** | ￥0 | ~￥20/月* | ￥0 | ￥0 | ￥0 |
| **架构匹配度** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **风险** | 中 | 低 | 低 | 中* | 低 |

> *全息记忆的 embedding 成本来自多投影编码新增的 API 调用  
> *技能编排的风险在 sandbox 安全，已有成熟方案

### 7.2 推荐实施路径

```
Phase 1 (v2.0-alpha, 2-3周) — 心智基础
  ├── 建议三: 情感驱动行为编排  (8-12天, 最短周期, 最低风险, 最立竿见影)
  └── 建议二: 全息记忆网络      (12-16天, 并行开发, 最大体验提升)
  
  交付: 情感状态不再只是数字，而是真正驱动行为；记忆检索从"猜"变成"建"

Phase 2 (v2.0-beta, 3-4周) — 预测引擎
  └── 建议一: 预测性世界模型    (18-22天, v2.0 最核心能力, 最大架构跃迁)
  
  交付: 大脑从反应式升级为预测式。常见情景响应 <200ms

Phase 3 (v2.0-rc, 2-3周) — 自省与协调
  ├── 建议四: 技能编排中枢      (10-14天)
  └── 建议五: 认知架构自审视    (8-10天, 并行开发)
  
  交付: 大脑能发现自己的不足并主动调度手脚去弥补
```

### 7.3 总资源评估

| 阶段 | 开发工时 | 月LLM成本 | 新增存储 | 新增/升级模块 |
|------|----------|-----------|----------|-------------|
| Phase 1 | ~25天 | ~￥20 | +200MB | 4新 + 5升 |
| Phase 2 | ~20天 | ￥0 | +50MB | 1新 + 1升 |
| Phase 3 | ~22天 | ￥0 | +1MB | 2新 + 2升 |
| **总计** | **~67天** | **~￥20/月** | **~250MB** | **7新 + 8升** |

### 7.4 v2.0 里程碑

| 指标 | v1.5 当前 | v2.0 目标 |
|------|----------|----------|
| 决策模式 | 反应式 | **预测式** (常见情景 <200ms) |
| 检索召回@10 | ~75% | **>90%** |
| 情感-行为闭环 | 断裂 (情感无影响) | **贯通** (情感调制全部引擎) |
| 技能生态 | 被动收技能 | **主动编排** (发现缺口→调度开发→验证) |
| 自我认知 | 引擎状态记录 | **架构效率审计** |
| 测试覆盖 | 384 | **500+** |
| 引擎版本 | 2个v2.0 / 6个v1.5 / 21个v1.0 | **全引擎 ≥v1.5** |

### 7.5 与上一版建议书的关键差异

| 项目 | FX-PROPOSAL-008 (废弃) | FX-PROPOSAL-V2-009 (本版) |
|------|----------------------|--------------------------|
| 架构假设 | 伏羲是全能系统 | 伏羲是大脑中枢，手脚分离 |
| 建议数 | 5 | 5 (但其中1个完全重写) |
| LLM成本 | ~￥230/月 | **~￥20/月** |
| 总工程量 | 85天 | **67天** |
| 提案是否让大脑伸手 | 建议二(是) | **全部为纯大脑能力** |
| 核心升级 | 多维度 | **聚焦: 预测式大脑** |

---

> 关联文档:
> - [FX-EVAL-001-全面系统评估报告](./FX-EVAL-001-全面系统评估报告.md)
> - [FX-ROADMAP-003-迭代升级路线图](./FX-ROADMAP-003-迭代升级路线图.md)
> - [FX-PROPOSAL-008-v2.0核心功能升级建议书](./FX-PROPOSAL-008-v2.0核心功能升级建议书.md)（已废弃）