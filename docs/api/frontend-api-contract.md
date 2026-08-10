# 前端联调用后端 API 契约

本文档按当前 FastAPI OpenAPI 实际路由整理，目标是让前端可以先开工联调，并尽早暴露接口缺口。

## 1. 基础约定

- Base URL：开发环境默认使用后端服务地址，接口前缀为 `/api/v1`。
- 认证：除健康检查和登录外，业务接口默认使用 `Authorization: Bearer <access_token>`。
- 时间：响应时间使用带时区的 ISO 字符串，业务时区按 `Asia/Shanghai`。
- 金额：所有金额字段均为整数分，字段名通常为 `*_cents`。
- 幂等：部分状态变更接口后端内部使用固定幂等键；前端第一版不需要额外传幂等键。

统一业务错误响应：

```json
{
  "code": "FORBIDDEN_ROLE",
  "message": "角色权限不足",
  "request_id": "uuid",
  "details": null
}
```

FastAPI 参数校验错误仍可能返回标准 `422` 结构。

## 2. 演示账号

`POST /api/v1/auth/demo-login`

固定演示密码：`YituDemo2026!`

| 账号 | 角色 | 推荐用途 |
| --- | --- | --- |
| `customer.demo` | `CUSTOMER` | 客户下单、地址、通知、运单详情 |
| `courier.bijing.demo` | `COURIER` | 北京揽派任务 |
| `courier.shanghai.demo` | `COURIER` | 上海揽派任务 |
| `operator.beijing.demo` | `STATION_OPERATOR` | 北京网点入库、干线、自取 |
| `operator.shanghai.demo` | `STATION_OPERATOR` | 上海网点入库、干线、自取 |
| `operations.demo` | `OPERATIONS_ADMIN` | 异常、SLA、恢复动作 |
| `system.demo` | `SYSTEM_ADMIN` | 死信管理 |

登录响应：

```json
{
  "access_token": "...",
  "token_type": "bearer"
}
```

当前用户：`GET /api/v1/auth/me`

```json
{
  "id": "uuid",
  "display_name": "演示客户",
  "role": "CUSTOMER",
  "station_id": null
}
```

## 3. 前端第一批主链路

建议第一批页面只接这些接口，先跑通「客户创建运单 → 报价支付 → 履约进度 → 通知」。

### 3.1 地址与网点

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/addresses` | 我的地址簿 |
| `POST` | `/api/v1/addresses` | 新增地址 |
| `PATCH` | `/api/v1/addresses/{address_id}` | 修改地址 |
| `DELETE` | `/api/v1/addresses/{address_id}` | 删除地址 |
| `GET` | `/api/v1/stations` | 查询网点，可按 `district_code` 过滤 |

地址创建：

```json
{
  "label": "家",
  "recipient_name": "张三",
  "phone": "13800000000",
  "district_code": "110101",
  "detail": "东城区示例地址 1 号"
}
```

网点响应：

```json
{
  "id": "uuid",
  "code": "BJS-001",
  "name": "北京示范网点",
  "district_code": "110101"
}
```

### 3.2 报价、运单与支付

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/v1/pricing/quotes` | 创建报价 |
| `GET` | `/api/v1/pricing/quotes/{quote_id}` | 查看报价 |
| `POST` | `/api/v1/shipments` | 创建运单 |
| `GET` | `/api/v1/shipments/{shipment_id}` | 查看运单 |
| `GET` | `/api/v1/shipments/{shipment_id}/tracking` | 查看轨迹 |
| `POST` | `/api/v1/payments/quotes/{quote_id}/pay` | 支付报价 |
| `POST` | `/api/v1/shipments/{shipment_id}/confirm-payment` | 将支付结果确认到运单 |

报价请求：

```json
{
  "origin_district_code": "110101",
  "destination_district_code": "310101",
  "pickup_method": "DOOR_PICKUP",
  "delivery_method": "HOME_DELIVERY",
  "actual_weight_grams": 1200,
  "length_cm": 30,
  "width_cm": 20,
  "height_cm": 10,
  "declared_value_cents": 0
}
```

运单创建：

```json
{
  "draft": {
    "sender_address_id": "uuid",
    "receiver_address_id": "uuid",
    "origin_station_id": null,
    "destination_station_id": null,
    "pickup_method": "DOOR_PICKUP",
    "delivery_method": "HOME_DELIVERY"
  },
  "status": "PENDING_PAYMENT"
}
```

