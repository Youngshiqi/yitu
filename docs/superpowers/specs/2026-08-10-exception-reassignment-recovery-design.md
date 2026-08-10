# 异常、任务重新分配与履约恢复设计

**状态：** 已获设计批准，待用户书面规格审核

**日期：** 2026-08-10

**对应计划：** 阶段三任务 5“异常、重新分配与恢复履约”

## 1. 目标

本设计为驿途建立独立、可审计的异常工单生命周期，并在不覆盖既有履约事实的前提下实现：

- 人工上报九类异常；
- SLA 超时自动、幂等地创建异常单；
- 异常责任网点和处理人分配；
- 阻断型异常冻结履约；
- 完整的人工处理状态机；
- 关闭旧任务并创建替代任务的重新分配；
- 异常解决后的显式履约恢复；
- 权限、网点范围、轨迹、审计、通知和 Outbox 闭环。

异常单、任务、SLA 和运单各自保留独立生命周期。异常模块只能通过其他模块的应用服务协调履约，不直接修改其他模块的 ORM 模型。

## 2. 范围

### 2.1 本任务包含

第一版支持以下异常类型：

- `PICKUP_FAILED`：揽收失败；
- `ADDRESS_ERROR`：地址错误；
- `RECIPIENT_UNREACHABLE`：联系不上收件人；
- `REFUSED`：收件人拒收；
- `DAMAGE`：包裹破损；
- `WEIGHT_MISMATCH`：重量不符；
- `STATION_DELAY`：网点滞留；
- `SUSPECTED_LOSS`：疑似丢失；
- `WAITING_FOR_SUPPLEMENT`：等待补差价。

本任务实现完整异常状态机、人工上报、SLA 自动开单、责任分配、履约冻结、SLA 暂停协调、任务重新分配以及显式恢复。

### 2.2 本任务不包含

以下恢复旅程属于阶段三任务 6：

- 取消及退款；
- 揽收后的拦截请求和拦截转退回；
- 拒收或派送失败后的重新派送；
- 转为网点自取；
- 退回审批、退回运输段和退回完成；
- 上述动作产生的新阶段 SLA 和支付影响。

任务 5 可以记录 `REFUSED` 等异常，但不能以通用异常接口替代任务 6 的命名恢复动作。解决方案要求执行未实现的任务 6 动作时，返回 `RECOVERY_ACTION_NOT_IMPLEMENTED`。

异常证据在本任务中只保存结构化文字摘要。文件上传和附件存储不在本任务范围内。

## 3. 架构决策

采用独立异常模块和同步应用服务编排：

```text
HTTP / SLA Scanner
        │
        ▼
ExceptionService
        ├── ExceptionCase 状态机
        ├── ShipmentControlService 冻结与放行
        ├── DispatchService 关闭并重建任务
        ├── SLAService 暂停与恢复指定来源
        ├── Tracking 追加客户可见事实
        ├── Audit 追加内部审计
        └── Outbox 追加通知请求
```

同步业务动作在一个数据库事务中完成，以便异常事实、Hold、任务、SLA、轨迹、审计和 Outbox 原子提交。Outbox 只承担通知等异步边界，不异步执行异常状态机。

不增加 `ShipmentStatus.PAUSED`。运单在冻结期间保留真实履约阶段；活动 Hold 负责阻止后续履约动作。这样无需为每个运单阶段建立暂停和回跳状态，也不会丢失冻结前的位置。

## 4. 模块与职责

新增 `backend/src/yitu/exceptions/`：

- `models.py`：异常单、任务重新分配事实；
- `schemas.py`：稳定的 HTTP 输入输出；
- `state_machine.py`：异常状态和纯转换规则；
- `service.py`：权限、幂等和跨模块用例编排；
- `router.py`：认证、请求头、分页、错误映射和事务提交。

现有模块进行聚焦扩展：

- `shipments`：增加 `ShipmentHold` 和 `ShipmentControlService`；
- `dispatch`：增加任务关闭字段、`CANCELLED` 状态和关闭后新建替代任务的应用服务动作；
- `sla`：增加结构化暂停来源以及超时扫描到异常单的事务编排；
- `notifications`：增加异常和 SLA 通知白名单模板；
- `main.py`、Alembic 环境：完成路由和模型接线。

