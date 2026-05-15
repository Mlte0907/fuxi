# 伏羲 (Fuxi) - Personal AI Memory System

> A personal AI cognitive assistant with long-term memory, built in Python.

## Overview

Fuxi is a personal AI memory system designed to remember, reason, and assist. It features a 4-layer memory architecture (sensory / short-term / long-term / knowledge graph), 36+ pluggable cognitive engines, and a FastAPI server with Anthropic proxy routing.

## Features

- **4-Layer Memory Architecture**
  - Sensory memory: Raw input capture
  - Working memory: Short-term focus with capacity limits
  - Long-term memory: Importance-weighted retention with decay
  - Knowledge graph: Entity and relation discovery

- **36+ Cognitive Engines**
  - Core: `cognitive_loop`, `perception`, `soul`, `metacognition`, `safety`, `dialogue`, `reasoning`, `distill`, `dream`, `emotion`
  - Advanced: `creative`, `narrative`, `proactive`, `resonance`, `prediction`, `decision`, `persona`, `adaptive`, `reconsolidation`, `reflection`, `nudge`, `curiosity`, `skill_evolution`
  - Infrastructure: `world_model`, `emotion_orchestrator`, `skill_orchestrator`, `arch_auditor`, `knowledge_miner`, `causal`, `decay`, `feishu_kb`

- **API Server** — FastAPI on port 19528
  - Anthropic proxy routing (MiniMax / DeepSeek / OpenRouter)
  - Token budget tracking
  - REST + WebSocket endpoints

- **Storage**
  - SQLite (default) with items table
  - PostgreSQL + pgvector support for production

## Quick Start

### 1. Install Dependencies

```bash
pip install -e fuxi/
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Start the Server

```bash
python -m fuxi.api.server
# Server runs on http://localhost:19528
```

### 4. Run Tests

```bash
pytest tests/ -v
```

## Configuration

All configuration is via environment variables. See `.env.example` for the full list.

| Variable | Description | Default |
|----------|-------------|---------|
| `FUXI_API_KEY` | API access key | — |
| `SILICONFLOW_KEY` | Vector embedding API key | — |
| `MINIMAX_API_KEY` | MiniMax LLM API key | — |
| `DEEPSEEK_API_KEY` | DeepSeek LLM API key | — |
| `OPENROUTER_API_KEY` | OpenRouter API key (fallback) | — |
| `FEISHU_APP_ID` | Feishu bot App ID | — |
| `FEISHU_APP_SECRET` | Feishu bot App Secret | — |
| `FUXI_BASE_DIR` | Fuxi data directory | `~/.openclaw/fuxi_v1` |
| `FUXI_ENGINE_TIER` | Engine tier (essential/standard/advanced/all) | `standard` |
| `FUXI_LOG_LEVEL` | Log level | `INFO` |

## Architecture

```
fuxi/
├── api/                  # FastAPI routes
│   ├── server.py         # Main server entry
│   ├── routes_anthropic_proxy.py  # LLM proxy router
│   ├── routes_bridge.py  # Claude Code bridge
│   └── ws.py             # WebSocket endpoint
├── engines/              # 36+ cognitive engines
│   ├── cognitive_loop.py # Main loop engine
│   ├── emotion.py        # Emotional processing
│   ├── perception.py     # Multi-modal perception
│   ├── knowledge_miner.py # Feishu wiki mining
│   ├── feishu_kb.py      # Feishu knowledge base
│   └── feishu_im.py      # Feishu IM integration
├── kernel/               # Core memory system
│   ├── sensory.py        # Sensory memory
│   ├── working_memory.py # Working memory
│   └── longterm_memory.py # Long-term memory
├── memory/               # Storage layer
│   ├── items.py          # SQLite items table
│   ├── embedding.py      # Vector embeddings
│   └── graph.py          # Knowledge graph
├── observability/        # Observability
│   ├── cost_tracker.py   # Token cost tracking
│   └── context_budget.py # Context budgeting
├── auth/                 # Authentication
├── compat/               # Compatibility adapters (Codex, OpenCode)
├── desktop_life/         # Desktop integration
├── fuxi_scripts/         # Utility scripts
└── tests/                # Test suite (439+ tests)
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v2/memories` | Store a memory |
| GET | `/api/v2/memories` | List memories |
| POST | `/api/v2/memory/recall` | Recall relevant memories |
| POST | `/api/v2/memory/search` | Full-text + vector search |
| GET | `/api/v2/engines` | List all engines |
| POST | `/api/v2/token/budget` | Record token usage |
| WS | `/api/v2/ws` | WebSocket endpoint |

## Engine Tiers

| Tier | Count | Description |
|------|-------|-------------|
| `essential` | 7 | Core loop, safety, dialogue |
| `standard` | 14 | + perception, reasoning, emotion, etc. |
| `advanced` | 25 | + creative, proactive, curiosity, etc. |
| `all` | 36+ | All engines including experimental |

## License

MIT