# Yitu Backend Phase 2 Logistics Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 通过真实 HTTP 接口交付五角色身份、网点匹配、运单状态机、四种寄收组合、任务、干线、轨迹、自取码和签收凭证。

**Architecture:** 路由只处理 HTTP，应用服务校验角色、范围、状态与幂等，领域状态机决定转换；聚合变更、轨迹、审计和 Outbox 在同一事务提交。

**Tech Stack:** Phase 1 stack、PyJWT、Argon2id、SQLAlchemy 条件更新、pytest/HTTPX。

## Global Constraints

- 先完成 Phase 1；使用 `/api/v1`、东八区时间和统一错误。
- 不提供通用状态修改接口；自寄不建揽收任务，自取不建派送任务。
- 取件码只存 Argon2id + pepper 哈希，普通日志和模型上下文不得出现明文。

---

### Task 1: Identity and Five-Role Authorization

**Files:** Create `backend/src/yitu/identity/{models,schemas,security,service,router}.py`; create migration `0004`; test `backend/tests/identity/test_auth.py` and `test_scope.py`; modify `main.py`.

**Interfaces:** Produces `Role`, `CurrentUser`, `require_roles(*roles)`, `POST /api/v1/auth/demo-login`, `GET /api/v1/auth/me`.

- [ ] Write failing tests for seven demo identities mapping to five roles, invalid credentials, wrong role and station scope.
- [ ] Run `cd backend; uv run pytest tests/identity -q`; expect missing routes/models.
- [ ] Implement Argon2 password hashes, JWT `sub/role/station_id`, current-user dependency and demo-login guard `APP_PROFILE=demo`.
- [ ] Run `cd backend; uv run alembic upgrade head; uv run pytest tests/identity -q`; expect all pass.
- [ ] Commit with `git commit -m "feat: add scoped identity and demo login"`.

### Task 2: Stations, Addresses, and Service Areas

**Files:** Create `backend/src/yitu/stations/{models,schemas,service,router}.py`; migration `0005`; tests `backend/tests/stations/test_matching.py` and `test_api.py`.

**Interfaces:** Produces `match_station(district_code, service_type)`, station/address DTOs, `GET /api/v1/stations`, address-book CRUD for the current customer.

- [ ] Write parameterized tests for Beijing/Shanghai/Guangzhou/Shenzhen districts, unsupported districts, drop-off selection and cross-user address access.
- [ ] Run `cd backend; uv run pytest tests/stations -q`; expect missing module.
- [ ] Implement deterministic district mappings, versioned service areas, customer ownership checks and seeded stations.
- [ ] Run `cd backend; uv run alembic upgrade head; uv run pytest tests/stations -q`; expect all pass.
- [ ] Commit with `git commit -m "feat: add deterministic station matching"`.

### Task 3: Shipment Aggregate, Draft, State Machine, and Creation

**Files:** Create `backend/src/yitu/shipments/{enums,models,schemas,state_machine,service,router}.py`; create `backend/src/yitu/tracking/{models,schemas,service}.py`; migration `0006`; tests `backend/tests/shipments/test_creation.py` and `test_state_machine.py`.

**Interfaces:** Produces `ShipmentStatus`, `ShipmentDraft`, `CreateShipmentCommand`, `ShipmentApplicationService.create(command, actor, idempotency_key) -> ShipmentView`, `transition()`, `append_tracking_event()`, shipment create/list/detail routes.

- [ ] Write failing tests for ownership, four service combinations, unsupported routes, illegal direct transitions and idempotent creation.
- [ ] Run `cd backend; uv run pytest tests/shipments/test_creation.py tests/shipments/test_state_machine.py -q`; expect missing aggregate.
- [ ] Implement one-package aggregate, immutable shipment number, explicit transition table, customer-visible tracking projection and `allowed_actions` response.
- [ ] Run `cd backend; uv run alembic upgrade head; uv run pytest tests/shipments -q`; expect all pass.
- [ ] Commit with `git commit -m "feat: create shipments through explicit transitions"`.

