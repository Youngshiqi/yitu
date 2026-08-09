# 驿途后端阶段二：物流核心实施计划

> **供智能体开发者使用：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按照本计划逐项实施。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 通过真实 HTTP 接口交付五角色身份、网点匹配、运单状态机、四种寄收组合、任务、干线、轨迹、自取码和签收凭证。

**架构：** 路由只处理 HTTP，应用服务校验角色、范围、状态与幂等，领域状态机决定转换；聚合变更、轨迹、审计和 Outbox 在同一事务提交。

**技术栈：** 阶段一技术栈、PyJWT、Argon2id、SQLAlchemy 条件更新、pytest/HTTPX。

## 全局约束

- 先完成阶段一；使用 `/api/v1`、东八区时间和统一错误。
- 不提供通用状态修改接口；自寄不建揽收任务，自取不建派送任务。
- 取件码只存 Argon2id + pepper 哈希，普通日志和模型上下文不得出现明文。

---

### 任务 1：身份与五角色授权

**文件：** 新建 `backend/src/yitu/identity/{models,schemas,security,service,router}.py`；新建迁移 `0004`；测试 `backend/tests/identity/test_auth.py` 和 `test_scope.py`；修改 `main.py`。

**接口：** 产出 `Role`、`CurrentUser`、`require_roles(*roles)`、`POST /api/v1/auth/demo-login`、`GET /api/v1/auth/me`。

- [ ] 为七个演示身份到五种角色的映射、无效凭据、错误角色和网点范围编写失败测试。
- [ ] 运行 `cd backend; uv run pytest tests/identity -q`；预期因缺少路由和模型而失败。
- [ ] 实现 Argon2 密码哈希、JWT `sub/role/station_id`、当前用户依赖，以及受 `APP_PROFILE=demo` 保护的演示登录。
- [ ] 运行 `cd backend; uv run alembic upgrade head; uv run pytest tests/identity -q`；预期全部通过。
- [ ] 提交：`git commit -m "功能：新增范围受控的身份与演示登录"`。

### 任务 2：网点、地址与服务区域

**文件：** 新建 `backend/src/yitu/stations/{models,schemas,service,router}.py`；迁移 `0005`；测试 `backend/tests/stations/test_matching.py` 和 `test_api.py`。

**接口：** 产出 `match_station(district_code, service_type)`、网点/地址 DTO、`GET /api/v1/stations`，以及当前客户的地址簿增删改查接口。

- [ ] 为北京、上海、广州、深圳的区县、不支持的区县、自寄网点选择和跨用户地址访问编写参数化测试。
- [ ] 运行 `cd backend; uv run pytest tests/stations -q`；预期因缺少模块而失败。
- [ ] 实现确定性区县映射、版本化服务区域、客户所有权检查和网点种子数据。
- [ ] 运行 `cd backend; uv run alembic upgrade head; uv run pytest tests/stations -q`；预期全部通过。
- [ ] 提交：`git commit -m "功能：新增确定性网点匹配"`。

### 任务 3：运单聚合、草稿、状态机与创建

**文件：** 新建 `backend/src/yitu/shipments/{enums,models,schemas,state_machine,service,router}.py`；新建 `backend/src/yitu/tracking/{models,schemas,service}.py`；迁移 `0006`；测试 `backend/tests/shipments/test_creation.py` 和 `test_state_machine.py`。

**接口：** 产出 `ShipmentStatus`、`ShipmentDraft`、`CreateShipmentCommand`、`ShipmentApplicationService.create(command, actor, idempotency_key) -> ShipmentView`、`transition()`、`append_tracking_event()`，以及运单创建、列表和详情路由。

- [ ] 为所有权、四种服务组合、不支持的路线、非法直接状态转换和幂等创建编写失败测试。
- [ ] 运行 `cd backend; uv run pytest tests/shipments/test_creation.py tests/shipments/test_state_machine.py -q`；预期因缺少聚合而失败。
- [ ] 实现单包裹聚合、不可变运单号、显式状态转换表、客户可见轨迹投影和 `allowed_actions` 响应。
- [ ] 运行 `cd backend; uv run alembic upgrade head; uv run pytest tests/shipments -q`；预期全部通过。
- [ ] 提交：`git commit -m "功能：通过显式状态转换创建运单"`。

