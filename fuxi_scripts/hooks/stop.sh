#!/bin/bash
# Stop Hook - 会话停止时执行完整清理 + 跨会话模式分析 + Token 结算
API_KEY="jinlange-fuxi-2026"
FUXI_URL="http://localhost:19528"
FUXI_SCRIPT="$HOME/fuxi/fuxi_scripts/upload_context.py"
AUTO_UPLOAD="$HOME/fuxi/fuxi_scripts/auto_upload.py"
SESSION_DIR="$HOME/.claude/relay_v2"
CTX_FILE="$SESSION_DIR/terminal_context.txt"
PATTERNS_FILE="$SESSION_DIR/patterns_detected.txt"
PENDING_FILE="$SESSION_DIR/pending_tasks.txt"
mkdir -p "$SESSION_DIR"

echo "🔴 [Stop] Running session cleanup and pattern extraction..."

# 0. 确保当前会话上下文已同步（从session-data → relay_v2）
if command -v sync_terminal_history.py > /dev/null 2>&1; then
  python3 "$HOME/fuxi/fuxi_scripts/sync_terminal_history.py" 2>/dev/null
fi

# 1. 自动上传 — 任务级分割 + tag 提取
if [[ -f "$AUTO_UPLOAD" ]]; then
  if [[ -f "$CTX_FILE" ]] && [[ -s "$CTX_FILE" ]]; then
    python3 "$AUTO_UPLOAD" --context "$CTX_FILE" --agent fuxi 2>/dev/null && echo "   ✅ Task-level memories uploaded"
  fi
else
  # 降级：直接用 upload_context.py
  if [[ -f "$CTX_FILE" ]] && [[ -s "$CTX_FILE" ]]; then
    python3 "$FUXI_SCRIPT" --agent fuxi --task "session-summary" --file "$CTX_FILE" 2>/dev/null && echo "   ✅ Session summary uploaded (legacy)"
  fi
fi

# 2. 模式提取（Python 驱动，比 grep 更精确）
echo "   📊 [PatternExtraction] Analyzing session patterns..."

if [[ -f "$CTX_FILE" ]]; then
  python3 -c "
import json, re, sys
from collections import Counter, defaultdict

text = sys.stdin.read()

# --- 工具调用链模式 ---
TOOLS = ['Read', 'Write', 'Edit', 'Bash', 'Glob', 'Grep', 'Agent', 'Skill', 'TodoWrite']
tool_mentions = []
for t in TOOLS:
    count = len(re.findall(rf'\b{t}\b', text))
    if count > 0:
        tool_mentions.append((t, count))

# 工具序列模式（检测常用工作流）
patterns = {
    'read_edit_chain': len(re.findall(r'Read.*?Edit', text, re.DOTALL)),
    'grep_read_chain': len(re.findall(r'Grep.*?Read', text, re.DOTALL)),
    'bash_verify_chain': len(re.findall(r'(Bash|Edit).*?Bash', text, re.DOTALL)),
    'agent_delegation': len(re.findall(r'Agent.*?description', text, re.DOTALL)),
}

# --- 错误/告警模式 ---
errors = {
    'rate_limit': len(re.findall(r'429|rate.limit|too many requests', text, re.I)),
    'connection_error': len(re.findall(r'connection.*(?:fail|refused|timeout|error)', text, re.I)),
    'auth_error': len(re.findall(r'401|403|unauthorized|forbidden', text, re.I)),
    'syntax_error': len(re.findall(r'SyntaxError|compile.error|traceback', text, re.I)),
}

# --- 决策节点 ---
decisions = len(re.findall(r'(决定|选择|方案[：:]|结论[：:]|approach|implement.*by)', text, re.I))

# --- 文件变更 ---
changed_files = re.findall(r'(?:modified:|创建|写入|File.*modified|→)\s*([\w/.]+\.\w+)', text)
changed_files = list(set(changed_files))[:15]

# --- 飞书 / 中继交互 ---
lark_mentions = len(re.findall(r'feishu|lark|飞书|卡片|card', text, re.I))

# --- 输出结构化报告 ---
print('=== 工具使用统计 ===')
for t, c in sorted(tool_mentions, key=lambda x: -x[1])[:8]:
    print(f'  {t}: {c}')
print()
print('=== 工作流模式 ===')
for name, cnt in patterns.items():
    if cnt > 0:
        print(f'  {name}: {cnt}')
print()
print('=== 错误/告警 ===')
for name, cnt in errors.items():
    if cnt > 0:
        print(f'  {name}: {cnt}')
print()
print(f'=== 决策节点 ===')
print(f'  检测到: {decisions}')
print()
if changed_files:
    print('=== 文件变更 ===')
    for f in changed_files:
        print(f'  {f}')
print()
print(f'=== 飞书交互 ===')
print(f'  提及次数: {lark_mentions}')
" < "$CTX_FILE" > "$PATTERNS_FILE" 2>/dev/null
  echo "   ✅ Patterns extracted to $PATTERNS_FILE"
fi

# 3. 记录会话 Token 消耗
echo "   💰 [TokenTracking] Recording session cost..."
TOKEN_DATA=$(curl -s -H "X-API-Key: $API_KEY" "$FUXI_URL/api/v2/token/budget" 2>/dev/null)
if [[ -n "$TOKEN_DATA" ]]; then
  echo "" >> "$PATTERNS_FILE"
  echo "=== Token 消耗 ===" >> "$PATTERNS_FILE"
  echo "$TOKEN_DATA" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin).get('data', {})
    for r in d.get('records', []):
        print(f\"  {r['model']}: {r['total_tokens']:,} tokens ({r['requests']} req)\")
except: pass
" >> "$PATTERNS_FILE"
  echo "   ✅ Token summary appended"
fi

# 4. 保存模式到伏羲记忆
if [[ -f "$AUTO_UPLOAD" ]]; then
  if [[ -f "$PATTERNS_FILE" ]] && [[ -s "$PATTERNS_FILE" ]]; then
    python3 "$AUTO_UPLOAD" --patterns "$PATTERNS_FILE" --agent fuxi 2>/dev/null
  fi
elif [[ -f "$PATTERNS_FILE" ]] && [[ -s "$PATTERNS_FILE" ]]; then
  python3 "$FUXI_SCRIPT" --agent fuxi --task "pattern-extraction" --file "$PATTERNS_FILE" 2>/dev/null
fi

# 5. 保存待处理任务列表
echo "   📋 [Tasks] Saving pending tasks..."
if [[ -f "$PENDING_FILE" ]] && [[ -s "$PENDING_FILE" ]]; then
  echo "   Pending tasks preserved for next session"
fi

echo "✅ Stop complete at $(date '+%H:%M:%S')"