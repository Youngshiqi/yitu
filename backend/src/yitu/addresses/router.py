from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.models import Address
from yitu.addresses.schemas import AddressCreate, AddressResponse, AddressUpdate
from yitu.addresses.service import (
    address_response,
    assign_region_path,
    delete_address,
    find_matching_address,
    get_owned_address,
    list_addresses,
)
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, get_current_user, require_roles
from yitu.platform.database import get_session
from yitu.platform.errors import AppError

router = APIRouter(prefix="/api/v1/addresses", tags=["addresses"])
_session = Depends(get_session)
_current_user = Depends(get_current_user)


def customer_user(
    current_user: CurrentUser = _current_user,
) -> CurrentUser:
    return require_roles(Role.CUSTOMER)(current_user)


_customer = Depends(customer_user)

@router.get("", response_model=list[AddressResponse])
async def list_book(user: CurrentUser = _customer, session: AsyncSession = _session) -> list[dict[str, object]]:
    return [address_response(item) for item in await list_addresses(session, user)]

@router.post("", response_model=AddressResponse)
async def create_address(payload: AddressCreate, user: CurrentUser = _customer, session: AsyncSession = _session) -> dict[str, object]:
    """创建地址；命中既有相同地址时复用并返回 200，避免地址簿重复。"""
    existing = await find_matching_address(
        session,
        user.id,
        payload.recipient_name,
        payload.phone,
        payload.district_region_id,
        payload.detail,
    )
    if existing is not None:
        if existing.ephemeral:
            # 一次性临时地址升级为正式条目并补标签
            existing.ephemeral = False
            existing.label = existing.label or payload.label
        elif existing.label is None and payload.label is not None:
            existing.label = payload.label
        await session.commit()
        return address_response(await get_owned_address(session, existing.id, user))
    values = payload.model_dump(exclude={"province_region_id", "city_region_id", "district_region_id"})
    address = Address(owner_id=user.id, district_code="", **values)
    await assign_region_path(
        session,
        address,
        payload.province_region_id,
        payload.city_region_id,
        payload.district_region_id,
    )
    session.add(address)
    await session.commit()
    return address_response(address)

@router.patch("/{address_id}", response_model=AddressResponse)
async def update_address(address_id: UUID, payload: AddressUpdate, user: CurrentUser = _customer, session: AsyncSession = _session) -> dict[str, object]:
    address = await get_owned_address(session, address_id, user)
    values = payload.model_dump(exclude_unset=True)
    region_keys = {"province_region_id", "city_region_id", "district_region_id"}
    if region_keys.intersection(values):
        province_region_id = values.get("province_region_id", address.province_region_id)
        city_region_id = values.get("city_region_id", address.city_region_id)
        district_region_id = values.get("district_region_id", address.district_region_id)
        if (
            province_region_id is None
            or city_region_id is None
            or district_region_id is None
        ):
            raise AppError("ADDRESS_REGION_REQUIRED", "地址必须包含完整省、市、区县", 422)
        await assign_region_path(
            session,
            address,
            province_region_id,
            city_region_id,
            district_region_id,
        )
    for key, value in values.items():
        if key in region_keys:
            continue
        setattr(address, key, value)
    await session.commit()
    return address_response(address)

@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_address(address_id: UUID, user: CurrentUser = _customer, session: AsyncSession = _session) -> Response:
    address = await get_owned_address(session, address_id, user)
    await delete_address(session, address)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
