# 驿途后端阶段二：物流核心实施计划

> **供智能体开发者使用：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按照本计划逐项实施。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 通过真实 HTTP 接口交付五角色身份、网点匹配、地址簿、运单状态机、四种寄收组合、快递员任务、模拟干线、轨迹、自取码和签收凭证。

**架构：** 路由只处理 HTTP；应用服务负责角色、网点范围、资源归属、状态和幂等校验；领域状态机决定合法转换。聚合变更、轨迹、审计和 Outbox 在同一事务提交。

**技术栈：** 阶段一技术栈、PyJWT、Argon2id、SQLAlchemy 条件更新、pytest、HTTPX。

## 全局约束

- 先完成阶段一；统一使用 `/api/v1`、`Asia/Shanghai` 时间和阶段一错误结构。
- 不提供通用状态修改接口；每个状态变化使用明确的业务动作。
- 所有写接口校验身份、角色、网点范围、资源归属、当前状态和 `Idempotency-Key`。
- 自寄不创建上门揽收任务；自取不创建派送任务。
- 取件码只存 Argon2id + pepper 哈希；普通日志、轨迹和模型上下文不得出现明文。
- 每个小任务只保留 1–3 个关键测试；并发、权限、状态机和凭证安全必须专项测试。
- 新增注释和 docstring 使用简体中文；每个小任务独立提交，提交信息使用中文。

---

## 小任务执行顺序

### 小任务 2.1：角色与身份数据模型

**文件：** 新建 `backend/src/yitu/identity/models.py`、`schemas.py`；迁移 `0004`；测试 `backend/tests/identity/test_models.py`。

**产出：** `Role`、`User`、`Station` 关联字段和七个确定性演示身份的数据结构。

- [ ] 编写角色值、用户唯一性、网点关联和演示身份字段测试。
- [ ] 运行聚焦测试，确认因模块和迁移不存在而失败。
- [ ] 实现最小模型、约束和迁移，不添加登录逻辑。
- [ ] 运行迁移与聚焦测试，确认通过。
- [ ] 提交：`功能：建立物流身份数据模型`。

### 小任务 2.2：密码哈希与 JWT 安全组件

**文件：** 新建 `backend/src/yitu/identity/security.py`；测试 `backend/tests/identity/test_security.py`。

**产出：** `hash_password()`、`verify_password()`、`create_access_token()`、`decode_access_token()`。

- [ ] 测试密码不可逆、错误密码拒绝、JWT 包含 `sub/role/station_id` 和过期令牌拒绝。
- [ ] 运行聚焦测试，确认红灯。
- [ ] 使用 Argon2id 和配置中的 JWT 密钥实现安全组件；禁止记录令牌正文。
- [ ] 运行聚焦测试和 mypy，确认通过。
- [ ] 提交：`安全：新增密码与 JWT 组件`。

### 小任务 2.3：当前用户依赖与角色/网点范围

**文件：** 新建 `backend/src/yitu/identity/service.py`；测试 `backend/tests/identity/test_scope.py`。

**产出：** `CurrentUser`、`get_current_user()`、`require_roles(*roles)`、`require_station_scope()`。

- [ ] 测试未登录、错误角色、同网点允许、跨网点拒绝和客户只能访问本人资源。
- [ ] 运行测试确认红灯。
- [ ] 实现依赖注入和统一 `AppError`，不创建路由。
- [ ] 运行测试确认权限矩阵通过。
- [ ] 提交：`功能：新增角色与网点范围校验`。

### 小任务 2.4：演示登录与当前用户接口

**文件：** 新建 `backend/src/yitu/identity/router.py`；修改 `backend/src/yitu/main.py`；测试 `backend/tests/identity/test_auth.py`。

**产出：** `POST /api/v1/auth/demo-login`、`GET /api/v1/auth/me`，仅 `APP_PROFILE=demo` 开放演示登录。

- [ ] 测试七个演示身份登录、错误凭据、非演示环境 404 和当前用户响应。
- [ ] 运行测试确认红灯。
- [ ] 实现登录路由、JWT 返回和当前用户路由；复用 2.2/2.3，不复制规则。
- [ ] 运行迁移、接口测试和健康检查。
- [ ] 提交：`功能：新增演示登录与当前用户接口`。

