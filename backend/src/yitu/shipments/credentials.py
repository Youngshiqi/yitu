import secrets
from datetime import timedelta
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.dispatch.models import CourierTask, CourierTaskStatus, CourierTaskType
from yitu.identity.models import Role
from yitu.identity.service import CurrentUser, require_station_scope
from yitu.platform.clock import Clock
from yitu.platform.config import get_settings
from yitu.platform.errors import AppError
from yitu.shipments.control import ShipmentControlService
from yitu.shipments.credential_models import PickupCredential, ProofOfDelivery
from yitu.shipments.enums import DeliveryMethod, ShipmentStatus
from yitu.shipments.models import Shipment
from yitu.shipments.service import ShipmentTransitionService

_hasher = PasswordHasher()


class LastMileService:
    """处理派送签收、网点自取凭证和签收证明。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start_delivery(self, shipment_id: UUID, actor: CurrentUser, request_id: str) -> Shipment:
        task = await self._delivery_task(shipment_id)
        if actor.role is not Role.COURIER or task.assignee_id != actor.id:
            raise AppError("FORBIDDEN_TASK_OWNER", "仅派送任务负责人可开始派送", 403)
        if CourierTaskStatus(task.status) is not CourierTaskStatus.ACCEPTED:
            raise AppError("TASK_NOT_ACCEPTED", "派送任务尚未接单", 409)
        shipment = await ShipmentControlService(self._session).lock_and_assert_fulfillment_allowed(shipment_id)
        await ShipmentTransitionService(self._session).transition(shipment, ShipmentStatus.OUT_FOR_DELIVERY, actor, "start_delivery", request_id)
        return shipment

    async def confirm_delivery(self, shipment_id: UUID, actor: CurrentUser, signer_name: str, request_id: str) -> ProofOfDelivery:
        existing = await self._session.scalar(select(ProofOfDelivery).where(ProofOfDelivery.shipment_id == shipment_id))
        if existing is not None:
            return existing
        task = await self._delivery_task(shipment_id)
        if actor.role is not Role.COURIER or task.assignee_id != actor.id:
            raise AppError("FORBIDDEN_TASK_OWNER", "仅派送任务负责人可完成签收", 403)
        shipment = await ShipmentControlService(self._session).lock_and_assert_fulfillment_allowed(shipment_id)
        await ShipmentTransitionService(self._session).transition(shipment, ShipmentStatus.DELIVERED, actor, "confirm_delivery", request_id)
        proof = ProofOfDelivery(shipment_id=shipment_id, delivery_method=DeliveryMethod.HOME_DELIVERY, signer_name=_mask_name(signer_name), verification_method="COURIER_CONFIRMATION", actor_id=actor.id, station_id=task.station_id, idempotency_key=request_id, created_at=Clock().now())
        self._session.add(proof)
        await self._session.flush()
        task.status = CourierTaskStatus.COMPLETED
        return proof

    async def issue_pickup_credential(self, shipment_id: UUID, actor: CurrentUser, request_id: str, *, code: str | None = None, expires_in: timedelta = timedelta(minutes=30)) -> PickupCredential:
        shipment = await self._require_station_pickup(shipment_id, actor)
        await ShipmentControlService(self._session).lock_and_assert_fulfillment_allowed(shipment.id)
        existing = await self._session.scalar(select(PickupCredential).where(PickupCredential.shipment_id == shipment_id, PickupCredential.consumed_at.is_(None)).order_by(PickupCredential.created_at.desc()))
        if existing is not None:
            existing.expires_at = Clock().now()
        if ShipmentStatus(shipment.status) is ShipmentStatus.AT_DESTINATION_STATION:
            await ShipmentTransitionService(self._session).transition(shipment, ShipmentStatus.WAITING_FOR_RECIPIENT_PICKUP, actor, "issue_pickup_credential", request_id)
        settings = get_settings()
        raw_code = code or (
            settings.demo_pickup_code
            if settings.app_profile == "demo"
            else f"{secrets.randbelow(1_000_000):06d}"
        )
        credential = PickupCredential(shipment_id=shipment_id, station_id=actor.station_id, code_hash=_hasher.hash(raw_code + get_settings().pickup_code_pepper), expires_at=Clock().now() + expires_in, failed_attempts=0, created_at=Clock().now())
        self._session.add(credential)
        await self._session.flush()
        return credential

    async def reissue_pickup_credential(self, shipment_id: UUID, actor: CurrentUser, request_id: str, *, code: str | None = None) -> PickupCredential:
        return await self.issue_pickup_credential(shipment_id, actor, request_id, code=code)

    async def verify_station_pickup(self, shipment_id: UUID, actor: CurrentUser, code: str, request_id: str) -> ProofOfDelivery:
        existing_proof = await self._session.scalar(select(ProofOfDelivery).where(ProofOfDelivery.shipment_id == shipment_id))
        if existing_proof is not None:
            return existing_proof
        shipment = await self._require_station_pickup(shipment_id, actor)
        await ShipmentControlService(self._session).lock_and_assert_fulfillment_allowed(shipment.id)
        credential = await self._session.scalar(select(PickupCredential).where(PickupCredential.shipment_id == shipment_id, PickupCredential.consumed_at.is_(None)).order_by(PickupCredential.created_at.desc()))
        if credential is None:
            raise AppError("PICKUP_CREDENTIAL_NOT_FOUND", "取件凭证不存在", 409)
        now = Clock().now()
        if credential.locked_at is not None:
            raise AppError("PICKUP_CREDENTIAL_LOCKED", "取件凭证已锁定", 409)
        if credential.expires_at <= now:
            raise AppError("PICKUP_CREDENTIAL_EXPIRED", "取件凭证已过期", 409)
        if not _verify_code(code, credential.code_hash):
            credential.failed_attempts += 1
            if credential.failed_attempts >= 5:
                credential.locked_at = now
            await self._session.flush()
            raise AppError("INVALID_PICKUP_CREDENTIAL", "取件凭证错误", 409)
        credential.consumed_at = now
        await ShipmentTransitionService(self._session).transition(shipment, ShipmentStatus.DELIVERED, actor, "verify_station_pickup", request_id)
        proof = ProofOfDelivery(shipment_id=shipment_id, delivery_method=DeliveryMethod.STATION_PICKUP, signer_name="网点自取", verification_method="PICKUP_CODE", actor_id=actor.id, station_id=actor.station_id, idempotency_key=request_id, created_at=now)
        self._session.add(proof)
        await self._session.flush()
        return proof

    async def _require_station_pickup(self, shipment_id: UUID, actor: CurrentUser) -> Shipment:
        if actor.role is not Role.STATION_OPERATOR:
            raise AppError("FORBIDDEN_ROLE", "角色权限不足", 403)
        shipment = await self._shipment(shipment_id)
        if DeliveryMethod(shipment.delivery_method) is not DeliveryMethod.STATION_PICKUP:
            raise AppError("PICKUP_NOT_REQUIRED", "该运单不是网点自取", 409)
        if shipment.destination_station_id is None:
            raise AppError("DESTINATION_STATION_REQUIRED", "运单缺少目标网点", 409)
        require_station_scope(shipment.destination_station_id, actor)
        return shipment

    async def _delivery_task(self, shipment_id: UUID) -> CourierTask:
        task = await self._session.scalar(select(CourierTask).where(CourierTask.shipment_id == shipment_id, CourierTask.task_type == CourierTaskType.DELIVERY))
        if task is None:
            raise AppError("DELIVERY_TASK_NOT_FOUND", "派送任务不存在", 409)
        return task

    async def _shipment(self, shipment_id: UUID) -> Shipment:
        shipment = await self._session.get(Shipment, shipment_id)
        if shipment is None:
            raise AppError("SHIPMENT_NOT_FOUND", "运单不存在", 404)
        return shipment


def _verify_code(code: str, code_hash: str) -> bool:
    try:
        return _hasher.verify(code_hash, code + get_settings().pickup_code_pepper)
    except (InvalidHash, VerificationError, VerifyMismatchError):
        return False


def _mask_name(name: str) -> str:
    if len(name) <= 1:
        return "*"
    return name[0] + "*" * (len(name) - 1)
