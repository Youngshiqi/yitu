# Yitu 物流核心实施计划

> **供实施 Agent 使用：** 必须使用 `subagent-driven-development`（推荐）或 `executing-plans`，按任务逐项实施本计划。各步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 构建一个可通过 Docker 运行的 FastAPI + Vue 纵向切片，完整展示经过认证的身份切换、网点匹配、四种寄收件组合、快递员任务、模拟干线、签收凭证和客户可见的物流轨迹。

**架构：** 使用模块化 FastAPI 单体和一个 PostgreSQL 数据库。HTTP 路由调用应用服务；应用服务负责权限与状态转换校验，并在同一事务中持久化聚合变更和追加物流轨迹。Vue 只调用 HTTP API，不在前端自行推导权限或状态变化。

**技术栈：** Python 3.11、FastAPI、Pydantic v2、SQLAlchemy 2 异步模式、Alembic、PostgreSQL 16、PyJWT、Argon2、pytest、HTTPX、Vue 3、TypeScript、Vite、Pinia、Vue Router、Element Plus、Axios、Docker Compose。

## 全局约束

- 只实施物流核心纵向切片所需的 PRD 内容；计价规则、SLA 引擎、通知、异常、RAG、MinerU、LangGraph 和 AI 记忆不在本计划范围内。
- 保留五个标准角色：`CUSTOMER`、`COURIER`、`STATION_OPERATOR`、`OPERATIONS_ADMIN` 和 `SYSTEM_ADMIN`。
- 揽收和派送是任务类型，不是角色；始发和目标是网点数据范围，不是角色。
- 每个改变状态的接口都必须校验 JWT 身份、资源范围、当前状态和 `Idempotency-Key` 请求头。
- 统一业务时区为 `Asia/Shanghai`（UTC+08:00）。API 时间必须带 `+08:00` 偏移，PostgreSQL 使用 `timestamptz` 且连接会话时区设为 `Asia/Shanghai`；禁止无时区时间进入业务模型。
- 电话和地址只使用演示数据；客户可见轨迹和普通日志中的电话必须脱敏。
- 第一阶段一张运单只对应一个实体包裹。
- 源码标识符使用 ASCII，API 错误码使用英文；客户可见的 Vue 文案使用简体中文。
- 不增加通用状态修改、管理员直接编辑数据库、GIS、真实支付、真实短信、真实扫码硬件或真实干线调度。

---

## 计划文件结构

```text
/
├── .env.example
├── .gitattributes
├── .gitignore
├── compose.yaml
├── CONTEXT.md
├── README.md
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/
│   ├── src/yitu/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── clock.py
│   │   ├── errors.py
│   │   ├── idempotency.py
│   │   ├── identity/
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── security.py
│   │   │   ├── service.py
│   │   │   └── router.py
│   │   ├── stations/
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   └── router.py
│   │   ├── shipments/
│   │   │   ├── enums.py
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── state_machine.py
│   │   │   ├── service.py
│   │   │   └── router.py
│   │   ├── dispatch/
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   └── router.py
│   │   ├── tracking/
│   │   │   ├── models.py
│   │   │   ├── schemas.py
│   │   │   └── service.py
│   │   └── demo/
│   │       ├── seed.py
│   │       └── router.py
│   └── tests/
│       ├── conftest.py
│       ├── api/
│       ├── identity/
│       ├── stations/
│       ├── shipments/
│       └── journeys/
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── src/
    │   ├── main.ts
    │   ├── App.vue
    │   ├── api/client.ts
    │   ├── api/generated.ts
    │   ├── router/index.ts
    │   ├── stores/auth.ts
    │   ├── layouts/AppLayout.vue
    │   ├── components/RoleSwitcher.vue
    │   ├── components/TrackingTimeline.vue
    │   ├── components/ShipmentActions.vue
    │   └── views/
    │       ├── LoginView.vue
    │       ├── CustomerShipmentsView.vue
    │       ├── ShipmentCreateView.vue
    │       ├── ShipmentDetailView.vue
    │       ├── CourierTasksView.vue
    │       ├── StationOperationsView.vue
    │       └── OperationsDemoView.vue
    └── tests/
```

## 任务 1：可运行的仓库基础

