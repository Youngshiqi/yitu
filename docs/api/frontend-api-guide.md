# Yitu 前端 API 完整使用手册

本文档面向前端开发，覆盖当前后端已注册的全部业务接口。接口基地址默认为：

```text
http://localhost:8000/api/v1
```

除登录、健康检查外，接口均需要：

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

所有 UUID 使用字符串格式；时间使用带时区的 ISO 8601 字符串；金额统一使用“分”（例如 `1800` 表示 18.00 元）。创建、支付、状态推进、退回等写操作应携带唯一的 `Idempotency-Key`，避免网络重试造成重复业务。

## 1. 角色与通用约定

角色值：`CUSTOMER` 客户、`COURIER` 快递员、`STATION_OPERATOR` 网点员、`OPERATIONS_ADMIN` 运营管理员、`SYSTEM_ADMIN` 系统管理员。

常见响应状态：

| 状态码 | 含义 |
| --- | --- |
| 200 | 查询或操作成功 |
| 201 | 创建成功 |
| 204 | 操作成功且无响应体 |
| 400 | 业务参数或状态不合法 |
| 401 | 未登录或令牌失效 |
| 403 | 角色、网点或资源权限不足 |
| 404 | 资源不存在 |
| 409 | 状态冲突、幂等键重复或前置条件未满足 |
| 422 | 请求字段校验失败 |
| 503 | 外部依赖暂不可用 |

错误响应统一按以下结构处理：

```json
{
  "code": "SHIPMENT_DRAFT_INCOMPLETE",
  "message": "运单草稿仍缺少必填字段",
  "request_id": "请求追踪 UUID",
  "details": {"missing_fields": ["receiver_address_id"]}
}
```

## 2. 登录与系统状态

### 演示登录

```http
POST /auth/demo-login
```

请求：

```json
{"login_name":"customer.demo","password":"YituDemo2026!"}
```

响应 `200`：

```json
{"access_token":"jwt-token","token_type":"bearer"}
```

### 当前用户

```http
GET /auth/me
```

响应字段：`id`、`display_name`、`role`、`station_id`。

### 健康检查

```http
GET /health
GET /readiness
```

无需登录。用于启动探针和就绪探针，成功返回 `200`，依赖不可用时返回非 2xx。

## 3. 客户端接口（CUSTOMER）

### 地址簿

```http
GET    /addresses
POST   /addresses
PATCH  /addresses/{address_id}
DELETE /addresses/{address_id}
```

创建请求：

```json
{
  "label":"家",
  "recipient_name":"张三",
  "phone":"13800000000",
  "district_code":"110101",
  "detail":"东城区示例路 1 号"
}
```

更新请求可只提交需要修改的字段。响应字段：`id`、`label`、`recipient_name`、`phone`、`district_code`、`detail`。创建返回 `201`，删除返回 `204`。

### 网点列表

```http
GET /stations
```

响应数组字段：`id`、`code`、`name`、`district_code`。

### 报价

```http
POST /pricing/quotes
GET  /pricing/quotes/{quote_id}
POST /pricing/quotes/{quote_id}/reweigh
```

报价请求：

```json
{
  "origin_district_code":"110101",
  "destination_district_code":"310101",
  "pickup_method":"DOOR_PICKUP",
  "delivery_method":"HOME_DELIVERY",
  "actual_weight_grams":1000,
  "length_cm":10,
  "width_cm":10,
  "height_cm":10,
  "declared_value_cents":0
}
```

复重请求只包含：`actual_weight_grams`、`length_cm`、`width_cm`、`height_cm`。报价响应字段：`id`、`rule_version`、`input_snapshot`、`fee_items`、`volume_weight_grams`、`billable_weight_grams`、`total_cents`、`created_at`。

### 创建和查询运单

```http
POST /shipments
GET  /shipments?status={status}&limit=50&offset=0
GET  /shipments/{shipment_id}
GET  /shipments/{shipment_id}/tracking
GET  /shipments/{shipment_id}/label
POST /shipments/{shipment_id}/confirm-payment
POST /shipments/{shipment_id}/resume
```

创建请求：

