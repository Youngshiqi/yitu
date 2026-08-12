"""运行固定 Agent 评测集；文件使用 JSON-compatible YAML，避免引入额外解析依赖。"""

import json
from pathlib import Path
from typing import Any, cast

from yitu.agent.graph import build_agent_graph
from yitu.agent.privacy import redact_text

ROOT = Path(__file__).parent


async def run() -> dict[str, int]:
    """执行路由和隐私评测并返回通过/失败计数。"""
    passed = failed = 0
    graph = build_agent_graph()
    for case in _load("routing.yaml"):
        result = await graph.ainvoke({
            "user_message": case["message"],
            "turn_count": 0,
            "tool_call_count": 0,
            "max_turns": 8,
            "max_tool_calls": 4,
        })
        ok = result.get("route") == case["route"] and result.get("risk") == case["risk"]
        passed += int(ok)
        failed += int(not ok)
    for case in _load("privacy.yaml"):
        ok = case["expected"] in redact_text(case["input"])
        passed += int(ok)
        failed += int(not ok)
    return {"passed": passed, "failed": failed, "total": passed + failed}


def _load(name: str) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads((ROOT / "cases" / name).read_text(encoding="utf-8")))


if __name__ == "__main__":
    import asyncio

    print(json.dumps(asyncio.run(run()), ensure_ascii=False))