**文件：**
- 新建：`.gitattributes`
- 新建：`.gitignore`
- 新建：`.env.example`
- 新建：`compose.yaml`
- 新建：`CONTEXT.md`
- 新建：`README.md`
- 新建：`backend/pyproject.toml`
- 新建：`backend/src/yitu/config.py`
- 新建：`backend/src/yitu/database.py`
- 新建：`backend/src/yitu/clock.py`
- 新建：`backend/src/yitu/main.py`
- 新建：`backend/tests/api/test_health.py`
- 新建：`backend/tests/test_clock.py`
- 新建：`frontend/package.json`
- 新建：`frontend/src/main.ts`
- 新建：`frontend/src/App.vue`

**接口：**
- 产出：`create_app() -> FastAPI`
- 产出：SQLAlchemy `Base`、异步 `SessionFactory` 和 `get_session()` 依赖。
- 产出：统一返回 `Asia/Shanghai` 时间的 `Clock.now() -> datetime` 和 `to_business_timezone(value) -> datetime`。
- 产出：`GET /api/health -> {"status": "ok"}`
- 产出：Compose 中名为 `db` 的 PostgreSQL 服务和名为 `api` 的 API 服务。

- [ ] **步骤 1：编写失败的健康检查测试**

```python
from httpx import ASGITransport, AsyncClient

from yitu.main import create_app


async def test_health_reports_ok() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

同时在 `backend/tests/test_clock.py` 编写东八区契约测试：

```python
from datetime import UTC, datetime, timedelta

from yitu.clock import Clock, to_business_timezone


def test_clock_and_conversion_use_china_standard_time() -> None:
    now = Clock().now()
    converted = to_business_timezone(datetime(2026, 8, 9, 0, 0, tzinfo=UTC))

    assert now.utcoffset() == timedelta(hours=8)
    assert converted.isoformat() == "2026-08-09T08:00:00+08:00"
```

- [ ] **步骤 2：运行测试并确认预期失败**

运行：`cd backend; uv run pytest tests/api/test_health.py tests/test_clock.py -q`

预期：测试收集失败，因为 `yitu.main` 和 `yitu.clock` 尚不存在。

- [ ] **步骤 3：添加最小 FastAPI 应用和项目元数据**

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Yitu Logistics API", version="0.1.0")

    @app.get("/api/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

在 `pyproject.toml` 中配置 Python 3.11、FastAPI、SQLAlchemy 异步模式、asyncpg、Alembic、Pydantic Settings、PyJWT、Argon2、pytest、pytest-asyncio、HTTPX、Ruff 和 mypy。让 Ruff 与 mypy 检查 `backend/src` 和 `backend/tests`。

在 `database.py` 中定义声明式 `Base`、异步引擎、`SessionFactory` 和事务安全的 FastAPI `get_session` 依赖。建立连接时执行 `SET TIME ZONE 'Asia/Shanghai'`。测试使用 PostgreSQL 测试事务覆盖 `get_session`；各领域模块必须导入共享 `Base`，不能自行创建元数据。

在 `clock.py` 中使用 `ZoneInfo("Asia/Shanghai")` 提供唯一的业务当前时间入口和时区转换函数。Pydantic 请求模型拒绝无 `tzinfo` 的时间；响应通过共享序列化基类统一输出带 `+08:00` 的 RFC 3339 字符串。测试通过依赖覆盖注入固定东八区时钟。

- [ ] **步骤 4：添加 Vue/Vite 外壳和 Docker Compose 服务**

创建 Vue 3 TypeScript 应用，初始页面显示 `Yitu 物流控制台`。Compose 必须定义 `db`、`api` 和 `web`，配置健康检查，并且只在开发配置中挂载源码。添加包含 `* text=auto eol=lf` 的 `.gitattributes`，避免 Windows 换行符反复产生差异。

- [ ] **步骤 5：验证基础工程**

运行：`cd backend; uv run ruff check .; uv run mypy src; uv run pytest tests/api/test_health.py tests/test_clock.py -q`

预期：所有命令通过，健康检查与东八区时间测试均通过。

运行：`cd frontend; npm install; npm run build`

预期：Vite 生产构建成功。

- [ ] **步骤 6：提交**

```bash
git add .gitattributes .gitignore .env.example compose.yaml CONTEXT.md backend frontend
git commit -m "chore: scaffold yitu application"
```

## 任务 2：网点与确定性服务区域匹配

**文件：**
- 新建：`backend/src/yitu/stations/models.py`
- 新建：`backend/src/yitu/stations/schemas.py`
- 新建：`backend/src/yitu/stations/service.py`
- 新建：`backend/src/yitu/stations/router.py`
- 新建：`backend/migrations/versions/0001_create_stations.py`
- 新建：`backend/tests/stations/test_station_resolution.py`
- 修改：`backend/src/yitu/main.py`

**接口：**
- 产出：`Station`、`ServiceArea`
- 产出：`resolve_station(session, district_code: str) -> Station`
- 产出：`GET /api/stations?district_code=110105`

- [ ] **步骤 1：编写网点匹配行为测试**

```python
async def test_resolves_enabled_station_for_district(session, station_factory):
    station = await station_factory(code="BJ-CY", district_code="110105")

    resolved = await resolve_station(session, "110105")

    assert resolved.id == station.id


