---
name: 伏羲
description: >
  瑾岚阁超级大脑。统一记忆系统，融合 MemPalace 归档能力 + PowerMem 结构化记忆 + 遗忘曲线。
  支持四层结构（世界→房间→抽屉→记忆项）、LLM 事实提炼、混合检索（BM25+向量+重排序）。

  触发词：查记忆、搜索记忆、存档、归档、写入伏羲、伏羲检索、记忆搜索、调用大脑

triggers:
  - 查记忆
  - 搜索记忆
  - 存档
  - 归档
  - 写入伏羲
  - 伏羲检索
  - 记忆搜索
  - 调用大脑
  - 记到记忆宫殿
  - 查伏羲
  - 伏羲写入

inputs:
  type: object
  required:
    - action
  properties:
    action:
      type: string
      enum:
        - search
        - remember
        - explore
        - stats
      description: 操作类型
    query:
      type: string
      description: 检索关键词（search 时必填）
    top_k:
      type: integer
      default: 5
      description: 返回结果数量
    world:
      type: string
      description: 世界名（remember 时必填）
    room:
      type: string
      description: 房间名（remember 时必填）
    drawer:
      type: string
      description: 抽屉名（remember 时必填）
    raw_text:
      type: string
      description: 要存档的原始文本（remember 时必填）
    importance:
      type: number
      default: 0.6
      description: 重要性 0-1
    tags:
      type: array
      items:
        type: string
      description: 标签数组

outputs:
  type: object
  format: structured
  fields:
    status:
      type: string
      description: ok | error
    action:
      type: string
      description: 执行的操作
    data:
      type: object
      description: 操作结果

---

## 服务信息

- **端点**：`http://127.0.0.1:18919`
- **API Key**：`my-powermem-key-2024`（HTTP header: `X-API-Key`）
- **Python 客户端**：`fuxi_client.py`

## 快速使用

### Python 调用

```python
from fuxi_client import FuxiClient
client = FuxiClient()

# 搜索记忆
result = client.search("皮皮总调度", top_k=5)

# 存档记忆
result = client.remember(
    world="瑾岚阁",
    room="调研",
    drawer="朱雀报告",
    text="竞品分析结论：叠界纪元差异化在叙事结构...",
    importance=0.7,
    tags=["朱雀", "调研"]
)

# 浏览结构
result = client.worlds()
result = client.explore("瑾岚阁世界ID")

# 健康检查
result = client.health()
```

### HTTP 直接调用

```bash
# 搜索
curl "http://127.0.0.1:18919/search?q=架构变更&top_k=5"

# 存档
curl -X POST http://127.0.0.1:18919/remember \
  -H "Content-Type: application/json" \
  -d '{"world":"瑾岚阁","room":"架构","drawer":"决策","text":"使用Qwen3替代GPT","importance":0.8}'
```

### 记忆世界参考

| 世界 | 用途 | 可写权限 |
|------|------|---------|
| `瑾岚阁` | 六使工作记录、架构设计、会议结论 | 玄武写入 |
| `叠界` | 《叠界纪元》小说章节、设定、人物 | 玄武写入 |
| `皮皮专属` | 皮皮的偏好、红线、操作宪章、个人记忆 | 仅皮皮 |
| `动漫` | anime-crafter / narrato-anime 项目记忆 | 玄武写入 |

### 世界→房间→抽屉 规范

**瑾岚阁：**
- `瑾岚阁/调研/` — 朱雀产出
- `瑾岚阁/策划/` — 青龙产出
- `瑾岚阁/文圣产出/` — 白虎→文圣产出
- `瑾岚阁/灵智产出/` — 白虎→灵智产出
- `瑾岚阁/安全审查/` — 阴司产出
- `瑾岚阁/质量审核/` — 阳司产出
- `瑾岚阁/架构/` — 系统性变更记录

**叠界：**
- `叠界/章节/` — 小说正文
- `叠界/设定/` — 世界观、人物设定
- `叠界/创作规范/` — 写作风格指南

**皮皮专属：**
- `皮皮专属/操作宪章/红线/` — 绝对红线
- `皮皮专属/操作宪章/架构决策/` — 架构重大决策
- `皮皮专属/偏好/模型配置/` — 模型偏好设置

### 调用时机

**皮皮调用（任务开始前必做）：**
> 每次接收到新任务 → 先调用 `/search?q=<任务关键词>` → 用结果约束自己的行为

**玄武调用（任务结束后自动）：**
> 链路任务完成 → 自动调用 `/remember` → 将产出归档到对应世界/房间/抽屉

**主人直接调用（任意时刻）：**
> "查一下瑾岚阁最近的架构变更" → `/search?q=架构变更&top_k=5`
> "帮我记住这个配置" → `/remember` + 对应 world/drawer

### 错误处理

- `ConnectionRefused` → 伏羲未启动，运行 `bash ~/.bin/start_fuxi.sh`
- `401 Unauthorized` → API Key 错误，检查 header
- 返回空结果 → FTS 未同步或确实无记忆，正常情况
