import pytest

from yitu.notifications.templates import render_template


def test_render_template_uses_whitelisted_chinese_template() -> None:
    result = render_template("PAYMENT_SUCCESS", {"shipment_no": "YT20260810001"})
    assert result.title == "支付成功"
    assert result.content == "运单 YT20260810001 已支付成功，等待揽收。"


def test_render_template_rejects_unknown_code_and_missing_variable() -> None:
    with pytest.raises(ValueError, match="不支持"):
        render_template("UNSAFE", {})
    with pytest.raises(ValueError, match="缺少"):
        render_template("PAYMENT_SUCCESS", {})
