"""
伏羲（Fuxi）Python 客户端
皮皮/玄武 调用伏羲记忆系统的标准接口

使用方式:
  from fuxi_client import FuxiClient
  client = FuxiClient()
  result = client.search("皮皮总调度")
  result = client.remember(world="瑾岚阁", room="架构", drawer="决策", text="...")
"""

import json, urllib.request, urllib.parse, urllib.error
from typing import Optional

FUXI_URL = "http://127.0.0.1:18919"
API_KEY = "my-powermem-key-2024"


class FuxiClient:
    """伏羲 API 客户端"""

    def __init__(self, url: str = FUXI_URL, api_key: str = API_KEY):
        self.url = url.rstrip("/")
        self.api_key = api_key

    def _request(self, method: str, path: str, data: Optional[dict] = None) -> dict:
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }
        url = f"{self.url}{path}"
        body = json.dumps(data or {}).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return {"status": "error", "code": e.code, "msg": e.read().decode()}
        except urllib.error.URLError as e:
            return {"status": "error", "msg": f"连接失败: {e.reason}，运行 bash ~/.bin/start_fuxi.sh"}

    def health(self) -> dict:
        """健康检查"""
        return self._request("GET", "/health")

    def search(self, query: str, top_k: int = 5) -> dict:
        """检索记忆"""
        q = urllib.parse.quote(query)
        return self._request("GET", f"/search?q={q}&top_k={top_k}")

    def remember(
        self,
        text: str,
        world: str = None,
        room: str = None,
        drawer: str = None,
        world_id: str = None,
        room_id: str = None,
        drawer_id: str = None,
        importance: float = 0.5,
        tags: list = None
    ) -> dict:
        """存档记忆"""
        data = {
            "text": text,
            "importance": importance,
            "tags": tags or [],
        }
        if drawer_id:
            data["drawer_id"] = drawer_id
        if world_id:
            data["world_id"] = world_id
        if room_id:
            data["room_id"] = room_id
        if world and room and drawer:
            data["world_id"] = world
            data["room_id"] = room
            data["drawer"] = drawer
        return self._request("POST", "/remember", data)

    def worlds(self) -> dict:
        """所有世界"""
        return self._request("GET", "/worlds")

    def explore(self, world_id: str) -> dict:
        """浏览世界结构"""
        return self._request("GET", f"/explore/{world_id}")

    def stats(self) -> dict:
        """统计信息"""
        return self._request("GET", "/stats")
