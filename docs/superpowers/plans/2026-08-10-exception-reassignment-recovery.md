# 阶段三任务 5：异常、任务重新分配与履约恢复实施计划

> **供实施 Agent 使用：** 必须使用 `subagent-driven-development`（推荐）或 `executing-plans`，按任务逐项实施。本计划只覆盖阶段三任务 5；每个任务均遵循测试先行、最小实现、相关回归和独立提交。

**目标：** 实现独立、可审计的异常工单生命周期，支持人工上报、SLA 超时自动开单、责任分配、阻断履约、任务重新分配和显式恢复，同时保留历史运单、任务、SLA、轨迹与通知事实。

**设计依据：** `docs/superpowers/specs/2026-08-10-exception-reassignment-recovery-design.md`

**架构：** 新增独立 `exceptions` 模块；`ExceptionService` 通过 `ShipmentControlService`、`DispatchService` 和 `SLAService` 编排同一事务，不跨模块直接修改 ORM。履约冻结使用独立 `ShipmentHold`，不增加 `ShipmentStatus.PAUSED`。Outbox 仅负责可靠通知，不异步执行异常状态机。

**技术栈：** Python 3.11、FastAPI、Pydantic v2、SQLAlchemy 2 异步模式、Alembic、PostgreSQL、Celery、pytest、HTTPX、Ruff、mypy。

## 全局约束

- 当前迁移链头是 `0017_create_notifications.py`；只新增 `0018_create_exceptions.py`，不得修改或重编号历史迁移。
- 本计划不实现取消、拦截、重新派送、转为网点自取、退回运输或相关退款；这些属于阶段三任务 6。
- 所有写接口必须要求 `Idempotency-Key`；同键同请求重放首次响应，同键不同请求返回 `IDEMPOTENCY_KEY_REUSED`。
- 所有履约推进与 Hold 变更必须先锁定 `Shipment`，再锁定异常、任务或 SLA，避免冻结快照与实际状态并发错位。
- 异常、Hold、任务关闭/替代、SLA 暂停/恢复、轨迹、审计和 Outbox 必须在调用方同一事务中提交。
- 客户轨迹只写中性事实；责任判断、敏感证据、处理人和赔付结论只进入异常单与审计。
- 通知失败不得回滚异常或履约事务。
- 新增注释和 docstring 使用简体中文；源码标识符和错误码使用 ASCII。
- 实施期间保留当前支付退款行为，不把任务 6 的取消逻辑混入本计划。

## 已识别的实现落点

1. `SLAService.scan_breaches()` 当前使用 `last_scan_key`，不同扫描窗口会再次返回已超时实例。任务 5 应把“首次违约”定义为 `breached = false → true`，保留 `last_scan_key` 仅作诊断；自动异常的 `(SLA_SCAN, instance_id)` 唯一约束作为第二道幂等保护。
2. 通知模块当前已有 `SLA_BREACH` 模板。为避免破坏现有测试，新增规格要求的 `SLA_BREACHED`，不重命名或删除旧模板。
3. `notification.requested` 每个事件只支持一个 `recipient_id`。通知多个运营管理员时，为每个接收人追加独立 Outbox 事件和稳定幂等键。
4. `SLAService.pause/resume` 当前只支持一个无来源的活动暂停。任务 5 必须扩展为按 `source_type + source_id` 管理，恢复异常 Hold 时不能结束其他来源的暂停。
5. `CourierTask` 当前没有关闭状态或替代链。任务 5 增加 `CANCELLED` 和关闭事实，但不改变既有 `AVAILABLE / ACCEPTED / COMPLETED` 语义。
6. 为避免 `shipments` 反向导入 `exceptions`，`ShipmentHold.source_id` 使用通用 UUID，不声明到 `exception_cases` 的 ORM 外键；异常服务负责来源存在性，数据库以唯一约束保护一个来源一个 Hold。

---

## 任务 1：异常枚举、默认策略与纯状态机

**文件：**

- 新建：`backend/src/yitu/exceptions/__init__.py`
- 新建：`backend/src/yitu/exceptions/enums.py`
- 新建：`backend/src/yitu/exceptions/state_machine.py`
- 新建：`backend/tests/exceptions/__init__.py`
- 新建：`backend/tests/exceptions/test_state_machine.py`

**产出：**

- `ExceptionType`：九类异常；
- `ExceptionSeverity`：`LOW / MEDIUM / HIGH / CRITICAL`；
- `ExceptionStatus`：`OPEN / ASSIGNED / PROCESSING / WAITING_FOR_CUSTOMER / RESOLVED / CLOSED`；
- `ExceptionSourceType`：`MANUAL / SLA_SCAN`；
- `ResolutionCode`：只包含任务 5 能表达的解决结果，并显式标识任务 6 才能执行的恢复动作；
- `default_policy(case_type) -> ExceptionPolicy`；
- `transition(current, action) -> ExceptionStatus`；
- 各角色允许上报类型的纯策略函数。

- [ ] **步骤 1：编写失败的纯领域测试**

