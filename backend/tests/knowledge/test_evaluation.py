"""检索评估指标（hit@k / MRR@k）与 golden set 的纯函数测试。"""

from yitu.knowledge.evaluation import (
    GOLDEN_SET,
    GoldenCase,
    evaluate_results,
    first_hit_rank,
)


def _case() -> GoldenCase:
    return GoldenCase("电池能寄吗", ("蓄电池",))


def test_first_hit_rank_found_at_rank_2() -> None:
    rank = first_hit_rank(_case(), ["无关内容", "蓄电池属于腐蚀性物质", "其他"])
    assert rank == 2


def test_first_hit_rank_miss_returns_none() -> None:
    assert first_hit_rank(_case(), ["无关", "也无关"]) is None


def test_first_hit_rank_empty_results() -> None:
    assert first_hit_rank(_case(), []) is None


def test_evaluate_results_metrics() -> None:
    cases = (_case(), _case(), _case())
    results = [
        ["蓄电池相关"],       # rank 1 -> RR 1.0
        ["无关", "蓄电池"],   # rank 2 -> RR 0.5
        ["无关", "无关"],     # miss  -> 0
    ]
    metrics = evaluate_results(cases, results, k=5)
    assert metrics["cases"] == 3
    assert metrics["hits"] == 2
    assert metrics["hit@k"] == 2 / 3
    assert metrics["mrr@k"] == (1.0 + 0.5 + 0.0) / 3


def test_evaluate_results_respects_k() -> None:
    cases = (_case(),)
    results = [["无关", "无关", "无关", "无关", "无关", "蓄电池"]]
    assert evaluate_results(cases, results, k=5)["hit@k"] == 0.0
    assert evaluate_results(cases, results, k=6)["hit@k"] == 1.0


def test_evaluate_results_length_mismatch_raises() -> None:
    import pytest

    with pytest.raises(ValueError):
        evaluate_results((_case(),), [["蓄电池"], ["另一条"]])


def test_golden_set_shape() -> None:
    assert len(GOLDEN_SET) >= 15
    for case in GOLDEN_SET:
        assert case.query.strip() == case.query
        assert case.expect_substrings, case.query
        # 期望子串必须非空且去除了空白
        for token in case.expect_substrings:
            assert token.strip() == token and len(token) >= 2
