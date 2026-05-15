# 伏羲 (Fuxi) - Personal AI Memory System

> 伏羲是中国神话中的人文始祖，创造了八卦、文字、历法，开创了华夏文明。伏羲系统以此命名，寓意：让 AI 拥有记忆、能够推理、持续进化，成为真正的个人智能助理。

**伏羲**是一个具有长期记忆的 Personal AI 认知助理，基于 Python 开发，具备四层记忆架构、36+ 可插拔认知引擎，支持多模型路由、飞书集成、WebSocket 实时通信。

---

## 核心能力

### 🧠 四层记忆架构

| 层级 | 功能 | 说明 |
|------|------|------|
| **感官记忆** | 原始输入捕获 | 实时接收并解析各类输入源 |
| **工作记忆** | 短期焦点记忆 | 容量受限，动态淘汰低价值记忆 |
| **长期记忆** | 重要性加权的持久存储 | 基于重要性评分 + 衰减算法自动遗忘 |
| **知识图谱** | 实体发现与关系推理 | 从记忆中自动抽取实体和关系构成 DAG |

### 🔧 36+ 可插拔认知引擎

引擎采用注册制，每个引擎独立运行、按优先级调度，支持热插拔。

**核心引擎（essential tier，7 个）**

| 引擎 | 功能 |
|------|------|
| `cognitive_loop` | 主循环引擎，协调所有引擎运行 |
| `decay` | 记忆衰减引擎，自动淘汰低价值记忆 |
| `perception` | 多模态感知，整合文本/语音/图像输入 |
| `soul` | 灵魂引擎，核心价值观与人格一致性维护 |
| `metacognition` | 元认知引擎，自我反思与学习策略优化 |
| `safety` | 安全引擎，内容过滤与边界控制 |
| `dialogue` | 对话引擎，管理多轮对话上下文 |

**标准引擎（standard tier，+7 个，共 14 个）**

| 引擎 | 功能 |
|------|------|
| `jinlange_ingestion` | 瑾岚阁采集，持续从飞书会话中提取记忆 |
| `reasoning` | 推理引擎，链式思维和逻辑推导 |
| `distill` | 知识蒸馏，从记忆中生成结构化知识卡片 |
| `dream` | 梦境整合，睡眠期间的记忆碎片重组 |
| `immune` | 免疫引擎，识别并纠正错误记忆 |
| `emotion` | 情感引擎，情感状态追踪与响应 |
| `emotion_orchestrator` | 情感编排器，协调多维度情感计算 |

**高级引擎（advanced tier，+11 个，共 25 个）**

| 引擎 | 功能 |
|------|------|
| `creative` | 创意生成引擎 |
| `narrative` | 叙事引擎，生成故事和报告 |
| `proactive` | 主动引擎，主动探索和发现 |
| `resonance` | 共情引擎，深度情感理解 |
| `prediction` | 预测引擎，时间序列分析与预取 |
| `decision` | 决策引擎，支持回滚的决策框架 |
| `persona` | 人格引擎，动态人格调整 |
| `adaptive` | 自适应引擎，参数动态调优 |
| `reconsolidation` | 再巩固引擎，记忆强化与修正 |
| `reflection` | 反思引擎，定期自我复盘 |
| `nudge` | 轻推引擎，行为引导建议 |
| `curiosity` | 好奇心引擎，主动知识探索 |
| `openclaw_memory` | OpenClaw 记忆同步 |
| `skill_evolution` | 技能进化引擎，AI 技能自优化 |

**基础设施引擎（+11 个，共 36+ 个）**

| 引擎 | 功能 |
|------|------|
| `world_model` | 因果预测世界模型，情景推演 + 预案生成 |
| `skill_orchestrator` | 技能编排器，管理 AI 技能生命周期 |
| `arch_auditor` | 架构审计器，审查系统架构合理性 |
| `knowledge_miner` | 知识挖掘，自动分类沉淀到飞书知识库 |
| `feishu_kb` | 飞书知识库，搜索/索引/检索飞书文档 |
| `feishu_im` | 飞书 IM 机器人，消息收发 |
| `causal` | 因果引擎，构建因果 DAG 图 |
| `decay` | 衰减引擎（已在 core） |
| `soul` | 灵魂引擎（已在 core） |
| `reconsolidation` | 再巩固（已在 advanced） |
| `reflection` | 反思（已在 advanced） |

### 🌐 多模型智能路由

内置 Anthropic API 代理，自动根据场景选择最优模型：