覆盖：

- 六个状态和所有合法转换；
- `WAITING_FOR_CUSTOMER → PROCESSING`；
- 从 `OPEN` 直接解决、从 `RESOLVED` 重新处理、修改 `CLOSED` 等非法转换；
- 九类异常默认严重度和默认阻断属性；
- 客户、快递员、网点人员、运营管理员的允许上报类型；
- 任务 6 的取消、拦截、重派、转自取和退回解决码不会被任务 5 当作可执行恢复动作。

- [ ] **步骤 2：运行测试并确认预期失败**

```powershell
cd D:\Projects\yitu\backend
$env:UV_CACHE_DIR='D:\Projects\yitu\backend\.uv-cache'
uv run pytest tests/exceptions/test_state_machine.py -q
```

预期：测试因 `yitu.exceptions` 不存在而失败。

- [ ] **步骤 3：实现最小枚举、默认策略和状态机**

使用显式动作映射，不提供通用目标状态写入函数。非法转换抛出：

```python
AppError("INVALID_EXCEPTION_TRANSITION", "不允许该异常状态转换", 409)
```

默认策略必须与批准规格中的表格完全一致。

- [ ] **步骤 4：验证纯领域测试和静态检查**

```powershell
uv run pytest tests/exceptions/test_state_machine.py -q
uv run ruff check src/yitu/exceptions tests/exceptions/test_state_machine.py
uv run mypy src/yitu/exceptions
```

- [ ] **步骤 5：提交**

```bash
git add backend/src/yitu/exceptions backend/tests/exceptions
git commit -m "功能：定义异常生命周期规则"
```

---

## 任务 2：持久化模型与 0018 迁移

**文件：**

- 新建：`backend/src/yitu/exceptions/models.py`
- 新建：`backend/src/yitu/shipments/hold_models.py`
- 修改：`backend/src/yitu/dispatch/models.py`
- 修改：`backend/src/yitu/sla/models.py`
- 修改：`backend/migrations/env.py`
- 新建：`backend/migrations/versions/0018_create_exceptions.py`
- 新建：`backend/tests/exceptions/test_models.py`

**产出：**

- `ExceptionCase`；
- `ExceptionTaskReassignment`；
- `ShipmentHold`；
- `CourierTaskStatus.CANCELLED` 及任务关闭/替代字段；
- `SLAPause` 的来源、操作者和幂等字段；
- 查询和幂等所需唯一约束与索引。

- [ ] **步骤 1：编写失败的 PostgreSQL 模型测试**

至少断言：

- 异常单能保存完整类型、状态、来源、严重度、阻断、责任和时间字段；
- `(source_type, source_id)` 阻止同一 SLA 实例创建两张自动异常；
- 同一异常来源只能创建一个 Hold；
- 一张运单可有多个不同来源 Hold；
- 任务关闭后保留 `assignee_id`，并可指向替代任务；
- 重新分配事实关联旧任务和新任务；
- SLA 暂停可区分不同来源并保存操作者和幂等键；
- 所有业务时间字段读取后仍带时区。

- [ ] **步骤 2：运行测试并确认预期失败**

```powershell
uv run pytest tests/exceptions/test_models.py -q
```

预期：模型或数据库列不存在。

- [ ] **步骤 3：实现 ORM 模型**

关键约束：

- `ExceptionCase.source_id` 为可空 UUID；对自动来源使用 `(source_type, source_id)` 唯一约束；
- `ShipmentHold` 对 `(source_type, source_id)` 唯一，并为 `(shipment_id, active)` 建索引；
- `ExceptionTaskReassignment` 对 `(case_id, old_task_id, idempotency_key)` 唯一；
- `CourierTask.replaced_by_task_id` 是可空自引用；
- `SLAPause` 增加可空来源字段以兼容历史通用暂停，并对来源幂等键设置合适唯一约束；
- 用 `String` 存储字符串枚举，保持项目现有风格。

- [ ] **步骤 4：编写 `0018_create_exceptions.py`**

`revision = "0018"`，`down_revision = "0017"`。升级顺序：

1. 扩展 `courier_tasks`；
2. 扩展 `sla_pauses`；
3. 创建 `exception_cases`；
4. 创建 `shipment_holds`；
5. 创建 `exception_task_reassignments`；
6. 创建列表、活动 Hold、自动来源和转派查询索引。

降级必须严格反向删除：先依赖表和索引，再扩展列。不要修改 0017 或更早迁移。

- [ ] **步骤 5：接入 Alembic 元数据并执行迁移**

在 `migrations/env.py` 导入异常和 Hold 模型。运行：

```powershell
uv run alembic upgrade head
uv run pytest tests/exceptions/test_models.py -q
uv run alembic downgrade 0017
uv run alembic upgrade head
uv run pytest tests/exceptions/test_models.py -q
```

- [ ] **步骤 6：验证静态检查**

```powershell
uv run ruff check src/yitu/exceptions src/yitu/shipments/hold_models.py src/yitu/dispatch/models.py src/yitu/sla/models.py migrations/versions/0018_create_exceptions.py tests/exceptions/test_models.py
uv run mypy src
```