异常服务不直接赋值 `Shipment.status`、`CourierTask.status` 或 `SLAInstance.status`；这些变化分别由所属模块的应用服务完成。

## 5. 数据模型

### 5.1 ExceptionCase

`exception_cases` 保存：

- `id`；
- `shipment_id`；
- `case_type`；
- `severity`：`LOW / MEDIUM / HIGH / CRITICAL`；
- `status`：`OPEN / ASSIGNED / PROCESSING / WAITING_FOR_CUSTOMER / RESOLVED / CLOSED`；
- `source_type`：`MANUAL / SLA_SCAN`；
- `source_id`：自动来源的稳定资源 ID，人工来源为空；
- `description`：上报事实摘要；
- `evidence_summary`：可选的结构化证据摘要；
- `blocks_fulfillment`；
- `frozen_shipment_status`：首次创建 Hold 时的运单状态，非阻断异常为空；
- `reported_by`：人工上报人，系统自动异常为空；
- `assigned_to`；
- `responsible_station_id`；
- `resolution_code`、`resolution_reason`；
- `opened_at`、`assigned_at`、`resolved_at`、`closed_at`；
- `idempotency_key`、`request_id`。

自动来源使用唯一约束 `(source_type, source_id)`。`SLA_SCAN + SLAInstance.id` 在不同扫描窗口、Worker 重试和并发执行下都只能生成一张异常单。人工接口由平台幂等记录保证请求级幂等。

### 5.2 ShipmentHold

`shipment_holds` 属于 `shipments` 模块，保存：

- `id`、`shipment_id`；
- `source_type = EXCEPTION_CASE`；
- `source_id = ExceptionCase.id`；
- `frozen_status`；
- `reason`；
- `active`；
- `placed_by`、`placed_at`；
- `released_by`、`released_at`；
- `place_idempotency_key`、`release_idempotency_key`。

同一个来源只能创建一个 Hold。释放时保留原记录，不删除或覆盖放置事实。一张运单可以同时具有多个活动 Hold。

把 Hold 放在 `shipments` 模块，可以让调度、干线、末端和 SLA 服务通过稳定的运单控制接口检查履约资格，而不反向依赖异常模块。

### 5.3 CourierTask 扩展

`CourierTaskStatus` 增加 `CANCELLED`。`courier_tasks` 增加：

- `closed_reason`；
- `closed_at`；
- `replaced_by_task_id`：指向新任务的可空自引用。

关闭旧任务不清空 `assignee_id`，从而保留历史负责人。

新增 `exception_task_reassignments`，保存：

- `id`、`case_id`；
- `old_task_id`、`new_task_id`；
- `reason`、`actor_id`；
- `idempotency_key`、`created_at`。

唯一约束保证同一异常、旧任务和幂等键不会重复产生替代任务。

### 5.4 SLA 暂停来源

`SLAPause` 补充：

- 结构化 `reason_code`；
- `source_type`、`source_id`；
- `actor_id`；
- `pause_idempotency_key`、`resume_idempotency_key`。

异常恢复只结束由相应异常 Hold 创建且仍活动的暂停，不得恢复法定节假日、客户预约或其他独立原因的暂停。

### 5.5 迁移编号

当前迁移链头为 `0017_create_notifications.py`。本任务新增 `0018_create_exceptions.py`，同时创建异常表、Hold、重新分配表以及任务/SLA 扩展字段和索引。不得修改或重编号历史迁移。

迁移必须支持从空数据库升级到 head，并能够逐步降级到 base。

## 6. 异常状态机

命名动作和合法转换为：

```text
open_case                    → OPEN
assign_case         OPEN     → ASSIGNED
start_processing    ASSIGNED → PROCESSING
wait_for_customer   PROCESSING → WAITING_FOR_CUSTOMER
resume_processing   WAITING_FOR_CUSTOMER → PROCESSING
resolve_case         PROCESSING / WAITING_FOR_CUSTOMER → RESOLVED
close_case           RESOLVED → CLOSED
```

不提供通用 `update_status` 接口。非法跳转统一返回 `INVALID_EXCEPTION_TRANSITION`。

