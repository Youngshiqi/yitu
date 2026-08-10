from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.addresses.models import Address
from yitu.addresses.schemas import AddressCreate, AddressResponse, AddressUpdate
from yitu.addresses.service import delete_address, get_owned_address, list_addresses
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, get_current_user, require_roles
from yitu.platform.database import get_session

router = APIRouter(prefix="/api/v1/addresses", tags=["addresses"])
_session = Depends(get_session)
_current_user = Depends(get_current_user)


def customer_user(
    current_user: CurrentUser = _current_user,
) -> CurrentUser:
    return require_roles(Role.CUSTOMER)(current_user)


_customer = Depends(customer_user)

@router.get("", response_model=list[AddressResponse])
async def list_book(user: CurrentUser = _customer, session: AsyncSession = _session) -> list[Address]:
    return await list_addresses(session, user)

@router.post("", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
async def create_address(payload: AddressCreate, user: CurrentUser = _customer, session: AsyncSession = _session) -> Address:
    address = Address(owner_id=user.id, **payload.model_dump())
    session.add(address)
    await session.commit()
    await session.refresh(address)
    return address

@router.patch("/{address_id}", response_model=AddressResponse)
async def update_address(address_id: UUID, payload: AddressUpdate, user: CurrentUser = _customer, session: AsyncSession = _session) -> Address:
    address = await get_owned_address(session, address_id, user)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(address, key, value)
    await session.commit()
    await session.refresh(address)
    return address

@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_address(address_id: UUID, user: CurrentUser = _customer, session: AsyncSession = _session) -> Response:
    address = await get_owned_address(session, address_id, user)
    await delete_address(session, address)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