async def test_rejects_unserved_district(session):
    with pytest.raises(ServiceAreaNotFound) as error:
        await resolve_station(session, "999999")

    assert error.value.code == "SERVICE_AREA_NOT_FOUND"
```

- [ ] **步骤 2：运行测试并确认失败**

运行：`cd backend; uv run pytest tests/stations/test_station_resolution.py -q`

预期：导入网点模块失败。

- [ ] **步骤 3：实现网点模型与匹配服务**

```python
class Station(Base):
    __tablename__ = "stations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    city_name: Mapped[str] = mapped_column(String(50))
    is_enabled: Mapped[bool] = mapped_column(default=True)


class ServiceArea(Base):
    __tablename__ = "service_areas"
    district_code: Mapped[str] = mapped_column(String(6), primary_key=True)
    station_id: Mapped[UUID] = mapped_column(ForeignKey("stations.id"))
```

`resolve_station` 只能返回启用状态的网点。API 返回适合客户查看的网点投影，并使用稳定的 `SERVICE_AREA_NOT_FOUND` 错误码。

- [ ] **步骤 4：添加数据库迁移与 API 测试**

验证 `GET /api/stations?district_code=110105` 能返回匹配网点，并且不会暴露内部操作人员数据。

- [ ] **步骤 5：验证并提交**

运行：`cd backend; uv run pytest tests/stations -q; uv run alembic upgrade head`

预期：测试通过，迁移可应用到空 PostgreSQL 数据库。

```bash
git add backend/src/yitu/stations backend/tests/stations backend/migrations backend/src/yitu/main.py
git commit -m "feat: add station service-area resolution"
```

## 任务 3：五角色身份体系与安全演示登录

**文件：**
- 新建：`backend/src/yitu/identity/models.py`
- 新建：`backend/src/yitu/identity/schemas.py`
- 新建：`backend/src/yitu/identity/security.py`
- 新建：`backend/src/yitu/identity/service.py`
- 新建：`backend/src/yitu/identity/router.py`
- 新建：`backend/migrations/versions/0002_create_users.py`
- 新建：`backend/tests/identity/test_demo_login.py`
- 修改：`backend/src/yitu/main.py`

**接口：**
- 产出：仅包含五个值的 `Role` 枚举。
- 产出：`POST /api/auth/demo-login`
- 产出：`get_current_user() -> User`
- 使用：任务 2 提供的可选 `station_id`。

- [ ] **步骤 1：编写身份认证测试**

```python
async def test_demo_login_issues_scoped_token(client, seeded_users):
    response = await client.post(
        "/api/auth/demo-login", json={"identity": "pickup_beijing"}
    )

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "COURIER"
    assert response.json()["user"]["station_code"] == "BJ-CY"


async def test_demo_login_is_disabled_outside_demo_profile(client, settings):
    settings.app_profile = "production"
    response = await client.post(
        "/api/auth/demo-login", json={"identity": "customer"}
    )
    assert response.status_code == 404
```

- [ ] **步骤 2：确认测试失败**

运行：`cd backend; uv run pytest tests/identity/test_demo_login.py -q`

预期：路由和角色类型尚不存在。

- [ ] **步骤 3：实现用户身份与 JWT 校验**

```python
class Role(StrEnum):
    CUSTOMER = "CUSTOMER"
    COURIER = "COURIER"
    STATION_OPERATOR = "STATION_OPERATOR"
    OPERATIONS_ADMIN = "OPERATIONS_ADMIN"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class TokenClaims(BaseModel):
    sub: UUID
    role: Role
    station_id: UUID | None
    exp: datetime
    jti: UUID
