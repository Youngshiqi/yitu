# Agent Streaming And Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让客户消息立即显示、AI 回复通过 SSE 增量展示，并固定为 Yitu 智能物流寄件助手身份。

**Architecture:** 保留现有整包消息接口用于兼容，新增 `POST /messages/stream`。流式请求先持久化用户消息，再按 `user_message`、`delta`、`done`/`error` 事件输出；模型完整回复在 `done` 前持久化。前端通过带 Bearer 令牌的 `fetch` 读取 SSE，不使用无法自定义请求头的原生 `EventSource`。

**Tech Stack:** FastAPI `StreamingResponse`、异步 OpenAI-compatible 流、Vue 3、TypeScript、Fetch Streams。

## Global Constraints

- 系统提示词必须明确 Yitu 身份，不向客户声明底层模型供应商。
- 确定性工具分支允许单段输出，普通对话使用真实模型增量。
- 不运行全量 pytest；只做 Ruff、mypy、Vue 类型检查和真实 HTTP 联调。

---

### Task 1: 固定模型身份上下文

**Files:**
- Modify: `backend/src/yitu/agent/prompts.py`
- Modify: `backend/src/yitu/agent/context.py`

- [ ] 将 `SYSTEM_PROMPT` 固定放在每次模型上下文首位。
- [ ] 明确回答身份时仅介绍 Yitu 物流助手及职责。

### Task 2: 增加真正的流式消息接口

**Files:**
- Modify: `backend/src/yitu/agent/service.py`
- Modify: `backend/src/yitu/agent/router.py`
- Modify: `backend/src/yitu/agent/sse.py`

- [ ] 定义 `user_message`、`delta`、`done`、`error` SSE 事件。
- [ ] 普通对话调用 `ModelAdapter.stream()`，拼接完整文本后持久化。
- [ ] 工具和受控分支使用相同事件协议返回确定性文本。

### Task 3: 前端即时渲染并消费 SSE

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.vue`

- [ ] 发送前立即加入本地用户消息和空助手气泡。
- [ ] 使用带 Authorization 的 `fetch` 读取并解析 SSE。
- [ ] 增量更新助手气泡，完成后替换为持久化消息；失败时保留用户消息并展示错误。

### Task 4: 定向验证

**Files:**
- Verify only

- [ ] 运行后端 Ruff 与 mypy。
- [ ] 运行 `vue-tsc --noEmit`。
- [ ] 真实登录后验证“你是谁”身份和至少两个 `delta` 的流式响应。
- [ ] 运行 `git diff --check` 并确认未修改无关数据。
