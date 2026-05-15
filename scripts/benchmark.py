#!/usr/bin/env python3
"""FuXi v1.0 Benchmark - 50 concurrent requests"""
import json
import os
import queue
import threading
import time
import urllib.request

BASE = "http://localhost:19528"
API_KEY = os.environ.get("FUXI_API_KEY", "")
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
CONCURRENT = 50

def request(method, path, data=None):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
    try:
        start = time.monotonic()
        with urllib.request.urlopen(req, timeout=30) as resp:
            duration = (time.monotonic() - start) * 1000
            return {"code": resp.status, "time_ms": round(duration, 2), "ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e), "time_ms": 0}

def bench(name, path, method="GET", data=None):
    results = queue.Queue()
    def worker():
        results.put(request(method, path, data))
    threads = [threading.Thread(target=worker) for _ in range(CONCURRENT)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = (time.monotonic() - start) * 1000
    items = [results.get() for _ in range(CONCURRENT)]
    ok = [i for i in items if i["ok"]]
    times = [i["time_ms"] for i in ok]
    if times:
        times.sort()
        avg = sum(times) / len(times)
        p50 = times[len(times) // 2]
        p95 = times[int(len(times) * 0.95)]
        print(f"  {name}: {len(ok)}/{CONCURRENT} ok, avg={avg:.0f}ms, p50={p50:.0f}ms, p95={p95:.0f}ms, total={total:.0f}ms")
        return avg
    else:
        print(f"  {name}: ALL FAILED")
        return None

print("FuXi v1.0 Benchmark - 50 concurrent requests")
print(f"Target: {BASE}")
print()

print("=== Read Endpoints ===")
a1 = bench("GET /health", "/health")
a2 = bench("GET /api/v2/memories", "/api/v2/memories?limit=5")
a3 = bench("GET /api/v2/engines", "/api/v2/engines")
a4 = bench("GET /api/v2/agents", "/api/v2/agents")
a5 = bench("GET /api/v2/system/info", "/api/v2/system/info")

print()
print("=== Write Endpoints ===")
a6 = bench("POST /api/v2/memories", "/api/v2/memories", "POST", {"text": "benchmark test", "importance": 0.5})
a7 = bench("POST /api/v2/engines/soul/run", "/api/v2/engines/soul/run", "POST")

print()
print("=== Summary ===")
all_avgs = [a for a in [a1, a2, a3, a4, a5, a6, a7] if a]
if all_avgs:
    overall = sum(all_avgs) / len(all_avgs)
    print(f"Overall average: {overall:.0f}ms")
    print(f"Worst case: {max(all_avgs):.0f}ms")
    under_500 = all(a < 500 for a in all_avgs)
    print(f"All under 500ms: {'PASS' if under_500 else 'FAIL'}")
else:
    print("All benchmarks failed!")
