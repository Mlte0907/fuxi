# 伏羲记忆系统 v1.0 BUG清单与修复方案

> 文档编号: FX-BUG-002  
> 版本: 1.0  
> 日期: 2026-05-11  
> 关联文档: [FX-EVAL-001-全面系统评估报告](./FX-EVAL-001-全面系统评估报告.md)  

---

## 目录

1. [严重BUG (P0)](#1-严重bug-p0)
2. [设计缺陷 (P1)](#2-设计缺陷-p1)
3. [代码冗余/死代码 (P2)](#3-代码冗余死代码-p2)
4. [紧急修复实施方案](#4-紧急修复实施方案)

---

## 1. 严重BUG (P0)

### BUG-001: DecisionExecutor.ACTION_HANDLERS 为空字典

| 属性 | 值 |
|------|-----|
| 编号 | BUG-001 |
| 优先级 | P0 — 核心功能失效 |
| 位置 | `fuxi/decision/executor.py` 第14行 |
| 影响范围 | 整个自主决策系统 |
| 状态 | ❌ 未修复 |

**问题描述**:

`DecisionExecutor.ACTION_HANDLERS: Dict[str, callable] = {}` 是空字典。`DecisionEngine` 生成的决策方案（如 `memory_cleanup`, `engine_priority_adjust`, `attention_reallocate`, `proactive_notify`, `agent_delegate`）**永远无法被真正执行**。`DecisionExecutor.execute()` 在第32行返回 `"No handler"` 错误。

**复现路径**:

```
1. DecisionEngine.run() 检测到情境（如记忆膨胀 >500条）
2. 生成 DecisionOption（action_type="memory_cleanup"）
3. DecisionFramework.evaluate_options() 评估并 APPROVED
4. DecisionExecutor.execute() 查找 ACTION_HANDLERS["memory_cleanup"]
5. 返回 {"status": "error", "reason": "No handler for memory_cleanup"}
```

**影响**: 整个自主决策系统形同虚设，所有决策永远无法执行。

---

### BUG-002: BehaviorCollector 未接入 EventBus

| 属性 | 值 |
|------|-----|
| 编号 | BUG-002 |
| 优先级 | P0 — 核心功能失效 |
| 位置 | `fuxi/adaptive/signals.py` 第21-28行 |
| 影响范围 | 整个自适应学习系统 |
| 状态 | ❌ 未修复 |

**问题描述**:

`BehaviorCollector.on_event()` 定义了事件处理逻辑（处理 `memory.accessed`, `search.query` 等9种信号），但**从未被任何地方注册到 EventBus**。`get_behavior_collector()` 被 `AdaptiveEngine` 调用，但采集器内部的 `_counters` 永远是空的。

**影响链路**:

```
BehaviorCollector._counters 为空
    → get_signal_rates() 返回全0
        → get_user_profile_signals() 所有信号为0
            → AdaptiveEngine.ADAPTATION_RULES 条件永远不满足
                → 自适应参数永远不调整
```

**影响**: `AdaptiveEngine` 的自适应调参功能完全失效，系统无法根据用户行为模式优化自身参数。

---

### BUG-003: remember() 去重检查仅扫描最近50条

| 属性 | 值 |
|------|-----|
| 编号 | BUG-003 |
| 优先级 | P0 — 数据正确性 |
| 位置 | `fuxi/memory/ingestion.py` 第99-101行 |
| 影响范围 | 记忆去重准确性 |
| 状态 | ❌ 未修复 |

**问题描述**:

`_find_duplicate` 的语义相似度检查只 `LIMIT 50`，当记忆库增长到成千上万条时，大量旧记忆不会被检查，可能导致重复摄入。特别是长期记忆（longterm抽屉）中的重要知识可能被重复写入。

**影响**: 记忆库膨胀，相同/相似内容重复存储，浪费存储空间且降低搜索质量。

---

## 2. 设计缺陷 (P1)

### BUG-004: MemoryJudge 与 ReasoningEngine 的 OpenClawAdapter 调用格式不一致

| 属性 | 值 |
|------|-----|
| 编号 | BUG-004 |
| 优先级 | P1 — 功能可靠性 |
| 位置 | `fuxi/memory/judge.py` 第89-102行 vs `fuxi/engines/reasoning.py` 第236行 |
| 状态 | ❌ 未修复 |

**问题描述**:

- `MemoryJudge._call_llm()` 调用 `adapter.call_agent(agent_id="persona", message=prompt)`，检查 `"reply" in response`
- `ReasoningEngine._synthesize()` 调用 `adapter.call_agent("qinglong", prompt)`，检查 `result.get("status") == "ok"`

两种调用方式使用不同的参数命名和返回格式检查，API响应格式不统一，可能导致其中一个或两个调用失败。

---

### BUG-005: recall() 缓存键不包含 min_importance 参数

| 属性 | 值 |
|------|-----|
| 编号 | BUG-005 |
| 优先级 | P1 — 数据正确性 |
| 位置 | `fuxi/memory/retrieval.py` 第30-32行 |
| 状态 | ❌ 未修复 |

**问题描述**:

`_make_cache_key` 的参数列表为 `(query, drawer_id, limit, offset, agent_id, sort_by)`，不包含 `min_importance`。如果两次调用 `min_importance` 不同但其他参数相同，可能返回错误缓存结果。

**示例**:

```python
# 第一次调用
recall(query="AI", min_importance=0.5)  # 返回高重要性记忆

# 第二次调用（缓存命中，但 min_importance=0.0）
recall(query="AI", min_importance=0.0)  # 错误地返回第一次的高重要性结果
```

---

### BUG-006: ReflectionEngine 缺少记忆写入频率限制

| 属性 | 值 |
|------|-----|
| 编号 | BUG-006 |
| 优先级 | P1 — 系统稳定性 |
| 位置 | `fuxi/engines/reflection.py` 第73-90行 |
| 状态 | ❌ 未修复 |

**问题描述**:

`SoulEngine` 有每日写入上限（10条自省记忆），但 `ReflectionEngine` 没有类似限制。每15分钟运行一次，每次最多写入3条疑问+1条建议，理论上每天可写入 `(3+1) * 96 = 384` 条自省记忆。这些记忆又会被其他引擎处理，可能导致记忆库膨胀。

---

### BUG-007: 自适应参数可能陷入负反馈循环

| 属性 | 值 |
|------|-----|
| 编号 | BUG-007 |
| 优先级 | P1 — 系统稳定性 |
| 位置 | `fuxi/engines/adaptive.py` 第127-135行 |
| 状态 | ❌ 未修复 |

**问题描述**:

`AdaptiveEngine._apply_params()` 直接修改 `config` 对象的属性，但没有防止参数漂移的保护机制。如果信号采集错误（如BUG-002导致信号恒为0），参数可能逐步偏离最优值。即使BUG-002修复后，如果行为信号被噪声干扰，参数也可能在错误方向上持续调整。

---

## 3. 代码冗余/死代码 (P2)

### DEAD-001: ImmuneEngine._on_eviction 双重处理

| 属性 | 值 |
|------|-----|
| 编号 | DEAD-001 |
| 位置 | `fuxi/engines/immune.py` 第22-41行 |
| 类型 | 冗余调用 |

**问题**: 事件处理器中第41行 `self._on_event(event)` 被调用，但 `_on_event` 只是把事件放入 pending 队列。在 `remember()` 调用之后再次调用 `_on_event` 无实际意义，因为 eviction 事件已经被处理了。

---

### DEAD-002: OpenClawMemoryEngine._on_engine_executed 为空

| 属性 | 值 |
|------|-----|
| 编号 | DEAD-002 |
| 位置 | `fuxi/engines/openclaw_memory.py` 第37-40行 |
| 类型 | 空方法 |

**问题**: 方法体中只有 `pass`，没有任何实际逻辑。订阅了 `engine.executed` 事件但无处理。

---

### DEAD-003: EmotionEngine.frustration 计算结果未被消费

| 属性 | 值 |
|------|-----|
| 编号 | DEAD-003 |
| 位置 | `fuxi/engines/emotion.py` 第123-169行 |
| 类型 | 无消费者 |

**问题**: `_calc_frustration` 实现详细（3个信号源），但 `frustration` 值仅存储在 `engine_states` 中，**没有被任何决策或行动引擎消费**。计算了但无人使用。

---

### DEAD-004: config.feishu_app_secret 硬编码

| 属性 | 值 |
|------|-----|
| 编号 | DEAD-004 |
| 位置 | `fuxi/config.py` 第86行 |
| 类型 | 安全隐患 |

**问题**: `feishu_app_secret: str = "EuyPNvpHeHUGJUvJiLhbEhIB0yXSeuVh"` — 密钥硬编码在源代码中，且由安全引擎扫描也检测不到（因为不是从记忆/配置文件中读取的）。

---

### DEAD-005: ReasoningEngine 双套逻辑冗余

| 属性 | 值 |
|------|-----|
| 编号 | DEAD-005 |
| 位置 | `fuxi/engines/reasoning.py` 第224-289行 |
| 类型 | 逻辑冗余 |

**问题**: `_synthesize` 和 `_template_fallback` 之间的协调较弱，两套逻辑重复处理同一种问题类型。应统一为一套可配置的推理链。

---

## 4. 紧急修复实施方案

### 4.1 修复 BUG-001: 实现 DecisionExecutor ACTION_HANDLERS

**步骤**:

| 步骤 | 操作 | 文件 | 预期结果 |
|------|------|------|----------|
| 1 | 创建处理器函数 | `fuxi/decision/handlers.py` | 5个核心处理器实现 |
| 2 | 在模块加载时注册 | `fuxi/decision/__init__.py` | import时自动注册 |
| 3 | 添加集成测试 | `tests/test_decision.py` | 决策可端到端执行 |

**实施代码**:

```python
# fuxi/decision/handlers.py

from fuxi.decision.executor import DecisionExecutor


def handle_memory_cleanup(params: dict) -> dict:
    from fuxi.memory.decay import purge_below_floor
    result = purge_below_floor(dry_run=False)
    return {"status": "ok", "purged": result["purged"]}


def handle_engine_priority_adjust(params: dict) -> dict:
    from fuxi.engines.base import get_engine_registry
    engine_name = params.get("engine")
    priority = params.get("priority")
    reg = get_engine_registry()
    engine = reg.get(engine_name)
    if engine:
        engine.priority = priority
        return {"status": "ok", "engine": engine_name, "new_priority": priority}
    return {"status": "error", "reason": f"Engine {engine_name} not found"}


def handle_attention_reallocate(params: dict) -> dict:
    from fuxi.kernel.attention import get_attention_system, AttentionStrategy
    strategy_name = params.get("strategy", "explore")
    attn = get_attention_system()
    attn.switch(AttentionStrategy(strategy_name), "decision_engine")
    return {"status": "ok", "strategy": strategy_name}


def handle_proactive_notify(params: dict) -> dict:
    from fuxi.memory.ingestion import remember
    message = params.get("message", "")
    importance = params.get("importance", 0.5)
    item_id = remember(
        raw_text=f"[决策通知] {message}",
        drawer_id="longterm",
        importance=importance,
        source="decision",
        created_by="decision_engine",
        tags=["决策通知", "proactive"],
    )
    return {"status": "ok", "notified": True, "item_id": item_id}


def handle_agent_delegate(params: dict) -> dict:
    agent_id = params.get("agent_id", "")
    message = params.get("message", "")
    try:
        from fuxi.agent.integration import OpenClawAdapter
        adapter = OpenClawAdapter()
        result = adapter.call_agent(agent_id, message)
        return {"status": "ok", "agent": agent_id, "result": result}
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def register_all_handlers():
    DecisionExecutor.register_handler("memory_cleanup", handle_memory_cleanup)
    DecisionExecutor.register_handler("engine_priority_adjust", handle_engine_priority_adjust)
    DecisionExecutor.register_handler("attention_reallocate", handle_attention_reallocate)
    DecisionExecutor.register_handler("proactive_notify", handle_proactive_notify)
    DecisionExecutor.register_handler("agent_delegate", handle_agent_delegate)
```

```python
# fuxi/decision/__init__.py — 添加自动注册

from fuxi.decision.handlers import register_all_handlers
register_all_handlers()
```

**验证方法**:

```python
# tests/test_decision.py

def test_memory_cleanup_handler():
    from fuxi.decision.handlers import handle_memory_cleanup
    result = handle_memory_cleanup({})
    assert result["status"] == "ok"

def test_decision_e2e():
    from fuxi.decision.framework import Decision, DecisionOption, DecisionStatus
    from fuxi.decision.executor import DecisionExecutor
    decision = Decision(
        id="test",
        options=[DecisionOption(
            id="cleanup_low_value",
            description="清理低衰减分记忆",
            action_type="memory_cleanup",
            risk_level=0.2,
            cost_estimate=0.3,
            confidence=0.8,
        )],
    )
    from fuxi.decision.framework import DecisionFramework
    framework = DecisionFramework()
    decision = framework.evaluate_options(decision)
    assert decision.status == DecisionStatus.APPROVED
    executor = DecisionExecutor()
    result = executor.execute(decision)
    assert result["status"] == "ok"
```

---

### 4.2 修复 BUG-002: 接入 BehaviorCollector 到 EventBus

**步骤**:

| 步骤 | 操作 | 文件 | 预期结果 |
|------|------|------|----------|
| 1 | 在 lifespan.start() 中注册采集器 | `fuxi/kernel/lifespan.py` | 9种信号事件被采集 |
| 2 | 在 API 层发布搜索事件 | `fuxi/api/routes_memory.py` | search.query/refine 事件发布 |
| 3 | 添加信号采集测试 | `tests/test_adaptive.py` | 信号采集率 > 0 |

**实施代码**:

```python
# fuxi/kernel/lifespan.py — start() 方法中添加

def start(self):
    logger.info("Lifespan starting...")
    for hook in self._startup_hooks:
        try:
            hook()
        except Exception as e:
            logger.error(f"Startup hook failed: {e}")

    from fuxi.api.ws import setup_event_bridge
    setup_event_bridge()

    from fuxi.adaptive.signals import get_behavior_collector, BEHAVIOR_SIGNALS
    from fuxi.kernel.event_bus import get_event_bus
    collector = get_behavior_collector()
    bus = get_event_bus()
    for signal_type in BEHAVIOR_SIGNALS:
        bus.subscribe(signal_type, collector.on_event)
    logger.info(f"BehaviorCollector subscribed to {len(BEHAVIOR_SIGNALS)} signal types")

    self._running = True
```

```python
# fuxi/api/routes_memory.py — search_memories() 中添加事件发布

@router.get("/memories/search")
@router.post("/memories/search")
async def search_memories(
    q: str = Query(..., min_length=1), drawer_id: Optional[str] = None,
    limit: int = 20, offset: int = 0, agent_id: Optional[str] = None,
    tags: Optional[str] = None, min_score: float = 0.0
):
    tag_list = tags.split(",") if tags else None
    get_event_bus().publish(Event(
        type="search.query",
        data={"query": q, "drawer_id": drawer_id},
        priority=EventPriority.LOW,
        source="api:memory",
    ))
    result = search(query=q, drawer_id=drawer_id, limit=limit,
                    offset=offset, agent_id=agent_id,
                    tags=tag_list, min_score=min_score)
    return ApiResponse.ok(result)
```

---

### 4.3 修复 BUG-003: 改进去重检查范围

**步骤**:

| 步骤 | 操作 | 文件 | 预期结果 |
|------|------|------|----------|
| 1 | 使用向量索引加速候选集筛选 | `fuxi/memory/ingestion.py` | 去重覆盖全库 |
| 2 | 添加抽屉级别去重 | `fuxi/memory/ingestion.py` | 同抽屉优先检查 |

**实施代码**:

```python
# fuxi/memory/ingestion.py — _find_duplicate() 改进

def _find_duplicate(raw_text: str, drawer_id: str = "default") -> Optional[dict]:
    pool = get_pool()
    # Step 1: 精确匹配
    row = pool.fetchone(
        "SELECT id, raw_text FROM items WHERE raw_text = ? AND archived = 0 LIMIT 1",
        (raw_text,)
    )
    if row:
        return dict(row)

    # Step 2: 语义相似度 — 优先使用向量索引
    embed = get_embedding_service()
    query_vec = embed.embed(raw_text)
    if query_vec is None:
        return None

    # 尝试使用向量索引加速
    try:
        from fuxi.memory.vector_index import get_vector_index
        vix = get_vector_index()
        if vix.is_built and vix.size > 0:
            candidates = vix.search(query_vec, top_k=20)
            if candidates:
                id_list = [item_id for item_id, _ in candidates]
                placeholders = ",".join("?" * len(id_list))
                rows = pool.fetchall(
                    f"SELECT id, raw_text, embedding FROM items "
                    f"WHERE id IN ({placeholders}) AND archived = 0",
                    id_list
                )
                best_score = 0.0
                best_row = None
                for r in rows:
                    if not r["embedding"]:
                        continue
                    try:
                        stored_vec = json.loads(r["embedding"])
                        score = _cosine_sim(query_vec, stored_vec)
                        if score > 0.92 and score > best_score:
                            best_score = score
                            best_row = dict(r)
                    except Exception:
                        continue
                if best_row:
                    logger.info(f"Semantic duplicate found (via index): score={best_score:.3f}")
                    return best_row
    except Exception:
        pass

    # Step 3: 降级为同抽屉扫描（扩大到200条）
    rows = pool.fetchall(
        "SELECT id, raw_text, embedding FROM items "
        "WHERE archived = 0 AND drawer_id = ? ORDER BY created_at DESC LIMIT 200",
        (drawer_id,)
    )
    best_score = 0.0
    best_row = None
    for r in rows:
        if not r["embedding"]:
            continue
        try:
            stored_vec = json.loads(r["embedding"])
            score = _cosine_sim(query_vec, stored_vec)
            if score > 0.92 and score > best_score:
                best_score = score
                best_row = dict(r)
        except Exception:
            continue
    if best_row:
        logger.info(f"Semantic duplicate found (scan): score={best_score:.3f}")
        return best_row

    return None
```

---

### 4.4 修复 BUG-005: recall() 缓存键包含 min_importance

**实施代码**:

```python
# fuxi/memory/retrieval.py — recall() 中修改缓存键生成

def recall(query: Optional[str] = None, drawer_id: Optional[str] = None, limit: int = 10,
           offset: int = 0, agent_id: Optional[str] = None, min_importance: float = 0.0,
           sort_by: str = "relevance", use_cache: bool = True,
           vector_weight: Optional[float] = None) -> List[dict]:
    if vector_weight is None:
        vector_weight = config.vector_weight_default

    cache_key = None
    if use_cache and query:
        cache_key = _make_cache_key(query, drawer_id, limit, offset,
                                     agent_id, sort_by, min_importance)
        # ... 后续不变
```

---

### 4.5 修复 DEAD-004: 移除硬编码密钥

**实施代码**:

```python
# fuxi/config.py — 修改飞书密钥配置

# 修改前:
# feishu_app_secret: str = "EuyPNvpHeHUGJUvJiLhbEhIB0yXSeuVh"

# 修改后:
feishu_app_secret: str = ""
```

密钥应通过环境变量 `FUXI_FEISHU_APP_SECRET` 或 `.openclaw/keys/fuxi.env` 文件注入。

---

### 4.6 修复汇总与优先级

| 编号 | 优先级 | 修复工作量 | 依赖关系 | 预期完成时间 |
|------|--------|-----------|----------|-------------|
| BUG-001 | P0 | 中 (2h) | 无 | 立即 |
| BUG-002 | P0 | 小 (0.5h) | 无 | 立即 |
| BUG-003 | P0 | 中 (1.5h) | 向量索引可用 | 立即 |
| BUG-004 | P1 | 小 (0.5h) | OpenClawAdapter接口统一 | 1周内 |
| BUG-005 | P1 | 小 (0.5h) | 无 | 1周内 |
| BUG-006 | P1 | 小 (0.5h) | 无 | 1周内 |
| BUG-007 | P1 | 中 (2h) | BUG-002修复后 | 2周内 |
| DEAD-001 | P2 | 小 (0.2h) | 无 | 随迭代 |
| DEAD-002 | P2 | 小 (0.2h) | 无 | 随迭代 |
| DEAD-003 | P2 | 中 (1h) | 决策引擎完善后 | 随迭代 |
| DEAD-004 | P2 | 小 (0.2h) | 无 | 立即 |
| DEAD-005 | P2 | 中 (1h) | 无 | 随迭代 |

---

> 相关文档:
> - [全面系统评估报告](./FX-EVAL-001-全面系统评估报告.md)
> - [迭代升级路线图](./FX-ROADMAP-003-迭代升级路线图.md)
