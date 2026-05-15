#!/bin/bash
# 启动 feishu-claude-code 的封装脚本
cd /tmp/feishu-claude-code
source .venv/bin/activate
python3 main.py >> /tmp/feishu-claude-code.log 2>&1