阻断异常必须遵循：

```text
resolve_case
→ resume_shipment
→ close_case
```

非阻断异常可以在解决后直接关闭。关闭后的异常不可重新编辑；如果后续发现错误，创建新异常单或追加新的纠正事实。

## 7. 严重度与阻断规则

服务端默认规则为：

| 异常类型 | 默认严重度 | 默认阻断 |
|---|---:|---:|
| `PICKUP_FAILED` | `MEDIUM` | 否 |
| `ADDRESS_ERROR` | `MEDIUM` | 是 |
| `RECIPIENT_UNREACHABLE` | `MEDIUM` | 否 |
| `REFUSED` | `HIGH` | 否 |
| `DAMAGE` | `HIGH` | 否 |
| `WEIGHT_MISMATCH` | `MEDIUM` | 否 |
| `STATION_DELAY` | `HIGH` | 否 |
| `SUSPECTED_LOSS` | `CRITICAL` | 是 |
| `WAITING_FOR_SUPPLEMENT` | `MEDIUM` | 是 |

普通破损默认不阻断。运营管理员确认严重破损后，可升级为 `CRITICAL` 并开启阻断。运营管理员也可以带必填原因覆盖默认严重度或阻断属性。

非阻断异常升级为阻断异常时，在同一事务中创建 Hold、保存当时运单状态，并按原因映射暂停适用的 SLA。工单一旦创建过 Hold，`blocks_fulfillment` 就不允许直接改回 `false`；运营管理员必须先解决异常并执行显式 `resume_shipment`，由恢复动作释放 Hold 并同步结束阻断。这样避免属性调整绕过恢复审计，也保证工单字段与活动 Hold 一致。

客户、快递员和网点人员不能自行指定严重度、阻断属性、责任网点或处理人。

## 8. 履约冻结和恢复

### 8.1 统一阻断检查

所有推进实体履约的服务必须在持有运单行锁时调用：

```text
ShipmentControlService.lock_and_assert_fulfillment_allowed(shipment_id)
```

存在活动 Hold 时返回 `SHIPMENT_FULFILLMENT_BLOCKED`。检查覆盖：

- 任务接单；
- 确认揽收；
- 客户自寄验收和始发到站；
- 干线发车和目标网点到站；
- 派送接单和开始派送；
- 签收和自取码核销。

以下动作不受 Hold 阻断：

- 查询；
- 异常处理和审计；
- 通知投递；
- 任务重新分配；
- `resume_shipment`。

重新分配创建的新任务可以保持 `AVAILABLE`，但在 Hold 释放前仍不能被快递员接单。

### 8.2 显式恢复

`resume_shipment(shipment_id, target_status, reason)` 只允许运营管理员调用，并按以下顺序执行：

1. 锁定运单及其全部活动 Hold；
2. 要求至少存在一个活动 Hold，否则返回 `SHIPMENT_NOT_BLOCKED`；
3. 要求所有 Hold 对应的阻断异常均已 `RESOLVED`；
4. 要求全部 Hold 的 `frozen_status` 一致；
5. 要求请求 `target_status` 等于冻结状态；
6. 校验目标阶段需要的有效任务、运输段或其他前置事实仍存在；
7. 恢复这些 Hold 引起的 SLA 暂停；
8. 原子释放全部活动 Hold；
9. 追加轨迹、审计和通知 Outbox。

恢复不修改 `Shipment.status`，因为状态始终停留在被冻结的阶段。

第一个 Hold 创建后，所有正常履约动作均被阻止，因此同一运单后续 Hold 应具有相同的冻结状态。若历史或损坏数据导致多个活动 Hold 的冻结状态不同，恢复必须返回 `RESUME_PRECONDITION_FAILED`，不得猜测目标状态。

## 9. SLA 协调

### 9.1 异常导致的 SLA 暂停

只对业务规则明确允许的原因暂停：

- `ADDRESS_ERROR` → `WAITING_FOR_ADDRESS`；
- `WAITING_FOR_SUPPLEMENT` → `WAITING_FOR_SUPPLEMENT`。

`SUSPECTED_LOSS` 和严重 `DAMAGE` 会冻结履约，但不暂停承诺计时，以保留真实违约事实。