支付请求：

```json
{
  "shipment_id": "uuid",
  "amount_cents": 1800
}
```

运单响应当前是最小视图：

```json
{
  "id": "uuid",
  "shipment_no": "YT202608110001",
  "owner_id": "uuid",
  "status": "PENDING_PICKUP"
}
```

前端注意：当前没有 `GET /api/v1/shipments` 运单列表接口。第一版如果需要列表页，需要补后端接口；否则先通过创建结果进入详情页。

### 3.3 通知与 SSE

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/notifications` | 查询当前用户通知 |
| `POST` | `/api/v1/notifications/{notification_id}/read` | 标记已读 |
| `GET` | `/api/v1/notifications/stream` | SSE 通知流 |

通知响应：

```json
{
  "id": "uuid",
  "template_code": "PAYMENT_SUCCESS",
  "title": "支付成功",
  "content": "运单 YT202608110001 已支付成功，等待揽收。",
  "status": "UNREAD",
  "created_at": "2026-08-11T10:00:00+08:00",
  "read_at": null
}
```

SSE 重连：前端保存最后收到的事件 `id`，重连时传 `?cursor=<last_id>`。响应会以 `: heartbeat` 作为心跳。

## 4. 第二批运营与履约接口

这些接口适合在客户主链路跑通后接入，用于网点、快递员和运营后台。

### 4.1 调度与履约动作

| 方法 | 路径 | 角色 | 用途 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/dispatch/tasks` | 快递员、网点、运营 | 查询任务，可传 `shipment_id` |
| `POST` | `/api/v1/dispatch/tasks/{task_id}/accept` | 快递员 | 接单 |
| `POST` | `/api/v1/dispatch/tasks/{task_id}/confirm-pickup` | 快递员 | 确认揽收 |
| `POST` | `/api/v1/dispatch/shipments/{shipment_id}/accept-dropoff` | 网点 | 接收客户到店寄件 |
| `POST` | `/api/v1/dispatch/shipments/{shipment_id}/confirm-origin-arrival` | 网点 | 确认始发到站 |
| `POST` | `/api/v1/dispatch/shipments/{shipment_id}/dispatch-linehaul` | 网点/运营 | 发出干线 |
| `POST` | `/api/v1/dispatch/shipments/{shipment_id}/arrive-destination` | 网点/运营 | 到达目的站 |
| `POST` | `/api/v1/dispatch/shipments/{shipment_id}/start-delivery` | 快递员 | 开始派送 |
| `POST` | `/api/v1/dispatch/shipments/{shipment_id}/confirm-delivery` | 快递员 | 确认签收 |
| `POST` | `/api/v1/dispatch/shipments/{shipment_id}/issue-pickup-credential` | 网点 | 发放自取码 |
| `POST` | `/api/v1/dispatch/shipments/{shipment_id}/verify-station-pickup` | 网点 | 核销自取码 |

签收请求：

```json
{
  "signer_name": "李四"
}
```

自取核销请求：

```json
{
  "code": "123456"
}
```

