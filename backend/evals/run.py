"""运行固定 Agent 评测集；文件使用 JSON-compatible YAML，避免引入额外解析依赖。"""

import json
from pathlib import Path
from typing import Any, cast

from yitu.agent.privacy import redact_text
from yitu.agent.workflows.assistant_graph import build_assistant_graph
from yitu.agent.workflows.shipment_graph import build_shipment_graph

ROOT = Path(__file__).parent


async def run() -> dict[str, int]:
    """执行新图结构和隐私评测并返回通过/失败计数。"""
    passed = failed = 0
    shipment_graph = build_shipment_graph()
    assistant_graph = build_assistant_graph(shipment_graph)
    for actual, expected in (
        (len(shipment_graph.nodes) - 1, 8),
        (len(assistant_graph.nodes) - 1, 7),
    ):
        ok = actual == expected
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