每个 Hold 只暂停该运单当前运行中的阶段 SLA；重复调用按来源和幂等键返回原暂停结果。恢复时只结束相同来源创建的活动暂停。

### 9.2 SLA 超时自动开单

定时任务在一个事务中执行：

```text
SLAService.scan_breaches(scan_key)
→ 得到本次首次标记超时的 SLA 实例
→ ExceptionService.open_from_sla(instance)
→ 写入异常、审计和通知 Outbox
→ 提交事务
```

自动异常属性：

- `case_type = STATION_DELAY`；
- `source_type = SLA_SCAN`；
- `source_id = SLAInstance.id`；
- `severity = HIGH`；
- `blocks_fulfillment = false`；
- `reported_by = null`；
- 初始状态为 `OPEN`。

责任网点按运单当前阶段确定：

- 揽收、始发入站和始发处理阶段关联始发网点；
- 目标网点处理、派送和自取阶段关联目标网点；
- 干线阶段若无法唯一判定责任网点，则责任网点为空，由运营管理员分配。

自动工单可以先有责任网点而没有具体处理人，等待运营管理员执行 `assign_case`。

SLA 超时标记、异常单、审计和 Outbox 必须同事务提交。任一步骤失败时全部回滚，下一次扫描可以安全重试。

## 10. 任务重新分配

`reassign_task(case_id, old_task_id, reason)` 仅允许运营管理员执行：

1. 锁定运单、异常单和旧任务；
2. 要求异常状态为 `ASSIGNED` 或 `PROCESSING`；
3. 要求旧任务属于该异常关联运单；
4. 要求旧任务尚未 `COMPLETED` 或 `CANCELLED`；
5. 通过 `DispatchService` 将旧任务关闭为 `CANCELLED`，保存原因和关闭时间；
6. 创建同一运单、同一任务类型和同一网点的 `AVAILABLE` 任务；
7. 将旧任务的 `replaced_by_task_id` 指向新任务；
8. 追加重新分配事实、轨迹、审计和 Outbox。

本任务不直接指定新快递员。新任务沿用原有并发接单机制；原负责人可以收到任务已关闭通知，尚未确定的未来接单人不创建通知。任务列表负责向所属网点快递员展示新任务。

## 11. HTTP 接口

统一前缀为 `/api/v1/exceptions`。所有写接口都要求 `Idempotency-Key` 请求头。

| 方法和路径 | 作用 |
|---|---|
| `POST /api/v1/exceptions` | 人工上报异常 |
| `GET /api/v1/exceptions` | 按权限分页查询异常单 |
| `GET /api/v1/exceptions/{case_id}` | 查看异常详情 |
| `POST /api/v1/exceptions/{case_id}/assign` | 分配责任处理人和责任网点 |
| `POST /api/v1/exceptions/{case_id}/start-processing` | 开始处理 |
| `POST /api/v1/exceptions/{case_id}/wait-for-customer` | 转为等待客户 |
| `POST /api/v1/exceptions/{case_id}/resume-processing` | 客户响应后继续处理 |
| `POST /api/v1/exceptions/{case_id}/resolve` | 写入解决方案并解决工单 |
| `POST /api/v1/exceptions/{case_id}/close` | 关闭已解决工单 |
| `POST /api/v1/exceptions/{case_id}/reassign-task` | 关闭旧任务并创建替代任务 |
| `POST /api/v1/shipments/{shipment_id}/resume` | 显式恢复被冻结的履约 |

异常列表采用 `limit + offset` 分页，支持以下筛选：

- `shipment_id`；
- `status`；
- `case_type`；
- `severity`；
- `responsible_station_id`；
- `assigned_to`；
- `blocks_fulfillment`。

本任务不提前引入全局游标分页框架。

## 12. 权限与资源范围

### 12.1 客户

客户只能为本人运单上报：

- `ADDRESS_ERROR`；
- `RECIPIENT_UNREACHABLE`；
- `REFUSED`；
- `DAMAGE`；
- `SUSPECTED_LOSS`。

客户可查看本人运单的异常，但不能分配、判责、调整严重度或阻断属性、解决、关闭、恢复履约或重新分配任务。

