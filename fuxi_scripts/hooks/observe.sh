#!/bin/bash
# ECC observe.sh - 会话观察捕获脚本
# 用于捕获工具使用、用户纠正、重复工作流等观察结果

PROJECT_HASH=$(git remote get-url origin 2>/dev/null | sha256sum | cut -d' ' -f1 | cut -c1-12)
PROJECT_NAME=$(basename $(git remote get-url origin 2>/dev/null | sed 's/.git$//') 2>/dev/null | sed 's/.*\///')
PROJECT_NAME=${PROJECT_NAME:-"default"}

INSTINCT_CLI="$HOME/fuxi/fuxi_scripts/instinct_cli.py"
OBS_DIR="$HOME/.claude/projects/$PROJECT_NAME/instinct"

mkdir -p "$OBS_DIR"

# 记录工具使用
if [[ -n "$TOOL_NAME" ]]; then
  python3 "$INSTINCT_CLI" capture \
    --tool "$TOOL_NAME" \
    --tool-calls "$TOOL_INPUT" \
    --outcome "$TOOL_OUTPUT" \
    --project "$PROJECT_NAME" \
    2>/dev/null
fi

echo "Observation captured for project: $PROJECT_NAME"
