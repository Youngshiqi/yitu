# Yitu Backend Phase 3 Commerce and Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付计价、支付、SLA、通知、异常、取消退回、可靠异步处理和可恢复演示闭环。

**Architecture:** 价格/SLA 使用版本化确定性策略；业务事务追加 Outbox，消费者幂等；异常和退回拥有独立生命周期但只能通过运单应用服务改变履约。

**Tech Stack:** Phase 1–2 stack、Celery Beat、SSE、qrcode/barcode payload generation。

## Global Constraints

- 金额为整数分，历史报价和 SLA 实例冻结规则版本。
- 通知失败不回滚履约；异常恢复必须显式调用 `resume_shipment`。
- 所有恢复、重派和退回动作记录原因、前后状态、操作者和幂等键。

---

### Task 1: Versioned Pricing and Quote Snapshots

**Files:** Create `backend/src/yitu/pricing/{models,schemas,policy,service,router}.py`; migration `0010`; tests `backend/tests/pricing/test_quotes.py`.

**Interfaces:** Produces `PricingService.quote()`, `reweigh()`, `QuoteSnapshot`, fee breakdown routes.

- [ ] Test dimensional weight, integer rounding, version effective time, historical stability and unsupported route.
- [ ] Run `cd backend; uv run pytest tests/pricing -q`; expect missing pricing module.
- [ ] Implement versioned templates and pure policy returning itemized integer amounts; persist inputs and rule snapshot.
- [ ] Run migration and `uv run pytest tests/pricing -q`; expect all pass.
- [ ] Commit `feat: add versioned shipment pricing`.

### Task 2: Simulated Payments, Supplements, Cancellation Refunds

**Files:** Create `backend/src/yitu/payments/{models,schemas,service,router}.py`; migration `0011`; tests `backend/tests/payments/test_flows.py`.

**Interfaces:** Produces `pay_quote()`, `pay_supplement()`, `refund_payment()`, immutable `PaymentTransaction`.

- [ ] Test duplicate callback, under/over payment rejection, reweigh supplement gate, pre-pickup cancellation and full refund.
- [ ] Run payment tests; expect missing service.
- [ ] Implement append-only payment transactions and idempotent simulated callback; shipment service consumes payment result.
- [ ] Run migration and payment/shipment tests; expect all pass.
- [ ] Commit `feat: add simulated payment lifecycle`.

### Task 3: SLA Rules, Instances, Pause/Resume, and ETA

**Files:** Create `backend/src/yitu/sla/{models,schemas,calendar,policy,service,router,tasks}.py`; migration `0012`; tests `backend/tests/sla/`.

**Interfaces:** Produces `SLAService.start/pause/resume/complete`, `calculate_eta()`, `scan_breaches()`.

- [ ] Test business-hour boundaries, UTC+8, frozen promise, paused supplement time, breach idempotency and ETA separation.
- [ ] Run SLA tests; expect missing module.
- [ ] Implement versioned rules, stage instances, injected Clock and idempotent scan windows.
- [ ] Run migration and SLA tests; expect all pass.
- [ ] Commit `feat: track shipment SLA and ETA`.

### Task 4: Notifications, Templates, Delivery Records, and SSE

**Files:** Create `backend/src/yitu/notifications/{models,schemas,service,router,tasks,sse}.py`; migration `0013`; tests `backend/tests/notifications/`.

**Interfaces:** Produces `NotificationService.from_event()`, `deliver_channel()`, `GET /api/v1/notifications/stream`.

- [ ] Test template whitelist, logical/channel status, duplicate Outbox events, retry, simulated SMS and SSE reconnect cursor.
- [ ] Run notification tests; expect missing module.
- [ ] Implement template rendering without model execution, delivery idempotency `(event, recipient, channel)`, and bounded SSE heartbeat.
- [ ] Run migration and notification tests; expect all pass.
- [ ] Commit `feat: deliver reliable notifications`.

### Task 5: Exceptions, Reassignment, and Resume

**Files:** Create `backend/src/yitu/exceptions/{models,schemas,state_machine,service,router}.py`; migration `0014`; tests `backend/tests/exceptions/test_cases.py`.

**Interfaces:** Produces `open_case()`, `assign_case()`, `resolve_case()`, `resume_shipment()`, task reassignment actions.

- [ ] Test all exception states, station/role scope, fulfillment pause, explicit resume target and audit reasons.
- [ ] Run exception tests; expect missing lifecycle.
- [ ] Implement independent case state machine and invoke shipment/dispatch/SLA application services rather than editing foreign models.
- [ ] Run migration and exception tests; expect all pass.
- [ ] Commit `feat: add auditable exception handling`.

### Task 6: Cancellation, Interception, Redelivery, Pickup Conversion, and Return

**Files:** Create `backend/src/yitu/returns/{models,schemas,service,router}.py`; migration `0015`; tests `backend/tests/journeys/test_recovery_flows.py`.

**Interfaces:** Produces explicit `cancel`, `request_interception`, `redeliver`, `convert_to_pickup`, `approve_return`, `advance_return` actions.

- [ ] Test pre/post-payment cancellation, post-pickup interception, refusal, two failures, new tasks/SLA, return transport and refund effects.
- [ ] Run recovery journey tests; expect missing actions.
- [ ] Implement return lifecycle with new legs/tasks and append-only tracking/audit/payment effects.
- [ ] Run migration and recovery tests; expect all pass.
- [ ] Commit `feat: close cancellation and return flows`.

### Task 7: Electronic Label, Dead-Letter Operations, and Phase Gate

**Files:** Create `backend/src/yitu/labels/service.py`; create `backend/src/yitu/platform/admin_router.py`; tests `backend/tests/journeys/test_commerce_reliability.py`, `test_dead_letter_replay.py`; modify README.

**Interfaces:** Produces safe QR query token, Code 128 shipment value, admin dead-letter list/replay routes.

- [ ] Test labels contain no PII, failed consumers dead-letter after five attempts, replay is idempotent, and old published facts remain intact.
- [ ] Implement label payload projection and system-admin-only dead-letter operations.
- [ ] Run `cd backend; uv run ruff check .; uv run mypy src; uv run pytest -q; uv run alembic downgrade base; uv run alembic upgrade head`.
- [ ] Run one normal and one exception HTTP journey in Compose; expect deterministic results.
- [ ] Commit `feat: complete reliable fulfillment backend`.
