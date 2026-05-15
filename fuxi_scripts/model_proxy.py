#!/usr/bin/env python3
"""本地模型路由代理 — 按模型名自动分发到 DeepSeek 或 MiniMax。

启动: python3 model_proxy.py --port 18900
模型匹配规则:
  - minimax/*        → MiniMax API (套餐订阅)
  - 其他所有模型      → DeepSeek API (token 付费)
"""

import argparse
import json
import logging
import sys
from urllib.parse import urljoin

import aiohttp
from aiohttp import web

# --- 后端配置 ---
BACKENDS = {
    "minimax": {
        "base_url": "https://api.minimaxi.com/anthropic/v1",
        "api_key": "sk-cp-fBkyFkFyXMCqED7LafpL2O389dGorEeN46_qjOW796j1kJdBzZlfs4vporP-1MkChB054mWs1R6UoGrHj5RXlAowPDxBGOplJH7R4dOox8OrbUF3R-L8J_U",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/anthropic",
        "api_key": "sk-30e8e0e697b64d92a350234fa76b34b1",
    },
}

log = logging.getLogger("model_proxy")


def resolve_backend(model: str) -> tuple[dict, str]:
    """根据模型名选择后端，返回 (backend_config, actual_model_name)。"""
    if model.lower().startswith("minimax/"):
        # 去掉 minimax/ 前缀，得到 MiniMax API 实际模型名
        return BACKENDS["minimax"], model.split("/", 1)[1]
    return BACKENDS["deepseek"], model


async def proxy_handler(request: web.Request) -> web.StreamResponse:
    """透明代理 Anthropic Messages API，按模型字段路由。"""
    path = request.match_info.get("path", "")
    body = await request.read()

    # 解析 model 字段决定路由
    backend = BACKENDS["deepseek"]  # 默认
    actual_body = body
    if body:
        try:
            payload = json.loads(body)
            model = payload.get("model", "")
            backend, actual_model = resolve_backend(model)
            if actual_model != model:
                payload["model"] = actual_model
                actual_body = json.dumps(payload).encode("utf-8")
            log.info("route %s → %s → %s", model, actual_model, backend["base_url"])
        except (json.JSONDecodeError, KeyError):
            log.warning("failed to parse model from body, using default")

    target_url = urljoin(backend["base_url"] + "/", path.lstrip("/"))

    # 转发请求
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "transfer-encoding")}
    headers["x-api-key"] = backend["api_key"]
    headers["authorization"] = f"Bearer {backend['api_key']}"

    timeout = aiohttp.ClientTimeout(total=600)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method=request.method,
                url=target_url,
                headers=headers,
                data=actual_body,
            ) as upstream:
                # 流式透传响应
                resp = web.StreamResponse(status=upstream.status)
                for k, v in upstream.headers.items():
                    if k.lower() not in ("transfer-encoding", "content-encoding"):
                        resp.headers[k] = v
                await resp.prepare(request)

                async for chunk in upstream.content.iter_any():
                    await resp.write(chunk)

                await resp.write_eof()
                return resp
    except aiohttp.ClientError as e:
        log.error("upstream error: %s", e)
        return web.json_response(
            {"error": f"upstream connection failed: {e}"}, status=502
        )


def main():
    parser = argparse.ArgumentParser(description="Model Routing Proxy")
    parser.add_argument("--port", type=int, default=18900)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    app = web.Application()
    # 匹配所有子路径，支持 /v1/messages 等 Anthropic 端点
    app.router.add_route("*", "/{path:.*}", proxy_handler)

    log.info("model proxy listening on http://%s:%d", args.host, args.port)
    log.info("route: minimax/* → %s", BACKENDS["minimax"]["base_url"])
    log.info("route: *        → %s", BACKENDS["deepseek"]["base_url"])
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
