#!/bin/bash
# PreToolUse Hook - 工具使用前的质量门检查
# 根据工具类型调用对应的检查器

TOOL_NAME="$1"
TOOL_INPUT="$2"
SESSION_DIR="$HOME/.claude/relay_v2"
mkdir -p "$SESSION_DIR"

# 跳过非编辑类工具
SKIP_TOOLS="Read|Bash|Glob|Grep|TaskList|TaskOutput|CronList|Agent"
if echo "$TOOL_NAME" | grep -qE "$SKIP_TOOLS"; then
  exit 0
fi

case "$TOOL_NAME" in
  Write|Edit)
    # 文件写入质量门
    FILE_PATH=$(echo "$TOOL_INPUT" | head -1)
    if [[ -f "$FILE_PATH" ]] && [[ -s "$FILE_PATH" ]]; then
      # 检查文件是否已有较完整的文档
      if ! grep -q "## " "$FILE_PATH" 2>/dev/null && ! grep -q "# " "$FILE_PATH" 2>/dev/null; then
        echo "💡 [QualityGate] Consider adding documentation to $FILE_PATH"
      fi
    fi
    ;;
  *)
    ;;
esac

exit 0
