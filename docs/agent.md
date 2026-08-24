# Agent 使用与验收指南

Agent 的会话、消息、草稿、授权和记忆都由后端确定性服务裁决。LangGraph 通过 7 节点主图和 8 节点寄件子图拥有完整控制流；模型只能调用白名单工具，不能直接修改运单或绕过权限。

## 关键流程

1. 创建会话：`POST /api/v1/agent/conversations`
2. 向统一助手入口发送需求：`POST .../{conversation_id}/messages/stream`
3. 寄件子图自主补全草稿，确定性节点校验并报价
4. `interrupt()` 暂停，用户确认后恢复并通过一次性授权创建运单

授权绑定草稿 revision、报价 ID/版本和命令快照，默认五分钟有效且只能消费一次。会话删除会级联删除消息、草稿和授权。

## 追踪与评测

节点 trace 和工具参数不会暴露给前端；公开流保持 `user_message/delta/done/error`。固定评测位于 `backend/evals/`，运行：

```bash
cd backend
PYTHONPATH=src uv run python evals/run.py
```

在线模型冒烟测试尚未执行。启用前必须先配置模型供应商、API Key 和预算，并只运行有界请求。

## 工作流状态

主图和子图使用独立 State，通过 `ShipmentHandoff` / `ShipmentWorkflowResult` 交换最小信息。Checkpoint 保存执行位置，PostgreSQL 保存业务事实；会话删除时同步删除 thread checkpoint。
