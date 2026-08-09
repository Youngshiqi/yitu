# 驿途智能物流

当前项目按“后端优先”顺序开发。阶段一提供 FastAPI、PostgreSQL、Redis、Celery、幂等、审计、Outbox、重试与死信恢复基础。

## 本地运行

1. 确认 Docker Desktop 已启动。
2. 在项目根目录根据 `.env.example` 创建本地 `.env`；`.env` 不会提交到 Git。
3. 运行 `docker compose up --build -d`。
4. 运行 `docker compose ps` 查看四个服务状态。
5. 访问 `http://localhost:8000/api/v1/health`。

数据库迁移由 API 容器启动时自动执行。停止服务使用 `docker compose down`；该命令保留数据库卷。