### Task 4: Pickup, Drop-Off, and Atomic Task Acceptance

**Files:** Create `backend/src/yitu/dispatch/{models,schemas,service,router}.py`; migration `0007`; tests `backend/tests/dispatch/test_pickup.py`, `test_concurrency.py`.

**Interfaces:** Produces `CourierTaskType`, `CourierTaskStatus`, `accept_task()`, `confirm_pickup()`, `accept_dropoff()`, `confirm_origin_arrival()` and corresponding routes.

- [ ] Write tests that two couriers concurrently accept one task and exactly one receives 200 while the other receives `409 TASK_ALREADY_ASSIGNED`.
- [ ] Run `cd backend; uv run pytest tests/dispatch -q`; expect missing task persistence.
- [ ] Implement conditional `UPDATE ... WHERE status=AVAILABLE RETURNING`, owner/station checks, state transitions, tracking and audit in one transaction.
- [ ] Run `cd backend; uv run alembic upgrade head; uv run pytest tests/dispatch -q`; expect all pass.
- [ ] Commit with `git commit -m "feat: fulfill origin pickup and dropoff"`.

### Task 5: Linehaul and Destination Branching

**Files:** Modify shipment models/service/router; migration `0008`; test `backend/tests/shipments/test_linehaul.py`.

**Interfaces:** Produces `dispatch_linehaul()`, `arrive_destination()`, `TransportLeg`; creates delivery task or pickup credential request according to delivery method.

- [ ] Write failing tests for origin operator departure, operations-admin arrival, premature arrival rejection and delivery-method branching.
- [ ] Run `cd backend; uv run pytest tests/shipments/test_linehaul.py -q`; expect missing transport leg.
- [ ] Implement transport-leg persistence and explicit `AT_ORIGIN_STATION → IN_LINEHAUL → destination` actions with tracking and audit.
- [ ] Run `cd backend; uv run alembic upgrade head; uv run pytest tests/shipments/test_linehaul.py -q`; expect all pass.
- [ ] Commit with `git commit -m "feat: simulate linehaul arrival"`.

### Task 6: Delivery, Station Pickup, and Proof of Delivery

**Files:** Modify dispatch/shipments; create `backend/src/yitu/shipments/credentials.py`; migration `0009`; tests `backend/tests/shipments/test_last_mile.py`.

**Interfaces:** Produces `start_delivery()`, `confirm_delivery()`, `issue_pickup_credential()`, `verify_station_pickup()`, `ProofOfDelivery`.

- [ ] Write failing tests for courier ownership, one proof/event only, five bad pickup attempts, lock/reissue, expiry and idempotent successful replay.
- [ ] Run `cd backend; uv run pytest tests/shipments/test_last_mile.py -q`; expect missing credential/proof.
- [ ] Implement six-digit credential hashing with server pepper, atomic attempt/consume updates, delivery proofs and terminal transition.
- [ ] Run `cd backend; uv run alembic upgrade head; uv run pytest tests/shipments/test_last_mile.py -q`; expect all pass.
- [ ] Commit with `git commit -m "feat: complete last-mile delivery"`.

### Task 7: Four-Journey Phase Gate and Demo Seed

**Files:** Create `backend/src/yitu/demo/seed.py`; tests `backend/tests/journeys/test_service_combinations.py`, `test_authorization_matrix.py`, `test_tracking.py`; modify Compose/README.

**Interfaces:** Produces seven deterministic identities and a reusable HTTP-only `JourneyClient`.

- [ ] Write a four-row pickup/delivery matrix and authorization cases for every mutating route.
- [ ] Run `cd backend; uv run pytest tests/journeys -q`; expect journey failures until fixtures and missing projections are completed.
- [ ] Add deterministic seed and HTTP helpers without calling ORM/services directly from journey tests.
- [ ] Run `cd backend; uv run ruff check .; uv run mypy src; uv run pytest -q; uv run alembic downgrade base; uv run alembic upgrade head`; expect all pass.
- [ ] Commit with `git commit -m "test: verify logistics core journeys"`.
