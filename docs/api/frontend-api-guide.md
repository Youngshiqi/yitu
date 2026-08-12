# Yitu 前端 API 使用手册

这份文档给前端开发者阅读。机器生成和代码生成请使用同目录的 `openapi.json`。

## 1. 基础信息

开发环境 API 地址：

```text
http://localhost:8000/api/v1
```

所有接口都使用 JSON，除文件上传接口外请求头为：

```http
Content-Type: application/json
Authorization: Bearer <登录返回的 access_token>
```

登录、健康检查不需要 Bearer Token。

写操作建议增加唯一幂等键：

```http
Idempotency-Key: <uuid-or-unique-string>
```

金额字段统一使用“分”，例如 `1800` 表示 18.00 元。时间统一为带时区的 ISO 字符串。

## 2. 登录

### 登录

```http
POST /auth/demo-login
```

请求：

```json
{
  "login_name": "customer.demo",
  "password": "YituDemo2026!"
}
```

响应：

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer"
}
```

前端保存 `access_token`，之后在每次请求中发送 `Authorization: Bearer <token>`。

### 当前用户

```http
GET /auth/me
```

响应：

```json
{
  "id": "用户 UUID",
  "display_name": "演示客户",
  "role": "CUSTOMER",
  "station_id": null
}
```

角色值：`CUSTOMER`、`COURIER`、`STATION_OPERATOR`、`OPERATIONS_ADMIN`、`SYSTEM_ADMIN`。

## 3. 地址簿

```http
GET    /addresses
POST   /addresses
PATCH  /addresses/{address_id}
DELETE /addresses/{address_id}
```

创建地址请求：

```json
{
  "label": "家",
  "recipient_name": "张三",
  "phone": "13800000000",
  "district_code": "110101",
  "detail": "东城区示例路 1 号"
}
```

地址响应：

```json
{
  "id": "地址 UUID",
  "label": "家",
  "recipient_name": "张三",
  "phone": "13800000000",
  "district_code": "110101",
  "detail": "东城区示例路 1 号"
}
```

## 4. 运单列表和详情

### 运单列表

```http
GET /shipments?status=PENDING_PAYMENT&limit=20&offset=0
```

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `status` | string | 可选运单状态 |
| `limit` | number | 1 到 100，默认 50 |
| `offset` | number | 默认 0 |

响应：

```json
{
  "items": [
    {
      "id": "运单 UUID",
      "shipment_no": "YT202608120001",
      "owner_id": "用户 UUID",
      "status": "PENDING_PAYMENT"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### 运单详情和轨迹

```http
GET /shipments/{shipment_id}
GET /shipments/{shipment_id}/tracking
GET /shipments/{shipment_id}/label
```

运单详情当前返回基础状态字段；轨迹接口返回按顺序排列的事件：

```json
{
  "id": "事件 UUID",
  "sequence_no": 1,
  "event_type": "SHIPMENT_CREATED",
  "message": "运单已创建",
  "visible_to_customer": true,
  "occurred_at": "2026-08-12T15:30:00+08:00"
}
```

## 5. 报价、创建和支付

### 报价

```http
POST /pricing/quotes
```

请求：

```json
{
  "origin_district_code": "110101",
  "destination_district_code": "310101",
  "pickup_method": "DOOR_PICKUP",
  "delivery_method": "HOME_DELIVERY",
  "actual_weight_grams": 1000,
  "length_cm": 10,
  "width_cm": 10,
  "height_cm": 10,
  "declared_value_cents": 0
}
```

响应重点字段：

```json
{
  "id": "报价 UUID",
  "rule_version": "pricing-demo-v1",
  "fee_items": [],
  "billable_weight_grams": 1000,
  "total_cents": 1800,
  "created_at": "2026-08-12T15:30:00+08:00"
}
```

### 直接创建运单

```http
POST /shipments
Idempotency-Key: create-shipment-unique-key
```

请求：

```json
{
  "draft": {
    "sender_address_id": "寄件地址 UUID",
    "receiver_address_id": "收件地址 UUID",
    "origin_station_id": null,
    "destination_station_id": null,
    "pickup_method": "DOOR_PICKUP",
    "delivery_method": "HOME_DELIVERY"
  },
  "status": "PENDING_PAYMENT"
}
```

### 支付报价

```http
POST /payments/quotes/{quote_id}/pay
Idempotency-Key: pay-unique-key
```

请求：

```json
{
  "shipment_id": "运单 UUID",
  "amount_cents": 1800
}
```

支付完成后刷新运单详情；如需推进履约状态，再调用：

```http
POST /shipments/{shipment_id}/confirm-payment
```

该接口返回 `204`，前端收到后重新请求运单详情和轨迹。

## 6. Agent 对话下单

### 创建和发送消息

```http
POST /agent/conversations
GET  /agent/conversations
POST /agent/conversations/{conversation_id}/messages
GET  /agent/conversations/{conversation_id}/messages
```

创建会话：

```json
{
  "title": "我的寄件"
}
```

发送消息：

```json
{
  "content": "我想从北京寄到上海"
}
```

响应包含 `user_message` 和 `assistant_message`。助手消息的 `envelope` 中包含：

```json
{
  "route": "respond",
  "intent": "GENERAL_CHAT",
  "risk": "LOW",
  "trace_id": "追踪 UUID",
  "next_action": "GENERATE_RESPONSE"
}
```

### Agent SSE

```http
GET /agent/conversations/{conversation_id}/stream
```

响应类型为 `text/event-stream`。前端应保存事件 `id`，断线重连时发送：

```http
Last-Event-ID: <last-event-id>
```

### Agent 草稿和确认

```http
GET   /agent/conversations/{conversation_id}/draft
PATCH /agent/conversations/{conversation_id}/draft
POST  /agent/conversations/{conversation_id}/draft/validate
POST  /agent/conversations/{conversation_id}/grant
POST  /agent/conversations/grants/{grant_id}/consume
```

草稿更新示例：

```json
{
  "sender_address_id": "寄件地址 UUID",
  "receiver_address_id": "收件地址 UUID",
  "pickup_method": "DOOR_PICKUP",
  "delivery_method": "HOME_DELIVERY",
  "origin_district_code": "110101",
  "destination_district_code": "310101",
  "actual_weight_grams": 1000,
  "length_cm": 10,
  "width_cm": 10,
  "height_cm": 10,
  "declared_value_cents": 0
}
```

推荐流程：

```text
PATCH draft
  -> POST draft/validate
  -> 展示报价和确认卡片
  -> POST grant
  -> 用户点击确认
  -> POST grants/{grant_id}/consume
  -> 刷新运单列表
```

授权默认五分钟有效，只能消费一次。前端不能直接用 Agent 绕过授权创建运单。

## 7. 通知

```http
GET  /notifications
POST /notifications/{notification_id}/read
GET  /notifications/stream
```

通知 SSE 同样使用 `Last-Event-ID` 断线续传。通知列表响应包含 `id`、`title`、`content`、`status`、`created_at` 和 `read_at`。

## 8. 知识库和 RAG

管理员文档流程：

```http
POST /knowledge/documents
GET  /knowledge/documents/{document_id}
POST /knowledge/documents/{document_id}/review
POST /knowledge/documents/{document_id}/publish
POST /knowledge/documents/{document_id}/archive
POST /knowledge/documents/{document_id}/reparse
```

检索：

```http
GET /knowledge/search?q=禁寄规则&limit=5
```

前端展示检索结果时保留文档名、版本、页码和引用信息。

## 9. 错误处理

业务错误统一格式：

```json
{
  "code": "SHIPMENT_DRAFT_INCOMPLETE",
  "message": "运单草稿仍缺少必要字段",
  "request_id": "请求 UUID",
  "details": {
    "missing_fields": ["receiver_address_id"]
  }
}
```

常见状态码：

| 状态码 | 含义 |
| --- | --- |
| `401` | 未登录或 Token 无效 |
| `403` | 角色、网点或资源权限不足 |
| `404` | 资源不存在或不属于当前用户 |
| `409` | 状态冲突、草稿不完整、授权已消费 |
| `422` | 请求字段校验失败 |
| `503` | 外部模型或依赖暂时不可用 |

前端应展示 `message`，调试和问题反馈保留 `code`、`request_id` 和 `details`。

## 10. 参考文件

- 人类阅读版：当前文件
- 机器契约：[openapi.json](./openapi.json)
- 在线 Swagger：`http://localhost:8000/docs`
- 在线 ReDoc：`http://localhost:8000/redoc`
