#!/bin/bash
# PreCompact Hook - 上下文压缩前持久化关键状态
API_KEY="jinlange-fuxi-2026"
FUXI_URL="http://localhost:19528"
FUXI_SCRIPT="$HOME/fuxi/fuxi_scripts/upload_context.py"
AUTO_UPLOAD="$HOME/fuxi/fuxi_scripts/auto_upload.py"
CTX_FILE="$HOME/.claude/relay_v2/terminal_context.txt"
PATTERNS_FILE="$HOME/.claude/relay_v2/patterns_detected.txt"

echo "💾 [PreCompact] Saving context snapshot before compaction..."

# 确保当前上下文已同步
python3 "$HOME/fuxi/fuxi_scripts/sync_terminal_history.py" 2>/dev/null

if [[ -f "$CTX_FILE" ]] && [[ -s "$CTX_FILE" ]]; then
  # 使用 auto_upload 如果可用（支持任务级分块）
  if [[ -f "$AUTO_UPLOAD" ]]; then
    python3 "$AUTO_UPLOAD" --context "$CTX_FILE" --agent fuxi 2>/dev/null && echo "   ✅ PreCompact: context snapshot uploaded (task-level)"
  else
    python3 "$FUXI_SCRIPT" --agent fuxi --task "precompact-snapshot" --file "$CTX_FILE" 2>/dev/null && echo "   ✅ PreCompact: context snapshot uploaded (legacy)"
  fi
else
  echo "   ⚠️  No terminal context to snapshot"
fi

echo "✅ PreCompact complete at $(date '+%H:%M:%S')"