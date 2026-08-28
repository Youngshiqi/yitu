"""运行固定 Agent 评测集；用例文件使用 JSON-compatible YAML，避免引入额外解析依赖。

当前架构为单张状态图：build_assistant_graph 装配 10 个业务节点，
隐私脱敏位于 yitu.agent.infrastructure.privacy。
"""

import json
import sys
from pathlib import Path
from typing import Any, cast

# 允许直接 `python -m evals.run` 运行（pytest 的 pythonpath 配置对普通脚本不生效）。
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from yitu.agent.infrastructure.privacy import redact_text
from yitu.agent.workflow.assistant_graph import build_assistant_graph
from yitu.agent.workflow.nodes.context_nodes import (
    _CROSS_USER_PATTERNS,
    _INJECTION_PATTERNS,
)

ROOT = Path(__file__).parent

# 单张主图的全部业务节点（START/END 为 LangGraph 内部节点，不计入）。
_EXPECTED_NODES = {
    "load_context_node",
    "security_gate_node",
    "assistant_agent_node",
    "assistant_tools_node",
    "shipment_process_node",
    "create_quote_node",
    "shipment_confirmation_node",
    "create_shipment_node",
    "finalize_turn_node",
    "handle_failure_node",
}


async def run() -> dict[str, int]:
    """执行图结构和隐私脱敏评测并返回通过/失败计数。"""
    passed = failed = 0

    graph = build_assistant_graph()
    business_nodes = {
        name for name in graph.nodes if name not in {"__start__", "__end__"}
    }
    structure_checks = (
        (business_nodes == _EXPECTED_NODES, "图节点集合与单图设计一致"),
        (len(business_nodes) == len(_EXPECTED_NODES), "业务节点数量为 10"),
    )
    for ok, _label in structure_checks:
        passed += int(ok)
        failed += int(not ok)

    for case in _load("privacy.yaml"):
        ok = case["expected"] in redact_text(case["input"])
        passed += int(ok)
        failed += int(not ok)

    # 安全门禁：routing.yaml 中 risk=BLOCKED 的必须被注入/越权正则拦截，
    # 其余正常消息必须放行（不能误伤）。
    for case in _load("routing.yaml"):
        message = str(case["message"])
        blocked = any(p.search(message) for p in _INJECTION_PATTERNS) or any(
            p.search(message) for p in _CROSS_USER_PATTERNS
        )
        expect_blocked = case.get("risk") == "BLOCKED" or case.get("route") == "blocked"
        ok = blocked == expect_blocked
        passed += int(ok)
        failed += int(not ok)

    return {"passed": passed, "failed": failed, "total": passed + failed}


def _load(name: str) -> list[dict[str, Any]]:
    return cast(
        list[dict[str, Any]],
        json.loads((ROOT / "cases" / name).read_text(encoding="utf-8")),
    )


if __name__ == "__main__":
    import asyncio

    print(json.dumps(asyncio.run(run()), ensure_ascii=False))
