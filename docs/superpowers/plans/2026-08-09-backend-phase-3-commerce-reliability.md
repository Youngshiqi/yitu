# 驿途后端阶段三：商业与履约可靠性实施计划

> **供智能体开发者使用：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按照本计划逐项实施。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 交付计价、支付、SLA、通知、异常、取消退回、可靠异步处理和可恢复演示闭环。

**架构：** 价格/SLA 使用版本化确定性策略；业务事务追加 Outbox，消费者幂等；异常和退回拥有独立生命周期，但只能通过运单应用服务改变履约。

**技术栈：** 阶段一至阶段二技术栈、Celery Beat、SSE、二维码/条形码载荷生成。

## 全局约束

- 金额为整数分，历史报价和 SLA 实例冻结规则版本。
- 通知失败不回滚履约；异常恢复必须显式调用 `resume_shipment`。
- 所有恢复、重派和退回动作记录原因、前后状态、操作者和幂等键。

---

### 任务 1：版本化计价与报价快照

**文件：** 新建 `backend/src/yitu/pricing/{models,schemas,policy,service,router}.py`；迁移 `0010`；测试 `backend/tests/pricing/test_quotes.py`。

**接口：** 产出 `PricingService.quote()`、`reweigh()`、`QuoteSnapshot` 和费用明细路由。

- [ ] 测试体积重量、整数舍入、版本生效时间、历史结果稳定性和不支持的路线。
- [ ] 运行 `cd backend; uv run pytest tests/pricing -q`；预期因缺少计价模块而失败。
- [ ] 实现版本化模板和返回整数分项金额的纯策略；持久化输入与规则快照。
- [ ] 运行迁移和 `uv run pytest tests/pricing -q`；预期全部通过。
- [ ] 提交：`功能：新增版本化运单计价`。

### 任务 2：模拟支付、补差价与取消退款

**文件：** 新建 `backend/src/yitu/payments/{models,schemas,service,router}.py`；迁移 `0011`；测试 `backend/tests/payments/test_flows.py`。

**接口：** 产出 `pay_quote()`、`pay_supplement()`、`refund_payment()` 和不可变的 `PaymentTransaction`。

- [ ] 测试重复回调、少付/多付拒绝、复重补差门槛、揽收前取消和全额退款。
- [ ] 运行支付测试；预期因缺少服务而失败。
- [ ] 实现只追加的支付交易和幂等模拟回调；由运单服务消费支付结果。
- [ ] 运行迁移以及支付/运单测试；预期全部通过。
- [ ] 提交：`功能：新增模拟支付生命周期`。

### 任务 3：SLA 规则、实例、暂停/恢复与 ETA

**文件：** 新建 `backend/src/yitu/sla/{models,schemas,calendar,policy,service,router,tasks}.py`；迁移 `0012`；测试 `backend/tests/sla/`。

**接口：** 产出 `SLAService.start/pause/resume/complete`、`calculate_eta()`、`scan_breaches()`。

- [ ] 测试工作时间边界、UTC+8、冻结承诺、暂停补差时间、超时扫描幂等和 ETA 分离。
- [ ] 运行 SLA 测试；预期因缺少模块而失败。
- [ ] 实现版本化规则、阶段实例、注入式 Clock 和幂等扫描窗口。
- [ ] 运行迁移和 SLA 测试；预期全部通过。
- [ ] 提交：`功能：跟踪运单 SLA 与 ETA`。

### 任务 4：通知、模板、投递记录与 SSE

**文件：** 新建 `backend/src/yitu/notifications/{models,schemas,service,router,tasks,sse}.py`；迁移 `0013`；测试 `backend/tests/notifications/`。

**接口：** 产出 `NotificationService.from_event()`、`deliver_channel()`、`GET /api/v1/notifications/stream`。

- [ ] 测试模板白名单、逻辑/渠道状态、重复 Outbox 事件、重试、模拟短信和 SSE 重连游标。
- [ ] 运行通知测试；预期因缺少模块而失败。
- [ ] 实现不调用模型的模板渲染、投递幂等键 `(event, recipient, channel)` 和有界 SSE 心跳。
- [ ] 运行迁移和通知测试；预期全部通过。
- [ ] 提交：`功能：交付可靠通知`。

### 任务 5：异常、重新分配与恢复履约

**文件：** 新建 `backend/src/yitu/exceptions/{models,schemas,state_machine,service,router}.py`；迁移 `0014`；测试 `backend/tests/exceptions/test_cases.py`。

**接口：** 产出 `open_case()`、`assign_case()`、`resolve_case()`、`resume_shipment()` 和任务重新分配动作。

- [ ] 测试全部异常状态、网点/角色范围、履约暂停、显式恢复目标和审计原因。
- [ ] 运行异常测试；预期因缺少生命周期而失败。
- [ ] 实现独立的异常单状态机，并调用运单、调度和 SLA 应用服务，不直接修改其他模块的模型。
- [ ] 运行迁移和异常测试；预期全部通过。
- [ ] 提交：`功能：新增可审计异常处理`。

### 任务 6：取消、拦截、再次派送、转自取与退回

**文件：** 新建 `backend/src/yitu/returns/{models,schemas,service,router}.py`；迁移 `0015`；测试 `backend/tests/journeys/test_recovery_flows.py`。

**接口：** 产出显式的 `cancel`、`request_interception`、`redeliver`、`convert_to_pickup`、`approve_return`、`advance_return` 动作。

- [ ] 测试支付前/后取消、揽收后拦截、拒收、两次失败、新任务/SLA、退回运输和退款影响。
- [ ] 运行恢复旅程测试；预期因缺少动作而失败。
- [ ] 使用新的运输段和任务实现退回生命周期，并只追加轨迹、审计和支付影响。
- [ ] 运行迁移和恢复测试；预期全部通过。
- [ ] 提交：`功能：闭环取消与退回流程`。

### 任务 7：电子面单、死信操作与阶段验收

**文件：** 新建 `backend/src/yitu/labels/service.py`；新建 `backend/src/yitu/platform/admin_router.py`；测试 `backend/tests/journeys/test_commerce_reliability.py`、`test_dead_letter_replay.py`；修改 README。

**接口：** 产出安全的二维码查询令牌、Code 128 运单值，以及管理员死信列表/重放路由。

- [ ] 测试面单不包含个人敏感信息、消费者失败五次后进入死信、重放幂等，且已发布的旧事实保持完整。
- [ ] 实现面单载荷投影和仅限系统管理员的死信操作。
- [ ] 运行 `cd backend; uv run ruff check .; uv run mypy src; uv run pytest -q; uv run alembic downgrade base; uv run alembic upgrade head`。
- [ ] 在 Compose 中运行一个正常旅程和一个异常旅程；预期结果确定且可重复。
- [ ] 提交：`功能：完成可靠履约后端`。