### 小任务 2.5：网点服务区域匹配

**文件：** 新建 `backend/src/yitu/stations/models.py`、`service.py`；迁移 `0005`；测试 `backend/tests/stations/test_matching.py`。

**产出：** `match_station(district_code, service_type) -> Station` 和确定性服务区域数据。

- [ ] 测试北京、上海、广州、深圳样例区县、不支持区县和寄件方式差异。
- [ ] 运行测试确认红灯。
- [ ] 实现版本化区域映射和网点种子数据；同样输入必须返回同一网点。
- [ ] 运行迁移与聚焦测试。
- [x] 提交：`功能：新增确定性网点服务区域匹配`。

### 小任务 2.6：网点查询与客户地址簿

**文件：** 新建 `backend/src/yitu/stations/schemas.py`、`router.py`；测试 `backend/tests/stations/test_api.py`。

**产出：** `GET /api/v1/stations` 和当前客户地址簿增删改查接口。

- [x] 测试网点筛选、地址创建/修改/删除、跨用户地址访问拒绝和统一错误响应。
- [x] 运行测试确认红灯。
- [x] 实现路由与应用服务调用，所有权校验放在服务层。
- [x] 运行接口测试和 mypy。
- [x] 提交：`功能：新增网点查询与客户地址簿`。

### 小任务 2.7：运单枚举、草稿与创建命令

**文件：** 新建 `backend/src/yitu/shipments/enums.py`、`schemas.py`；测试 `backend/tests/shipments/test_commands.py`。

**产出：** `ShipmentStatus`、`ShipmentDraft`、`CreateShipmentCommand`、四种寄收组合校验。

- [x] 测试四种合法组合、缺少地址、寄收网点不支持和禁用字段拒绝。
- [x] 运行测试确认红灯。
- [x] 实现纯 Pydantic 命令校验，不写数据库、不改变状态。
- [x] 运行聚焦测试。
- [x] 提交：`功能：定义运单命令与四种寄收组合`。

### 小任务 2.8：运单聚合与幂等创建

**文件：** 新建 `backend/src/yitu/shipments/models.py`、`service.py`；迁移 `0006`；测试 `backend/tests/shipments/test_creation.py`。

**产出：** `ShipmentApplicationService.create(command, actor, idempotency_key) -> ShipmentView`。

- [ ] 测试客户所有权、运单号不可变、相同幂等键重放和不同请求哈希冲突。
- [ ] 运行测试确认红灯。
- [ ] 实现创建事务、幂等服务调用、初始状态和 Outbox 追加；不得直接允许任意状态写入。
- [ ] 运行迁移和创建测试。
- [ ] 提交：`功能：实现运单聚合与幂等创建`。

### 小任务 2.9：运单状态机与轨迹投影

**文件：** 新建 `backend/src/yitu/shipments/state_machine.py`、`backend/src/yitu/tracking/{models,schemas,service}.py`；迁移 `0007`；测试 `backend/tests/shipments/test_state_machine.py`。

**产出：** `transition()`、`append_tracking_event()`、客户可见轨迹和 `allowed_actions`。

- [ ] 测试合法初始转换、非法跳转、重复事件和轨迹顺序。
- [ ] 运行测试确认红灯。
- [ ] 实现显式转换表；状态、轨迹、审计在同一事务写入。
- [ ] 运行迁移与状态机测试。
- [ ] 提交：`功能：实现运单状态机与轨迹记录`。

### 小任务 2.10：上门揽收与网点自寄任务

**文件：** 新建 `backend/src/yitu/dispatch/models.py`、`service.py`、`router.py`；迁移 `0008`；测试 `backend/tests/dispatch/test_pickup.py`。

**产出：** `CourierTaskType`、`CourierTaskStatus`、`accept_task()`、`confirm_pickup()`、`accept_dropoff()`、`confirm_origin_arrival()`。

- [ ] 测试上门揽收创建任务、网点自寄不创建揽收任务、任务归属和始发到站动作。
- [ ] 运行测试确认红灯。
- [ ] 实现角色/网点检查、状态转换、轨迹和审计；接单并发放在下一个小任务。
- [ ] 运行迁移与聚焦测试。
- [ ] 提交：`功能：新增始发端揽收与自寄任务`。

