# Yitu OpenAPI 文档

## 契约文件

- 机器可读契约：[openapi.json](./openapi.json)
- 服务标题：`Yitu Logistics API`
- 当前版本：`0.1.0`
- API 前缀：`/api/v1`

`openapi.json` 由 FastAPI 当前实际路由、请求模型和响应模型生成。前端类型、请求封装和接口联调应以该文件为准，不要手工复制已经变化的字段。

## 在线查看

启动后端后访问：

- Swagger UI：`http://localhost:8000/docs`
- ReDoc：`http://localhost:8000/redoc`
- 原始 schema：`http://localhost:8000/openapi.json`

## 认证

除登录、健康检查和就绪检查外，接口使用：

```http
Authorization: Bearer <access_token>
```

登录接口：

```http
POST /api/v1/auth/demo-login
Content-Type: application/json
```

写操作通常还需要：

```http
Idempotency-Key: <unique-key>
```

## 错误响应

业务错误统一为：

```json
{
  "code": "ERROR_CODE",
  "message": "面向用户的错误说明",
  "request_id": "uuid",
  "details": {}
}
```

前端应保留 `request_id`，便于问题反馈和后端追踪。HTTP 状态码、路径参数、请求体和响应体的准确结构以 `openapi.json` 为准。

## 主要业务域

| 标签 | 范围 |
| --- | --- |
| `system` | 健康检查和就绪检查 |
| `auth` | 登录和当前用户 |
| `addresses` | 地址簿 |
| `stations` | 网点 |
| `shipments` | 运单、轨迹、面单和恢复 |
| `pricing` | 报价和复秤 |
| `payments` | 支付、补款和退款 |
| `agent` | 会话、SSE、草稿、授权和记忆 |
| `knowledge` | PDF 文档、审核、发布和检索 |
| `notifications` | 通知和通知 SSE |
| `exceptions` | 异常工单 |
| `returns` | 取消、拦截、重派和退回 |
| `sla` | SLA 规则和实例 |
| `dispatch` | 快递员和网点调度 |
| `admin` | 死信查询和重放 |

## Agent 关键流程

```text
创建会话
  -> 更新 /draft
  -> /draft/validate 生成报价
  -> /grant 签发一次性确认授权
  -> /grants/{grant_id}/consume 创建正式运单
```

敏感写操作必须经过用户明确确认，前端不能直接绕过授权调用业务写接口。

## 重新生成

在后端依赖和路由模型变化后，从项目根目录运行：

```powershell
$env:PYTHONPATH = "backend/src"
Set-Location backend
uv run python -c "import json; from pathlib import Path; from yitu.main import create_app; Path('../docs/api/openapi.json').write_text(json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')"
```
