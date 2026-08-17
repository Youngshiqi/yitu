"""草稿填写 agentic loop 的 update_draft 工具：白名单参数 + 确定性落库。"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.models import Address
from yitu.addresses.service import assign_region_path, find_matching_address
from yitu.agent.drafts import DraftPatch, DraftService, DraftView
from yitu.identity.service import CurrentUser
from yitu.regions.service import resolve_region_by_names


class UpdateDraftToolArgs(BaseModel):
    """模型可填写的草稿字段；地址只能用标签，禁止生成地址 ID。"""

    model_config = ConfigDict(extra="forbid")

    sender_address_label: str | None = Field(default=None, max_length=128)
    receiver_address_label: str | None = Field(default=None, max_length=128)
    estimated_weight_grams: int | None = Field(default=None, gt=0)
    estimated_length_cm: int | None = Field(default=None, gt=0)
    estimated_width_cm: int | None = Field(default=None, gt=0)
    estimated_height_cm: int | None = Field(default=None, gt=0)
    declared_value_cents: int | None = Field(default=None, ge=0)
    package_category: str | None = Field(default=None, max_length=64)
    package_description: str | None = Field(default=None, max_length=2000)
    special_instructions: str | None = Field(default=None, max_length=2000)


class SaveAddressToolArgs(BaseModel):
    """对话口述的地址簿外新地址；一次只填写寄件或收件其一。"""

    model_config = ConfigDict(extra="forbid")

    role: Literal["sender", "receiver"]
    recipient_name: str = Field(min_length=1, max_length=128)
    phone: str = Field(min_length=1, max_length=32)
    province_name: str = Field(min_length=1, max_length=64)
    city_name: str = Field(min_length=1, max_length=64)
    district_name: str = Field(min_length=1, max_length=64)
    detail: str = Field(min_length=1, max_length=256)


UPDATE_DRAFT_TOOL_SPECS: tuple[dict[str, object], ...] = (
    {
        "type": "function",
        "function": {
            "name": "update_draft",
            "description": (
                "更新寄件草稿的一个或多个字段。地址用地址簿标签，重量用克，"
                "尺寸用厘米，金额用分；未明确的字段不要填写。"
            ),
            "parameters": UpdateDraftToolArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_address",
            "description": (
                "用户口述了一个不在地址簿标签列表中的寄件或收件地址时，"
                "把收件人姓名、手机号、省市区名称和详细地址保存为本次寄件的"
                "临时地址并填入草稿。必须已问清全部字段，一次只保存一个地址。"
            ),
            "parameters": SaveAddressToolArgs.model_json_schema(),
        },
    },
)


async def execute_save_address(
    session: AsyncSession,
    actor: CurrentUser,
    conversation_id: UUID,
    arguments: dict[str, object],
) -> str:
    """解析口述地址并落库为临时地址，回填草稿寄件或收件侧字段。"""
    args = SaveAddressToolArgs.model_validate(arguments)
    province, city, district = await resolve_region_by_names(
        session, args.province_name, args.city_name, args.district_name
    )
    existing = await find_matching_address(
        session,
        actor.id,
        args.recipient_name,
        args.phone,
        district.id,
        args.detail,
    )
    if existing is not None:
        address = existing
    else:
        address = Address(
            owner_id=actor.id,
            label=None,
            recipient_name=args.recipient_name,
            phone=args.phone,
            detail=args.detail,
            ephemeral=True,
        )
        await assign_region_path(session, address, province.id, city.id, district.id)
        session.add(address)
        await session.flush()
    patch = DraftPatch(
        sender_address_id=address.id if args.role == "sender" else None,
        receiver_address_id=address.id if args.role == "receiver" else None,
        origin_district_code=(
            address.district_code if args.role == "sender" else None
        ),
        destination_district_code=(
            address.district_code if args.role == "receiver" else None
        ),
    )
    draft = await DraftService(session).update(conversation_id, actor, patch)
    role_label = "寄件" if args.role == "sender" else "收件"
    missing = "、".join(draft.missing_fields)
    if missing:
        return f"已填入{role_label}地址。仍缺失字段：{missing}。"
    return f"已填入{role_label}地址。草稿字段已齐全，可以生成报价。"


async def execute_update_draft(
    session: AsyncSession,
    actor: CurrentUser,
    addresses: list[Address],
    conversation_id: UUID,
    arguments: dict[str, object],
) -> str:
    """执行 update_draft：标签唯一匹配后落库，返回面向模型的结果文本。"""
    args = UpdateDraftToolArgs.model_validate(arguments)
    patch_data: dict[str, object] = args.model_dump(exclude_none=True)
    sender_label = patch_data.pop("sender_address_label", None)
    receiver_label = patch_data.pop("receiver_address_label", None)

    unresolved: list[str] = []
    if isinstance(sender_label, str) and sender_label:
        sender = _match_address_label(sender_label, addresses)
        if sender is None:
            unresolved.append(f"寄件地址「{sender_label}」")
        else:
            patch_data["sender_address_id"] = sender.id
            patch_data["origin_district_code"] = sender.district_code
    if isinstance(receiver_label, str) and receiver_label:
        receiver = _match_address_label(receiver_label, addresses)
        if receiver is None:
            unresolved.append(f"收件地址「{receiver_label}」")
        else:
            patch_data["receiver_address_id"] = receiver.id
            patch_data["destination_district_code"] = receiver.district_code

    if patch_data:
        draft = await DraftService(session).update(
            conversation_id, actor, DraftPatch.model_validate(patch_data)
        )
    else:
        draft = DraftView.model_validate(
            await DraftService(session).get_or_create(conversation_id, actor)
        )

    parts: list[str] = []
    if patch_data:
        parts.append("已更新草稿字段。")
    if draft.missing_fields:
        parts.append("仍缺失字段：" + "、".join(draft.missing_fields) + "。")
    else:
        parts.append("草稿字段已齐全，可以生成报价。")
    if unresolved:
        parts.append("未匹配地址：" + "、".join(unresolved) + "。")
    return "".join(parts)


def _match_address_label(label: str, addresses: list[Address]) -> Address | None:
    """只接受地址簿中唯一匹配的标签，避免歧义选错收寄地址。"""
    matches = [address for address in addresses if address.label == label]
    return matches[0] if len(matches) == 1 else None
