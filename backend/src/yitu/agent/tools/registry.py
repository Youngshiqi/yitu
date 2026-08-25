"""Agent 可自主选择的工具注册表。

这里仅描述工具名称、用途和输入 schema；实际执行仍由
``assistant_tools_node`` 分发到对应业务服务。
"""

from yitu.agent.tools.knowledge import KnowledgeSearchInput
from yitu.agent.tools.shipments import ShipmentReadInput


def _function_tool(
    name: str, description: str, parameters: dict[str, object]
) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


_EMPTY_PARAMETERS: dict[str, object] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


ASSISTANT_TOOL_SPECS: tuple[dict[str, object], ...] = (
    _function_tool(
        "search_knowledge",
        "检索已发布且当前生效的物流规则证据。",
        KnowledgeSearchInput.model_json_schema(),
    ),
    _function_tool(
        "get_own_shipment",
        "读取当前登录客户有权访问的运单、轨迹、费用和时效。",
        ShipmentReadInput.model_json_schema(),
    ),
    _function_tool(
        "list_addresses", "读取当前客户的最小化地址选项。", _EMPTY_PARAMETERS
    ),
    _function_tool("get_current_identity", "读取当前登录身份摘要。", _EMPTY_PARAMETERS),
    _function_tool(
        "get_pricing_rules", "读取当前生效的确定性运费规则。", _EMPTY_PARAMETERS
    ),
    _function_tool(
        "start_shipment",
        "用户要新建或继续寄件时，把已明确的草稿候选字段交给寄件工作流。",
        {
            "type": "object",
            "properties": {
                "extracted_fields": {"type": "object"},
            },
            "required": ["extracted_fields"],
            "additionalProperties": False,
        },
    ),
)