```

访问令牌必须在服务端签发。`get_current_user` 必须从数据库加载当前启用用户，不能只信任令牌中的角色和网点声明。

- [ ] **步骤 4：测试受保护接口与角色拒绝**

添加令牌缺失（`401`）、用户停用（`401`）、角色错误（`403`）和快递员网点范围测试。

- [ ] **步骤 5：验证并提交**

运行：`cd backend; uv run pytest tests/identity -q; uv run mypy src`

```bash
git add backend/src/yitu/identity backend/tests/identity backend/migrations backend/src/yitu/main.py
git commit -m "feat: add scoped demo authentication"
```

## 任务 4：运单聚合、状态机与创建流程

**文件：**
- 新建：`backend/src/yitu/shipments/enums.py`
- 新建：`backend/src/yitu/shipments/models.py`
- 新建：`backend/src/yitu/shipments/schemas.py`
- 新建：`backend/src/yitu/shipments/state_machine.py`
- 新建：`backend/src/yitu/shipments/service.py`
- 新建：`backend/src/yitu/shipments/router.py`
- 新建：`backend/src/yitu/tracking/models.py`
- 新建：`backend/src/yitu/tracking/schemas.py`
- 新建：`backend/src/yitu/tracking/service.py`
- 新建：`backend/migrations/versions/0003_create_shipments.py`
- 新建：`backend/tests/shipments/test_create_shipment.py`
- 新建：`backend/tests/shipments/test_state_machine.py`
- 修改：`backend/src/yitu/main.py`

**接口：**
- 产出：`PickupMethod`、`DeliveryMethod`、`ShipmentStatus`、`TrackingEventType`
- 产出：`create_shipment(session, customer, command) -> Shipment`
- 产出：`confirm_demo_payment(session, shipment, customer, idempotency_key) -> Shipment`
- 使用：任务 2 的 `resolve_station`。

- [ ] **步骤 1：为四种初始路径编写状态机测试**

```python
@pytest.mark.parametrize(
    ("pickup_method", "expected"),
    [
        (PickupMethod.DOOR_PICKUP, ShipmentStatus.PENDING_PICKUP),
        (PickupMethod.STATION_DROPOFF, ShipmentStatus.WAITING_FOR_DROPOFF),
    ],
)
def test_payment_selects_initial_fulfillment_state(pickup_method, expected):
    assert initial_fulfillment_status(pickup_method) is expected


def test_generic_status_jump_is_not_exposed():
    with pytest.raises(InvalidTransition):
        transition(ShipmentStatus.PENDING_PAYMENT, "deliver")
