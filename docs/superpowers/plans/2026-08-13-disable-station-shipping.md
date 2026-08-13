# Disable Station Shipping Implementation Plan

> **For agentic workers:** Execute inline and preserve unrelated working-tree changes.

**Goal:** 禁止新运单使用网点寄件和网点自提，同时保留历史运单履约兼容性。

**Architecture:** 在运单应用服务统一拒绝非上门取件/送货上门的创建命令；客户前端移除对应入口；AI 草稿默认使用当前唯一可用组合，并在发现旧方式时返回明确业务错误。枚举、数据库字段和历史履约代码保持不变。

**Tech Stack:** FastAPI、Pydantic、Vue 3、TypeScript、Element Plus

## Global Constraints

- 不删除历史枚举和履约代码。
- 不运行完整 pytest。
- 不覆盖现有未提交改动。

### Task 1: 封锁新运单的网点服务方式

**Files:**
- Modify: `backend/src/yitu/shipments/service.py`
- Modify: `backend/src/yitu/agent/drafts.py`

- [ ] 运单创建服务拒绝网点寄件和网点自提。
- [ ] AI 草稿默认补入上门取件和送货上门。
- [ ] AI 草稿对旧方式返回稳定业务错误。

### Task 2: 移除前端入口

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/OperationsWorkspace.vue`

- [ ] 客户创建页固定显示上门取件和送货上门。
- [ ] 删除寄件、收件网点选择和无用前端状态。
- [ ] 运营端服务类型仅显示上门取件和送货上门。
- [ ] 运行后端静态检查和前端生产构建。