### 12.2 快递员

快递员只能为本人当前负责且未完成的任务关联运单上报：

- `PICKUP_FAILED`；
- `ADDRESS_ERROR`；
- `RECIPIENT_UNREACHABLE`；
- `REFUSED`；
- `DAMAGE`；
- `WEIGHT_MISMATCH`；
- `SUSPECTED_LOSS`。

快递员只能查看本人上报或本人任务关联的异常，不能判责和解决。

### 12.3 网点人员

网点人员只能访问所属网点是运单始发网点、目标网点或当前任务网点的异常。网点人员：

- 可以上报除 `WAITING_FOR_SUPPLEMENT` 外的业务异常；
- 可以查看本网点责任异常；
- 可以对已分配给本人或本网点的异常开始处理、标记等待客户和继续处理；
- 不能跨网点分配、最终解决、恢复履约或重新分配任务。

### 12.4 运营管理员

运营管理员可以：

- 查看和上报全部异常；
- 分配责任网点和处理人；
- 调整严重度和阻断属性；
- 执行全部处理状态动作；
- 解决和关闭异常；
- 重新分配任务；
- 显式恢复履约。

覆盖默认规则、判责、解决、转派和恢复时必须填写原因。

### 12.5 系统管理员

系统管理员可以读取异常和审计事实用于技术排障，但不能执行运营判责、解决、履约恢复或任务转派。系统管理员继续负责技术参数，不代替运营管理员作业务决定。

### 12.6 分配约束

`assign_case` 接收 `assignee_id`、`responsible_station_id` 和必填原因，并验证：

- 处理人存在；
- 处理人角色是 `STATION_OPERATOR` 或 `OPERATIONS_ADMIN`；
- 网点处理人属于指定责任网点；
- 责任网点是运单始发网点、目标网点或当前任务网点之一。

本任务不允许通过异常分配任意改变履约路线。跨路线改变由任务 6 的显式恢复动作处理。

## 13. 事务与并发

所有状态变更先锁定运单，再锁定相关异常、Hold、任务或 SLA：

```text
锁定 Shipment
→ 检查或管理活动 Hold
→ 锁定相关业务记录
→ 校验权限和状态
→ 写入业务事实
→ 追加轨迹、审计和 Outbox
→ 提交
```

该顺序解决履约推进与阻断异常并发：

- 履约动作先获得运单锁时，本次动作完成，随后异常冻结新的当前阶段；
- 异常动作先获得运单锁时，随后履约动作看到 Hold 并拒绝；
- 不会保存一个已经过期的冻结阶段快照。

任务重新分配锁定旧任务。两个不同请求并发重新分配同一旧任务时，只允许一个成功；另一个返回 `TASK_NOT_REASSIGNABLE`。

## 14. 幂等

- 人工写接口使用现有 `IdempotencyService`，作用域包含动作、资源和操作者；
- 同键同请求返回首次响应；
- 同键不同请求返回 `IDEMPOTENCY_KEY_REUSED`；
- SLA 自动异常使用 `(source_type, source_id)` 唯一约束；
- Hold 使用 `(source_type, source_id)` 唯一约束；
- SLA 暂停使用来源和幂等键约束；
- 重新分配使用异常、旧任务和幂等键约束；
- 轨迹和 Outbox 使用稳定的业务幂等键。

数据库唯一冲突必须转换成稳定业务结果或 `409`，不能向客户端暴露原始数据库异常。

## 15. 审计与客户轨迹

以下动作必须写入追加式审计：

- 打开、分配、开始处理、等待客户、继续处理；
- 调整严重度或阻断属性；
- 解决、恢复履约和关闭；
- 关闭旧任务并创建替代任务；
- SLA 扫描自动创建异常。

审计至少记录：操作者或系统身份、动作、异常单和相关资源、前后状态摘要、原因、请求 ID或扫描键。SLA 自动任务使用稳定操作者 `system:sla-scanner`。

客户轨迹只追加影响履约理解的中性事实，例如：

- “运单出现异常，正在处理中”；
- “需要客户补充信息”；
- “异常已解决”；
- “履约已恢复”。

