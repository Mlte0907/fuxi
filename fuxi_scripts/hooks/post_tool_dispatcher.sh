#!/bin/bash
# PostToolUse Hook - 工具使用后的质量门和模式提取
TOOL_NAME="$1"
TOOL_INPUT="$2"
TOOL_OUTPUT="$3"
EXIT_CODE="$4"

SESSION_DIR="$HOME/.claude/relay_v2"
mkdir -p "$SESSION_DIR"

# 模式检测：检测重复工作流
detect_patterns() {
  local tool="$1"
  local input="$2"
  local output="$3"
  
  # 检测是否重复执行相似的Bash命令
  if [[ "$tool" == "Bash" ]]; then
    CMD=$(echo "$input" | head -1 | cut -d' ' -f1-3)
    # 可以在这里扩展模式检测逻辑
  fi
}

case "$TOOL_NAME" in
  Bash)
    # PR记录 - 检测git push
    if echo "$input" | grep -q "git push"; then
      echo "📤 [GitPush] Don't forget to create PR after push"
    fi
    # 构建分析
    if echo "$input" | grep -q "build\|test\|compile"; then
      if [[ "$EXIT_CODE" != "0" ]]; then
        echo "❌ [BuildFailed] Check the error output above"
      fi
    fi
    ;;
  Write|Edit)
    # 检查是否创建了新文件
    if [[ "$EXIT_CODE" == "0" ]]; then
      echo "✅ [FileModified] $(echo "$TOOL_INPUT" | head -1)"
    fi
    ;;
esac

exit 0
