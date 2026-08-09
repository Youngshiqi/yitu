# 驿途后端阶段六：API 冻结实施计划

> **供智能体开发者使用：** 必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按照本计划逐项实施。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 完成全量后端验证、确定性演示、性能与安全基线，并冻结可供前端生成类型的 OpenAPI v1。

**架构：** 不增加新业务范围，只修复跨阶段一致性并产出机器可验证契约和人工可读文档。API 快照与错误/权限目录共同成为前端基线。

**技术栈：** 全部后端技术栈、OpenAPI JSON、openapi-typescript 验证工具、pytest、Docker Compose。

## 全局约束

- 本阶段禁止顺便开发 Vue；禁止为文档绕过实际响应模型。
- 所有完成声明必须基于本轮新运行的验证结果。
- 破坏性契约修正必须在冻结前完成，并同步旅程测试。

---

### 任务 1：迁移与数据完整性演练

**文件：** 新建 `backend/tests/migrations/test_full_history.py`；仅在测试暴露不一致时更新迁移或模型。

**接口：** 产出已验证的空数据库升级、降级策略和数据库结构/模型一致性报告。

- [ ] 测试空库升级、带种子数据升级、约束/索引/扩展和允许的降级边界。
- [ ] 针对全新 PostgreSQL 数据库运行迁移测试；修改前先记录失败。
- [ ] 修复顺序、命名或数据迁移问题，不得静默改变已发布语义。
- [ ] 重新运行迁移测试和 `alembic check`；预期退出码为 0。
- [ ] 提交：`测试：验证完整迁移历史`。

### 任务 2：确定性演示种子、时钟推进与范围重置

**文件：** 完成 `backend/src/yitu/demo/{seed,router,scenarios}.py`；需要时新增迁移；测试 `backend/tests/journeys/test_demo_reset.py`。

**接口：** 产出 `POST /api/v1/demo/reset`、场景推进路由和七个稳定的演示身份键。

- [ ] 测试非演示环境返回 404、系统管理员重置、范围删除、两次相同重置和保留非演示数据行。
- [ ] 运行演示测试；场景覆盖不完整时预期失败。
- [ ] 在已承诺的位置实现确定性 ID/编号、注入式 Clock 推进和带范围标签的重置事务。
- [ ] 运行两次完整北京至上海旅程，中间执行重置；预期可观察结果完全一致。
- [ ] 提交：`功能：新增可重复的后端演示场景`。

### 任务 3：跨模块安全与性能基线

**文件：** 新建 `backend/tests/security/test_matrix.py`、`backend/tests/performance/test_baseline.py`；新建 `docs/backend/security-baseline.md`。

**接口：** 产出有记录的授权矩阵、查询次数限制和代表性 P95 基线命令。

- [ ] 为未认证、错误角色/网点/所有者/状态、重放、文件滥用、提示词注入和密钥泄漏生成用例。
- [ ] 为列表/详情、轨迹、混合检索和固定模型 Agent 响应添加有界性能用例；意外触发 N+1 阈值时失败。
- [ ] 在 Compose 中运行安全/性能套件，并记录环境和结果。
- [ ] 只修复有证据的正确性或性能回归，然后重新运行验证。
- [ ] 提交：`测试：建立后端安全与性能基线`。

### 任务 4：OpenAPI 规范化与契约快照

**文件：** 新建 `backend/scripts/export_openapi.py`；新建 `docs/api/openapi-v1.json`、`errors.md`、`permissions.md`、`examples.md`；新建 `backend/tests/api/test_openapi_contract.py`。

**接口：** 产出冻结的 `/api/v1` 操作 ID、模式、错误、示例、分页，以及 SSE/文件工作流文档。

- [ ] 测试操作 ID 唯一、响应模型/状态显式、无未记录的 2xx、错误信封稳定且不存在携带密钥的字段。
- [ ] 导出 OpenAPI 并检查命名、分页和过滤约定；测试必须精确指出每项不一致。
- [ ] 规范化路由和模式，并记录角色/资源矩阵、幂等、异步状态及 Agent 工具关系。
- [ ] 连续导出两次，并断言 JSON 快照逐字节稳定。
- [ ] 提交：`文档：冻结 OpenAPI v1 契约`。

### 任务 5：前端类型生成兼容性

**文件：** 新建 `tools/api-contract/package.json`；新建 `tools/api-contract/typecheck.ts`；修改 API 文档。

**接口：** 证明可以从 `openapi-v1.json` 生成无模式错误的 TypeScript 客户端。

- [ ] 配置固定版本的 `openapi-typescript`，并为代表性的认证、运单、上传、SSE 和 Agent DTO 编写仅编译消费者。
- [ ] 运行 `cd tools/api-contract; npm install; npm run generate; npm run typecheck`；预期退出码为 0。
- [ ] 修复 OpenAPI 源模型，不得手工编辑生成结果。
- [ ] 从干净目录重复生成并比较输出。
- [ ] 提交：`测试：验证前端 API 类型生成`。

### 任务 6：后端最终验收与交接

**文件：** 更新 `README.md`、`CONTEXT.md`；新建 `docs/backend/verification-report.md`、`frontend-handoff.md`。

**接口：** 产出一条命令启动方式、演示脚本、故障排查、验证证据和冻结的前端交接文档。

- [ ] 从干净容器运行 `docker compose up --build -d` 和 `alembic upgrade head`；验证全部健康检查。
- [ ] 运行 `cd backend; uv run ruff check .; uv run mypy src; uv run pytest -q`；记录精确数量和版本。
- [ ] 运行四种物流旅程、一个异常/退回旅程、RAG 上传到引用旅程、固定 Agent 评测和经批准的在线冒烟测试。
- [ ] 运行两次演示重置并重新生成 OpenAPI/类型；验证输出确定且可重复。
- [ ] 只有当每条新运行命令的退出码均为 0 后，才提交：`文档：交接冻结的后端 API`。