| 场景 | 模型 | 策略 |
|------|------|------|
| 主会话 / Sonnet / Opus | MiniMax-M2.7 | 套餐，省 token |
| DeepSeek / Haiku / Coding | DeepSeek V4 Pro | Token 付费 |
| DeepSeek 429 时 | OpenRouter | 自动兜底 |

Token 消耗自动追踪记录。

### 💬 飞书深度集成

- **飞书 IM Bot**：实时消息收发，支持 WebSocket 长连接
- **飞书知识库**：自动将高价值记忆沉淀到 Wiki，支持分类自动创建
- **瑾岚阁会话采集**：持续从飞书群聊中提取有价值信息存入记忆

### 📊 可观测性

- **健康检查**：所有引擎支持 `/api/v2/engine/health/{name}` 健康端点
- **Token 预算追踪**：自动记录每次 API 调用的 token 消耗
- **上下文预算**：防止上下文窗口溢出
- **事件日志**：错误/警告实时记录到 event_log

---

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                      伏羲 API Server                     │
│              FastAPI :19528 / WebSocket :19528            │
├─────────────────────────────────────────────────────────┤
│  Anthropic Proxy  │  Token Budget  │  Engine Health   │
├────────────────┬──────────────────┬──────────────────────┤
│   Memory Store  │  Cognitive Loop │  36+ Engines       │
│   ────────────  │   (优先级调度)  │  ────────────────  │
│   SQLite / PG   │                 │  perception        │
│   向量索引       │                 │  emotion          │
│   知识图谱       │                 │  reasoning        │
│                 │                 │  knowledge_miner  │
│                 │                 │  feishu_kb        │
│                 │                 │  world_model       │
│                 │                 │  ...              │
└────────────────┴──────────────────┴──────────────────────┘
         │                                    │
         ▼                                    ▼
┌─────────────────┐               ┌─────────────────────┐
│  飞书 IM Bot    │               │  飞书知识库 Wiki   │
│  WebSocket 连接  │               │  lark-cli           │
└─────────────────┘               └─────────────────────┘
```

---

## 快速开始

### 环境要求

- Python 3.10+
- SQLite（默认）或 PostgreSQL + pgvector（可选）
- lark-cli（飞书知识库功能可选）

### 1. 克隆项目

```bash
git clone https://github.com/Mlte0907/fuxi.git
cd fuxi
```

### 2. 安装依赖

```bash
pip install -e .
```

### 3. 配置环境变量

```bash
cp env.example .env
# 编辑 .env 填入你的 API keys
```

主要配置项：

| 变量 | 说明 |
|------|------|
| `FUXI_API_KEY` | API 访问密钥（保护本地服务器） |
| `MINIMAX_API_KEY` | MiniMax LLM（主会话） |
| `DEEPSEEK_API_KEY` | DeepSeek LLM（编程/子代理） |
| `OPENROUTER_API_KEY` | OpenRouter（限流兜底） |
| `SILICONFLOW_KEY` | 向量嵌入服务 |
| `FEISHU_APP_ID` / `FEISHU_APP_SECRET` | 飞书机器人凭证 |
| `FUXI_FEISHU_WIKI_SPACE_ID` | 飞书知识库 Space ID |
| `FUXI_FEISHU_WIKI_ROOT_NODE` | 飞书知识库根目录 Token |

### 4. 启动服务

```bash
python -m fuxi.api.server
# 服务运行在 http://localhost:19528
```

### 5. 运行测试

```bash
pytest tests/ -v
# 439+ 测试用例
```

---

## API 路由示例

```bash
# 存储记忆
curl -X POST http://localhost:19528/api/v2/memories \
  -H "X-API-Key: your_key" \
  -d '{"content": "用户说今天要去开会", "importance": 0.8, "tags": ["meeting"]}'

# 检索相关记忆
curl -X POST http://localhost:19528/api/v2/memory/recall \
  -H "X-API-Key: your_key" \
  -d '{"query": "用户最近有什么安排？"}'

# 查看所有引擎状态
curl http://localhost:19528/api/v2/engines \
  -H "X-API-Key: your_key"