```json
{
  "draft":{
    "sender_address_id":"寄件地址 UUID",
    "receiver_address_id":"收件地址 UUID",
    "origin_station_id":null,
    "destination_station_id":null,
    "pickup_method":"DOOR_PICKUP",
    "delivery_method":"HOME_DELIVERY"
  },
  "status":"PENDING_PAYMENT"
}
```

`DOOR_PICKUP` 必须提供 `sender_address_id`；`STATION_DROPOFF` 必须提供 `origin_station_id`；`HOME_DELIVERY` 必须提供 `receiver_address_id`；`STATION_PICKUP` 必须提供 `destination_station_id`。

运单列表响应：

```json
{
  "items":[{"id":"UUID","shipment_no":"YT...","owner_id":"UUID","status":"PENDING_PAYMENT"}],
  "total":1,"limit":50,"offset":0
}
```

详情响应还包含 `tracking`、`paid_total_cents`、`eta_at`、`promised_delivery_at`。标签接口返回当前标签投影对象。恢复履约请求：`{"target_status":"目标状态","reason":"原因"}`，响应字段为 `shipment_id`、`status`、`resumed_hold_count`。

### 支付

```http
POST /payments/quotes/{quote_id}/pay
POST /payments/quotes/{quote_id}/supplement
POST /payments/transactions/{transaction_id}/refund
```

支付和补差请求：`{"shipment_id":"UUID","amount_cents":1800}`。退款接口无请求体。响应字段：`id`、`quote_id`、`shipment_id`、`related_transaction_id`、`transaction_type`、`status`、`amount_cents`、`created_at`。支付成功后调用 `POST /shipments/{shipment_id}/confirm-payment`，该接口返回 `204`。

### 通知

```http
GET  /notifications
POST /notifications/{notification_id}/read
GET  /notifications/stream
```

通知字段：`id`、`template_code`、`title`、`content`、`status`、`created_at`、`read_at`。SSE 使用 `Content-Type: text/event-stream`，断线重连时发送 `Last-Event-ID`。

### 退回与恢复履约

```http
POST /returns/shipments/{shipment_id}/cancel
POST /returns/shipments/{shipment_id}/request-interception
POST /returns/shipments/{shipment_id}/redeliver
POST /returns/shipments/{shipment_id}/convert-to-pickup
POST /returns/shipments/{shipment_id}/approve-return
POST /returns/shipments/{shipment_id}/advance-return
```

请求体统一为：`{"reason":"操作原因"}`，必须携带 `Idempotency-Key`。响应字段：`shipment_id`、`shipment_status`、`recovery`、`refund_amount_cents`、`new_task_id`；其中 `recovery` 包含 `id`、`action`、`status`、`reason`、`actor_id`、`created_at`、`completed_at`。不同动作受当前运单状态和角色限制，前端应根据错误码提示并刷新运单详情。

## 4. 快递员与网点员接口

### 任务列表

```http
GET /dispatch/tasks?shipment_id={shipment_id}
```

快递员、网点员只能看到所属网点任务；运营管理员可查看运营范围任务。任务字段：`id`、`shipment_id`、`task_type`、`status`、`assignee_id`。

### 取件与交接

```http
POST /dispatch/tasks/{task_id}/accept
POST /dispatch/tasks/{task_id}/confirm-pickup
POST /dispatch/shipments/{shipment_id}/accept-dropoff
POST /dispatch/shipments/{shipment_id}/confirm-origin-arrival
```

前两个接口无请求体，成功返回 `204`；后两个返回运单基础对象：`id`、`shipment_no`、`owner_id`、`status`。调用顺序通常为：任务接受 -> 确认取件，或网点接收 -> 原寄件网点确认到达。

### 干线运输

```http
POST /dispatch/shipments/{shipment_id}/dispatch-linehaul
POST /dispatch/shipments/{shipment_id}/arrive-destination
```

网点员负责发车，运营管理员负责目的地到达确认。响应：`shipment_id`、`status`、`next_action`。到达目的地后，`next_action` 可能是 `CREATE_DELIVERY_TASK` 或 `ISSUE_PICKUP_CREDENTIAL`。

### 派送与签收

```http
POST /dispatch/shipments/{shipment_id}/start-delivery
POST /dispatch/shipments/{shipment_id}/confirm-delivery
```

仅派送任务负责人可开始派送和签收。签收请求：`{"signer_name":"李四"}`，两个接口成功均返回 `204`。