### 任务 4：上门揽收、网点自寄与原子接单

**文件：** 新建 `backend/src/yitu/dispatch/{models,schemas,service,router}.py`；迁移 `0007`；测试 `backend/tests/dispatch/test_pickup.py`、`test_concurrency.py`。

**接口：** 产出 `CourierTaskType`、`CourierTaskStatus`、`accept_task()`、`confirm_pickup()`、`accept_dropoff()`、`confirm_origin_arrival()` 及对应路由。

- [ ] 测试两名快递员并发接受同一任务时，只有一人获得 200，另一人获得 `409 TASK_ALREADY_ASSIGNED`。
- [ ] 运行 `cd backend; uv run pytest tests/dispatch -q`；预期因缺少任务持久化而失败。
- [ ] 在同一事务中实现条件更新 `UPDATE ... WHERE status=AVAILABLE RETURNING`、所有者/网点检查、状态转换、轨迹和审计。
- [ ] 运行 `cd backend; uv run alembic upgrade head; uv run pytest tests/dispatch -q`；预期全部通过。
- [ ] 提交：`git commit -m "功能：完成始发端揽收与自寄"`。

### 任务 5：干线运输与目标端分支

**文件：** 修改运单模型、服务和路由；迁移 `0008`；测试 `backend/tests/shipments/test_linehaul.py`。

**接口：** 产出 `dispatch_linehaul()`、`arrive_destination()`、`TransportLeg`；根据收件方式创建派送任务或自取凭证请求。

- [ ] 为始发网点操作员发车、运营管理员到站、过早到站拒绝和收件方式分支编写失败测试。
- [ ] 运行 `cd backend; uv run pytest tests/shipments/test_linehaul.py -q`；预期因缺少运输段而失败。
- [ ] 实现运输段持久化，以及带轨迹和审计的显式 `AT_ORIGIN_STATION → IN_LINEHAUL → 目标端` 动作。
- [ ] 运行 `cd backend; uv run alembic upgrade head; uv run pytest tests/shipments/test_linehaul.py -q`；预期全部通过。
- [ ] 提交：`git commit -m "功能：模拟干线到站"`。

### 任务 6：派送、网点自取与签收凭证

**文件：** 修改调度和运单模块；新建 `backend/src/yitu/shipments/credentials.py`；迁移 `0009`；测试 `backend/tests/shipments/test_last_mile.py`。

**接口：** 产出 `start_delivery()`、`confirm_delivery()`、`issue_pickup_credential()`、`verify_station_pickup()`、`ProofOfDelivery`。

- [ ] 为快递员所有权、只允许一份凭证/事件、五次错误自取尝试、锁定/补发、过期和成功结果幂等重放编写失败测试。
- [ ] 运行 `cd backend; uv run pytest tests/shipments/test_last_mile.py -q`；预期因缺少凭证和签收证明而失败。
- [ ] 使用服务端 pepper 实现六位凭证哈希、原子尝试/消费更新、签收证明和终态转换。
- [ ] 运行 `cd backend; uv run alembic upgrade head; uv run pytest tests/shipments/test_last_mile.py -q`；预期全部通过。
- [ ] 提交：`git commit -m "功能：完成末端派送与签收"`。

### 任务 7：四种旅程阶段验收与演示种子数据

**文件：** 新建 `backend/src/yitu/demo/seed.py`；测试 `backend/tests/journeys/test_service_combinations.py`、`test_authorization_matrix.py`、`test_tracking.py`；修改 Compose/README。

**接口：** 产出七个确定性身份和可复用的纯 HTTP `JourneyClient`。

- [ ] 编写四行寄件/收件组合矩阵，并为每个写路由添加授权用例。
- [ ] 运行 `cd backend; uv run pytest tests/journeys -q`；在夹具和缺失投影补齐前，预期旅程测试失败。
- [ ] 添加确定性种子数据和 HTTP 辅助工具；旅程测试不得直接调用 ORM 或服务。
- [ ] 运行 `cd backend; uv run ruff check .; uv run mypy src; uv run pytest -q; uv run alembic downgrade base; uv run alembic upgrade head`；预期全部通过。
- [ ] 提交：`git commit -m "测试：验证物流核心旅程"`。
