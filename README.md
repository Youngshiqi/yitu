# 驿途智能物流

当前项目按“后端优先”顺序开发。阶段一提供 FastAPI、PostgreSQL、Redis、Celery、幂等、审计、Outbox、重试与死信恢复基础。

## 本地运行

1. 确认 Docker Desktop 已启动。
2. 在项目根目录根据 `.env.example` 创建本地 `.env`；`.env` 不会提交到 Git。
3. 运行 `docker compose up --build -d`。
4. 运行 `docker compose ps` 查看四个服务状态。
5. 访问 `http://localhost:8000/api/v1/health`。

PostgreSQL 为避免与本机及测试数据库冲突，映射到宿主机 `127.0.0.1:55433`；容器内部仍使用 `5432`。

数据库迁移由 API 容器启动时自动执行。停止服务使用 `docker compose down`；该命令保留数据库卷。

## 本地演示身份

Compose 会以演示模式启动并自动创建以下固定身份，统一密码为 `YituDemo2026!`：

- 客户：`customer.demo`
- 北京快递员：`courier.bijing.demo`
- 上海快递员：`courier.shanghai.demo`
- 北京网点员：`operator.beijing.demo`
- 上海网点员：`operator.shanghai.demo`
- 运营管理员：`operations.demo`
- 系统管理员：`system.demo`

网点自取的演示取件码固定为 `123456`，仅用于本地 demo 配置。正式环境必须关闭 demo 配置，并配置独立的取件码 pepper；接口和轨迹均不会返回取件码明文。
