"""Agent 运单草稿的持久化、校验和报价前置服务。"""

from datetime import datetime
from typing import cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.service import address_response, get_owned_address
from yitu.agent.models import AgentShipmentDraft
from yitu.identity.service import CurrentUser
from yitu.platform.clock import Clock
from yitu.platform.errors import AppError
from yitu.pricing.schemas import QuoteRequest, QuoteView
from yitu.pricing.service import PricingService
from yitu.shipments.enums import DeliveryMethod, PickupMethod
from yitu.shipments.schemas import CreateShipmentCommand, ShipmentDraft


class DraftPatch(BaseModel):
    """模型或表单提交的结构化字段变更，禁止额外字段。"""

    model_config = ConfigDict(extra="forbid")

    sender_address_id: UUID | None = None
    receiver_address_id: UUID | None = None
    origin_station_id: UUID | None = None
    destination_station_id: UUID | None = None
    pickup_method: PickupMethod | None = None
    delivery_method: DeliveryMethod | None = None
    origin_district_code: str | None = Field(default=None, min_length=6, max_length=6)
    destination_district_code: str | None = Field(default=None, min_length=6, max_length=6)
    actual_weight_grams: int | None = Field(default=None, gt=0)
    length_cm: int | None = Field(default=None, gt=0)
    width_cm: int | None = Field(default=None, gt=0)
    height_cm: int | None = Field(default=None, gt=0)
    estimated_weight_grams: int | None = Field(default=None, gt=0)
    estimated_length_cm: int | None = Field(default=None, gt=0)
    estimated_width_cm: int | None = Field(default=None, gt=0)
    estimated_height_cm: int | None = Field(default=None, gt=0)
    package_category: str | None = Field(default=None, max_length=64)
    package_description: str | None = Field(default=None, max_length=2000)
    special_instructions: str | None = Field(default=None, max_length=2000)


