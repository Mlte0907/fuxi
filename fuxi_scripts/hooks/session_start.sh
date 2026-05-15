#!/bin/bash
# SessionStart Hook - 伏羲记忆系统自动加载上次会话上下文 + MCP健康检查
API_KEY="jinlange-fuxi-2026"
FUXI_URL="http://localhost:19528"
SESSION_DIR="$HOME/.claude/relay_v2"
CTX_FILE="$SESSION_DIR/terminal_context.txt"
PATTERNS_FILE="$SESSION_DIR/patterns_detected.txt"
PENDING_FILE="$SESSION_DIR/pending_tasks.txt"
mkdir -p "$SESSION_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

# 绘制分隔线
div() {
    echo -e "${DIM}────────────────────────────────────────────────${RESET}"
}

# 标题
echo ""
echo -e "${MAGENTA}${BOLD}  ╔══════════════════════════════════════════════╗${RESET}"
echo -e "${MAGENTA}${BOLD}  ║   伏羲 (Fuxi) 会话启动                      ║${RESET}"
echo -e "${MAGENTA}${BOLD}  ╚══════════════════════════════════════════════╝${RESET}"
echo ""

# 1. MCP Health Check
div
echo -e "  ${CYAN}▸ MCP 健康检查${RESET}"

MCP_OK=true
if ! curl -s --max-time 3 "$FUXI_URL/health" > /dev/null 2>&1; then
    echo -e "    ${YELLOW}⚠${RESET}  Fuxi API · 未响应"
    MCP_OK=false
fi

if pgrep -f "larkcc" > /dev/null 2>&1; then
    echo -e "    ${GREEN}✓${RESET}  larkcc · 运行中"
else
    echo -e "    ${YELLOW}⚠${RESET}  larkcc · 未运行"
fi

if pgrep -f "uvicorn fuxi.api.server" > /dev/null 2>&1; then
    echo -e "    ${GREEN}✓${RESET}  Fuxi API · 运行中"
else
    echo -e "    ${YELLOW}⚠${RESET}  Fuxi API · 未运行"
fi

div
echo -e "  ${CYAN}▸ 加载最近记忆${RESET}"
_ctx_count=0
response=$(curl -s -H "X-API-Key: $API_KEY" "$FUXI_URL/api/v2/memories?limit=5" 2>/dev/null)
if [[ -n "$response" ]] && [[ "$response" != *"error"* ]] && [[ "$response" != *"Not Found"* ]]; then
  echo "【伏羲记忆 - 最近会话参考】" > "$CTX_FILE"
  echo "更新时间: $(date '+%Y-%m-%d %H:%M:%S')" >> "$CTX_FILE"
  echo "MCP状态: $([ "$MCP_OK" = true ] && echo '✓ OK' || echo '⚠ 部分异常')" >> "$CTX_FILE"
  echo "" >> "$CTX_FILE"

  _ctx_count=$(echo "$response" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    memories = data.get('data', data.get('memories', []))
    for i, m in enumerate(memories[:5], 1):
        text = m.get('raw_text', m.get('text', m.get('content', '')))[:300]
        print(f'--- 记忆 {i} ---')
        print(text)
        print()
    print(len(memories[:5]))
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    print(0)
" 2>/dev/null | tee -a "$CTX_FILE" | tail -1)
  echo -e "    ${GREEN}✓${RESET}  已加载 ${_ctx_count:-0} 条记忆"
else
  echo -e "    ${YELLOW}⚠${RESET}  无记忆或 API 异常"
fi

# 3. Check for pending tasks from last session
div
echo -e "  ${CYAN}▸ 待处理任务${RESET}"
if [[ -f "$PENDING_FILE" ]] && [[ -s "$PENDING_FILE" ]]; then
  echo -e "    ${YELLOW}📋${RESET}  来自上次会话:"
  cat "$PENDING_FILE" | head -5 | sed 's/^/      /'
fi

# 4. Load terminal session context from relay_v2 (if exists from previous session)
if [[ -f "$CTX_FILE" ]] && [[ -s "$CTX_FILE" ]]; then
  _size=$(stat -c%s "$CTX_FILE" 2>/dev/null || stat -f%z "$CTX_FILE" 2>/dev/null)
  echo -e "    ${BLUE}▸${RESET}  终端上下文: ${_size:-?} bytes"
fi

div
echo -e "  ${GREEN}${BOLD}✓ SessionStart 完成 · $(date '+%H:%M:%S')${RESET}"
echo ""