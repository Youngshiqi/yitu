# Agent 使用与验收指南

Agent 的会话、消息、草稿、授权和记忆都由后端确定性服务裁决。LangGraph 只负责编排，不能直接修改运单或绕过权限。

## 关键流程

1. 创建会话：`POST /api/v1/agent/conversations`
2. 通过草稿接口补全并报价：`PATCH .../{conversation_id}/draft`、`POST .../draft/validate`
3. 用户明确确认后签发授权：`POST .../{conversation_id}/grant`
4. 消费一次性授权创建运单：`POST /api/v1/agent/conversations/grants/{grant_id}/consume`

授权绑定草稿 revision、报价 ID/版本和命令快照，默认五分钟有效且只能消费一次。会话删除会级联删除消息、草稿和授权。

## 追踪与评测

每个 Agent 回合的助手消息信封包含 `trace_id`，用于关联路由、工具和审计事件。固定评测集位于 `backend/evals/cases/`，运行：

```bash
cd backend
PYTHONPATH=src uv run python evals/run.py
```

在线模型冒烟测试尚未执行。启用前必须先配置模型供应商、API Key 和预算，并只运行有界请求。

## 在线验收记录

2026-08-12 使用 DeepSeek OpenAI-compatible 接口完成有界冒烟：普通对话返回模型回复并生成 `trace_id`；“确认下单”进入 `confirmation` 且要求显式确认；“禁寄规则”进入 `knowledge`。未执行授权消费和正式运单创建。
