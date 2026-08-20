"""LangGraph 使用的类型化 Agent 编排状态。"""

from operator import add
from typing import Annotated, Literal, TypedDict

AgentIntent = Literal[
    "GENERAL_CHAT",
    "KNOWLEDGE_QUERY",
    "PRICING_QUERY",
    "SHIPMENT_QUERY",
    "DRAFT_UPDATE",
    "SENSITIVE_ACTION",
    "ADDRESS_QUERY",
    "IDENTITY_QUERY",
]
AgentRisk = Literal["LOW", "PERSONAL_DATA", "WRITE_ACTION", "BLOCKED"]
AgentRoute = Literal[
    "respond",
    "knowledge",
    "pricing_rule",
    "read_tool",
    "draft",
    "confirmation",
    "blocked",
    "address_tool",
    "identity_tool",
]


class AgentState(TypedDict, total=False):
    """保存一次图执行的编排信息，不复制业务模块中的事实。"""

    # 身份与输入
    conversation_id: str  # 会话ID
    user_id: str          # 用户ID
    user_role: str        # 用户角色
    user_message: str     # 用户这轮说的话原文
    history: list[dict[str, str]] # 会话历史记录 【格式：role: message】


    # 意图理解结果，由图外UnderstandingService算好塞进来，前缀为 semantic_
    semantic_intents: list[AgentIntent]  # 识别出多个候选意图，最多三个(按置信度排序)
    semantic_intent: AgentIntent        # 主意图
    semantic_confidence: float         # 置信度0-1
    semantic_shipment_no: str | None   # 从原话提取的运单号(YT开头)，没有则None
    semantic_knowledge_query: str | None # 改写之后的检索词
    semantic_draft: dict[str, object]  # 从原话提取的草稿候选字段（重量/尺寸/地址等）
    requires_confirmation: bool        # 是否需要人工确认
    clarification_question: str | None # 置信度底时生成的追问问题

    # 路由结果 主图 classify_intent 节点裁决出来的，无前缀
    intent: AgentIntent # 裁决后的最终意图
    risk: AgentRisk     # 风险等级 LOW/PERSONAL_DATA/WRITE_ACTION/BLOCKED
    route: AgentRoute   # 路由结果 respond/knowledge/pricing_rule/read_tool/draft/confirmation/address_tool/identity_tool/blocked
    next_action: str    # 工具节点产出的确定性动作，如 QUERY_PRICING_RULES
    response: str       # 主图节点产出的临时回复文案
    refusal_reason: str | None  # 拒绝原因，如安全拦截/预算超限时
    
    # 执行预算，防止AI无限循环
    turn_count: int       # 当前已跑轮次
    tool_call_count: int  # 已调工具次数
    max_turns: int        # 最大轮次上限默认为8，超过后会拒绝
    max_tool_calls: int   # 工具调用上限，默认为4
    execution_started_at: float # 执行开始时间戳
    timeout_seconds: float # 超时秒数


    # 草稿子图专用（只有进 draft 分支才用）
    draft_missing_fields: list[str] # 草稿还缺少哪些字段
    draft_filled_fields: str        # 已填充字段的文本描述
    address_labels: list[str]       # 用户地址簿的标签列表（只给标签，不给电话/门牌），供模型选地址用
    draft_turns: Annotated[list[dict[str, object]], add] # 草稿 loop 的对话轮次
    draft_response: str             # 草稿 loop 的最终回复
    # 地址簿外新地址的历史收集信号字段，保留向后兼容；当前已改为 save_address 工具直接落库。
    pending_address: dict[str, object] | None