内部判责、处理人、敏感证据和未确认赔付结论不进入客户轨迹。

## 16. 通知

异常模块不直接写通知表，而是在业务事务中追加 `notification.requested` Outbox 事件。新增白名单模板：

- `EXCEPTION_OPENED`；
- `EXCEPTION_WAITING_FOR_CUSTOMER`；
- `EXCEPTION_RESOLVED`；
- `SHIPMENT_RESUMED`；
- `SLA_BREACHED`。

通知规则：

- 人工异常打开、等待客户、解决和恢复时通知运单所有者；
- SLA 超时通知运营管理员；
- 任务重新分配时通知旧负责人；
- 新任务通过任务列表向所属网点快递员开放，不向尚未确定的接单人创建通知；
- 疑似丢失、严重破损和责任争议使用中性模板，不发送赔付或责任结论；
- 通知失败不回滚异常、任务、SLA 或运单事务。

## 17. 错误契约

主要稳定错误码：

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

映射规则：

- 资源不存在：HTTP 404；
- 角色或范围不足：HTTP 403；
- 非法状态、活动阻断、目标不匹配或不可转派：HTTP 409；
- 结构化输入错误：HTTP 422。

## 18. 测试设计

### 18.1 纯领域测试

覆盖：

- 全部合法状态转换；
- 每一条非法跳转；
- 九类异常的默认严重度和阻断属性；
- 各角色允许上报的异常类型。

### 18.2 PostgreSQL 集成测试

覆盖：

- 客户只能为本人运单上报允许类型；
- 快递员必须关联本人未完成任务；
- 网点人员不能越过所属网点；
- 运营管理员可以分配、升级、解决和恢复；
- 阻断异常创建 Hold，并只暂停允许暂停的 SLA；
- 非阻断异常不影响正常履约；
- 活动 Hold 阻止所有履约入口；
- 解决异常不会自动恢复；
- 恢复目标不匹配时拒绝；
- 多个阻断异常中仍有未解决项时拒绝恢复；
- 成功恢复释放全部 Hold，并只恢复对应来源的 SLA 暂停；
- 旧任务关闭、新任务创建，旧负责人保留；
- 两个并发转派只有一个成功；
- 履约推进和阻断异常并发时结果串行一致；
- 幂等重放不重复写入异常、Hold、任务、轨迹、审计或 Outbox。

### 18.3 SLA 与 Worker 测试

覆盖：

- 首次超时创建一张 `STATION_DELAY` 工单；
- 相同扫描窗口不重复创建；
- 不同扫描窗口扫描同一实例仍不重复创建；
- 根据阶段匹配正确责任网点；
- 异常、审计和 Outbox 原子提交；
- 中途失败时 SLA 标记、异常和 Outbox 一并回滚；
- Worker 重试能够恢复并保持幂等。

### 18.4 HTTP 测试

覆盖：

- 完整异常生命周期；
- 查询筛选、分页和资源范围；
- 稳定错误码及 HTTP 状态；
- 写接口缺少 `Idempotency-Key` 时拒绝；
- 同键同请求重放；
- 同键不同请求返回 `IDEMPOTENCY_KEY_REUSED`。

## 19. 验收与质量门槛

实施完成后运行：

```powershell
cd D:\Projects\yitu\backend
$env:UV_CACHE_DIR='D:\Projects\yitu\backend\.uv-cache'
uv run pytest tests/exceptions -q
uv run pytest tests/dispatch tests/shipments tests/sla tests/notifications -q
uv run ruff check .
uv run mypy src
uv run pytest -q
uv run alembic downgrade base
uv run alembic upgrade head
uv run pytest -q
```

完成定义：

1. 全量异常状态、权限范围、阻断、恢复和任务重新分配测试通过；
2. SLA 超时自动开单并跨扫描窗口幂等；
3. 所有恢复、转派和异常动作记录原因、前后状态、操作者和幂等事实；
4. 历史轨迹、任务、SLA 和异常事实不被覆盖；
5. 任务 6 的取消、拦截、重派、转自取和退回边界保持未侵入；
6. Ruff、mypy 和全量 pytest 通过；
7. 迁移链能从空数据库升级到 head，并完整降级到 base。