- [ ] **步骤 7：提交**

```bash
git add backend/src/yitu/exceptions/models.py backend/src/yitu/shipments/hold_models.py backend/src/yitu/dispatch/models.py backend/src/yitu/sla/models.py backend/migrations/env.py backend/migrations/versions/0018_create_exceptions.py backend/tests/exceptions/test_models.py
git commit -m "数据：持久化异常与履约冻结事实"
```

---

## 任务 3：运单控制服务与全履约入口阻断

**文件：**

- 新建：`backend/src/yitu/shipments/control.py`
- 修改：`backend/src/yitu/dispatch/service.py`
- 修改：`backend/src/yitu/shipments/linehaul.py`
- 修改：`backend/src/yitu/shipments/credentials.py`
- 修改：`backend/src/yitu/payments/service.py`
- 新建：`backend/tests/exceptions/test_fulfillment_holds.py`
- 修改：`backend/tests/dispatch/test_concurrency.py`

**产出：**

- `ShipmentControlService.lock_shipment()`；
- `lock_and_assert_fulfillment_allowed()`；
- `place_exception_hold()`；
- `release_exception_holds()`；
- 所有实体履约推进路径统一在运单行锁下检查活动 Hold。

- [ ] **步骤 1：编写失败的 Hold 服务与阻断测试**

覆盖活动 Hold 阻止：

- 揽收/派送任务接单；
- 确认揽收；
- 自寄验收和始发到站；
- 干线发车和目标到站；
- 开始派送；
- 派送签收和自取核销。

同时覆盖：

- 查询不受阻断；
- `place_exception_hold` 重放返回已有 Hold；
- Hold 释放后原履约动作恢复可用；
- 支付推进运单状态前也持有运单锁并检查 Hold，避免支付与异常冻结并发错位；
- 所有阻断入口返回 `SHIPMENT_FULFILLMENT_BLOCKED`。

- [ ] **步骤 2：运行测试并确认预期失败**

```powershell
uv run pytest tests/exceptions/test_fulfillment_holds.py tests/dispatch/test_concurrency.py -q
```

- [ ] **步骤 3：实现 `ShipmentControlService`**

使用 `SELECT ... FOR UPDATE` 锁定运单；检查 `ShipmentHold.active is true`。放置 Hold 时保存锁定后的当前 `Shipment.status`。释放时只更新指定来源或调用方已验证的一组 Hold，保存释放人、释放时间和释放幂等键。

不要在控制服务中导入 `ExceptionCase`；来源存在性由异常服务验证。

- [ ] **步骤 4：把统一检查接入现有履约服务**

接入顺序必须是“先锁运单并检查 Hold，再读取/更新相关任务或运输段”。避免在多个服务中复制 SQL。保留原角色、网点和任务归属校验。

`PaymentService.pay_quote()` 也必须在幂等 operation 内重新锁定运单并检查 Hold；退款行为不在本任务改造为新取消流程。

- [ ] **步骤 5：增加并发测试**

使用两个独立 Session 并发执行“放置 Hold”和“履约推进”，断言结果只能是：

- 履约先完成，Hold 保存推进后的状态；或
- Hold 先创建，履约动作被拒绝。

不得出现 Hold 保存旧状态而运单已经推进。

- [ ] **步骤 6：验证相关回归**

```powershell
uv run pytest tests/exceptions/test_fulfillment_holds.py tests/dispatch tests/shipments tests/payments/test_flows.py -q
uv run ruff check .
uv run mypy src
```

- [ ] **步骤 7：提交**

```bash
git add backend/src/yitu/shipments/control.py backend/src/yitu/dispatch/service.py backend/src/yitu/shipments/linehaul.py backend/src/yitu/shipments/credentials.py backend/src/yitu/payments/service.py backend/tests/exceptions/test_fulfillment_holds.py backend/tests/dispatch/test_concurrency.py
git commit -m "功能：阻断异常期间的履约推进"
```

---

## 任务 4：异常 Schema、人工开单、权限范围和查询 API

**文件：**

- 新建：`backend/src/yitu/exceptions/schemas.py`
- 新建：`backend/src/yitu/exceptions/service.py`
- 新建：`backend/src/yitu/exceptions/router.py`
- 修改：`backend/src/yitu/main.py`
- 修改：`backend/src/yitu/sla/service.py`
- 修改：`backend/src/yitu/notifications/templates.py`
- 修改：`backend/tests/notifications/test_templates.py`
- 修改：`backend/tests/sla/test_service.py`
- 新建：`backend/tests/exceptions/test_cases.py`
- 新建：`backend/tests/exceptions/test_api.py`

**产出：**

- `ExceptionService.open_case()`；
- `get_case()`、`list_cases()`；
- `POST /api/v1/exceptions`；
- `GET /api/v1/exceptions`；
- `GET /api/v1/exceptions/{case_id}`；
- 客户、快递员、网点人员、运营管理员和系统管理员读取/上报范围。

