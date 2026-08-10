"""通知正文的白名单模板。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RenderedTemplate:
    """已完成变量替换的通知正文。"""

    title: str
    content: str


_TEMPLATES: dict[str, RenderedTemplate] = {
    "PAYMENT_SUCCESS": RenderedTemplate(
        title="支付成功",
        content="运单 {shipment_no} 已支付成功，等待揽收。",
    ),
    "SHIPMENT_DELIVERED": RenderedTemplate(
        title="运单已送达",
        content="运单 {shipment_no} 已完成送达。",
    ),
    "SLA_BREACH": RenderedTemplate(
        title="运输时效提醒",
        content="运单 {shipment_no} 的 {stage} 阶段可能延误，请关注后续轨迹。",
    ),
    "EXCEPTION_OPENED": RenderedTemplate(
        title="运单异常已受理",
        content="运单 {shipment_no} 出现异常，正在处理中。",
    ),
}


def render_template(template_code: str, data: dict[str, object]) -> RenderedTemplate:
    """渲染系统白名单模板，拒绝未知模板和缺失变量。"""
    template = _TEMPLATES.get(template_code)
    if template is None:
        raise ValueError("不支持的通知模板")
    try:
        return RenderedTemplate(
            title=template.title.format_map(data),
            content=template.content.format_map(data),
        )
    except KeyError as error:
        raise ValueError(f"通知模板缺少变量: {error.args[0]}") from error
