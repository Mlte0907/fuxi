"""伏羲 v1.0 嵌入服务（API为主 + 本地fallback）"""
import asyncio
import hashlib
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import numpy as np

from fuxi.config import config

logger = logging.getLogger("fuxi.memory.embed")

class EmbeddingService:
    """统一嵌入服务：优先外部API，失败降级为本地hash向量"""

    def __init__(self):
        self._cache: dict = {}
        self._cache_lock = threading.Lock()
        self._fail_count = 0
        self._last_fail_time = 0
        self._circuit_open = False
        self._half_open_until = 0  # timestamp until which half-open probe is allowed

    def embed(self, text: str) -> Optional[List[float]]:
        if not text:
            return None
        cache_key = hashlib.md5(text.encode()).hexdigest()
        with self._cache_lock:
            if cache_key in self._cache:
                return self._cache[cache_key]
        # Circuit breaker with half-open recovery
        use_api = False
        if self._circuit_open:
            if time.time() >= self._half_open_until:
                use_api = True  # half-open: allow one probe request
        else:
            use_api = True
        vec = self._call_api(text) if use_api else self._local_embed(text)
        if vec is None:
            vec = self._local_embed(text)
        if vec:
            with self._cache_lock:
                if len(self._cache) >= config.embed_cache_max:
                    oldest = next(iter(self._cache))
                    del self._cache[oldest]
                self._cache[cache_key] = vec
        return vec

    def embed_batch(self, texts: List[str], max_workers: int = 4) -> List[Optional[List[float]]]:
        """并发批量嵌入，使用线程池并行调用 API"""
        if len(texts) <= 1:
            return [self.embed(t) for t in texts]
        results: List[Optional[List[float]]] = [None] * len(texts)
        with ThreadPoolExecutor(max_workers=min(max_workers, len(texts))) as ex:
            futures = {ex.submit(self.embed, t): i for i, t in enumerate(texts)}
            for f in as_completed(futures):
                i = futures[f]
                try:
                    results[i] = f.result()
                except Exception as e:
                    logger.warning(f"Batch embed failed for index {i}: {e}")
        return results

    def _call_api(self, text: str) -> Optional[List[float]]:
        if not config.siliconflow_key:
            return None
        try:
            from fuxi.privacy.sanitizer import MemorySanitizer
            safe_text = MemorySanitizer.sanitize_for_embedding(text)

            # Use aiohttp for async HTTP to avoid GIL blocking during I/O
            async def _fetch():
                import aiohttp
                data = {"model": config.embed_api_model, "input": safe_text, "encoding_format": "float"}
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        config.embed_api_url,
                        json=data,
                        headers={"Authorization": f"Bearer {config.siliconflow_key}"},
                    ) as resp:
                        resp.raise_for_status()
                        result = await resp.json()
                        return result["data"][0]["embedding"]

            vec = asyncio.run(_fetch())
            self._fail_count = 0
            if self._circuit_open:
                self._circuit_open = False
                self._half_open_until = 0
                logger.info("Circuit breaker CLOSED — API recovered")
            return vec
        except Exception as e:
            self._fail_count += 1
            self._last_fail_time = time.time()
            logger.warning(f"Embed API failed ({self._fail_count}): {e}")
            if self._fail_count >= config.embed_fail_threshold:
                self._circuit_open = True
                self._half_open_until = time.time() + 60
                logger.warning("Circuit breaker OPEN — using local fallback, half-open in 60s")
            return None

    def _local_embed(self, text: str) -> List[float]:
        """基于hash的本地向量生成（无需外部模型，确定性降级方案）"""
        # 使用字符级n-gram hash作为简单特征
        vec = np.zeros(config.embed_dim, dtype=np.float32)
        for i in range(len(text) - 2):
            ngram = text[i:i+3]
            h = int(hashlib.md5(ngram.encode()).hexdigest(), 16)
            idx = h % config.embed_dim
            vec[idx] += 1.0
        # L2归一化
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.tolist()

    @property
    def stats(self) -> dict:
        return {
            "cache_size": len(self._cache),
            "cache_max": config.embed_cache_max,
            "fail_count": self._fail_count,
            "circuit_open": self._circuit_open,
        }


_embed_service = None

def get_embedding_service() -> EmbeddingService:
    global _embed_service
    if _embed_service is None:
        _embed_service = EmbeddingService()
    return _embed_service