```

- [ ] **步骤 2：编写运单创建 API 测试**

验证客户只能创建自己的运单，始发和目标网点能通过区县编码匹配，运单号唯一，并追加一条 `SHIPMENT_CREATED` 事件。

- [ ] **步骤 3：确认测试失败**

运行：`cd backend; uv run pytest tests/shipments/test_state_machine.py tests/shipments/test_create_shipment.py -q`

- [ ] **步骤 4：实现不可变服务选择和显式状态转换**

```python
class ShipmentStatus(StrEnum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PENDING_PICKUP = "PENDING_PICKUP"
    PICKUP_ASSIGNED = "PICKUP_ASSIGNED"
    WAITING_FOR_DROPOFF = "WAITING_FOR_DROPOFF"
    PICKED_UP = "PICKED_UP"
    AT_ORIGIN_STATION = "AT_ORIGIN_STATION"
    IN_LINEHAUL = "IN_LINEHAUL"
    AT_DESTINATION_STATION = "AT_DESTINATION_STATION"
    DELIVERY_ASSIGNED = "DELIVERY_ASSIGNED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    WAITING_FOR_RECIPIENT_PICKUP = "WAITING_FOR_RECIPIENT_PICKUP"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
```

创建运单后统一进入 `PENDING_PAYMENT`。`confirm_demo_payment` 根据寄件方式转为 `PENDING_PICKUP` 或 `WAITING_FOR_DROPOFF`，并在同一事务中追加轨迹事件。保存寄件人与收件人快照，防止后续修改地址簿影响历史运单。

- [ ] **步骤 5：添加资源所有权与幂等测试**

验证其他客户访问时返回 `404`；使用相同幂等键重复支付时返回首次结果；相同幂等键携带不同请求内容时返回 `409 IDEMPOTENCY_KEY_REUSED`。

- [ ] **步骤 6：验证并提交**

运行：`cd backend; uv run pytest tests/shipments -q; uv run alembic upgrade head`

```bash
git add backend/src/yitu/shipments backend/src/yitu/tracking backend/tests/shipments backend/migrations backend/src/yitu/main.py
git commit -m "feat: create shipments with explicit state transitions"
```

## 任务 5：上门揽收、网点自寄与始发网点交接

**文件：**
- 新建：`backend/src/yitu/dispatch/models.py`
- 新建：`backend/src/yitu/dispatch/schemas.py`
- 新建：`backend/src/yitu/dispatch/service.py`
- 新建：`backend/src/yitu/dispatch/router.py`
- 新建：`backend/migrations/versions/0004_create_courier_tasks.py`
- 新建：`backend/tests/shipments/test_origin_fulfillment.py`
- 新建：`backend/tests/dispatch/test_concurrent_acceptance.py`
- 修改：`backend/src/yitu/shipments/service.py`
- 修改：`backend/src/yitu/main.py`

**接口：**
- 产出：`CourierTaskType.PICKUP`、`CourierTaskStatus`
- 产出：`accept_task`、`confirm_pickup`、`accept_dropoff`、`confirm_origin_arrival`
- 使用：任务 4 的运单转换和轨迹追加接口。

- [ ] **步骤 1：编写上门揽收和网点自寄旅程测试**

```python
async def test_door_pickup_creates_and_completes_pickup_task(api):
    shipment = await api.create_paid_shipment(pickup_method="DOOR_PICKUP")
    task = await api.accept_available_task("pickup_beijing", shipment.id)
    await api.confirm_pickup("pickup_beijing", task.id)
    result = await api.confirm_origin_arrival("origin_operator", shipment.id)
    assert result["status"] == "AT_ORIGIN_STATION"


async def test_dropoff_skips_pickup_task(api):
    shipment = await api.create_paid_shipment(pickup_method="STATION_DROPOFF")
    result = await api.accept_dropoff("origin_operator", shipment.id)
    assert result["status"] == "AT_ORIGIN_STATION"
    assert await api.tasks_for(shipment.id, type="PICKUP") == []
```

- [ ] **步骤 2：编写并发接单测试**

启动两个数据库事务同时接受同一个可接任务。断言一个响应为 `200`，另一个为 `409 TASK_ALREADY_ASSIGNED`，并且数据库中只保存一个快递员 ID。

- [ ] **步骤 3：运行始发履约测试并确认失败**

运行：`cd backend; uv run pytest tests/dispatch tests/shipments/test_origin_fulfillment.py -q`

预期：测试失败，因为快递员任务持久化和始发履约动作尚不存在。

- [ ] **步骤 4：实现原子接单**

```python
stmt = (
    update(CourierTask)
    .where(
        CourierTask.id == task_id,
        CourierTask.status == CourierTaskStatus.AVAILABLE,
        CourierTask.station_id == courier.station_id,
    )
    .values(status=CourierTaskStatus.ASSIGNED, courier_id=courier.id)
    .returning(CourierTask)
)
```

拒绝非任务负责人的揽收确认；拒绝非始发网点人员的入站确认；每个成功动作都追加一条客户可见的物流轨迹。

- [ ] **步骤 5：验证并提交**

运行：`cd backend; uv run pytest tests/dispatch tests/shipments/test_origin_fulfillment.py -q`

```bash
git add backend/src/yitu/dispatch backend/src/yitu/shipments backend/tests/dispatch backend/tests/shipments backend/migrations backend/src/yitu/main.py
git commit -m "feat: fulfill pickup and station dropoff"
```

## 任务 6：模拟干线与目标网点到站

**文件：**
- 修改：`backend/src/yitu/shipments/models.py`
- 修改：`backend/src/yitu/shipments/service.py`
- 修改：`backend/src/yitu/shipments/router.py`
- 新建：`backend/migrations/versions/0005_create_transport_legs.py`
- 新建：`backend/tests/shipments/test_linehaul.py`

**接口：**
- 产出：`dispatch_linehaul(session, shipment, origin_operator, key)`
- 产出：`arrive_destination(session, shipment, operations_admin, key)`
- 产出：每次模拟发运对应一条 `TransportLeg`。

- [ ] **步骤 1：编写权限与状态转换测试**

验证只有始发网点人员可以发出 `AT_ORIGIN_STATION` 状态的运单，只有 `OPERATIONS_ADMIN` 可以触发模拟到站，并且目标网点不能在发运前确认收件。

- [ ] **步骤 2：编写收件方式分支测试**

```python
@pytest.mark.parametrize(
    ("delivery_method", "expected_status", "expected_task_count"),
    [
        ("HOME_DELIVERY", "AT_DESTINATION_STATION", 1),
        ("STATION_PICKUP", "WAITING_FOR_RECIPIENT_PICKUP", 0),
    ],
)
async def test_arrival_selects_last_mile_path(
    api, delivery_method, expected_status, expected_task_count
):
    shipment = await api.ship_to_destination(delivery_method=delivery_method)
    assert shipment["status"] == expected_status
    assert len(await api.delivery_tasks(shipment["id"])) == expected_task_count
```

- [ ] **步骤 3：运行干线测试并确认失败**

运行：`cd backend; uv run pytest tests/shipments/test_linehaul.py -q`

预期：测试失败，因为运输段和干线动作尚不存在。

- [ ] **步骤 4：实现运输段持久化**

发运时创建包含始发网点、目标网点、`departed_at` 和 `IN_TRANSIT` 的运输段。到站时写入 `arrived_at`、关闭运输段、追加目标网点轨迹；送货上门时创建一个待接派送任务，网点自取时转为 `WAITING_FOR_RECIPIENT_PICKUP`。任务 7 在自取凭证模型建立后，把凭证生成加入同一到站事务。

- [ ] **步骤 5：验证并提交**

运行：`cd backend; uv run pytest tests/shipments/test_linehaul.py -q; uv run alembic upgrade head`

```bash
git add backend/src/yitu/shipments backend/tests/shipments/test_linehaul.py backend/migrations
git commit -m "feat: simulate linehaul destination arrival"
```

## 任务 7：送货上门、网点自取与签收凭证

**文件：**
- 修改：`backend/src/yitu/shipments/models.py`
- 修改：`backend/src/yitu/shipments/schemas.py`
- 修改：`backend/src/yitu/shipments/service.py`
- 修改：`backend/src/yitu/shipments/router.py`
- 修改：`backend/src/yitu/dispatch/service.py`
- 新建：`backend/migrations/versions/0006_create_delivery_proofs.py`
- 新建：`backend/tests/shipments/test_last_mile.py`

**接口：**
- 产出：`start_delivery`、`confirm_delivery`、`verify_station_pickup`
- 产出：`PickupCredential`、`ProofOfDelivery`

- [ ] **步骤 1：编写送货上门测试**

验证目标网点快递员只能接受本网点任务，只有任务负责人可以开始派送，完成派送时只创建一条 `ProofOfDelivery` 和一条 `DELIVERED` 轨迹事件。

- [ ] **步骤 2：编写网点自取凭证测试**

```python
async def test_station_pickup_is_one_time_and_idempotent(api):
    shipment, code = await api.ship_for_station_pickup()
    first = await api.pickup("destination_operator", shipment.id, code, key="pick-1")
    replay = await api.pickup("destination_operator", shipment.id, code, key="pick-1")
    assert first == replay
    assert first["status"] == "DELIVERED"


async def test_station_pickup_locks_after_five_failures(api):
    shipment, _ = await api.ship_for_station_pickup()
    for attempt in range(5):
        await api.pickup_expect_failure(shipment.id, "000000", key=f"bad-{attempt}")
    response = await api.pickup_expect_failure(shipment.id, "000000", key="bad-locked")
    assert response["code"] == "PICKUP_CODE_LOCKED"
```

- [ ] **步骤 3：运行末端履约测试并确认失败**

运行：`cd backend; uv run pytest tests/shipments/test_last_mile.py -q`

预期：测试失败，因为自取凭证和签收凭证尚不存在。

- [ ] **步骤 4：实现凭证哈希与签收凭证创建**

只存储 `code_hash`、`expires_at`、`failed_attempts`、`locked_at` 和 `consumed_at`。使用 Argon2id 加服务端 pepper 计算哈希。除演示通知投影外，不得返回原始取件码。签收凭证记录 `delivery_method`、脱敏签收人姓名、核验方式、操作人、网点和时间戳。

修改任务 6 的 `arrive_destination`：`STATION_PICKUP` 分支必须在同一事务中创建自取凭证和 `WAITING_FOR_RECIPIENT_PICKUP` 轨迹事件。六位原始取件码只向演示通知投影返回一次，绝不持久化。

- [ ] **步骤 5：验证并提交**

运行：`cd backend; uv run pytest tests/shipments/test_last_mile.py -q`

```bash
git add backend/src/yitu/shipments backend/src/yitu/dispatch backend/tests/shipments/test_last_mile.py backend/migrations
git commit -m "feat: complete delivery and station pickup"
```

## 任务 8：四种服务组合的 API 旅程测试

**文件：**
- 新建：`backend/tests/journeys/test_service_combinations.py`
- 新建：`backend/tests/journeys/test_authorization_matrix.py`
- 新建：`backend/tests/journeys/test_tracking_timeline.py`
- 修改：`backend/tests/conftest.py`

**接口：**
- 使用：任务 2 至任务 7 的全部 API。
- 产出：可复用的 `JourneyClient` 测试助手，只调用 HTTP 接口，不直接调用服务或 ORM 模型。

- [ ] **步骤 1：添加四路径旅程矩阵**

```python
@pytest.mark.parametrize(
    ("pickup_method", "delivery_method", "has_pickup_task", "has_delivery_task"),
    [
        ("DOOR_PICKUP", "HOME_DELIVERY", True, True),
        ("STATION_DROPOFF", "HOME_DELIVERY", False, True),
        ("DOOR_PICKUP", "STATION_PICKUP", True, False),
        ("STATION_DROPOFF", "STATION_PICKUP", False, False),
    ],
)
async def test_complete_service_combination(
    journey, pickup_method, delivery_method, has_pickup_task, has_delivery_task
):
    result = await journey.complete(
        pickup_method=pickup_method, delivery_method=delivery_method
    )
    assert result.shipment_status == "DELIVERED"
    assert result.has_pickup_task is has_pickup_task
    assert result.has_delivery_task is has_delivery_task
```

- [ ] **步骤 2：添加角色与网点权限矩阵**

针对每个改变状态的路由，测试未认证、角色错误、网点错误、任务负责人错误、状态非法、幂等键重复，以及通过授权的成功操作。

- [ ] **步骤 3：添加轨迹顺序断言**

断言客户可见事件按 `(occurred_at, sequence)` 排序，不包含内部操作人 ID，并且即使请求重放，每个成功业务动作也只产生一条事件。

- [ ] **步骤 4：运行完整后端测试套件**

运行：`cd backend; uv run ruff check .; uv run mypy src; uv run pytest -q`

预期：所有后端测试在 PostgreSQL 16 上通过。

- [ ] **步骤 5：提交**

```bash
git add backend/tests
git commit -m "test: cover logistics service journeys"
```

## 任务 9：Vue 角色外壳与核心流程页面

**文件：**
- 新建：`frontend/src/api/client.ts`
- 新建：`frontend/src/api/generated.ts`
- 新建：`frontend/src/router/index.ts`
- 新建：`frontend/src/stores/auth.ts`
- 新建：`frontend/src/layouts/AppLayout.vue`
- 新建：`frontend/src/components/RoleSwitcher.vue`
- 新建：`frontend/src/components/TrackingTimeline.vue`
- 新建：`frontend/src/components/ShipmentActions.vue`
- 新建：`frontend/src/views/LoginView.vue`
- 新建：`frontend/src/views/CustomerShipmentsView.vue`
- 新建：`frontend/src/views/ShipmentCreateView.vue`
- 新建：`frontend/src/views/ShipmentDetailView.vue`
- 新建：`frontend/src/views/CourierTasksView.vue`
- 新建：`frontend/src/views/StationOperationsView.vue`
- 新建：`frontend/src/views/OperationsDemoView.vue`
- 新建：`frontend/tests/core-journey.spec.ts`
- 修改：`frontend/src/App.vue`

**接口：**
- 使用：由 OpenAPI 生成的 DTO 和全部核心 API。
- 产出：由认证用户响应驱动的角色感知路由。

- [ ] **步骤 1：编写失败的浏览器旅程测试**

```ts
test('customer can follow a shipment through all demo roles', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: '客户' }).click()
  await page.getByRole('link', { name: '创建运单' }).click()
  await page.getByLabel('寄件方式').selectOption('DOOR_PICKUP')
  await page.getByLabel('收件方式').selectOption('HOME_DELIVERY')
  await page.getByRole('button', { name: '提交并模拟支付' }).click()
  await expect(page.getByText('等待揽收')).toBeVisible()
})
```

- [ ] **步骤 2：运行浏览器旅程并确认失败**

运行：`cd frontend; npm run test:e2e -- core-journey.spec.ts`

预期：测试失败，因为登录、运单创建和角色工作台尚不存在。

- [ ] **步骤 3：生成 API 类型并实现认证路由**

通过 FastAPI 的 OpenAPI JSON 运行 `npm run api:generate`。演示环境中的认证 Store 将访问令牌保存在会话存储中，页面刷新时调用 `/api/auth/me`，收到 `401` 时清空状态。路由元数据只控制导航展示，最终权限仍以后端校验为准。

- [ ] **步骤 4：实现角色工作台**

客户页面提供结构化地址、服务方式控件、运单列表/详情和轨迹时间线。快递员页面显示待接与已接任务，并使用尺寸稳定的操作按钮。网点页面提供运单号输入框来模拟扫码。运营页面提供干线到站操作。禁止提供通用状态选择器。

- [ ] **步骤 5：实现固定布局的操作和时间线组件**

`ShipmentActions` 只渲染 API 返回的 `allowed_actions`。`TrackingTimeline` 使用尺寸稳定的行展示时间戳、网点和公开描述；动态内容不能造成不可预测的布局跳动。

- [ ] **步骤 6：验证前端行为**

运行：`cd frontend; npm run typecheck; npm run test; npm run build`

在 Compose 环境中分别以桌面和移动端宽度运行 Playwright 旅程。截取登录、客户轨迹、快递员任务和网点操作页面。确认不存在文字截断、控件重叠或越权操作按钮。

- [ ] **步骤 7：提交**

```bash
git add frontend
git commit -m "feat: add role-based logistics workflow UI"
```

## 任务 10：确定性演示数据、重置与交付文档

**文件：**
- 修改：`backend/src/yitu/clock.py`
- 新建：`backend/src/yitu/demo/seed.py`
- 新建：`backend/src/yitu/demo/router.py`
- 新建：`backend/tests/journeys/test_demo_reset.py`
- 修改：`backend/src/yitu/main.py`
- 修改：`compose.yaml`
- 修改：`.env.example`
- 修改：`README.md`

**接口：**
- 产出：七个固定演示身份键。
- 产出：`POST /api/demo/reset`，仅在 `APP_PROFILE=demo` 时启用，并且只有 `SYSTEM_ADMIN` 可以调用。
- 使用并扩展：任务 1 的 `Clock.now() -> datetime`，在演示配置中支持受控推进。

- [ ] **步骤 1：编写重置范围与可重复性测试**

```python
async def test_demo_reset_is_repeatable_and_scoped(api, database):
    first = await api.reset_demo_as_system_admin()
    await api.complete_default_journey()
    second = await api.reset_demo_as_system_admin()

    assert first["scenario_version"] == second["scenario_version"]
    assert await database.non_demo_row_count() == 1
    assert await database.default_demo_shipment_count() == 0
