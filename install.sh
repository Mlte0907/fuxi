#!/bin/bash
#
# 伏羲 (Fuxi) 一键安装脚本
# 皮皮执行此脚本即可完成伏羲的安装
#

set -e

FUXI_DIR="$HOME/.openclaw/fuxi"
LOG_DIR="$FUXI_DIR/logs"
CHROMA_DIR="$FUXI_DIR/chroma"

echo "📦 正在安装伏羲..."

# 1. 创建目录
mkdir -p "$LOG_DIR" "$CHROMA_DIR"

# 2. 安装依赖
echo "📦 安装 Python 依赖..."
pip install chromadb requests --quiet 2>/dev/null || pip3 install chromadb requests --quiet 2>/dev/null

# 3. 复制源码（如果从 git clone 的目录运行）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/fuxi_server.py" ]; then
    cp "$SCRIPT_DIR"/*.py "$SCRIPT_DIR"/*.sh "$SCRIPT_DIR"/SKILL.md "$FUXI_DIR/" 2>/dev/null || true
    echo "✅ 源码已复制到 $FUXI_DIR"
fi

# 4. 初始化数据库
echo "🗄️ 初始化数据库..."
python3 -c "
import sys
sys.path.insert(0, '$FUXI_DIR')
from fuxi_core import init_db, create_world, get_worlds

init_db()

# 创建默认世界
existing = [w.name for w in get_worlds()]
if '瑾岚阁' not in existing:
    create_world('瑾岚阁', '六使工作记录、架构设计、会议结论', '🏛️')
if '叠界' not in existing:
    create_world('叠界', '《叠界纪元》小说章节、设定、人物', '📖')
if '皮皮专属' not in existing:
    create_world('皮皮专属', '皮皮的偏好、红线、操作宪章', '👤')
print('✅ 数据库初始化完成')
"

# 5. 启动伏羲
echo "🚀 启动伏羲 API 服务..."
bash "$FUXI_DIR/start_fuxi.sh"

echo ""
echo "✅ 伏羲安装完成！"
echo "   服务地址: http://127.0.0.1:18919"
echo "   查看状态: curl http://127.0.0.1:18919/health"
