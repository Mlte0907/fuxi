#!/bin/bash
# ACP Link Wrapper - 瑾岚阁Agent通过acp-link接入伏羲ACP协议
# 用法: acp_link_wrapper.sh <agent_name> <port>
#
# 这是一个wrapper，实际外部Agent通过以下方式接入:
# 1. acp-link --port 9000 /path/to/agent (CCB推荐方式)
# 2. RCS + ACP Relay via ACP_RCS_URL + ACP_RCS_TOKEN

AGENT_NAME="${1:-jinlange_agent}"
PORT="${2:-9000}"
FUXI_ACP_URL="ws://localhost:19528/api/v2/acp"

echo "🔗 ACP Link Wrapper for $AGENT_NAME"
echo "   Target: $FUXI_ACP_URL"
echo "   Local port: $PORT"
echo ""
echo "要通过 acp-link 让瑾岚阁Agent接入，请运行:"
echo "   acp-link --port $PORT /path/to/jinlange_agent"
echo ""
echo "或者通过 RCS 注册:"
echo "   export ACP_RCS_URL=http://localhost:9001"
echo "   export ACP_RCS_TOKEN=your_token"
echo "   acp-relay-handler --register $AGENT_NAME"
