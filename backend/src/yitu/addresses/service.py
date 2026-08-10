from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.models import Address
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser
from yitu.platform.errors import AppError


async def get_owned_address(session: AsyncSession, address_id: UUID, user: CurrentUser) -> Address:
    address = await session.get(Address, address_id)
    if address is None:
        raise AppError("ADDRESS_NOT_FOUND", "地址不存在", 404)
    if user.role is Role.CUSTOMER and address.owner_id != user.id:
        raise AppError("FORBIDDEN_RESOURCE_OWNER", "只能访问本人资源", 403)
    return address

async def list_addresses(session: AsyncSession, user: CurrentUser) -> list[Address]:
    result = await session.scalars(select(Address).where(Address.owner_id == user.id))
    return list(result)

async def delete_address(session: AsyncSession, address: Address) -> None:
    await session.execute(delete(Address).where(Address.id == address.id))
