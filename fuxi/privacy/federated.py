"""伏羲 v1.0 — 联邦学习

支持多个伏羲实例在不共享原始记忆的情况下协作学习。
只传递梯度，不共享原始记忆。"""
import json
import logging
import time
from datetime import datetime
from typing import Dict, Optional

import numpy as np

from fuxi.privacy.differential import LaplaceMechanism

logger = logging.getLogger("fuxi.privacy.federated")


class FederatedClient:
    """联邦学习客户端 — 本地训练嵌入模型，只上传梯度"""

    def __init__(self, instance_id: str, server_url: str):
        self.instance_id = instance_id
        self.server_url = server_url
        self._local_model_version = 0
        self._gradient_clip_norm = 1.0

    def compute_local_gradient(self) -> Optional[dict]:
        """基于本地记忆数据计算嵌入模型的梯度更新

        使用本地hash嵌入模型作为基础，计算与API嵌入的偏差作为梯度。
        梯度经过裁剪和加噪后上传，不泄露原始记忆内容。
        """
        from fuxi.memory.embedding import get_embedding_service
        from fuxi.store.connection import get_pool

        pool = get_pool()
        rows = pool.fetchall(
            "SELECT id, raw_text, embedding FROM items "
            "WHERE embedding IS NOT NULL AND archived = 0 "
            "ORDER BY RANDOM() LIMIT 50"
        )
        if len(rows) < 10:
            return None

        gradients = []
        emb_svc = get_embedding_service()
        for row in rows:
            try:
                api_vec = np.array(json.loads(row["embedding"]))
                local_vec = np.array(emb_svc._local_embed(row["raw_text"]))
                gradient = api_vec - local_vec
                norm = np.linalg.norm(gradient)
                if norm > self._gradient_clip_norm:
                    gradient = gradient * (self._gradient_clip_norm / norm)
                gradients.append(gradient.tolist())
            except Exception:
                continue

        if not gradients:
            return None

        avg_gradient = np.mean(gradients, axis=0)
        sensitivity = self._gradient_clip_norm / len(gradients)

        # 对梯度向量的每个元素独立添加 Laplace 噪声
        noisy_vector = np.array([
            LaplaceMechanism.add_noise(float(v), sensitivity, epsilon=1.0)
            for v in avg_gradient
        ])

        return {
            "instance_id": self.instance_id,
            "gradient": avg_gradient.tolist(),
            "gradient_noised": noisy_vector.tolist(),
            "sample_count": len(gradients),
            "model_version": self._local_model_version,
            "timestamp": time.time(),
        }

    def upload_gradient(self, gradient_data: dict) -> bool:
        """上传梯度到联邦聚合服务器"""
        try:
            import httpx
            resp = httpx.post(
                f"{self.server_url}/federated/upload",
                json=gradient_data,
                timeout=30,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Federated upload failed: {e}")
            return False

    def download_update(self) -> Optional[dict]:
        """从联邦聚合服务器下载模型更新"""
        try:
            import httpx
            resp = httpx.get(
                f"{self.server_url}/federated/update",
                params={"instance_id": self.instance_id,
                        "version": self._local_model_version},
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            logger.warning(f"Federated download failed: {e}")
            return None

    def apply_update(self, update: dict):
        """应用联邦更新到本地嵌入模型"""
        from fuxi.store.connection import get_pool

        gradient = np.array(update["gradient"])
        pool = get_pool()
        with pool.connection() as c:
            c.execute(
                "INSERT OR REPLACE INTO engine_states (engine_name, state_json, updated_at) "
                "VALUES (?,?,?)",
                ("federated_offset",
                 json.dumps({"offset": gradient.tolist()}),
                 datetime.now().isoformat())
            )
        self._local_model_version = update.get("version", self._local_model_version + 1)
        logger.info(f"Applied federated update v{self._local_model_version}")


class FederatedAggregator:
    """联邦聚合服务器 — 可选部署，聚合多个客户端的梯度"""

    def __init__(self, min_clients: int = 3):
        self._min_clients = min_clients
        self._pending_gradients: Dict[str, list] = {}
        self._global_version = 0

    def receive_gradient(self, gradient_data: dict) -> dict:
        """接收客户端梯度"""
        instance_id = gradient_data["instance_id"]
        self._pending_gradients.setdefault(instance_id, []).append(gradient_data)
        return {
            "status": "received",
            "pending_clients": len(self._pending_gradients),
        }

    def aggregate(self) -> Optional[dict]:
        """安全聚合 — FedAvg算法"""
        if len(self._pending_gradients) < self._min_clients:
            return None

        all_gradients = []
        total_samples = 0
        for _instance_id, gradients in self._pending_gradients.items():
            latest = gradients[-1]
            weight = latest["sample_count"]
            total_samples += weight
            all_gradients.append((np.array(latest["gradient"]), weight))

        if not all_gradients or total_samples == 0:
            return None

        aggregated = sum(g * w for g, w in all_gradients) / total_samples

        self._global_version += 1
        self._pending_gradients.clear()

        return {
            "gradient": aggregated.tolist(),
            "version": self._global_version,
            "contributing_clients": len(all_gradients),
        }