- [ ] **步骤 1：编写失败的服务层权限测试**

覆盖：

- 客户只能为本人运单上报允许类型；
- 快递员必须存在本人 `ACCEPTED` 且未完成的关联任务；
- 网点人员的网点必须是始发、目标或当前任务网点；
- 运营管理员可以上报全部类型；
- 系统管理员只能读取，不能人工上报；
- 非授权类型返回 `EXCEPTION_TYPE_NOT_ALLOWED`；
- 越权资源返回 `FORBIDDEN_EXCEPTION_SCOPE`；
- 上报者不能覆盖严重度、阻断属性、责任网点或处理人；
- 同键同请求只生成一张异常、一次轨迹、一次审计和一组通知事件；
- 同键不同请求返回 `IDEMPOTENCY_KEY_REUSED`。

- [ ] **步骤 2：编写失败的查询/API 测试**

覆盖：

- 写接口缺少 `Idempotency-Key` 返回 422；
- 客户只看到本人运单异常；
- 快递员只看到本人上报或本人任务关联异常；
- 网点人员只看到本网点范围；
- 运营管理员看到全部；
- 系统管理员只读全部；
- `shipment_id/status/case_type/severity/responsible_station_id/assigned_to/blocks_fulfillment` 筛选；
- `limit + offset` 分页；
- 不存在返回 `EXCEPTION_CASE_NOT_FOUND`。

- [ ] **步骤 3：运行测试并确认预期失败**

```powershell
uv run pytest tests/exceptions/test_cases.py tests/exceptions/test_api.py -q
```

- [ ] **步骤 4：实现 Pydantic Schema**

Schema 必须区分：上报请求、列表过滤、详情视图和分页响应。上报请求只接受 `shipment_id`、`case_type`、`description` 和可选 `evidence_summary`，避免低权限角色注入运营字段。

- [ ] **步骤 5：实现 `open_case()` 和读取范围**

在 `IdempotencyService.execute()` 的 operation 内：

1. 锁定运单；
2. 校验角色和资源范围；
3. 读取服务端默认策略；
4. 创建 `ExceptionCase(OPEN)`；
5. 阻断类型通过 `ShipmentControlService` 创建 Hold；
6. 追加中性客户轨迹；
7. 写审计；
8. 追加面向运单所有者的 `notification.requested`；
9. 返回可重放视图。

在实现 `open_case()` 前，先在 `SLAService` 落地最小且完整可用的 `pause_for_source()` / `resume_for_source()` 契约，并增加对应 SLA 测试；不能提交内部占位函数或 TODO。`open_case()` 对 `ADDRESS_ERROR` 和 `WAITING_FOR_SUPPLEMENT` 创建 Hold 后立即调用来源化暂停，其余阻断类型不暂停计时。任务 5 在该契约上补充分类升级、完整生命周期和旧管理 API 兼容。

同时先加入本任务开单所需的 `EXCEPTION_OPENED` 白名单模板及模板测试，避免创建尚不能被通知消费者物化的 Outbox 事件。其余异常模板在任务 8 补齐。

- [ ] **步骤 6：实现路由并注册**

所有写操作只在路由层提交事务。路由不得复制状态机和权限规则。

- [ ] **步骤 7：验证测试与静态检查**

```powershell
uv run pytest tests/exceptions/test_cases.py tests/exceptions/test_api.py tests/sla/test_service.py tests/notifications/test_templates.py -q
uv run pytest tests/shipments tests/dispatch -q
uv run ruff check .
uv run mypy src
```

- [ ] **步骤 8：提交**

```bash
git add backend/src/yitu/exceptions backend/src/yitu/main.py backend/src/yitu/sla/service.py backend/src/yitu/notifications/templates.py backend/tests/exceptions/test_cases.py backend/tests/exceptions/test_api.py backend/tests/sla/test_service.py backend/tests/notifications/test_templates.py
git commit -m "功能：支持受限异常上报与查询"
```

---

## 任务 5：责任分配、处理生命周期、阻断升级与来源化 SLA 暂停

**文件：**

- 修改：`backend/src/yitu/exceptions/schemas.py`
- 修改：`backend/src/yitu/exceptions/service.py`
- 修改：`backend/src/yitu/exceptions/router.py`
- 修改：`backend/src/yitu/sla/service.py`
- 修改：`backend/src/yitu/sla/router.py`
- 修改：`backend/tests/sla/test_service.py`
- 新建：`backend/tests/exceptions/test_lifecycle.py`

**产出：**

- `assign_case()`；
- `start_processing()`；
- `wait_for_customer()`；
- `resume_processing()`；
- `update_classification()`；
- `resolve_case()`；
- 来源化 `SLAService.pause/resume`。

- [ ] **步骤 1：编写失败的完整生命周期测试**

覆盖：