### 网点自提

```http
POST /dispatch/shipments/{shipment_id}/issue-pickup-credential
POST /dispatch/shipments/{shipment_id}/verify-station-pickup
```

网点员签发取件凭证，无请求体，返回 `204`；核验请求：`{"code":"123456"}`，成功返回 `204`。前端不应展示服务端保存的凭证哈希，只处理用户输入的一次性取件码。

## 5. 运营异常工单（运营管理员）

```http
POST /exceptions
GET  /exceptions
GET  /exceptions/{case_id}
POST /exceptions/{case_id}/assign
POST /exceptions/{case_id}/start-processing
POST /exceptions/{case_id}/wait-for-customer
POST /exceptions/{case_id}/resume-processing
POST /exceptions/{case_id}/resolve
POST /exceptions/{case_id}/close
POST /exceptions/{case_id}/reassign-task
```

创建请求：

```json
{
  "shipment_id":"UUID",
  "case_type":"PICKUP_FAILED",
  "description":"未能联系收件人",
  "evidence_summary":{}
}
```

列表查询参数：`shipment_id`、`status`、`case_type`、`severity`、`responsible_station_id`、`assigned_to`、`blocks_fulfillment`、`limit`（1-100）、`offset`（大于等于 0）。

分配请求：`{"assignee_id":"UUID","responsible_station_id":"UUID","reason":"分配原因"}`。开始处理、等待客户、恢复处理、关闭请求均可使用 `{"reason":"原因"}`。解决请求：`{"resolution_code":"INFORMATION_CORRECTED","reason":"处理说明"}`。重派任务请求：`{"old_task_id":"UUID","reason":"重派原因"}`。

工单响应字段：`id`、`shipment_id`、`case_type`、`severity`、`status`、`description`、`evidence_summary`、`blocks_fulfillment`、`frozen_shipment_status`、`reported_by`、`assigned_to`、`responsible_station_id`、`opened_at`、`assigned_at`、`resolved_at`、`closed_at`。创建返回 `201`，其他操作返回 `200`。

## 6. SLA（运营管理员/系统管理员）

```http
POST /sla/rules
POST /sla/shipments/{shipment_id}/instances
GET  /sla/shipments/{shipment_id}/instances
POST /sla/instances/{instance_id}/pause
POST /sla/instances/{instance_id}/resume
POST /sla/instances/{instance_id}/complete
POST /sla/instances/{instance_id}/eta
```

发布规则请求：

```json
{
  "version":"sla-v1",
  "route_code":"GZ-SH",
  "service_type":"STANDARD",
  "stage":"LINEHAUL",
  "target_work_hours":24,
  "target_natural_hours":null,
  "effective_from":"2026-08-12T00:00:00+08:00",
  "effective_to":null
}
```

工作时长和自然时长必须二选一。启动实例请求：`{"route_code":"GZ-SH","stage":"LINEHAUL","service_type":"STANDARD"}`；暂停请求：`{"reason":"等待客户补充资料"}`；恢复、完成无请求体；更新 ETA 请求：`{"delay_minutes":30}`。

规则响应字段：`id`、`version`、`route_code`、`service_type`、`stage`、`target_work_hours`、`target_natural_hours`、`effective_from`、`effective_to`、`active`。实例响应字段：`id`、`shipment_id`、`rule_version`、`stage`、`status`、`started_at`、`promised_delivery_at`、`eta_at`、`completed_at`、`paused_seconds`、`breached`。

## 7. 知识库与 RAG

知识库维护角色为 `OPERATIONS_ADMIN` 和 `SYSTEM_ADMIN`；其他已登录角色只能检索。

### 上传文档

```http
POST /knowledge/documents
Content-Type: multipart/form-data
```

表单字段：`file`，当前用于上传 PDF。成功返回 `201`，文件会进入异步 MinerU 解析队列。

### 文档生命周期

```http
GET  /knowledge/documents/{document_id}
POST /knowledge/documents/{document_id}/review
POST /knowledge/documents/{document_id}/publish
POST /knowledge/documents/{document_id}/archive
POST /knowledge/documents/{document_id}/deactivate
POST /knowledge/documents/{document_id}/reparse
```

审核请求可传：