### 4.2 异常与恢复动作

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/v1/exceptions` | 异常列表，支持筛选和分页 |
| `POST` | `/api/v1/exceptions` | 人工开异常 |
| `GET` | `/api/v1/exceptions/{case_id}` | 异常详情 |
| `POST` | `/api/v1/exceptions/{case_id}/assign` | 分配异常 |
| `POST` | `/api/v1/exceptions/{case_id}/start-processing` | 开始处理 |
| `POST` | `/api/v1/exceptions/{case_id}/wait-for-customer` | 等待客户 |
| `POST` | `/api/v1/exceptions/{case_id}/resume-processing` | 恢复处理 |
| `POST` | `/api/v1/exceptions/{case_id}/resolve` | 解决异常 |
| `POST` | `/api/v1/exceptions/{case_id}/close` | 关闭异常 |
| `POST` | `/api/v1/exceptions/{case_id}/reassign-task` | 重派履约任务 |
| `POST` | `/api/v1/returns/shipments/{shipment_id}/cancel` | 取消 |
| `POST` | `/api/v1/returns/shipments/{shipment_id}/request-interception` | 申请拦截 |
| `POST` | `/api/v1/returns/shipments/{shipment_id}/redeliver` | 再次派送 |
| `POST` | `/api/v1/returns/shipments/{shipment_id}/convert-to-pickup` | 转自取 |
| `POST` | `/api/v1/returns/shipments/{shipment_id}/approve-return` | 批准退回 |
| `POST` | `/api/v1/returns/shipments/{shipment_id}/advance-return` | 推进退回运输 |
| `POST` | `/api/v1/shipments/{shipment_id}/resume` | 显式恢复被冻结履约 |

恢复动作统一请求：

```json
{
  "reason": "客户要求重新派送"
}
```

异常创建：

```json
{
  "shipment_id": "uuid",
  "case_type": "ADDRESS_ERROR",
  "description": "收件地址门牌缺失",
  "evidence_summary": {
    "source": "customer_service"
  }
}
```

### 4.3 SLA 与管理端

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/v1/sla/rules` | 创建 SLA 规则 |
| `POST` | `/api/v1/sla/shipments/{shipment_id}/instances` | 创建运单 SLA 实例 |
| `GET` | `/api/v1/sla/shipments/{shipment_id}/instances` | 查看运单 SLA |
| `POST` | `/api/v1/sla/instances/{instance_id}/pause` | 暂停 SLA |
| `POST` | `/api/v1/sla/instances/{instance_id}/resume` | 恢复 SLA |
| `POST` | `/api/v1/sla/instances/{instance_id}/complete` | 完成 SLA |
| `POST` | `/api/v1/sla/instances/{instance_id}/eta` | 更新 ETA |
| `GET` | `/api/v1/admin/dead-letters` | 死信列表，仅系统管理员 |
| `POST` | `/api/v1/admin/dead-letters/{dead_letter_id}/replay` | 重放死信，仅系统管理员 |
| `GET` | `/api/v1/shipments/{shipment_id}/label` | 安全面单投影 |

## 5. 前端要内置的枚举

角色：

```text
CUSTOMER, COURIER, STATION_OPERATOR, OPERATIONS_ADMIN, SYSTEM_ADMIN
```

寄件方式：

```text
DOOR_PICKUP, STATION_DROPOFF
```

收件方式：

```text
HOME_DELIVERY, STATION_PICKUP
```

运单状态：

```text
PENDING_PAYMENT, PENDING_PICKUP, PICKUP_ASSIGNED, WAITING_FOR_DROPOFF,
PICKED_UP, AT_ORIGIN_STATION, IN_LINEHAUL, AT_DESTINATION_STATION,
DELIVERY_ASSIGNED, OUT_FOR_DELIVERY, WAITING_FOR_RECIPIENT_PICKUP,
DELIVERED, CANCELLED, RETURN_APPROVED, IN_RETURN, RETURNED
```

异常类型：

```text
PICKUP_FAILED, ADDRESS_ERROR, RECIPIENT_UNREACHABLE, REFUSED, DAMAGE,
WEIGHT_MISMATCH, STATION_DELAY, SUSPECTED_LOSS, WAITING_FOR_SUPPLEMENT
```

异常状态：

```text
OPEN, ASSIGNED, PROCESSING, WAITING_FOR_CUSTOMER, RESOLVED, CLOSED
```

恢复动作：

```text
CANCEL, INTERCEPTION, REDELIVERY, CONVERT_TO_PICKUP, RETURN
```

## 6. 开前端前已发现的 API 缺口

这些不是阶段三阻塞，但会影响前端体验，建议前端第一批联调时顺手补：

1. 缺少运单列表：需要 `GET /api/v1/shipments` 支撑客户/运营列表页。
2. 运单详情较薄：`ShipmentView` 只返回 `id/shipment_no/owner_id/status`，前端详情页可能还需要地址快照、寄收方式、关联报价/金额。
3. 调度任务响应未声明正式 schema：当前返回 `list[dict]`，前端可先用字段接入，但建议后端补 `CourierTaskView`。
4. 部分状态动作返回 `204`：适合命令式按钮，但前端点击后需要主动刷新运单、任务和轨迹。
5. OpenAPI 没有声明 BearerAuth security scheme：前端照样可加 token，但后续生成 TS client 前建议补。

## 7. 推荐前端切片顺序

1. API client、登录页、当前用户态。
2. 地址簿和网点选择。
3. 报价表单、运单创建、模拟支付。
4. 运单详情、轨迹、通知列表、SSE 通知。
5. 快递员/网点履约按钮台。
6. 运营异常台、恢复动作。
7. 系统管理员死信台、面单查看。

