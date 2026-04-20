# 伏羲 (Fuxi) — 瑾岚阁超级大脑

> 统一记忆系统，融合 MemPalace 归档 + PowerMem 结构化记忆 + 遗忘曲线。
> 四层结构（世界 → 房间 → 抽屉 → 记忆项），支持混合检索（向量 + FTS + 重排序）。

## 架构

```
皮皮/玄武
    ↓ 调用
伏羲 API (http://127.0.0.1:18919)
    ↓
SQLite Fuxi.db ←→ Chroma 向量库
    ↓
ScNet API（Qwen3-Embedding-8B 向量化）
```

## 目录结构

```
fuxi/
├── fuxi_server.py   # HTTP API 服务器（端口 18919）
├── fuxi_core.py     # 核心：SQLite 四层数据模型 + 遗忘曲线
├── fuxi_search.py   # 混合检索引擎（向量 + FTS + RRF 重排序）
├── fuxi_client.py   # Python 客户端（皮皮/玄武调用用）
├── start_fuxi.sh    # 一键启动脚本
├── SKILL.md         # WorkBuddy Agent 技能卡
└── install.sh       # 皮皮一键安装脚本
```

## 快速安装（皮皮用）

皮皮执行：

```bash
cd ~
git clone https://github.com/Mlte0907/fuxi.git fuxi-code
mkdir -p ~/.openclaw/fuxi
cp -r ~/fuxi-code/* ~/.openclaw/fuxi/
cd ~/.openclaw/fuxi
pip install chromadb requests
bash start_fuxi.sh
```

## 手动启动

```bash
mkdir -p ~/.openclaw/fuxi/{chroma,logs}
cp *.py *.sh SKILL.md ~/.openclaw/fuxi/
pip install chromadb requests
python3 ~/.openclaw/fuxi/fuxi_server.py
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/remember` | 存入记忆（自动事实提取 + 向量化） |
| GET | `/search?q=关键词` | 混合检索 |
| GET | `/worlds` | 所有世界列表 |
| GET | `/explore/:world_id` | 浏览世界结构 |
| GET | `/stats` | 统计信息 |

## 四层结构

```
世界 (World)
  └── 房间 (Room)
        └── 抽屉 (Drawer)
              └── 记忆项 (Item) ← raw_text + facts + importance + decay_score + tags
```

## 记忆世界

| 世界 | 用途 |
|------|------|
| `瑾岚阁` | 六使工作记录、架构决策 |
| `叠界` | 《叠界纪元》小说章节/设定 |
| `皮皮专属` | 皮皮的偏好、红线、操作宪章 |

## 皮皮调用规范

**任务开始前** → 查询相关记忆约束行为：
```
GET /search?q=<任务关键词>&top_k=5
```

**任务结束后** → 自动归档产出：
```
POST /remember { world, room, drawer, text, importance, tags }
```

## 技术栈

- **向量引擎**：Chroma（本地持久化）
- **嵌入模型**：ScNet Qwen3-Embedding-8B（可替换）
- **LLM 事实提取**：ScNet Qwen3-30B（可替换）
- **存储**：SQLite + FTS5
- **遗忘曲线**：基于访问频率的指数衰减