```json
{
  "category":"禁寄规则",
  "effective_from":"2026-08-12T00:00:00+08:00",
  "effective_to":null
}
```

发布、归档、停用、重新解析无请求体。文档字段：`id`、`filename`、`content_type`、`size_bytes`、`sha256`、`status`、`page_count`、`error_message`、`mineru_task_id`、`source_artifact_key`、`markdown_artifact_key`、`result_archive_key`、`parse_started_at`、`parse_finished_at`、`created_at`、`updated_at`、`reviewed_by`、`reviewed_at`、`published_at`、`effective_from`、`effective_to`、`category`。

### 检索

```http
GET /knowledge/search?query=禁寄规则&category=禁寄规则&limit=5
```

`query` 必填，长度 1-500；`limit` 范围 1-20。响应为 `{ "items": [...] }`，每条证据包含 `document_id`、`filename`、`category`、`index_version`、`title`、`section_path`、`content_type`、`page_start`、`page_end`、`content`、`score`。

## 8. Agent 对话与智能下单

```http
POST   /agent/conversations
GET    /agent/conversations
GET    /agent/conversations/{conversation_id}
DELETE /agent/conversations/{conversation_id}
GET    /agent/conversations/{conversation_id}/messages
POST   /agent/conversations/{conversation_id}/messages
GET    /agent/conversations/{conversation_id}/stream
```

创建会话请求：`{"title":"我的寄件"}`；发送消息请求：`{"content":"我想从广州寄到上海"}`。消息字段：`id`、`conversation_id`、`role`、`content`、`envelope`、`created_at`。单轮响应包含 `user_message` 和 `assistant_message`。SSE 使用 `text/event-stream` 和 `Last-Event-ID`。

### Agent 草稿、授权与记忆

```http
GET   /agent/conversations/{conversation_id}/draft
PATCH /agent/conversations/{conversation_id}/draft
POST  /agent/conversations/{conversation_id}/draft/validate
POST  /agent/conversations/{conversation_id}/grant
POST  /agent/conversations/grants/{grant_id}/consume
GET   /agent/conversations/memories
POST  /agent/conversations/memories
DELETE /agent/conversations/memories/{memory_id}
```

草稿 PATCH 支持：地址 UUID、网点 UUID、`pickup_method`、`delivery_method`、起终点行政区编码、重量、长宽高、声明价值。校验接口返回 `command`、`quote`、`draft`；只有草稿状态为 `READY_FOR_CONFIRMATION` 时才展示确认按钮。推荐顺序：更新草稿 -> 校验并报价 -> 创建授权 -> 用户确认 -> 消费授权。授权不可直接绕过正式运单创建。

记忆创建请求：

```json
{"memory_type":"preference","content":"默认使用上门取件","expires_at":null}
```

`memory_type` 只能是 `preference`、`instruction`、`profile`。敏感凭证和联系方式不会被保存。

## 9. 系统管理员运维接口

```http
GET  /admin/dead-letters?limit=50&offset=0
POST /admin/dead-letters/{dead_letter_id}/replay
```

仅 `SYSTEM_ADMIN` 可调用。死信字段：`id`、`event_id`、`event_type`、`business_id`、`attempts`、`last_error`、`failed_at`、`replayed_at`、`suggested_action`。重放成功响应：`{"dead_letter_id":"UUID","event_id":"UUID","status":"pending"}`。

## 10. 前端实现建议

1. 登录成功后保存 `access_token`，每次请求统一注入 Bearer Token；收到 `401` 清理会话并跳转登录。
2. 根据 `/auth/me` 的 `role` 显示菜单，但最终权限以接口返回为准；收到 `403` 不要重试。
3. 所有写操作生成稳定的 `Idempotency-Key`，网络超时可使用同一键重试。
4. 运单详情页同时请求详情和轨迹；状态推进成功后重新拉取详情、任务和通知。
5. SSE 连接保存最后事件 ID，断线使用 `Last-Event-ID` 重连，并在组件卸载时关闭连接。
6. 知识库上传后轮询文档状态，直到 `PUBLISHED`、`ARCHIVED`、`DEACTIVATED` 或出现 `error_message`。

本文档以当前后端路由和 schema 为准；接口变更时应同步更新本文件。
