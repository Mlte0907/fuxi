#!/bin/bash
# 伏羲 v1.0 自动备份脚本
# Cron: 0 3 * * * /home/xiaoxin/fuxi/scripts/backup.sh
# 直接通过 Python 调用 backup_db()，不依赖 API key

set -e

LOG_DIR="/home/xiaoxin/.openclaw/fuxi_v1/logs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p "$LOG_DIR"

echo "[${TIMESTAMP}] 伏羲 v1.0 备份开始"

# 通过 Python 直接调用备份函数（不需要 API key）
RESULT=$(cd /home/xiaoxin/fuxi && /home/xiaoxin/fuxi/venv/bin/python -c "
import sys; sys.path.insert(0, '.')
from fuxi.store.backup import backup_db
import json
print(json.dumps(backup_db()))
" 2>&1)

echo "备份结果: ${RESULT}"

# 验证备份文件是否存在
BACKUP_FILE=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('file',''))" 2>/dev/null)
if [ -n "$BACKUP_FILE" ] && [ -f "$BACKUP_FILE" ]; then
    SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || echo "0")
    echo "[${TIMESTAMP}] 备份成功: $(basename $BACKUP_FILE) (${SIZE} bytes)"
else
    echo "[${TIMESTAMP}] 备份失败: $RESULT"
    exit 1
fi

echo "[${TIMESTAMP}] 伏羲 v1.0 备份完成"
