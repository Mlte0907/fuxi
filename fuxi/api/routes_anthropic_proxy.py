"""伏羲内置 Anthropic API 代理 — 按模型名自动路由 + Token 消耗追踪

路由逻辑：
  1. MiniMax-M2.7 → MiniMax（套餐，主会话）
  2. sonnet/haiku/coding/deepseek → DeepSeek（token 付费）
  3. DeepSeek 429 → OpenRouter 兜底

Token 追踪：
  流式响应结束后自动解析 usage 字段并记录到 /api/v2/token/budget
"""

import asyncio
import json
import logging
import os
from urllib.parse import urljoin

import aiohttp
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger("fuxi.api.anthropic_proxy")

router = APIRouter(tags=["anthropic_proxy"])

BACKENDS = {
    "minimax": {
        "base_url": "https://api.minimaxi.com/anthropic",
        "api_key": os.environ.get("MINIMAX_API_KEY", "your_minimax_api_key_here"),
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/anthropic",
        "api_key": os.environ.get("DEEPSEEK_API_KEY", "your_deepseek_api_key_here"),
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": os.environ.get("OPENROUTER_API_KEY", "your_openrouter_api_key_here"),
    },
}


def _route(body: bytes | None) -> tuple[dict, bytes | None, str | None, str]:
    """根据 model 字段选择后端。

    路由规则：
      MiniMax-M2.7 → MiniMax 套餐（主会话/聊天/搜索）
      sonnet/haiku/coding/deepseek → DeepSeek（token 付费）
      DeepSeek 429 → OpenRouter 兜底
    """
    default_backend = BACKENDS["minimax"]

    if not body:
        return default_backend, None, None, "MiniMax-M2.7"

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, KeyError):
        return default_backend, body, None, "MiniMax-M2.7"

    model = payload.get("model", "")
    model_lower = model.lower()

    # MiniMax-M2.7 → 套餐 MiniMax（主会话/聊天/搜索/查询）
    if model_lower == "minimax-m2.7":
        return default_backend, body, None, model

    # sonnet/haiku/coding/deepseek → DeepSeek（token 付费）
    if any(x in model_lower for x in ["haiku", "sonnet", "coding", "deepseek"]):
        if model_lower.startswith("openrouter/"):
            # openrouter/xxx 格式直接转发，去掉前缀
            backend = BACKENDS["openrouter"]
            payload["model"] = model.split("/", 1)[1]
            return backend, json.dumps(payload).encode("utf-8"), "chat/completions", model
        else:
            backend = BACKENDS["deepseek"]
            return backend, json.dumps(payload).encode("utf-8"), "chat/completions", model

    # 默认 → MiniMax 套餐
    return default_backend, body, None, model


async def _record_tokens(model: str, input_tokens: int, output_tokens: int):
    """异步记录 token 消耗到 token/budget"""
    try:
        import aiohttp
        payload = {
            "agent_id": "anthropic_proxy",
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:19528/api/v2/token/budget",
                json=payload,
                headers={"X-API-Key": os.environ.get("FUXI_API_KEY", "")},
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"token record failed: {resp.status}")
    except Exception as e:
        logger.warning(f"token record error: {e}")


