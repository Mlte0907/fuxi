#!/usr/bin/env python3
"""伏羲系统状态监测脚本 - 监测 token 优化效果和引擎运行状态"""
import sys, os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())

import json
from datetime import datetime, timedelta

def get_token_stats():
    """获取 token 消耗统计"""
    import requests
    try:
        resp = requests.get("http://localhost:19528/api/v2/token/budget", 
            headers={"X-API-Key": "jinlange-fuxi-2026"}, timeout=5)
        if resp.ok:
            data = resp.json().get("data", {})
            records = data.get("records", [])
            if records:
                r = records[0]
                return {
                    "input": r.get("input_tokens", 0),
                    "output": r.get("output_tokens", 0),
                    "total": r.get("total_tokens", 0),
                    "requests": r.get("requests", 0),
                    "avg_per_req": r.get("avg_tokens_per_request", 0)
                }
    except Exception:
        pass
    return None

def get_engine_states():
    """获取引擎状态"""
    from fuxi.engines.base import get_engine_registry
    from fuxi.store.connection import get_pool
    
    r = get_engine_registry()
    pool = get_pool()
    exp_engines = ['cognitive_loop', 'openclaw_memory', 'skill_evolution']
    states = {}
    
    for name in exp_engines:
        if name in r._engines:
            eng = r._engines[name]
            row = pool.fetchone(
                'SELECT state_json, updated_at FROM engine_states WHERE engine_name=?',
                (name,)
            )
            if row:
                state = json.loads(row['state_json'])
                last_run = state.get('last_run')
                run_count = state.get('run_count', 0)
                # 计算多久没运行了
                updated = row['updated_at']
                states[name] = {
                    "last_run": last_run,
                    "run_count": run_count,
                    "updated": updated,
                    "interval": eng.interval
                }
            else:
                states[name] = {"status": "从未运行"}
    
    return states

def get_memory_stats():
    """获取记忆统计"""
    from fuxi.store.connection import get_pool
    
    pool = get_pool()
    stats = {}
    
    # 总记忆数
    row = pool.fetchone("SELECT COUNT(*) as cnt FROM items WHERE archived=0")
    stats["total_memories"] = row["cnt"] if row else 0
    
    # 各抽屉记忆数
    rows = pool.fetchall(
        "SELECT drawer_id, COUNT(*) as cnt FROM items WHERE archived=0 GROUP BY drawer_id"
    )
    stats["by_drawer"] = {r["drawer_id"]: r["cnt"] for r in rows}
    
    # 工作记忆推送数
    row = pool.fetchone(
        "SELECT state_json FROM engine_states WHERE engine_name='cognitive_loop'"
    )
    if row:
        state = json.loads(row["state_json"])
        wm = state.get("working_memory", {})
        stats["wm_pushed"] = wm.get("total_pushed", 0)
        stats["wm_evictions"] = wm.get("evictions", 0)
        stats["wm_focus"] = len(wm.get("wm_focus", []))
    
    return stats

def get_event_stats():
    """获取事件统计"""
    from fuxi.store.connection import get_pool
    
    pool = get_pool()
    stats = {}
    
    # 近 30 分钟 error/warning
    for evt_type in ['error', 'warning']:
        row = pool.fetchone(
            "SELECT COUNT(*) as cnt FROM event_log WHERE event_type=? AND created_at > datetime('now', '-30 minutes')",
            (evt_type,)
        )
        stats[f"last_30m_{evt_type}"] = row["cnt"] if row else 0
    
    # 总事件数
    row = pool.fetchone("SELECT COUNT(*) as cnt FROM event_log")
    stats["total_events"] = row["cnt"] if row else 0
    
    return stats

def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"伏羲系统监测报告 - {now}")
    print(f"{'='*60}")
    
    # Token 统计
    print("\n【Token 消耗】")
    token = get_token_stats()
    if token:
        print(f"  输入 tokens:   {token['input']:,}")
        print(f"  输出 tokens:   {token['output']:,}")
        print(f"  总 tokens:    {token['total']:,}")
        print(f"  请求次数:     {token['requests']:,}")
        print(f"  平均/请求:    {token['avg_per_req']:,}")
    else:
        print("  无法获取（服务可能未运行）")
    
    # 引擎状态
    print("\n【实验性引擎状态】")
    engines = get_engine_states()
    for name, state in engines.items():
        interval_mins = state.get("interval", 0) / 60
        print(f"  {name}:")
        print(f"    运行间隔: {interval_mins:.0f}分钟")
        print(f"    运行次数: {state.get('run_count', 'N/A')}")
        print(f"    上次运行: {state.get('last_run', state.get('updated', 'N/A'))}")
    
    # 记忆统计
    print("\n【记忆系统状态】")
    mem = get_memory_stats()
    print(f"  总记忆数: {mem.get('total_memories', 0)}")
    print(f"  工作记忆推送: {mem.get('wm_pushed', 0)}")
    print(f"  工作记忆淘汰: {mem.get('wm_evictions', 0)}")
    print(f"  注意力焦点: {mem.get('wm_focus', 0)}")
    if mem.get("by_drawer"):
        print("  各抽屉:")
        for drawer, cnt in sorted(mem["by_drawer"].items(), key=lambda x: -x[1])[:5]:
            print(f"    {drawer}: {cnt}")
    
    # 事件统计
    print("\n【事件日志】")
    events = get_event_stats()
    print(f"  近30分钟 error: {events.get('last_30m_error', 0)}")
    print(f"  近30分钟 warning: {events.get('last_30m_warning', 0)}")
    print(f"  总事件数: {events.get('total_events', 0)}")
    
    print(f"\n{'='*60}")

if __name__ == "__main__":
    main()