```

---

## 引擎分层机制

伏羲采用引擎分层（tier）机制，可以按需启用不同复杂度的引擎组合：

| 分层 | 引擎数 | 包含内容 |
|------|--------|---------|
| `essential` | 7 | 核心循环、安全、对话 |
| `standard` | 14 | + 感知、推理、情感、梦境蒸馏 |
| `advanced` | 25 | + 创意、预测、决策、好奇心 |
| `all` | 36+ | 全部引擎（含实验性） |

```bash
# 启动时指定分层
ENGINE_TIER=advanced python -m fuxi.api.server
```

---

## 知识挖掘引擎详解

`knowledge_miner` 是伏羲的自动知识沉淀引擎，工作流程：

1. **扫描**：`importance >= 0.7` 的未归档记忆
2. **提炼**：通过 LLM 提取核心要点（100-200字摘要）
3. **分类**：根据 `drawer + tags` 自动推断分类
   - `longterm:wm_eviction` → 系统事件
   - `default:python` → 技术笔记
   - `default:cooking` → 生活记录
   - 其他 → 工作记录
4. **上传**：创建飞书 Wiki 页面到对应分类

每次运行前自动清理旧页面，同一分类下只保留最新沉淀文档，已上传记忆自动归档（不重复上传）。

---

## 项目结构

```
fuxi/
├── fuxi/
│   ├── api/                    # FastAPI 路由层
│   │   ├── server.py          # 主入口
│   │   ├── routes_anthropic_proxy.py  # Anthropic 模型代理
│   │   ├── routes_bridge.py   # Claude Code 桥接
│   │   ├── routes_memory.py    # 记忆 CRUD
│   │   ├── routes_engines.py   # 引擎管理
│   │   └── ws.py               # WebSocket
│   ├── engines/                # 36+ 认知引擎
│   │   ├── base.py             # 引擎基类 + 注册表
│   │   ├── cognitive_loop.py   # 主循环
│   │   ├── perception.py        # 多模态感知
│   │   ├── emotion.py          # 情感处理
│   │   ├── reasoning.py        # 推理引擎
│   │   ├── world_model.py      # 因果世界模型
│   │   ├── knowledge_miner.py  # 知识挖掘
│   │   └── feishu_kb.py        # 飞书知识库
│   ├── memory/                 # 记忆存储层
│   │   ├── embedding.py        # 向量嵌入
│   │   ├── graph.py            # 知识图谱
│   │   ├── decay.py            # 衰减算法
│   │   └── retrieval.py        # 检索算法
│   ├── kernel/                 # 内核
│   │   ├── attention.py        # 注意力机制
│   │   └── working_memory.py   # 工作记忆
│   ├── observability/          # 可观测性
│   │   ├── health.py           # 健康检查
│   │   ├── metrics.py          # 指标采集
│   │   └── logging.py          # 结构化日志
│   ├── store/                  # 数据持久化
│   │   └── connection.py       # SQLite / PG 连接
│   ├── auth/                   # 认证鉴权
│   ├── adaptive/               # 自适应参数
│   ├── decision/                # 决策框架
│   ├── compat/                 # 兼容适配器（Claude/OpenCode）
│   ├── skill_market/           # 技能市场
│   ├── desktop_life/           # 桌面集成（语音/TTS/唤醒词）
│   └── privacy/                # 隐私保护
├── fuxi_scripts/              # 工具脚本
│   ├── upload_context.py       # 上下文上传
│   ├── health_scan.py          # 健康扫描
│   └── hooks/                  # Claude Code Hooks
├── tests/                      # 测试套件（439+）
├── docs/                       # 设计文档
├── fuxi_personas/             # 人格定义（10个角色）
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## 技术亮点

- **四层记忆架构**：从原始感觉到结构化知识，完整模拟人类记忆机制
- **引擎注册制**：36+ 独立引擎通过 `@register_engine` 自动注册，热插拔
- **重要性衰减算法**：基于指数衰减的记忆管理，自动淘汰低价值信息
- **因果 DAG**：从事件序列中自动构建因果关系图，支持反事实推理
- **多模型路由**：MiniMax 套餐 + DeepSeek Token + OpenRouter 兜底，成本最优
- **飞书知识库自动沉淀**：无需人工干预，AI 自主判断分类并上传 Wiki
- **Engine Tier 分层**：essential / standard / advanced / all，按需启用
- **WebSocket 实时通信**：支持流式输出和工具调用进度实时显示

---

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| v1.5.0 | 2026-05-12 | +5 引擎（world_model、emotion_orchestrator 等），引擎总数 36 个 |
| v1.1.0 | 2026-05-11 | 情感系统非线性化、多模态感知、元学习、好奇心引擎 |
| v1.0.0 | 2026-04-20 | 初始版本 |

---

## License

MIT