def _extract_usage_from_sse(buffer: bytes) -> tuple[int, int]:
    """从 SSE 响应体中解析 usage 字段（input_tokens, output_tokens）"""
    input_tokens = 0
    output_tokens = 0
    try:
        text = buffer.decode("utf-8", errors="replace")
        for line in text.split("\n"):
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    msg_type = data.get("type", "")
                    usage = data.get("message", {}).get("usage", {}) if msg_type == "message_start" else data.get("usage", {})
                    if msg_type == "message_start":
                        input_tokens = usage.get("input_tokens", 0)
                    if msg_type == "message_delta":
                        output_tokens = usage.get("output_tokens", 0)
                    if msg_type == "message_stop" and data.get("message", {}).get("usage"):
                        usage = data["message"]["usage"]
                        if not output_tokens:
                            output_tokens = usage.get("output_tokens", 0)
                except (json.JSONDecodeError, KeyError):
                    pass
    except Exception:
        pass
    return input_tokens, output_tokens


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy(request: Request, path: str):
    body = await request.body()
    backend, actual_body, path_override, model = _route(body)

    actual_path = path_override or path.lstrip("/")
    target_url = urljoin(backend["base_url"] + "/", actual_path)

    # 只透传安全的请求头，排除可能冲突的
    safe = {"content-type", "accept", "accept-encoding", "user-agent", "x-stainless-arch", "x-stainless-os",
            "x-stainless-lang", "x-stainless-package-version", "x-stainless-runtime", "x-stainless-runtime-version"}
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() in safe
    }
    headers["authorization"] = f"Bearer {backend['api_key']}"

    if "accept-encoding" in headers:
        encodings = [e.strip() for e in headers["accept-encoding"].split(",") if e.strip() != "br"]
        if encodings:
            headers["accept-encoding"] = ", ".join(encodings)
        else:
            del headers["accept-encoding"]

    timeout = aiohttp.ClientTimeout(total=600)
    client = aiohttp.ClientSession(timeout=timeout)

    try:
        upstream = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=actual_body,
        )
    except aiohttp.ClientError as e:
        await client.close()
        logger.error(f"anthropic proxy upstream error: {e}")
        return StreamingResponse(
            iter([json.dumps({"error": f"upstream connection failed: {e}"}).encode()]),
            status_code=502,
            media_type="application/json",
        )

    # 限速自动切换到备选后端
    if upstream.status == 429:
        upstream.close()
        await client.close()
        logger.warning(f"anthropic proxy rate limit on {backend['base_url']}, falling back to openrouter")
        
        # 限速时切到 OpenRouter 兜底
        fallback = BACKENDS["openrouter"]
        fallback_url = urljoin(fallback["base_url"] + "/", path.lstrip("/"))
        headers["authorization"] = f"Bearer {fallback['api_key']}"

        # OpenRouter 保持原 model 名（可能需要调整）
        if actual_body:
            try:
                fb_payload = json.loads(actual_body)
                # OpenRouter 接受的模型格式
                if not fb_payload.get("model", "").startswith("openrouter/"):
                    fb_payload["model"] = f"openrouter/{fb_payload['model']}"
                actual_body = json.dumps(fb_payload).encode("utf-8")
            except:
                pass
        
        client = aiohttp.ClientSession(timeout=timeout)
        try:
            upstream = await client.request(
                method=request.method,
                url=fallback_url,
                headers=headers,
                data=actual_body,
            )
        except aiohttp.ClientError as e:
            await client.close()
            logger.error(f"anthropic proxy fallback error: {e}")
            return StreamingResponse(
                iter([json.dumps({"error": f"upstream connection failed: {e}"}).encode()]),
                status_code=502,
                media_type="application/json",
            )

    response_headers = {
        k: v for k, v in upstream.headers.items()
        if k.lower() not in ("transfer-encoding", "content-encoding")
    }

    # 从请求中提取原始模型名用于记录
    request_model = "unknown"
    try:
        body_data = await request.body()
        if body_data:
            req_payload = json.loads(body_data)
            request_model = req_payload.get("model", "unknown")
    except Exception:
        pass

    sse_buffer = bytearray()
    recorded = False

    async def stream():
        nonlocal recorded
        try:
            async for chunk in upstream.content.iter_any():
                sse_buffer.extend(chunk)
                yield chunk
        finally:
            upstream.close()
            await client.close()
            # 流结束后解析 usage 并记录
            if not recorded:
                recorded = True
                inp, out = _extract_usage_from_sse(bytes(sse_buffer))
                if inp or out:
                    logger.info(f"Token usage: {request_model} in={inp} out={out}")
                    # 异步记录，不阻塞响应
                    asyncio.ensure_future(_record_tokens(request_model, inp, out))

    return StreamingResponse(
        stream(),
        status_code=upstream.status,
        headers=response_headers,
    )
