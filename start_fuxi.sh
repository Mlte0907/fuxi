#!/bin/bash
#
# 伏羲 (Fuxi) — 瑾岚阁超级大脑 启动脚本
# 使用超算互联网 ScNet API（Qwen3-30B LLM + Qwen3-Embedding-8B 向量）
#
# 环境变量（可选）:
#   FUXI_BASE_DIR   — 安装目录，默认 ~/.openclaw/fuxi
#   FUXI_PORT       — API 端口，默认 18919
#   SCNET_KEY       — ScNet API Key（必填，否则使用随机向量降级）
#

set -e

FUXI_BASE_DIR="${FUXI_BASE_DIR:-$HOME/.openclaw/fuxi}"
FUXI_PORT="${FUXI_PORT:-18919}"

# 杀掉旧进程
pkill -f "python3.*fuxi_server" 2>/dev/null || true
sleep 1

# 创建目录
mkdir -p "$FUXI_BASE_DIR/chroma" "$FUXI_BASE_DIR/logs"

# 启动伏羲 API 服务器
cd "$FUXI_BASE_DIR"
nohup python3 fuxi_server.py > "$FUXI_BASE_DIR/logs/fuxi.log" 2>&1 &

echo $! > /tmp/fuxi.pid
sleep 3

# 检查是否启动成功
if ss -tlnp 2>/dev/null | grep -q "$FUXI_PORT" || netstat -tlnp 2>/dev/null | grep -q "$FUXI_PORT"; then
    echo "✅ 伏羲启动成功 @ http://127.0.0.1:$FUXI_PORT"
    echo "   查看日志: tail -f $FUXI_BASE_DIR/logs/fuxi.log"
else
    echo "❌ 伏羲启动失败，查看日志："
    tail -20 "$FUXI_BASE_DIR/logs/fuxi.log" 2>/dev/null || echo "无法读取日志"
fi