class DraftView(BaseModel):
    """草稿公开视图，供确认卡片和表单继续编辑。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    conversation_id: UUID
    payload: dict[str, object]
    revision: int
    status: str
    missing_fields: list[str]
    quote_id: UUID | None
    quote_version: str | None
    updated_at: datetime
    summary: list[dict[str, str]] = Field(default_factory=list)


class DraftValidationView(BaseModel):
    """草稿校验后的共享创建命令和确定性报价。"""

    command: CreateShipmentCommand
    quote: QuoteView
    draft: DraftView


class DraftService:
    """维护当前用户会话草稿，所有业务校验集中在后端。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(
        self, conversation_id: UUID, actor: CurrentUser
    ) -> AgentShipmentDraft:
        draft = await self._session.scalar(
            select(AgentShipmentDraft).where(
                AgentShipmentDraft.conversation_id == conversation_id,
                AgentShipmentDraft.owner_id == actor.id,
            )
        )
        if draft is not None:
            return draft
        draft = AgentShipmentDraft(
            conversation_id=conversation_id,
            owner_id=actor.id,
            payload={},
            revision=0,
            status="INCOMPLETE",
            missing_fields=[],
            updated_at=Clock.now(),
        )
        self._session.add(draft)
        await self._session.flush()
        return draft

    async def update(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
        patch: DraftPatch,
    ) -> DraftView:
        draft = await self.get_or_create(conversation_id, actor)
        payload = dict(draft.payload)
        payload.update(patch.model_dump(mode="json", exclude_none=True))
        # 平台当前只开放门到门寄件，模型未提供方式时直接使用唯一可用组合。
        payload.setdefault("pickup_method", PickupMethod.DOOR_PICKUP.value)
        payload.setdefault("delivery_method", DeliveryMethod.HOME_DELIVERY.value)
        missing = self.missing_fields(payload)
        draft.payload = payload
        draft.missing_fields = missing
        draft.status = "READY_FOR_QUOTE" if not missing else "INCOMPLETE"
        draft.revision += 1
        draft.quote_id = None
        draft.quote_version = None
        draft.updated_at = Clock.now()
        await self._session.flush()
        return DraftView.model_validate(draft)

    async def validate(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
    ) -> CreateShipmentCommand:
        draft = await self.get_or_create(conversation_id, actor)
        payload = dict(draft.payload)
        # 兼容功能调整前创建但尚未填写寄送方式的会话草稿。
        payload.setdefault("pickup_method", PickupMethod.DOOR_PICKUP.value)
        payload.setdefault("delivery_method", DeliveryMethod.HOME_DELIVERY.value)
        pickup = payload.get("pickup_method")
        delivery = payload.get("delivery_method")
        if pickup == PickupMethod.STATION_DROPOFF.value:
            raise AppError(
                "STATION_DROPOFF_DISABLED",
                "暂不支持网点寄件，请使用上门取件",
                422,
            )
        if delivery == DeliveryMethod.STATION_PICKUP.value:
            raise AppError(
                "STATION_PICKUP_DISABLED",
                "暂不支持网点自提，请使用送货上门",
                422,
            )
        missing = self.missing_fields(payload)
        if missing:
            raise AppError(
                "SHIPMENT_DRAFT_INCOMPLETE",
                "运单草稿仍缺少必要字段",
                409,
                details={"missing_fields": missing},
            )
        draft.payload = payload
        sender_id = _uuid_value(payload, "sender_address_id")
        receiver_id = _uuid_value(payload, "receiver_address_id")
        if sender_id is not None:
            await get_owned_address(self._session, sender_id, actor)
        if receiver_id is not None:
            await get_owned_address(self._session, receiver_id, actor)
        try:
            shipment_draft = ShipmentDraft.model_validate(
                {
                    key: payload[key]
                    for key in (
                        "sender_address_id",
                        "receiver_address_id",
                        "origin_station_id",
                        "destination_station_id",
                        "pickup_method",
                        "delivery_method",
                        "quote_id",
                        "package_category",
                        "package_description",
                        "estimated_weight_grams",
                        "estimated_length_cm",
                        "estimated_width_cm",
                        "estimated_height_cm",
                        "special_instructions",
                    )
                    if key in payload
                }
            )
        except ValueError as error:
            raise AppError("SHIPMENT_DRAFT_INVALID", "运单草稿校验失败", 422) from error
        return CreateShipmentCommand(draft=shipment_draft)

    async def validate_and_quote(
        self,
        conversation_id: UUID,
        actor: CurrentUser,
    ) -> DraftValidationView:
        """校验草稿并调用正式计价服务，绑定报价版本供后续授权。"""
        command = await self.validate(conversation_id, actor)
        draft = await self.get_or_create(conversation_id, actor)
        request = QuoteRequest.model_validate(
            {
                "origin_district_code": draft.payload["origin_district_code"],
                "destination_district_code": draft.payload["destination_district_code"],
                "pickup_method": draft.payload["pickup_method"],
                "delivery_method": draft.payload["delivery_method"],
                "actual_weight_grams": draft.payload["estimated_weight_grams"],
                "length_cm": draft.payload["estimated_length_cm"],
                "width_cm": draft.payload["estimated_width_cm"],
                "height_cm": draft.payload["estimated_height_cm"],
            }
        )
        quote = await PricingService(self._session).quote(
            request,
            actor,
            idempotency_key=(
                f"agent-draft:{draft.id}:revision:{draft.revision}:quote"
            ),
        )
        # JSONB 原地修改不被 SQLAlchemy 追踪，必须整体替换 payload 才能持久化 quote_id。
        draft.payload = {**draft.payload, "quote_id": str(quote.id)}
        draft.quote_id = quote.id
        draft.quote_version = quote.rule_version
        draft.status = "READY_FOR_CONFIRMATION"
        draft.updated_at = Clock.now()
        await self._session.flush()
        return DraftValidationView(
            command=command,
            quote=quote,
            draft=await self.view(draft, actor),
        )

    @staticmethod
    def missing_fields(payload: dict[str, object]) -> list[str]:
        """根据寄收方式和报价必填项计算稳定的缺失字段列表。"""
        missing: list[str] = []
        pickup = payload.get("pickup_method")
        delivery = payload.get("delivery_method")
        if pickup is None:
            missing.append("pickup_method")
        elif pickup == PickupMethod.DOOR_PICKUP.value and not payload.get("sender_address_id"):
            missing.append("sender_address_id")
        elif pickup == PickupMethod.STATION_DROPOFF.value and not payload.get("origin_station_id"):
            missing.append("origin_station_id")
        if delivery is None:
            missing.append("delivery_method")
        elif delivery == DeliveryMethod.HOME_DELIVERY.value and not payload.get("receiver_address_id"):
            missing.append("receiver_address_id")
        elif delivery == DeliveryMethod.STATION_PICKUP.value and not payload.get("destination_station_id"):
            missing.append("destination_station_id")
        for field in (
            "origin_district_code",
            "destination_district_code",
            "estimated_weight_grams",
            "estimated_length_cm",
            "estimated_width_cm",
            "estimated_height_cm",
        ):
            if not payload.get(field):
                missing.append(field)
        for field in ("package_category", "package_description"):
            if not payload.get(field):
                missing.append(field)
        return missing

    async def describe(
        self, draft: AgentShipmentDraft, actor: CurrentUser
    ) -> list[dict[str, str]]:
        """生成草稿已填字段的中文展示条目，供确认卡片与草稿 loop 提示复用。"""
        payload = draft.payload
        items: list[dict[str, str]] = []
        for key, label in (
            ("sender_address_id", "寄件地址"),
            ("receiver_address_id", "收件地址"),
        ):
            value = payload.get(key)
            if value:
                text = await self._address_text(value, actor)
                if text:
                    items.append({"label": label, "value": text})
        weight = payload.get("estimated_weight_grams")
        if weight:
            items.append({"label": "预估重量", "value": f"{cast(int, weight)} 克"})
        dims = [
            payload.get(k)
            for k in ("estimated_length_cm", "estimated_width_cm", "estimated_height_cm")
        ]
        if all(v is not None for v in dims):
            items.append(
                {
                    "label": "尺寸",
                    "value": " × ".join(f"{cast(int, v)}" for v in dims) + " 厘米",
                }
            )
        if payload.get("package_category"):
            items.append({"label": "物品类型", "value": str(payload["package_category"])})
        if payload.get("package_description"):
            items.append({"label": "物品内容", "value": str(payload["package_description"])})
        if payload.get("special_instructions"):
            items.append({"label": "特殊备注", "value": str(payload["special_instructions"])})
        return items

    async def view(self, draft: AgentShipmentDraft, actor: CurrentUser) -> DraftView:
        """构建含中文展示摘要的草稿视图。"""
        view = DraftView.model_validate(draft)
        view.summary = await self.describe(draft, actor)
        return view

    async def _address_text(self, value: object, actor: CurrentUser) -> str | None:
        try:
            address = await get_owned_address(self._session, UUID(str(value)), actor)
        except (ValueError, TypeError, AppError):
            return None
        resp = address_response(address)
        return f"{resp['recipient_name']!s} {resp['phone']!s} {resp['full_address']!s}"


def _uuid_value(payload: dict[str, object], key: str) -> UUID | None:
    value = payload.get(key)
    return UUID(value) if isinstance(value, str) else value if isinstance(value, UUID) else None