### 小任务 2.11：并发接单与任务所有权

**文件：** 修改 `backend/src/yitu/dispatch/service.py`；测试 `backend/tests/dispatch/test_concurrency.py`。

**产出：** 条件更新接单，两个快递员竞争时严格一成一败。

- [ ] 编写两个并发请求争抢同一任务的测试：一个返回 200，另一个返回 `409 TASK_ALREADY_ASSIGNED`。
- [ ] 运行并发测试确认红灯。
- [ ] 使用 `UPDATE ... WHERE status=AVAILABLE RETURNING` 和数据库事务锁实现原子接单。
- [ ] 连续运行并发测试 3 次，确认结果稳定。
- [ ] 提交：`并发：保证快递员任务原子接单`。

### 小任务 2.12：模拟干线运输与目标网点分支

**文件：** 新建 `backend/src/yitu/shipments/linehaul.py`；修改运单路由；迁移 `0009`；测试 `backend/tests/shipments/test_linehaul.py`。

**产出：** `dispatch_linehaul()`、`arrive_destination()`、`TransportLeg`；按收件方式创建派送任务或自取凭证请求。

- [ ] 测试始发操作员发车、运营管理员到站、过早到站拒绝和派送/自取分支。
- [ ] 运行测试确认红灯。
- [ ] 实现 `AT_ORIGIN_STATION -> IN_LINEHAUL -> AT_DESTINATION_STATION` 显式动作、运输段、轨迹和审计。
- [ ] 运行迁移与干线测试。
- [ ] 提交：`功能：新增模拟干线与目标端分支`。

### 小任务 2.13：派送与网点自取凭证

**文件：** 新建 `backend/src/yitu/shipments/credentials.py`；修改调度/运单服务；迁移 `0010`；测试 `backend/tests/shipments/test_last_mile.py`。

**产出：** `start_delivery()`、`confirm_delivery()`、`issue_pickup_credential()`、`verify_station_pickup()`、`ProofOfDelivery`。

- [ ] 测试快递员所有权、一次签收证明、六位取件码哈希、五次错误锁定、过期、补发和成功幂等重放。
- [ ] 运行末端测试确认红灯。
- [ ] 使用 Argon2id + pepper 和原子尝试/消费更新实现派送、自取和终态转换。
- [ ] 运行迁移与末端测试，确认明文凭证不出现在响应日志。
- [ ] 提交：`安全：完成派送与网点自取凭证`。

### 小任务 2.14：四种物流旅程与阶段验收

**文件：** 新建 `backend/src/yitu/demo/seed.py`；测试 `backend/tests/journeys/test_service_combinations.py`、`test_authorization_matrix.py`、`test_tracking.py`；修改 Compose/README。

**产出：** 七个确定性演示身份、纯 HTTP `JourneyClient` 和四种旅程验收。

- [ ] 编写“上门揽收-送货上门、上门揽收-网点自取、网点自寄-送货上门、网点自寄-网点自取”四行矩阵。
- [ ] 编写每个写接口的角色、网点、所有权、状态和幂等授权用例。
- [ ] 通过 HTTP 辅助工具运行四条完整旅程，断言轨迹顺序、终态和不可见明文凭证。
- [ ] 运行 `cd backend; uv run ruff check .; uv run mypy src; uv run pytest -q; uv run alembic downgrade base; uv run alembic upgrade head`。
- [ ] 提交：`测试：完成阶段二物流核心验收`。

## 阶段二完成标准

- [ ] 14 个小任务均已独立提交，提交信息为中文。
- [ ] 五种角色的登录、角色权限和网点范围均通过真实 HTTP 测试。
- [ ] 四种寄收组合均可从下单走到派送或自取终态。
- [ ] 运单、任务、轨迹、审计和 Outbox 在事务边界内保持一致。
- [ ] 并发接单、幂等重放、取件码安全和越权访问均有专项测试。
- [ ] Ruff、mypy、pytest、迁移往返和 Compose HTTP 旅程全部通过。