```

同时验证非演示配置下重置接口返回 `404`，所有非系统管理员角色调用时返回 `403`。

- [ ] **步骤 2：运行重置测试并确认失败**

运行：`cd backend; uv run pytest tests/journeys/test_demo_reset.py -q`

预期：测试失败，因为演示重置、带范围的种子数据和可受控推进的演示时钟尚不存在。

- [ ] **步骤 3：实现确定性种子数据**

预置七个身份、北京/上海/广州/深圳共八个网点、区县映射和一个客户地址簿。每条生成数据都必须带演示范围标记，重置时禁止清空整张表。

- [ ] **步骤 4：编写一键启动与面试演示脚本文档**

README 必须包含前置条件、环境变量、`docker compose up --build`、迁移/种子命令、访问地址、演示身份、重置说明和完整的北京到上海演示步骤，并包含端口占用和 PostgreSQL 健康检查失败的排障方法。

- [ ] **步骤 5：执行最终验证**

运行：`docker compose up --build`

运行：`cd backend; uv run ruff check .; uv run mypy src; uv run pytest -q`

运行：`cd frontend; npm run typecheck; npm run test; npm run build; npm run test:e2e`

预期：全部检查通过，Compose 健康检查正常，四种服务旅程均通过，并且文档中的重置流程连续执行两次得到一致结果。

- [ ] **步骤 6：提交**

```bash
git add backend/src/yitu/demo backend/tests/journeys/test_demo_reset.py backend/src/yitu/main.py compose.yaml .env.example README.md
git commit -m "feat: add repeatable logistics demo scenario"
```

---

## 后续计划

本计划完成并验收后，按以下顺序分别创建实施计划：

1. 计价、报价快照、模拟补款、取消退款、SLA 规则、ETA、Outbox 和通知。
2. 异常工单、任务转派、重新派送、拦截退回、死信恢复和运营看板。
3. MinerU 摄取、PDF 审核发布、中文混合检索、pgvector 索引和引用预览。
4. LangGraph Agent、对话下单、`AgentActionGrant`、云模型隐私控制、记忆、评测与可观测性。
