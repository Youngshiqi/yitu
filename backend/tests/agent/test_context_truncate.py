"""上下文组装器截断行为的关键契约。"""

from yitu.agent.context import _truncate


def test_short_value_untouched() -> None:
    assert _truncate("短内容") == "短内容"


def test_truncation_closes_at_json_boundary() -> None:
    """超长 JSON 必须在完整闭合边界收口，不得输出残缺结构。"""
    payload = '{"items":[' + ",".join('{"id":%d}' % i for i in range(2000)) + "]}"
    truncated = _truncate(payload)
    assert len(truncated) <= 8000 + len("…(超长截断)")
    body = truncated[: -len("…(超长截断)")]
    assert body.endswith("}")
    assert not body.endswith('{"id":')  # 未停在半个对象中间


def test_plain_text_falls_back_to_hard_cut() -> None:
    """无可靠 JSON 边界时退回硬截断，仍带截断标记。"""
    truncated = _truncate("字" * 10000)
    assert truncated.endswith("…(超长截断)")
    assert len(truncated) <= 8000 + len("…(超长截断)")
