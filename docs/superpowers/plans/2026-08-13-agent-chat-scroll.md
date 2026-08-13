# AI Chat Scroll Implementation Plan

> **For agentic workers:** Implement this task inline and preserve unrelated working-tree changes.

**Goal:** 固定 AI 寄件工作区高度，让消息区独立滚动并在流式回复时跟随最新消息。

**Architecture:** 保持现有三栏组件结构，只通过 Vue DOM 引用控制消息滚动，通过 CSS 的明确高度和 `min-height: 0` 建立稳定的滚动边界。

**Tech Stack:** Vue 3、TypeScript、Element Plus、CSS

## Global Constraints

- 不修改后端。
- 不运行 pytest。
- 不覆盖现有未提交改动。

### Task 1: 固定聊天布局并增加自动滚动

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/styles.css`

- [ ] 为消息容器添加模板引用。
- [ ] 消息新增或流式内容变化后滚动到底部。
- [ ] AI 工作区使用视口剩余高度，三栏内容独立滚动。
- [ ] 运行 `npm run build` 验证 TypeScript 与生产构建。