- `OPEN → ASSIGNED → PROCESSING → WAITING_FOR_CUSTOMER → PROCESSING → RESOLVED`；
- 处理人只能是 `STATION_OPERATOR` 或 `OPERATIONS_ADMIN`；
- 网点处理人必须属于责任网点；
- 责任网点只能是始发、目标或当前任务网点；
- 网点人员只能处理分配给本人或本网点的工单；
- 只有运营管理员能分配、调整分类和最终解决；
- 所有运营动作要求非空原因；
- 每步写前后状态、操作者和请求 ID 审计；
- 状态非法时返回 `INVALID_EXCEPTION_TRANSITION`。

- [ ] **步骤 2：编写失败的阻断升级和 SLA 来源测试**

覆盖：

- `ADDRESS_ERROR` 和 `WAITING_FOR_SUPPLEMENT` 创建 Hold 时暂停当前运行 SLA；
- `SUSPECTED_LOSS` 和严重 `DAMAGE` 创建 Hold 但不暂停 SLA；
- 非阻断 `DAMAGE` 升级为阻断时创建 Hold；
- 已创建 Hold 的工单不能直接把 `blocks_fulfillment` 改回 false；
- 同一来源重复暂停不生成第二条 `SLAPause`；
- 不同来源可被独立识别；
- 异常来源恢复不会结束节假日、预约或其他来源暂停；
- `resolve_case()` 不释放 Hold，也不自动恢复 SLA。

- [ ] **步骤 3：运行测试并确认预期失败**

```powershell
uv run pytest tests/exceptions/test_lifecycle.py tests/sla/test_service.py -q
```

- [ ] **步骤 4：扩展 `SLAService`**

增加来源化方法，例如：

- `pause_for_source(instance_id, reason_code, source_type, source_id, actor_id, idempotency_key)`；
- `resume_for_source(source_type, source_id, actor_id, idempotency_key)`。

保留现有管理 API 的 `pause/resume` 兼容行为，但内部统一走来源模型。若一个实例存在多个活动暂停，只有最后一个活动暂停结束后才把实例改回 `RUNNING`；累计暂停时长和承诺延后只计算各暂停区间一次。

- [ ] **步骤 5：实现生命周期应用服务**

每个动作使用独立幂等作用域和请求哈希。`resolve_case` 接受结构化 `resolution_code` 和原因；若解决码要求取消、拦截、重派、转自取或退回，返回 `RECOVERY_ACTION_NOT_IMPLEMENTED`，不写部分状态。

`update_classification` 只允许运营管理员：

- 非阻断变阻断：锁运单、创建 Hold、按规则暂停 SLA；
- 已有 Hold 时禁止直接改回非阻断；
- 所有覆盖默认值动作写必填原因审计。

- [ ] **步骤 6：实现命名路由**

新增：

- `POST /{case_id}/assign`；
- `POST /{case_id}/start-processing`；
- `POST /{case_id}/wait-for-customer`；
- `POST /{case_id}/resume-processing`；
- `POST /{case_id}/classification`；
- `POST /{case_id}/resolve`。

规格接口表未单列分类调整端点；实施时采用专用 `/classification` 命名动作，不提供通用 PATCH，保持领域意图和审计边界。

- [ ] **步骤 7：验证相关测试**

```powershell
uv run pytest tests/exceptions/test_lifecycle.py tests/sla -q
uv run pytest tests/exceptions tests/shipments tests/dispatch -q
uv run ruff check .
uv run mypy src
```

- [ ] **步骤 8：提交**

```bash
git add backend/src/yitu/exceptions backend/src/yitu/sla backend/tests/exceptions/test_lifecycle.py backend/tests/sla/test_service.py
git commit -m "功能：实现异常分配与处理生命周期"
```

---

## 任务 6：关闭旧任务并创建替代任务

**文件：**

- 修改：`backend/src/yitu/dispatch/service.py`
- 修改：`backend/src/yitu/dispatch/router.py`
- 修改：`backend/src/yitu/exceptions/schemas.py`
- 修改：`backend/src/yitu/exceptions/service.py`
- 修改：`backend/src/yitu/exceptions/router.py`
- 新建：`backend/tests/exceptions/test_reassignment.py`
- 修改：`backend/tests/dispatch/test_concurrency.py`

**产出：**

- `DispatchService.cancel_and_replace_task()`；
- `ExceptionService.reassign_task()`；
- `POST /api/v1/exceptions/{case_id}/reassign-task`。

- [ ] **步骤 1：编写失败的重新分配测试**

覆盖：

- 仅运营管理员可执行；
- 异常必须处于 `ASSIGNED` 或 `PROCESSING`；
- 旧任务必须属于同一运单；
- `COMPLETED` 和 `CANCELLED` 任务不可重新分配；
- 旧任务变为 `CANCELLED`，保留原 `assignee_id`、关闭原因和时间；
- 新任务保持同一运单、类型和网点，状态为 `AVAILABLE` 且无负责人；
- `replaced_by_task_id` 和 `ExceptionTaskReassignment` 正确；
- 活动 Hold 不阻止转派，但阻止新任务接单；
- 重放不重复创建新任务、轨迹、审计或 Outbox；
- 两个不同幂等键并发转派同一旧任务时只有一个成功，另一个返回 `TASK_NOT_REASSIGNABLE`。

