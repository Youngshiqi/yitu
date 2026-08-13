# Agent Structured Understanding Implementation Plan

> **For agentic workers:** Execute inline and preserve unrelated working-tree changes.

**Goal:** 用模型结构化语义理解替代业务关键词意图分类，并让寄件对话能够提取和更新草稿字段。

**Architecture:** 新增 `UnderstandingService` 深模块，统一隐藏提示词、JSON 输出、Pydantic 校验、置信度降级和地址引用字段。会话服务先调用理解模块，再把可信结构化结果交给 LangGraph；LangGraph 保留安全预检查、预算和确定性路由，工具与写操作继续经过后端权限校验。

**Tech Stack:** FastAPI、Pydantic、LangGraph、OpenAI-compatible SDK、DeepSeek

## Global Constraints

- 不允许模型提供 user_id、address_id 或直接执行写操作。
- 安全拦截、资源归属、显式确认和业务校验保持确定性。
- 不运行完整 pytest。
- 新增复杂逻辑使用中文注释和 docstring。

### Task 1: 结构化模型输出

**Files:**
- Modify: `backend/src/yitu/agent/model_adapter.py`
- Create: `backend/src/yitu/agent/understanding.py`

- [ ] 为模型适配器增加 Pydantic 结构化输出接口。
- [ ] 定义意图、置信度、参数和草稿候选字段契约。
- [ ] 对解析失败、低置信度和模型不可用提供安全降级。

### Task 2: LangGraph 与会话接线

**Files:**
- Modify: `backend/src/yitu/agent/state.py`
- Modify: `backend/src/yitu/agent/nodes.py`
- Modify: `backend/src/yitu/agent/service.py`

- [ ] 删除业务关键词路由，保留安全预检查。
- [ ] 将理解结果注入图状态并由后端映射路由。
- [ ] 运单查询和知识检索使用结构化参数。
- [ ] 草稿意图解析当前用户地址标签并更新草稿。
- [ ] 运行 Ruff、mypy 和针对性非 pytest 验证。
