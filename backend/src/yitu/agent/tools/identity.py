"""当前身份和最小化地址簿工具。"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from yitu.addresses.service import list_addresses
from yitu.agent.tools.base import ToolContext, ToolResult


class CurrentIdentity(BaseModel):
    """只包含 JWT 已验证的身份范围。"""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    role: str
    station_id: UUID | None


class AddressSummary(BaseModel):
    """供草稿选择地址使用的最小字段，不发送电话和详细门牌。"""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    label: str | None
    district_code: str


class AddressBookResult(BaseModel):
    """当前客户的最小化地址选项。"""

    model_config = ConfigDict(extra="forbid")

    items: list[AddressSummary]


class IdentityTool:
    """从 JWT 上下文返回身份，不接受模型提供 user_id。"""

    async def execute(self, context: ToolContext) -> ToolResult[CurrentIdentity]:
        actor = context.actor
        return ToolResult(
            tool="current_identity",
            found=True,
            data=CurrentIdentity(
                user_id=actor.id,
                role=actor.role.value,
                station_id=actor.station_id,
            ),
            message="已加载当前登录身份。",
        )


class AddressBookTool:
    """通过地址应用服务读取当前客户地址，输出经过最小化的字段。"""

    async def execute(self, context: ToolContext) -> ToolResult[AddressBookResult]:
        addresses = await list_addresses(context.session, context.actor)
        items = [
            AddressSummary(
                id=address.id,
                label=address.label,
                district_code=address.district_code,
            )
            for address in addresses
        ]
        return ToolResult(
            tool="address_book",
            found=bool(items),
            data=AddressBookResult(items=items),
            message="已读取当前客户的地址选项。" if items else "当前客户没有地址。",
        )