- [ ] **步骤 2：运行测试并确认预期失败**

```powershell
uv run pytest tests/exceptions/test_reassignment.py tests/dispatch/test_concurrency.py -q
```

- [ ] **步骤 3：实现调度模块命名动作**

`DispatchService.cancel_and_replace_task()` 负责锁定旧任务、校验状态、关闭并新建。异常模块不能直接给 `CourierTask.status` 赋值。

更新任务读取/执行逻辑：

- 任务列表可以显示 `CANCELLED` 历史；
- 接单和确认动作明确拒绝已关闭任务；
- 读取当前派送任务时不能误取历史已关闭任务，应按有效状态和创建顺序选择。

- [ ] **步骤 4：实现异常编排、轨迹、审计和通知**

通知旧负责人仅在其存在时追加。新任务没有接单人，不创建虚假接收人通知。客户轨迹使用中性文案，不公开原负责人或内部原因。

- [ ] **步骤 5：验证调度和异常回归**

```powershell
uv run pytest tests/exceptions/test_reassignment.py tests/dispatch tests/shipments/test_last_mile.py -q
uv run ruff check .
uv run mypy src
```

- [ ] **步骤 6：提交**

```bash
git add backend/src/yitu/dispatch backend/src/yitu/exceptions backend/tests/exceptions/test_reassignment.py backend/tests/dispatch/test_concurrency.py
git commit -m "功能：保留历史地重新分配任务"
```

---

## 任务 7：显式恢复履约与关闭异常

**文件：**

- 修改：`backend/src/yitu/shipments/control.py`
- 修改：`backend/src/yitu/exceptions/schemas.py`
- 修改：`backend/src/yitu/exceptions/service.py`
- 修改：`backend/src/yitu/exceptions/router.py`
- 新建：`backend/tests/exceptions/test_recovery.py`

**产出：**

- `ExceptionService.resume_shipment()`；
- `ExceptionService.close_case()`；
- `POST /api/v1/shipments/{shipment_id}/resume`；
- `POST /api/v1/exceptions/{case_id}/close`。

- [ ] **步骤 1：编写失败的恢复测试**

覆盖：

- 只有运营管理员可恢复；
- 无活动 Hold 返回 `SHIPMENT_NOT_BLOCKED`；
- 任一阻断异常未解决返回 `UNRESOLVED_BLOCKING_CASES`；
- `target_status` 与冻结状态不同返回 `RESUME_TARGET_MISMATCH`；
- 多个 Hold 冻结状态不一致返回 `RESUME_PRECONDITION_FAILED`；
- 目标阶段缺少有效任务、运输段或其他前置事实时返回 `RESUME_PRECONDITION_FAILED`；
- 成功恢复不改变 `Shipment.status`；
- 成功恢复只结束相关异常来源 SLA 暂停并释放全部活动 Hold；
- 恢复动作把相关工单的 `blocks_fulfillment` 同步为 false，但保留 `frozen_shipment_status` 和 Hold 历史；
- 重放不重复恢复、轨迹、审计或通知；
- 阻断工单在 Hold 释放前不能关闭；
- 非阻断工单解决后可以直接关闭；
- 关闭后不能再执行处理动作。

- [ ] **步骤 2：运行测试并确认预期失败**

```powershell
uv run pytest tests/exceptions/test_recovery.py -q
```

- [ ] **步骤 3：实现阶段前置条件校验**

在 `ShipmentControlService` 中集中定义只读校验，不改变状态：

- `PICKUP_ASSIGNED` / `DELIVERY_ASSIGNED` / `OUT_FOR_DELIVERY` 需要有效、未关闭的对应任务；
- `IN_LINEHAUL` 需要进行中的运输段；
- 其他状态按现有模型校验必要网点或凭证；
- 发现损坏或不一致数据时拒绝恢复，不自动创建任务或运输段，因为这些属于任务 6 的恢复动作。

- [ ] **步骤 4：实现原子恢复**

锁顺序：Shipment → 全部活动 Hold → 对应 ExceptionCase → 来源 SLAPause。全部校验通过后：

1. 恢复相关 SLA 来源；
2. 释放所有活动 Hold；
3. 将相关工单当前阻断属性同步为 false；
4. 追加一条“履约已恢复”客户轨迹；
5. 写恢复前后状态和目标阶段审计；
6. 追加 `SHIPMENT_RESUMED` 通知 Outbox。

- [ ] **步骤 5：实现关闭动作**

`close_case` 只允许 `RESOLVED → CLOSED`。若工单仍有关联活动 Hold，返回 409。关闭只写状态、时间、审计和必要通知，不删除历史事实。

- [ ] **步骤 6：验证恢复与履约回归**

```powershell
uv run pytest tests/exceptions/test_recovery.py tests/exceptions/test_fulfillment_holds.py -q
uv run pytest tests/shipments tests/dispatch tests/sla -q
uv run ruff check .
uv run mypy src
```

