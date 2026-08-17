"""Fast Path 快速路由的关键行为契约。"""

import pytest

from yitu.agent.understanding import fast_path, preprocess_text


def run_fast_path(message: str, address_labels: list[str] | None = None):
    return fast_path(preprocess_text(message), address_labels or ["公司", "家"])


def test_pure_draft_update_still_takes_fast_path() -> None:
    """纯填写草稿语句（无查询信号）仍走快速路径。"""
    result = run_fast_path("从公司寄到家，2公斤")
    assert result is not None
    assert result.primary_intent == "DRAFT_UPDATE"
    assert result.recognition_path == "RULE"
    assert result.draft.actual_weight_grams == 2000


@pytest.mark.parametrize(
    "message",
    [
        "查一下从北京寄到上海的运单",
        "从北京寄到上海多少钱",
        "从北京寄到上海要多久",
        "看看从公司寄到家的包裹到哪了",
    ],
)
def test_query_signal_defers_draft_rule_to_llm(message: str) -> None:
    """查询型语句命中 DRAFT_UPDATE 路由正则时必须放弃快速路径交给 LLM。"""
    assert run_fast_path(message) is None


def test_shipment_query_fast_path_unaffected() -> None:
    """运单查询快速路径不受查询信号守卫影响。"""
    result = run_fast_path("帮我查一下运单YT1234ABCD5678的状态")
    assert result is not None
    assert result.primary_intent == "SHIPMENT_QUERY"
    assert result.shipment_no == "YT1234ABCD5678"