- [ ] **步骤 7：提交**

```bash
git add backend/src/yitu/shipments/control.py backend/src/yitu/exceptions backend/tests/exceptions/test_recovery.py
git commit -m "功能：显式恢复被冻结的履约"
```

---

## 任务 8：SLA 超时自动开单与异常通知模板

**文件：**

- 修改：`backend/src/yitu/sla/service.py`
- 修改：`backend/src/yitu/sla/tasks.py`
- 修改：`backend/src/yitu/exceptions/service.py`
- 修改：`backend/src/yitu/notifications/templates.py`
- 修改：`backend/tests/sla/test_service.py`
- 新建：`backend/tests/exceptions/test_sla_integration.py`
- 修改：`backend/tests/notifications/test_templates.py`
- 修改：`backend/tests/notifications/test_tasks.py`

**产出：**

- `ExceptionService.open_from_sla()`；
- SLA 扫描与自动异常、审计、通知同事务提交；
- `EXCEPTION_OPENED`、`EXCEPTION_WAITING_FOR_CUSTOMER`、`EXCEPTION_RESOLVED`、`SHIPMENT_RESUMED`、`SLA_BREACHED` 白名单模板。

- [ ] **步骤 1：编写失败的 SLA 自动开单测试**

覆盖：

- 首次超时创建 `STATION_DELAY / HIGH / non-blocking / OPEN` 工单；
- `source_type = SLA_SCAN`，`source_id = SLAInstance.id`；
- 相同扫描窗口不重复；
- 不同扫描窗口不重复；
- Worker 重试不重复审计、轨迹或通知；
- 揽收/始发阶段匹配始发网点；
- 目标处理/派送/自取阶段匹配目标网点；
- 干线阶段责任网点为空；
- 中途注入失败时 SLA `breached`、异常、审计和 Outbox 一起回滚。

- [ ] **步骤 2：编写失败的通知模板测试**

覆盖五个新模板的成功渲染、缺失变量拒绝和中性措辞。保留旧 `SLA_BREACH` 模板测试，避免破坏已有契约。

- [ ] **步骤 3：运行测试并确认预期失败**

```powershell
uv run pytest tests/exceptions/test_sla_integration.py tests/notifications/test_templates.py tests/notifications/test_tasks.py -q
```

- [ ] **步骤 4：修正首次违约语义**

`scan_breaches()` 只领取 `status == RUNNING`、截止时间已过且 `breached is false` 的实例，并在事务中将其置为 true。使用行锁或条件更新防止多个扫描 Worker 同时把同一实例作为首次违约返回。`last_scan_key` 保存首次成功扫描键，不再使不同窗口重复返回已违约实例。

- [ ] **步骤 5：实现 `open_from_sla()` 和任务编排**

`sla/tasks.py` 在现有 `SessionFactory` 事务中：

1. 扫描首次违约实例；
2. 逐个调用 `open_from_sla()`；
3. 查询全部 `OPERATIONS_ADMIN` 用户；
4. 为每个运营管理员追加独立 `notification.requested`，幂等键包含 SLA 实例 ID 和接收人 ID；
5. 返回首次创建的异常数。

不要通过新的 Outbox 事件再异步创建异常，以免失去事务原子性。

- [ ] **步骤 6：实现并验证模板与通知物化**

异常业务服务为运单所有者生成异常打开、等待客户、解决和恢复通知。SLA 超时通知运营管理员。每个 `notification.requested` 仍只含一个 `recipient_id`。

- [ ] **步骤 7：验证 SLA、通知和 Worker 回归**

```powershell
uv run pytest tests/exceptions/test_sla_integration.py tests/sla tests/notifications -q
uv run pytest tests/platform/test_worker_runtime.py tests/platform/test_worker_recovery.py -q
uv run ruff check .
uv run mypy src
```

- [ ] **步骤 8：提交**

```bash
git add backend/src/yitu/sla backend/src/yitu/exceptions/service.py backend/src/yitu/notifications/templates.py backend/tests/exceptions/test_sla_integration.py backend/tests/sla backend/tests/notifications
git commit -m "功能：从 SLA 超时生成异常与通知"
```

---

## 任务 9：HTTP 完整旅程、幂等和并发验收

**文件：**

- 修改：`backend/tests/exceptions/test_api.py`
- 新建：`backend/tests/exceptions/test_journey.py`
- 视失败结果最小修改：`backend/src/yitu/exceptions/{schemas,service,router}.py`
- 视失败结果最小修改：相关现有服务文件

**产出：** 一条通过真实 FastAPI 接口执行的完整任务 5 旅程。

- [ ] **步骤 1：编写 HTTP 异常恢复旅程**

使用真实 JWT/演示身份和 PostgreSQL：

1. 创建并推进一张存在已接任务的运单；
2. 客户或履约人员上报阻断异常；
3. 验证后续履约动作被拒绝；
4. 运营管理员分配责任人；
5. 网点人员开始处理、等待客户、继续处理；
6. 运营管理员解决异常；
7. 验证解决后仍被 Hold 阻断；
8. 运营管理员提交匹配冻结阶段的 `resume`；
9. 关闭异常；
10. 验证履约可以继续；
11. 验证轨迹、审计、Hold、SLA 暂停、Outbox 和通知记录都只有预期数量。

- [ ] **步骤 2：补充真实 HTTP 错误和幂等矩阵**

覆盖所有批准错误：

- `EXCEPTION_CASE_NOT_FOUND`；
- `INVALID_EXCEPTION_TRANSITION`；
- `EXCEPTION_TYPE_NOT_ALLOWED`；
- `FORBIDDEN_EXCEPTION_SCOPE`；
- `INVALID_RESPONSIBLE_STATION`；
- `INVALID_CASE_ASSIGNEE`；
- `SHIPMENT_FULFILLMENT_BLOCKED`；
- `SHIPMENT_NOT_BLOCKED`；
- `UNRESOLVED_BLOCKING_CASES`；
- `RESUME_TARGET_MISMATCH`；
- `RESUME_PRECONDITION_FAILED`；
- `TASK_NOT_REASSIGNABLE`；
- `RECOVERY_ACTION_NOT_IMPLEMENTED`。

并断言 403/404/409/422 映射正确。

- [ ] **步骤 3：运行旅程并最小修复**

```powershell
uv run pytest tests/exceptions/test_api.py tests/exceptions/test_journey.py -q
```

只修复测试暴露的任务 5 契约问题，不扩展到任务 6。

- [ ] **步骤 4：运行异常模块全量测试**

```powershell
uv run pytest tests/exceptions -q
```

- [ ] **步骤 5：运行受影响模块回归**

```powershell
uv run pytest tests/dispatch tests/shipments tests/sla tests/notifications tests/payments/test_flows.py -q
```

- [ ] **步骤 6：提交**

```bash
git add backend/tests/exceptions backend/src/yitu/exceptions backend/src/yitu/shipments backend/src/yitu/dispatch backend/src/yitu/sla backend/src/yitu/notifications
git commit -m "测试：验收异常处理与履约恢复旅程"
```

---

## 任务 10：全量质量门禁与迁移演练

**文件：**

- 修改：`docs/superpowers/plans/2026-08-09-backend-phase-3-commerce-reliability.md`
- 如验证发现问题，仅最小修改任务 5 相关文件

- [ ] **步骤 1：运行静态质量门禁**

```powershell
cd D:\Projects\yitu\backend
$env:UV_CACHE_DIR='D:\Projects\yitu\backend\.uv-cache'
uv run ruff check .
uv run mypy src
```

预期：全部通过。

- [ ] **步骤 2：运行全量测试**

```powershell
uv run pytest -q
```

预期：现有 104 个测试加任务 5 新增测试全部通过。

- [ ] **步骤 3：执行完整迁移往返**

```powershell
uv run alembic downgrade base
uv run alembic upgrade head
uv run pytest -q
```

预期：空数据库迁移到 0018 成功，迁移后的全量测试通过。

- [ ] **步骤 4：检查迁移头与工作区**

```powershell
uv run alembic heads
git status --short
git diff --check
```

预期：唯一迁移头为 `0018`；没有意外生成文件、缓存或未解释修改；diff 无空白错误。

- [ ] **步骤 5：更新阶段三总计划**

只把任务 5 的复选框标为完成，并记录实际迁移编号 `0018_create_exceptions.py` 和最终验证结果。不要改写任务 4 的历史迁移描述，也不要提前勾选任务 6。

- [ ] **步骤 6：最终范围审查**

确认代码中没有新增以下任务 6 能力：

- cancel API 或新退款流程；
- interception；
- redelivery；
- convert-to-pickup；
- return 状态和运输段；
- 任务 6 新 SLA 或支付影响。

- [ ] **步骤 7：提交任务 5**

```bash
git add backend docs/superpowers/plans/2026-08-09-backend-phase-3-commerce-reliability.md
git commit -m "功能：新增可审计异常处理"
```

提交前确认没有把 `.env`、数据库数据、缓存或秘密加入 Git。

## 最终完成标准

1. 异常单完整支持 `OPEN → ASSIGNED → PROCESSING → WAITING_FOR_CUSTOMER → RESOLVED → CLOSED`；
2. 九类异常默认策略和角色范围符合批准规格；
3. 阻断异常保留原 `Shipment.status`，活动 Hold 一致阻止所有履约入口；
4. 解决异常不会自动恢复，`resume_shipment` 必须显式匹配冻结阶段；
5. 任务重新分配关闭旧任务并新建任务，不覆盖历史负责人；
6. SLA 首次超时自动、跨扫描窗口幂等地创建异常并通知运营管理员；
7. 所有动作具有原因、前后状态、操作者、请求/扫描标识和幂等事实；
8. 客户轨迹不泄露内部责任或敏感证据；
9. Ruff、mypy、全量 pytest 和 Alembic base↔head 往返全部通过；
10. 任务 6 的取消、拦截、重派、转自取和退回没有混入本次实现。
